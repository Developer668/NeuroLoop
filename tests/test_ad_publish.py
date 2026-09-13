"""Publish Ads contracts. External responses here are explicit HTTP test doubles."""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from neuroloop_app.ad_publish import AdProviderFailure, AdPublishService, TokenVault
from neuroloop_app.api import create_app
from neuroloop_app.config import Settings
from neuroloop_app.db import AdConnection, AdPublication, Store
from neuroloop_app.domain import AdAssetSyncRequest
from neuroloop_app.engine import LoopEngine
from neuroloop_app.storage import ObjectStore
from test_loop import campaign


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "state",
        operator_token="o" * 40,
        agent_token="a" * 40,
        worker_token="w" * 40,
        local_bootstrap_token="b" * 40,
        signing_key="s" * 40,
        META_APP_ID="meta-app",
        META_APP_SECRET="meta-secret",
        meta_graph_version="v99.0",
        GOOGLE_ADS_CLIENT_ID="google-client",
        GOOGLE_ADS_CLIENT_SECRET="google-secret",
        GOOGLE_ADS_DEVELOPER_TOKEN="google-developer",
        TIKTOK_APP_ID="tiktok-app",
        TIKTOK_APP_SECRET="tiktok-secret",
    )


@pytest.fixture
def state(settings):
    store = Store(settings)
    store.initialize()
    objects = ObjectStore(settings)
    return store, objects


def test_tokens_are_encrypted_and_round_trip(settings):
    vault = TokenVault(settings)
    sealed = vault.seal("secret-provider-token")
    assert sealed != "secret-provider-token"
    assert "secret-provider-token" not in sealed
    assert vault.open(sealed) == "secret-provider-token"


def test_publish_routes_are_human_only(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v2/publish/providers", headers={"Authorization": "Bearer " + "a" * 40}).status_code == 403
        session = client.post("/auth/local", headers={"X-NeuroLoop-Bootstrap": "b" * 40}).json()["token"]
        response = client.get("/api/v2/publish/providers", headers={"Authorization": "Bearer " + session})
        assert response.status_code == 200
        assert {row["provider"] for row in response.json()} == {"meta", "google", "tiktok"}
        assert all(row["configured"] for row in response.json())


def test_oauth_state_is_one_time_and_meta_token_is_not_exposed(state, settings):
    store, objects = state
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "META_TEST_TOKEN", "expires_in": 3600})
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"id": "user-1", "name": "Fixture User"})
        raise AssertionError(str(request.url))

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    start = service.begin_oauth("meta")
    parsed = urlparse(start["authorization_url"])
    state_token = parse_qs(parsed.query)["state"][0]
    connection = service.complete_oauth("meta", state_token, "AUTH_CODE")
    assert connection["display_name"] == "Fixture User"
    assert "access_token" not in connection
    with store.read() as session:
        row = session.scalar(select(AdConnection).where(AdConnection.provider == "meta"))
        assert row is not None
        assert "META_TEST_TOKEN" not in row.access_token_ciphertext
    with pytest.raises(AdProviderFailure) as exc:
        service.complete_oauth("meta", state_token, "AUTH_CODE")
    assert exc.value.code == "INVALID_OAUTH_STATE"


def _image_asset(store, objects, tmp_path):
    engine = LoopEngine(store, objects)
    c = campaign(engine)
    path = tmp_path / "creative.png"
    Image.new("RGB", (64, 64), (23, 45, 67)).save(path)
    asset = engine.add_asset(c["id"], path, "creative.png")
    return c, asset


def test_meta_image_sync_is_idempotent_and_preserves_remote_receipt(state, settings, tmp_path):
    store, objects = state
    c, asset = _image_asset(store, objects, tmp_path)
    posts = 0

    def handler(request: httpx.Request):
        nonlocal posts
        if request.method == "GET" and request.url.path.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": [{"id": "act_123", "name": "Fixture Meta", "currency": "USD"}]})
        if request.method == "POST" and request.url.path.endswith("/act_123/adimages"):
            posts += 1
            return httpx.Response(200, json={"images": {"creative": {"hash": "REMOTE_IMAGE_HASH"}}})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    vault = TokenVault(settings)
    with store.transaction() as session:
        session.add(AdConnection(provider="meta", active=True, display_name="Fixture", access_token_ciphertext=vault.seal("token"), scopes=[], details={}))
    body = AdAssetSyncRequest(provider="meta", asset_id=asset["id"], account_id="act_123", label="Fixture creative")
    first = service.sync_asset(body)
    second = service.sync_asset(body)
    assert first["state"] == "SYNCED"
    assert first["remote"]["image_hash"] == "REMOTE_IMAGE_HASH"
    assert second["id"] == first["id"]
    assert posts == 1
    with store.read() as session:
        assert session.scalar(select(AdPublication)).spec["asset_sha256"] == asset["sha256"]


def test_google_image_and_video_upload_contracts(state, settings):
    store, objects = state
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path.endswith("/assets:mutate"):
            payload = __import__("json").loads(request.content)
            assert payload["operations"][0]["create"]["type"] == "IMAGE"
            assert request.headers["developer-token"] == "google-developer"
            return httpx.Response(200, json={"results": [{"resourceName": "customers/123/assets/456"}]})
        if "/resumable/upload/" in request.url.path:
            return httpx.Response(200, headers={"x-goog-upload-url": "https://googleads.googleapis.com/upload/fixture"})
        if request.url.path == "/upload/fixture":
            assert request.method == "PUT"
            assert request.headers["authorization"] == "Bearer token"
            assert request.headers["x-goog-upload-command"] == "upload, finalize"
            assert request.headers["content-length"] == str(len(b"VIDEO"))
            return httpx.Response(200, json={"resourceName": "customers/123/youTubeVideoUploads/789", "videoId": "yt123", "state": "PROCESSING"})
        raise AssertionError(str(request.url))

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    image = service._upload_google("token", "123", {"kind": "image", "name": "a.png", "mime": "image/png"}, b"PNG", "image")
    video = service._upload_google("token", "123", {"kind": "video", "name": "a.mp4", "mime": "video/mp4"}, b"VIDEO", "video")
    assert image["resource_name"].endswith("/456")
    assert video["video_id"] == "yt123"
    assert any("/v25/customers/123/assets:mutate" in str(request.url) for request in calls)
    assert any("/resumable/upload/v25/customers/123/youTubeVideoUploads:create" in str(request.url) for request in calls)


def test_tiktok_image_and_video_upload_contracts(state, settings):
    store, objects = state
    paths = []

    def handler(request: httpx.Request):
        paths.append(request.url.path)
        assert request.headers["access-token"] == "token"
        if request.url.path.endswith("/file/image/ad/upload/"):
            return httpx.Response(200, json={"code": 0, "data": {"image_id": "img-1"}, "request_id": "req-image"})
        if request.url.path.endswith("/file/video/ad/upload/"):
            return httpx.Response(200, json={"code": 0, "data": {"video_id": "vid-1"}, "request_id": "req-video"})
        raise AssertionError(str(request.url))

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    common = {"name": "creative", "sha256": "f" * 64}
    image = service._upload_tiktok("token", "adv-1", {**common, "kind": "image", "mime": "image/png"}, b"IMAGE", "creative")
    video = service._upload_tiktok("token", "adv-1", {**common, "kind": "video", "mime": "video/mp4"}, b"VIDEO", "creative")
    assert image["image_id"] == "img-1"
    assert video["video_id"] == "vid-1"
    assert "/open_api/v1.3/file/image/ad/upload/" in paths
    assert "/open_api/v1.3/file/video/ad/upload/" in paths


def test_google_oauth_and_accessible_account_discovery(state, settings):
    store, objects = state

    def handler(request: httpx.Request):
        if request.method == "POST" and request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={
                "access_token": "GOOGLE_ACCESS",
                "refresh_token": "GOOGLE_REFRESH",
                "expires_in": 3600,
                "scope": "openid email profile https://www.googleapis.com/auth/adwords",
            })
        if request.method == "GET" and request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"sub": "google-user", "email": "fixture@example.test"})
        if request.method == "GET" and request.url.path.endswith("/customers:listAccessibleCustomers"):
            assert request.headers["developer-token"] == "google-developer"
            return httpx.Response(200, json={"resourceNames": ["customers/1234567890"]})
        raise AssertionError(str(request.url))

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    start = service.begin_oauth("google")
    query = parse_qs(urlparse(start["authorization_url"]).query)
    assert "https://www.googleapis.com/auth/adwords" in query["scope"][0]
    connection = service.complete_oauth("google", query["state"][0], "GOOGLE_CODE")
    assert connection["display_name"] == "fixture@example.test"
    assert service.accounts("google") == [{"id": "1234567890", "name": "Google Ads 1234567890", "currency": None}]
    with store.read() as session:
        row = session.scalar(select(AdConnection).where(AdConnection.provider == "google"))
        assert "GOOGLE_ACCESS" not in row.access_token_ciphertext
        assert "GOOGLE_REFRESH" not in (row.refresh_token_ciphertext or "")


def test_tiktok_oauth_uses_authorized_advertiser_ids(state, settings):
    store, objects = state

    def handler(request: httpx.Request):
        if request.method == "POST" and request.url.path.endswith("/oauth2/access_token/"):
            return httpx.Response(200, json={
                "code": 0,
                "message": "OK",
                "data": {"access_token": "TIKTOK_ACCESS", "refresh_token": "TIKTOK_REFRESH", "expires_in": 86400, "scope": "Creative Management"},
            })
        if request.method == "GET" and request.url.path.endswith("/oauth2/advertiser/get/"):
            return httpx.Response(200, json={
                "code": 0,
                "message": "OK",
                "data": {"list": [
                    {"advertiser_id": "adv-123", "advertiser_name": "Fixture TikTok 1"},
                    {"advertiser_id": "adv-456", "advertiser_name": "Fixture TikTok 2"},
                ]},
            })
        raise AssertionError(str(request.url))

    service = AdPublishService(store, objects, httpx.Client(transport=httpx.MockTransport(handler)))
    start = service.begin_oauth("tiktok")
    query = parse_qs(urlparse(start["authorization_url"]).query)
    assert query["app_id"] == ["tiktok-app"]
    connection = service.complete_oauth("tiktok", query["state"][0], "TIKTOK_CODE")
    assert connection["provider"] == "tiktok"
    assert service.accounts("tiktok") == [
        {"id": "adv-123", "name": "Fixture TikTok 1", "currency": None},
        {"id": "adv-456", "name": "Fixture TikTok 2", "currency": None},
    ]
    with store.read() as session:
        row = session.scalar(select(AdConnection).where(AdConnection.provider == "tiktok"))
        assert row is not None
        assert "TIKTOK_REFRESH" not in (row.refresh_token_ciphertext or "")
