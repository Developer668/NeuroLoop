"""Real advertiser OAuth connections and exact creative-asset handoff.

This module deliberately stops at uploading an existing NeuroLoop image/video to
an authorized provider asset library. It does not pretend to create equivalent
campaigns, targeting, budgets, or live delivery across providers.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from .config import Settings
from .db import AdConnection, AdOAuthAttempt, AdPublication, Asset, record
from .domain import AdAssetSyncRequest, digest, now
from .engine import DomainError, required

PROVIDERS = ("meta", "google", "tiktok")


class AdProviderFailure(RuntimeError):
    def __init__(self, code: str, detail: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(detail)


class TokenVault:
    def __init__(self, settings: Settings):
        key = settings.signing_key.get_secret_value()
        if not key:
            raise RuntimeError("NEUROLOOP_SIGNING_KEY is required for encrypted ad-account credentials")
        derived = base64.urlsafe_b64encode(hashlib.sha256((key + ":ad-oauth-v1").encode()).digest())
        self.fernet = Fernet(derived)

    def seal(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def open(self, value: str | None) -> str:
        if not value:
            return ""
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise AdProviderFailure(
                "CREDENTIAL_DECRYPTION_FAILED",
                "Stored provider authorization cannot be decrypted; reconnect the account.",
            ) from exc


class AdPublishService:
    def __init__(self, store, objects, client: httpx.Client | None = None):
        self.store = store
        self.objects = objects
        self.settings = store.settings
        self.client = client or httpx.Client(timeout=httpx.Timeout(120, connect=30), follow_redirects=False)

    def _vault(self) -> TokenVault:
        return TokenVault(self.settings)

    def _secret(self, name: str) -> str:
        return getattr(self.settings, name).get_secret_value()

    def _redirect_uri(self, provider: str) -> str:
        field = f"{provider if provider != 'google' else 'google_ads'}_oauth_redirect_uri"
        configured = getattr(self.settings, field)
        if configured:
            return configured
        return self.settings.frontend_origin.rstrip("/") + f"/api/publish/oauth/{provider}/callback"

    def _configured(self, provider: str) -> bool:
        if provider == "meta":
            return bool(
                self._secret("meta_app_id")
                and self._secret("meta_app_secret")
                and re.fullmatch(r"v[0-9]+\.[0-9]+", self.settings.meta_graph_version)
            )
        if provider == "google":
            return bool(
                self._secret("google_ads_client_id")
                and self._secret("google_ads_client_secret")
                and self._secret("google_ads_developer_token")
            )
        if provider == "tiktok":
            return bool(self._secret("tiktok_app_id") and self._secret("tiktok_app_secret"))
        return False

    @staticmethod
    def dashboard_url(provider: str) -> str:
        return {
            "meta": "https://adsmanager.facebook.com/adsmanager/manage/campaigns",
            "google": "https://ads.google.com/aw/overview",
            "tiktok": "https://ads.tiktok.com/i18n/perf/creative",
        }[provider]

    def _connection(self, provider: str, *, include_inactive: bool = False) -> AdConnection | None:
        with self.store.read() as session:
            row = session.scalar(select(AdConnection).where(AdConnection.provider == provider))
            if row and (row.active or include_inactive):
                session.expunge(row)
                return row
        return None

    @staticmethod
    def _connection_public(row: AdConnection | None) -> dict | None:
        if not row or not row.active:
            return None
        return {
            "id": row.id,
            "provider": row.provider,
            "external_user_id": row.external_user_id,
            "display_name": row.display_name,
            "scopes": row.scopes,
            "token_expires_at": row.token_expires_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def statuses(self) -> list[dict]:
        rows = {provider: self._connection(provider) for provider in PROVIDERS}
        details = {
            "meta": "Requires a Meta developer app with Marketing API access.",
            "google": "Requires Google OAuth credentials and a Google Ads developer token.",
            "tiktok": "Requires a TikTok for Business developer app.",
        }
        return [
            {
                "provider": provider,
                "configured": self._configured(provider),
                "connected": bool(rows[provider]),
                "connection": self._connection_public(rows[provider]),
                "dashboard_url": self.dashboard_url(provider),
                "supports": ["image", "video"],
                "upload_ready": bool(rows[provider]) and self._configured(provider),
                "detail": details[provider],
            }
            for provider in PROVIDERS
        ]

    def begin_oauth(self, provider: str) -> dict:
        if provider not in PROVIDERS:
            raise DomainError("Unknown advertising provider", 404)
        if not self._configured(provider):
            raise DomainError(f"{provider.title()} integration is not configured on the server", 503)
        state = secrets.token_urlsafe(40)
        with self.store.transaction() as session:
            session.add(
                AdOAuthAttempt(
                    provider=provider,
                    state_hash=hashlib.sha256(state.encode()).hexdigest(),
                    expires_at=now() + 600,
                )
            )
        redirect = self._redirect_uri(provider)
        if provider == "meta":
            query = urlencode(
                {
                    "client_id": self._secret("meta_app_id"),
                    "redirect_uri": redirect,
                    "state": state,
                    "scope": "ads_management,ads_read,business_management,pages_show_list",
                    "response_type": "code",
                }
            )
            url = f"https://www.facebook.com/{self.settings.meta_graph_version}/dialog/oauth?{query}"
        elif provider == "google":
            query = urlencode(
                {
                    "client_id": self._secret("google_ads_client_id"),
                    "redirect_uri": redirect,
                    "state": state,
                    "response_type": "code",
                    "access_type": "offline",
                    "prompt": "consent",
                    "scope": "openid email profile https://www.googleapis.com/auth/adwords",
                }
            )
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + query
        else:
            query = urlencode(
                {
                    "app_id": self._secret("tiktok_app_id"),
                    "state": state,
                    "redirect_uri": redirect,
                }
            )
            url = "https://ads.tiktok.com/marketing_api/auth?" + query
        return {"provider": provider, "authorization_url": url}

    def _consume_state(self, provider: str, state: str) -> None:
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        with self.store.transaction() as session:
            row = session.scalar(select(AdOAuthAttempt).where(AdOAuthAttempt.state_hash == state_hash))
            if not row or row.provider != provider or row.used or row.expires_at < now():
                raise AdProviderFailure(
                    "INVALID_OAUTH_STATE",
                    "The account-connection request expired or was already used.",
                )
            row.used = True

    def complete_oauth(self, provider: str, state: str, code: str) -> dict:
        if provider not in PROVIDERS or not self._configured(provider):
            raise AdProviderFailure("NOT_CONFIGURED", "Advertising provider OAuth is not configured.")
        self._consume_state(provider, state)
        redirect = self._redirect_uri(provider)

        if provider == "meta":
            body = self._json(
                self.client.get(
                    f"https://graph.facebook.com/{self.settings.meta_graph_version}/oauth/access_token",
                    params={
                        "client_id": self._secret("meta_app_id"),
                        "client_secret": self._secret("meta_app_secret"),
                        "redirect_uri": redirect,
                        "code": code,
                    },
                ),
                "Meta OAuth",
            )
            token = body.get("access_token")
            refresh = None
            expires = body.get("expires_in")
            scopes = ["ads_management", "ads_read", "business_management", "pages_show_list"]
            if not isinstance(token, str) or not token:
                raise AdProviderFailure("INVALID_OAUTH_RESPONSE", "Meta did not return an access token.")
            profile = self._meta_get(token, "/me", {"fields": "id,name"})
            external_id = profile.get("id")
            display_name = profile.get("name")

        elif provider == "google":
            body = self._json(
                self.client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self._secret("google_ads_client_id"),
                        "client_secret": self._secret("google_ads_client_secret"),
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect,
                    },
                ),
                "Google OAuth",
            )
            token = body.get("access_token")
            refresh = body.get("refresh_token")
            expires = body.get("expires_in")
            scopes = str(body.get("scope", "")).split()
            if not isinstance(token, str) or not token:
                raise AdProviderFailure("INVALID_OAUTH_RESPONSE", "Google did not return an access token.")
            profile_response = self.client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": "Bearer " + token},
            )
            profile = self._json(profile_response, "Google profile") if profile_response.status_code < 400 else {}
            external_id = profile.get("sub")
            display_name = profile.get("email") or profile.get("name")

        else:
            envelope = self._json(
                self.client.post(
                    "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
                    json={
                        "app_id": self._secret("tiktok_app_id"),
                        "secret": self._secret("tiktok_app_secret"),
                        "auth_code": code,
                    },
                ),
                "TikTok OAuth",
            )
            if envelope.get("code") not in {0, "0"}:
                raise AdProviderFailure("OAUTH_REJECTED", "TikTok rejected the authorization exchange.")
            body = envelope.get("data", {})
            token = body.get("access_token")
            refresh = body.get("refresh_token")
            expires = body.get("expires_in")
            scopes = str(body.get("scope", "")).replace(",", " ").split()
            external_id = body.get("open_id") or body.get("core_user_id")
            display_name = "TikTok for Business"
            if not isinstance(token, str) or not token:
                raise AdProviderFailure("INVALID_OAUTH_RESPONSE", "TikTok did not return an access token.")

        expiry = now() + float(expires) if isinstance(expires, (int, float)) and expires > 0 else None
        vault = self._vault()
        with self.store.transaction() as session:
            row = session.scalar(select(AdConnection).where(AdConnection.provider == provider))
            if row is None:
                row = AdConnection(provider=provider, access_token_ciphertext=vault.seal(token))
                session.add(row)
            row.active = True
            row.external_user_id = external_id
            row.display_name = display_name
            row.access_token_ciphertext = vault.seal(token)
            if refresh:
                row.refresh_token_ciphertext = vault.seal(str(refresh))
            row.token_expires_at = expiry
            row.scopes = scopes
            row.details = {}
            row.updated_at = now()
            session.flush()
            return self._connection_public(row)

    @staticmethod
    def _json(response: httpx.Response, label: str) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdProviderFailure("INVALID_RESPONSE", f"{label} returned an unreadable response.") from exc
        if response.status_code >= 400:
            raise AdProviderFailure("PROVIDER_REJECTED", f"{label} rejected the request (HTTP {response.status_code}).")
        if not isinstance(body, dict):
            raise AdProviderFailure("INVALID_RESPONSE", f"{label} returned an invalid response.")
        return body

    def _meta_get(self, token: str, path: str, params: dict | None = None) -> dict:
        response = self.client.get(
            f"https://graph.facebook.com/{self.settings.meta_graph_version}{path}",
            headers={"Authorization": "Bearer " + token},
            params=params or {},
        )
        return self._json(response, "Meta")

    def _access_token(self, connection: AdConnection) -> str:
        vault = self._vault()
        token = vault.open(connection.access_token_ciphertext)
        if connection.token_expires_at and connection.token_expires_at < now() + 300:
            if connection.provider == "google":
                refresh = vault.open(connection.refresh_token_ciphertext)
                if not refresh:
                    raise AdProviderFailure("REAUTH_REQUIRED", "Google authorization expired; reconnect Google Ads.")
                body = self._json(
                    self.client.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": self._secret("google_ads_client_id"),
                            "client_secret": self._secret("google_ads_client_secret"),
                            "refresh_token": refresh,
                            "grant_type": "refresh_token",
                        },
                    ),
                    "Google token refresh",
                )
                token = body.get("access_token")
                if not isinstance(token, str) or not token:
                    raise AdProviderFailure("REAUTH_REQUIRED", "Google token refresh returned no access token.")
                with self.store.transaction() as session:
                    row = required(session, AdConnection, connection.id, lock=True)
                    row.access_token_ciphertext = vault.seal(token)
                    row.token_expires_at = now() + float(body.get("expires_in", 3600))
                    row.updated_at = now()
            elif connection.provider == "tiktok":
                # TikTok Business OAuth returns a refresh token, but the refresh
                # contract has changed across auth products. Do not guess a refresh
                # endpoint: require a clean reauthorization when the access token is stale.
                raise AdProviderFailure("REAUTH_REQUIRED", "TikTok authorization expired; reconnect TikTok Ads.")
            else:
                raise AdProviderFailure("REAUTH_REQUIRED", "Meta authorization expired; reconnect Meta Ads.")
        return token

    def accounts(self, provider: str) -> list[dict]:
        connection = self._connection(provider)
        if not connection:
            raise DomainError(f"Connect {provider.title()} first", 409)
        token = self._access_token(connection)

        if provider == "meta":
            body = self._meta_get(
                token,
                "/me/adaccounts",
                {"fields": "id,name,currency,account_status", "limit": 100},
            )
            return [
                {"id": item["id"], "name": item.get("name") or item["id"], "currency": item.get("currency")}
                for item in body.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]

        if provider == "google":
            response = self.client.get(
                f"https://googleads.googleapis.com/{self.settings.google_ads_api_version}/customers:listAccessibleCustomers",
                headers=self._google_headers(token),
            )
            body = self._json(response, "Google Ads account discovery")
            return [
                {"id": name.split("/", 1)[1], "name": "Google Ads " + name.split("/", 1)[1], "currency": None}
                for name in body.get("resourceNames", [])
                if isinstance(name, str) and name.startswith("customers/")
            ]

        response = self.client.get(
            "https://business-api.tiktok.com/open_api/v1.3/oauth2/advertiser/get/",
            headers={"Access-Token": token},
            params={"app_id": self._secret("tiktok_app_id"), "secret": self._secret("tiktok_app_secret")},
        )
        body = self._json(response, "TikTok advertiser discovery")
        if body.get("code") not in {0, "0"}:
            raise AdProviderFailure("PROVIDER_REJECTED", "TikTok rejected advertiser discovery.")
        items = body.get("data", {}).get("list", []) or body.get("data", {}).get("advertiser_ids", [])
        result = []
        for item in items:
            if isinstance(item, dict):
                identity = str(item.get("advertiser_id") or item.get("id") or "")
                if identity:
                    result.append(
                        {
                            "id": identity,
                            "name": item.get("advertiser_name") or item.get("name") or "TikTok Ads " + identity,
                            "currency": item.get("currency"),
                        }
                    )
            elif str(item):
                result.append({"id": str(item), "name": "TikTok Ads " + str(item), "currency": None})
        return result

    def server_access_token(self, provider: str) -> str:
        connection = self._connection(provider)
        return self._access_token(connection) if connection else ""

    def disconnect(self, provider: str) -> dict:
        connection = self._connection(provider)
        if not connection:
            return {"provider": provider, "connected": False}
        with self.store.transaction() as session:
            row = required(session, AdConnection, connection.id, lock=True)
            row.active = False
            row.access_token_ciphertext = self._vault().seal("")
            row.refresh_token_ciphertext = None
            row.token_expires_at = None
            row.details = {"local_credentials_deleted_at": now()}
            row.updated_at = now()
        return {"provider": provider, "connected": False}

    def publications(self, campaign_id: str | None = None) -> list[dict]:
        with self.store.read() as session:
            query = select(AdPublication)
            if campaign_id:
                query = query.where(AdPublication.campaign_id == campaign_id)
            query = query.order_by(AdPublication.created_at.desc()).limit(50)
            return [record(row) for row in session.scalars(query)]

    def sync_asset(self, request: AdAssetSyncRequest) -> dict:
        connection = self._connection(request.provider)
        if not connection:
            raise DomainError(f"Connect {request.provider.title()} before uploading a creative", 409)
        authorized_accounts = {str(account["id"]) for account in self.accounts(request.provider)}
        if str(request.account_id) not in authorized_accounts:
            raise DomainError("Selected advertising account is not authorized by the connected provider session", 403)

        with self.store.read() as session:
            asset = required(session, Asset, request.asset_id)
            if asset.kind not in {"image", "video"}:
                raise DomainError("Only image and video creatives can be sent to ad platforms", 422)
            asset_record = record(asset)

        key = digest(
            {
                "provider": request.provider,
                "connection": connection.id,
                "account": str(request.account_id),
                "sha256": asset_record["sha256"],
            }
        )
        with self.store.transaction() as session:
            existing = session.scalar(select(AdPublication).where(AdPublication.idempotency_key == key))
            if existing:
                return record(existing)
            row = AdPublication(
                provider=request.provider,
                connection_id=connection.id,
                campaign_id=asset_record["campaign_id"],
                asset_id=asset_record["id"],
                account_id=str(request.account_id),
                idempotency_key=key,
                spec={
                    "label": request.label,
                    "asset_sha256": asset_record["sha256"],
                    "asset_name": asset_record["name"],
                    "asset_kind": asset_record["kind"],
                },
                state="SYNCING",
                remote={},
            )
            session.add(row)
            session.flush()
            publication_id = row.id

        try:
            data = self.objects.read(asset_record["object_key"])
            token = self._access_token(connection)
            if request.provider == "meta":
                remote = self._upload_meta(token, request.account_id, asset_record, data, request.label)
            elif request.provider == "google":
                remote = self._upload_google(token, request.account_id, asset_record, data, request.label)
            else:
                remote = self._upload_tiktok(token, request.account_id, asset_record, data, request.label)
            remote["dashboard_url"] = self.dashboard_url(request.provider)
            with self.store.transaction() as session:
                row = required(session, AdPublication, publication_id, lock=True)
                row.state = "SYNCED"
                row.remote = remote
                row.error = None
                row.updated_at = now()
                return record(row)
        except Exception as exc:
            code = exc.code if isinstance(exc, AdProviderFailure) else type(exc).__name__
            uncertain = not isinstance(exc, AdProviderFailure) or exc.uncertain
            with self.store.transaction() as session:
                row = required(session, AdPublication, publication_id, lock=True)
                row.state = "NEEDS_RECONCILIATION" if uncertain else "FAILED"
                row.error = f"{code}: " + (
                    str(exc)
                    if isinstance(exc, AdProviderFailure)
                    else "Unexpected provider failure; inspect the provider asset library before retrying."
                )
                row.updated_at = now()
                return record(row)

    def _upload_meta(self, token: str, account_id: str, asset: dict, data: bytes, label: str) -> dict:
        account = "act_" + str(account_id).removeprefix("act_")
        url = f"https://graph.facebook.com/{self.settings.meta_graph_version}/{account}/"
        headers = {"Authorization": "Bearer " + token}
        try:
            if asset["kind"] == "image":
                response = self.client.post(
                    url + "adimages",
                    headers=headers,
                    data={"bytes": base64.b64encode(data).decode(), "name": label},
                )
                body = self._json(response, "Meta image upload")
                images = list(body.get("images", {}).values())
                image_hash = images[0].get("hash") if len(images) == 1 and isinstance(images[0], dict) else None
                if not image_hash:
                    raise AdProviderFailure("MISSING_RECEIPT", "Meta did not return an image hash.", uncertain=True)
                return {"kind": "image", "image_hash": image_hash}

            response = self.client.post(
                url + "advideos",
                headers=headers,
                data={"title": label},
                files={"source": (asset["name"], data, asset["mime"])},
            )
            body = self._json(response, "Meta video upload")
            video_id = body.get("id")
            if not isinstance(video_id, str) or not video_id:
                raise AdProviderFailure("MISSING_RECEIPT", "Meta did not return a video ID.", uncertain=True)
            return {"kind": "video", "video_id": video_id, "processing": "provider_managed"}
        except httpx.TransportError as exc:
            raise AdProviderFailure(
                "TRANSPORT_FAILURE",
                "Meta upload acknowledgement was lost; inspect Ads Manager before retrying.",
                uncertain=True,
            ) from exc

    def _google_headers(self, token: str) -> dict:
        developer = self._secret("google_ads_developer_token")
        if not developer:
            raise AdProviderFailure("NOT_CONFIGURED", "GOOGLE_ADS_DEVELOPER_TOKEN is required for Google Ads uploads.")
        return {"Authorization": "Bearer " + token, "developer-token": developer}

    def _upload_google(self, token: str, customer_id: str, asset: dict, data: bytes, label: str) -> dict:
        customer = re.sub(r"[^0-9]", "", str(customer_id))
        if not customer:
            raise AdProviderFailure("INVALID_ACCOUNT", "Google Ads customer ID is invalid.")
        headers = self._google_headers(token)
        version = self.settings.google_ads_api_version
        try:
            if asset["kind"] == "image":
                response = self.client.post(
                    f"https://googleads.googleapis.com/{version}/customers/{customer}/assets:mutate",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "operations": [
                            {
                                "create": {
                                    "name": label,
                                    "type": "IMAGE",
                                    "imageAsset": {"data": base64.b64encode(data).decode()},
                                }
                            }
                        ]
                    },
                )
                body = self._json(response, "Google Ads image upload")
                resource = ((body.get("results") or [{}])[0]).get("resourceName")
                if not resource:
                    raise AdProviderFailure(
                        "MISSING_RECEIPT",
                        "Google Ads did not return an image asset resource.",
                        uncertain=True,
                    )
                return {"kind": "image", "resource_name": resource}

            start = self.client.post(
                f"https://googleads.googleapis.com/resumable/upload/{version}/customers/{customer}/youTubeVideoUploads:create",
                headers={
                    **headers,
                    "Content-Type": "application/json",
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(len(data)),
                },
                json={
                    "customer_id": customer,
                    "you_tube_video_upload": {
                        "video_title": label,
                        "video_description": "Uploaded from NeuroLoop",
                        "video_privacy": "UNLISTED",
                    },
                },
            )
            if start.status_code >= 400:
                self._json(start, "Google Ads video upload start")
            upload_url = start.headers.get("x-goog-upload-url")
            parsed = urlparse(upload_url or "")
            if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith("googleapis.com"):
                raise AdProviderFailure("INVALID_RESPONSE", "Google Ads did not return a trusted resumable upload URL.")

            final = self.client.put(
                upload_url,
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                    "Content-Length": str(len(data)),
                },
                content=data,
            )
            body = self._json(final, "Google Ads video upload")
            resource = body.get("resourceName") or body.get("resource_name")
            if not resource:
                raise AdProviderFailure(
                    "MISSING_RECEIPT",
                    "Google Ads did not return a video upload resource.",
                    uncertain=True,
                )
            return {
                "kind": "video",
                "resource_name": resource,
                "video_id": body.get("videoId") or body.get("video_id"),
                "state": body.get("state", "PENDING"),
            }
        except httpx.TransportError as exc:
            raise AdProviderFailure(
                "TRANSPORT_FAILURE",
                "Google Ads upload acknowledgement was lost; inspect the asset library before retrying.",
                uncertain=True,
            ) from exc

    def _upload_tiktok(self, token: str, advertiser_id: str, asset: dict, data: bytes, label: str) -> dict:
        base = "https://business-api.tiktok.com/open_api/v1.3/file/"
        headers = {"Access-Token": token}
        signature = hashlib.md5(data).hexdigest()  # TikTok's documented upload integrity field.
        unique_name = (label[:70] + "-" + asset["sha256"][:12])[:100]
        try:
            if asset["kind"] == "image":
                response = self.client.post(
                    base + "image/ad/upload/",
                    headers=headers,
                    data={
                        "advertiser_id": str(advertiser_id),
                        "file_name": unique_name,
                        "image_signature": signature,
                    },
                    files={"image_file": (asset["name"], data, asset["mime"])},
                )
                body = self._json(response, "TikTok image upload")
                if body.get("code") not in {0, "0"}:
                    raise AdProviderFailure("PROVIDER_REJECTED", "TikTok rejected the image upload.")
                payload = body.get("data", {})
                image_id = payload.get("image_id")
                if not image_id and isinstance(payload.get("images"), list) and payload["images"]:
                    image_id = payload["images"][0].get("image_id")
                if not image_id:
                    raise AdProviderFailure("MISSING_RECEIPT", "TikTok did not return an image ID.", uncertain=True)
                return {"kind": "image", "image_id": str(image_id), "request_id": body.get("request_id")}

            response = self.client.post(
                base + "video/ad/upload/",
                headers=headers,
                data={
                    "advertiser_id": str(advertiser_id),
                    "file_name": unique_name,
                    "video_signature": signature,
                },
                files={"video_file": (asset["name"], data, asset["mime"])},
            )
            body = self._json(response, "TikTok video upload")
            if body.get("code") not in {0, "0"}:
                raise AdProviderFailure("PROVIDER_REJECTED", "TikTok rejected the video upload.")
            payload = body.get("data", {})
            video_id = payload.get("video_id")
            if not video_id and isinstance(payload.get("videos"), list) and payload["videos"]:
                video_id = payload["videos"][0].get("video_id")
            if not video_id:
                raise AdProviderFailure("MISSING_RECEIPT", "TikTok did not return a video ID.", uncertain=True)
            return {"kind": "video", "video_id": str(video_id), "request_id": body.get("request_id")}
        except httpx.TransportError as exc:
            raise AdProviderFailure(
                "TRANSPORT_FAILURE",
                "TikTok upload acknowledgement was lost; inspect the creative library before retrying.",
                uncertain=True,
            ) from exc
