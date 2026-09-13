# Publish Ads

Publish Ads is a real creative-library handoff, not a simulated cross-platform campaign builder.

The workflow is deliberately narrow:

1. Select an existing NeuroLoop image or video.
2. Connect Meta Ads, Google Ads, or TikTok Ads with that provider's OAuth flow.
3. Choose an advertiser account returned by the provider.
4. Upload the exact stored creative bytes to that provider's asset library.
5. Persist the returned provider asset ID/hash/resource name beside the NeuroLoop asset SHA-256.
6. Open the provider's Ads Manager to finish campaign configuration, targeting, budget, billing, and activation.

NeuroLoop does **not** claim that one generic form can truthfully create equivalent campaigns across Meta, Google, and TikTok. Those platforms have different campaign/objective/targeting/placement requirements. The shared NeuroLoop action therefore stops at the part that is actually common and verifiable: authorized creative upload.

## Providers

### Meta Ads

- OAuth requests Marketing API permissions including `ads_management` and `ads_read`.
- Ad accounts are read from the authorized Meta user.
- Images are uploaded to the selected ad account's ad-image library.
- Videos are uploaded to the selected ad account's ad-video library.
- NeuroLoop stores the real image hash or video ID returned by Meta.

The separate advanced Meta deployment subsystem remains available for its existing reviewed PAUSED campaign flow. It can reuse the Meta OAuth authorization from Publish Ads.

### Google Ads

- OAuth uses the Google Ads `adwords` scope.
- A Google Ads developer token is required in addition to OAuth credentials.
- Accessible customer IDs are loaded from `customers:listAccessibleCustomers`.
- Images are created through the Google Ads Asset service.
- Videos use Google Ads' resumable `YouTubeVideoUploadService`: create the upload session, then `PUT` the exact video bytes to Google's returned upload URL.

### TikTok Ads

- OAuth uses a TikTok for Business developer app.
- Authorized advertisers are loaded from the Marketing API.
- Images and videos are uploaded to the selected advertiser's Asset Library.
- NeuroLoop stores the image/video ID returned by TikTok.

## OAuth callback

The default local callback stays on the frontend origin so provider login can occur in a popup without replacing the NeuroLoop workspace:

```text
http://localhost:3010/api/publish/oauth/meta/callback
http://localhost:3010/api/publish/oauth/google/callback
http://localhost:3010/api/publish/oauth/tiktok/callback
```

The frontend callback forwards the provider response to the local NeuroLoop API. The API validates the one-time OAuth state, exchanges the code server-side, encrypts the resulting authorization, then redirects the popup to `/publish/oauth-return`. Provider access tokens are never returned to browser code or stored in browser storage.

Explicit callback overrides are available through:

```text
NEUROLOOP_META_OAUTH_REDIRECT_URI=
NEUROLOOP_GOOGLE_ADS_OAUTH_REDIRECT_URI=
NEUROLOOP_TIKTOK_OAUTH_REDIRECT_URI=
```

Production callbacks must be HTTPS.

## Required configuration

```text
META_APP_ID=
META_APP_SECRET=
NEUROLOOP_META_GRAPH_VERSION=

GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
NEUROLOOP_GOOGLE_ADS_API_VERSION=v25

TIKTOK_APP_ID=
TIKTOK_APP_SECRET=
```

If a provider is not configured, Publish Ads says **Setup required** and does not manufacture a connected account or successful upload.

## Reliability boundaries

- Publishing routes require an authenticated human session. Restricted agent credentials cannot connect advertiser accounts or upload creatives.
- OAuth state is random, one-use, server-stored, and expires after ten minutes.
- Provider tokens are encrypted at rest using a key derived from `NEUROLOOP_SIGNING_KEY`.
- The selected ad account must be returned by the active provider authorization.
- The upload idempotency key binds provider, connection, account, and exact asset SHA-256.
- A confirmed provider response becomes `SYNCED`.
- A clear provider rejection becomes `FAILED`.
- A lost or ambiguous remote acknowledgement becomes `NEEDS_RECONCILIATION`, rather than issuing an automatic duplicate upload.
- Publish Ads does not modify billing and does not activate campaign spend.

## Verification status

Local automated tests validate OAuth state handling, encrypted tokens, account-discovery request contracts, Meta upload receipts, Google image upload, Google resumable video initiation plus authenticated `PUT` finalization, TikTok image/video upload contracts, idempotency, human-only permissions, frontend type checking, production build, and browser layout.

A provider is **not** reported as live-verified unless actual developer credentials and an authorized advertiser account are present. On the current local checkout, provider credentials are not configured, so the honest UI state is **Setup required**.
