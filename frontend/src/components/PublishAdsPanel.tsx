"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight,
  Check,
  Loader2,
  RefreshCw,
  Send,
  Unplug,
  X,
} from "lucide-react";
import type { Asset, Campaign } from "./LoopWorkspace";

type ProviderName = "meta" | "google" | "tiktok";
type Connection = {
  id: string;
  provider: ProviderName;
  display_name: string | null;
  external_user_id: string | null;
  token_expires_at: number | null;
};
type Provider = {
  provider: ProviderName;
  configured: boolean;
  connected: boolean;
  upload_ready: boolean;
  connection: Connection | null;
  dashboard_url: string;
  detail: string;
};
type Account = { id: string; name: string; currency: string | null };
type Receipt = {
  id: string;
  provider: ProviderName;
  asset_id: string;
  account_id: string;
  state: string;
  spec: { asset_name?: string; asset_kind?: string };
  remote: Record<string, unknown>;
  error: string | null;
  created_at: number;
};

const PROVIDER_NAMES: ProviderName[] = ["meta", "google", "tiktok"];
const INFO: Record<ProviderName, { name: string; sub: string; mark: string }> = {
  meta: { name: "Meta Ads", sub: "Facebook + Instagram", mark: "M" },
  google: { name: "Google Ads", sub: "Google + YouTube", mark: "G" },
  tiktok: { name: "TikTok Ads", sub: "TikTok for Business", mark: "T" },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v2${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
  if (!response.ok)
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as T;
}

const assetUrl = (id: string) => `/api/v2/assets/${id}/content`;

export default function PublishAdsPanel({
  assets,
  campaign,
  campaignId,
  preferredAssetId,
}: {
  assets: Asset[];
  campaign: Campaign | null;
  campaignId: string;
  preferredAssetId?: string | null;
}) {
  const media = useMemo(
    () => assets.filter((asset) => asset.kind === "image" || asset.kind === "video"),
    [assets],
  );
  const [providers, setProviders] = useState<Provider[]>([]);
  const [accounts, setAccounts] = useState<Partial<Record<ProviderName, Account[]>>>({});
  const [selectedAccounts, setSelectedAccounts] = useState<Partial<Record<ProviderName, string>>>({});
  const [selectedProviders, setSelectedProviders] = useState<ProviderName[]>([]);
  const [assetId, setAssetId] = useState("");
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [uploaded, setUploaded] = useState<ProviderName[]>([]);
  const initialized = useRef(false);

  useEffect(() => {
    if (assetId && media.some((asset) => asset.id === assetId)) return;
    const preferred = media.find((asset) => asset.id === preferredAssetId)?.id;
    setAssetId(preferred || media.at(-1)?.id || "");
  }, [assetId, media, preferredAssetId]);

  const refresh = useCallback(async () => {
    const [nextProviders, nextReceipts] = await Promise.all([
      request<Provider[]>("/publish/providers"),
      request<Receipt[]>(`/publish/receipts${campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : ""}`),
    ]);
    setProviders(nextProviders);
    setReceipts(nextReceipts);

    const accountPairs = await Promise.all(
      nextProviders.map(async (provider) => {
        if (!provider.connected || !provider.upload_ready)
          return [provider.provider, [] as Account[]] as const;
        try {
          return [provider.provider, await request<Account[]>(`/publish/${provider.provider}/accounts`)] as const;
        } catch {
          return [provider.provider, [] as Account[]] as const;
        }
      }),
    );

    const nextAccounts: Partial<Record<ProviderName, Account[]>> = {};
    const defaults: Partial<Record<ProviderName, string>> = {};
    for (const [name, values] of accountPairs) {
      nextAccounts[name] = values;
      if (values[0]) defaults[name] = values[0].id;
    }
    setAccounts(nextAccounts);
    setSelectedAccounts((current) => ({ ...defaults, ...current }));

    const usable = nextProviders
      .filter((provider) => provider.connected && provider.upload_ready && (nextAccounts[provider.provider] || []).length)
      .map((provider) => provider.provider);
    setSelectedProviders((current) => {
      if (!initialized.current) {
        initialized.current = true;
        return usable;
      }
      return current.filter((name) => usable.includes(name));
    });
  }, [campaignId]);

  useEffect(() => {
    void refresh().catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [refresh]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.data?.type !== "neuroloop-publish-oauth") return;
      setBusy("");
      if (event.data.status === "connected") {
        setError("");
        void refresh();
      } else {
        setError(`Account connection failed: ${String(event.data.code || "provider error").replaceAll("_", " ").toLowerCase()}.`);
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [refresh]);

  const selectedAsset = media.find((asset) => asset.id === assetId) || null;

  async function connect(name: ProviderName) {
    setBusy(`connect-${name}`);
    setError("");
    const popup = window.open(
      "about:blank",
      `neuroloop-${name}-oauth`,
      "popup=yes,width=560,height=760,resizable=yes,scrollbars=yes",
    );
    try {
      const result = await request<{ authorization_url: string }>(`/publish/${name}/connect`, {
        method: "POST",
        body: "{}",
      });
      if (popup) popup.location.href = result.authorization_url;
      else window.location.assign(result.authorization_url);
    } catch (reason) {
      popup?.close();
      setBusy("");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function disconnect(name: ProviderName) {
    setBusy(`disconnect-${name}`);
    try {
      await request(`/publish/${name}/disconnect`, { method: "POST", body: "{}" });
      setSelectedProviders((current) => current.filter((provider) => provider !== name));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy("");
    }
  }

  function toggle(name: ProviderName) {
    const provider = providers.find((item) => item.provider === name);
    if (!provider?.connected || !provider.upload_ready || !(accounts[name] || []).length) return;
    setSelectedProviders((current) =>
      current.includes(name) ? current.filter((providerName) => providerName !== name) : [...current, name],
    );
  }

  async function upload() {
    if (!selectedAsset || !selectedProviders.length) return;
    setBusy("upload");
    setError("");
    setUploaded([]);
    const done: ProviderName[] = [];
    const failures: string[] = [];

    for (const provider of selectedProviders) {
      const accountId = selectedAccounts[provider];
      if (!accountId) {
        failures.push(`${INFO[provider].name}: choose an ad account`);
        continue;
      }
      try {
        const receipt = await request<Receipt>("/publish/sync", {
          method: "POST",
          body: JSON.stringify({
            provider,
            asset_id: selectedAsset.id,
            account_id: accountId,
            label: selectedAsset.name.replace(/\.[^.]+$/, "").slice(0, 90) || "NeuroLoop creative",
          }),
        });
        if (receipt.state === "SYNCED") done.push(provider);
        else failures.push(`${INFO[provider].name}: ${receipt.state.replaceAll("_", " ").toLowerCase()}`);
      } catch (reason) {
        failures.push(`${INFO[provider].name}: ${reason instanceof Error ? reason.message : String(reason)}`);
      }
    }

    await refresh().catch(() => undefined);
    setUploaded(done);
    if (failures.length) setError(failures.join(" · "));
    setBusy("");
  }

  return (
    <div className="publish2-page">
      <header className="publish2-header">
        <div>
          <span>Publish Ads</span>
          <h2>Send a finished creative to your ad libraries.</h2>
          <p>
            This uploads the exact NeuroLoop image or video. Campaign setup, targeting, budget, billing, and activation stay in each Ads Manager.
          </p>
        </div>
        <button className="publish2-refresh" onClick={() => void refresh()} aria-label="Refresh publishing">
          <RefreshCw size={15} />
        </button>
      </header>

      {error && (
        <div className="publish2-error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")} aria-label="Dismiss"><X size={14} /></button>
        </div>
      )}

      {!campaignId || !media.length ? (
        <section className="publish2-empty">
          <h3>{!campaignId ? "Select a campaign" : "No image or video in this campaign"}</h3>
          <p>
            {!campaignId
              ? "Choose a campaign from the workspace, then return here."
              : "Add or generate a real creative in Library first. Publish Ads does not create placeholder media."}
          </p>
        </section>
      ) : (
        <div className="publish2-layout">
          <section className="publish2-preview-card">
            <div className="publish2-card-heading">
              <div>
                <strong>{campaign?.spec.title || "Creative"}</strong>
                <span>{campaign?.spec.brand.name}</span>
              </div>
              <span>{selectedAsset?.kind}</span>
            </div>
            <div className="publish2-preview">
              {selectedAsset?.kind === "image" ? (
                <img src={assetUrl(selectedAsset.id)} alt={selectedAsset.name} />
              ) : selectedAsset?.kind === "video" ? (
                <video src={assetUrl(selectedAsset.id)} controls playsInline preload="metadata" />
              ) : null}
            </div>
            <div className="publish2-asset-name">{selectedAsset?.name}</div>
            {media.length > 1 && (
              <div className="publish2-thumbs" aria-label="Choose creative">
                {media.slice(-8).map((asset) => (
                  <button
                    key={asset.id}
                    className={asset.id === assetId ? "active" : ""}
                    onClick={() => { setAssetId(asset.id); setUploaded([]); }}
                    aria-label={`Use ${asset.name}`}
                  >
                    {asset.kind === "image" ? <img src={assetUrl(asset.id)} alt="" /> : <video src={assetUrl(asset.id)} muted preload="metadata" />}
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="publish2-destinations">
            <div className="publish2-card-heading">
              <div>
                <strong>Destinations</strong>
                <span>Connect a real advertiser account, then choose where to upload.</span>
              </div>
            </div>

            <div className="publish2-provider-list">
              {PROVIDER_NAMES.map((name) => {
                const provider = providers.find((item) => item.provider === name);
                const providerAccounts = accounts[name] || [];
                const selected = selectedProviders.includes(name);
                return (
                  <article className={`publish2-provider ${selected ? "selected" : ""}`} key={name}>
                    <button
                      className="publish2-provider-select"
                      onClick={() => toggle(name)}
                      disabled={!provider?.connected || !provider.upload_ready || !providerAccounts.length}
                      aria-pressed={selected}
                    >
                      <span className={`publish2-mark ${name}`}>{INFO[name].mark}</span>
                      <span className="publish2-provider-copy">
                        <strong>{INFO[name].name}</strong>
                        <small>
                          {provider?.connected
                            ? providerAccounts.length
                              ? provider.connection?.display_name || INFO[name].sub
                              : "No accessible ad accounts"
                            : provider?.configured
                              ? "Not connected"
                              : "Integration not configured"}
                        </small>
                      </span>
                      <span className={`publish2-check ${selected ? "on" : ""}`}>{selected && <Check size={12} />}</span>
                    </button>

                    {provider?.connected && providerAccounts.length ? (
                      <div className="publish2-account-row">
                        <select
                          aria-label={`${INFO[name].name} account`}
                          value={selectedAccounts[name] || ""}
                          onChange={(event) => setSelectedAccounts((current) => ({ ...current, [name]: event.target.value }))}
                        >
                          {providerAccounts.map((account) => (
                            <option value={account.id} key={account.id}>
                              {account.name}{account.currency ? ` · ${account.currency}` : ""}
                            </option>
                          ))}
                        </select>
                        <button
                          className="publish2-disconnect"
                          onClick={() => void disconnect(name)}
                          disabled={Boolean(busy)}
                          aria-label={`Disconnect ${INFO[name].name}`}
                        >
                          <Unplug size={13} />
                        </button>
                      </div>
                    ) : (
                      <div className="publish2-connect-row">
                        <button
                          className="publish2-connect"
                          disabled={!provider?.configured || Boolean(busy)}
                          onClick={() => void connect(name)}
                        >
                          {busy === `connect-${name}` ? <Loader2 className="spin" size={14} /> : null}
                          {provider?.configured ? `Connect ${INFO[name].name}` : "Setup required"}
                        </button>
                        {!provider?.configured && <small>{provider?.detail}</small>}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>

            <button
              className="publish2-upload"
              disabled={!selectedAsset || !selectedProviders.length || Boolean(busy)}
              onClick={() => void upload()}
            >
              {busy === "upload" ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
              Upload to {selectedProviders.length} {selectedProviders.length === 1 ? "destination" : "destinations"}
            </button>
            <p className="publish2-scope-note">
              Upload only. NeuroLoop does not claim this creates or activates a campaign.
            </p>
          </section>
        </div>
      )}

      {uploaded.length > 0 && (
        <section className="publish2-success">
          <div>
            <Check size={16} />
            <span>
              Uploaded to {uploaded.map((name) => INFO[name].name).join(", ")}. The provider asset IDs were saved with the NeuroLoop asset hash.
            </span>
          </div>
          <div>
            {uploaded.map((name) => {
              const provider = providers.find((item) => item.provider === name);
              return provider ? (
                <a href={provider.dashboard_url} target="_blank" rel="noreferrer" key={name}>
                  Open {INFO[name].name} <ArrowUpRight size={12} />
                </a>
              ) : null;
            })}
          </div>
        </section>
      )}

      {receipts.length > 0 && (
        <section className="publish2-history">
          <span>Recent real uploads</span>
          {receipts.slice(0, 5).map((receipt) => (
            <article key={receipt.id}>
              <span className={`publish2-mark small ${receipt.provider}`}>{INFO[receipt.provider].mark}</span>
              <div>
                <strong>{receipt.spec.asset_name || receipt.asset_id}</strong>
                <small>{INFO[receipt.provider].name} · {new Date(receipt.created_at * 1000).toLocaleString()}</small>
                {receipt.error && <small className="error">{receipt.error}</small>}
              </div>
              <span className={`publish2-state ${receipt.state.toLowerCase()}`}>{receipt.state.replaceAll("_", " ")}</span>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
