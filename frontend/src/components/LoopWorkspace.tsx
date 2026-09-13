"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  ArrowUpRight,
  BrainCircuit,
  Check,
  ChevronRight,
  GitBranch,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  Send,
  Settings2,
  Square,
  Upload,
  X,
} from "lucide-react";
import MetaPanel from "@/components/MetaPanel";
import RunProgress from "./RunProgress";
import LiveLogPanel from "./LiveLogPanel";
import liveStyles from "./LiveLogPanel.module.css";
import LoopShell, { navigation } from "./LoopShell";
import LoopComposer, { type ComposeRequest } from "./LoopComposer";
import {
  CampaignCollection,
  MediaLibrary,
  CreativeComparison,
} from "./LoopCollections";
import LoopLogin from "./LoopLogin";
const EvidenceStudio = dynamic(() => import("./EvidenceStudio"));
const HelpGuide = dynamic(() => import("./HelpGuide"));
const TelemetryPanel = dynamic(() => import("./TelemetryPanel"));
const PublishAdsPanel = dynamic(() => import("./PublishAdsPanel"));
type Json = Record<string, unknown>;
export type Asset = {
  id: string;
  job_id?: string | null;
  name: string;
  mime: string;
  kind: string;
  details: Json;
};
export type Campaign = {
  id: string;
  spec: {
    title: string;
    brief: string;
    media_kind: string;
    brand: { name: string };
  };
};
type Run = {
  id: string;
  state: string;
  round: number;
  champion_id: string | null;
  stop_reason: string | null;
  stats: Record<string, number | string | null>;
  selected_ids: string[];
};
type Evidence = {
  eligible: boolean;
  quality: { value: number; confidence: number | null } | null;
  hard_constraints: { name: string; status: string; evidence: string }[];
  evaluations: {
    id: string;
    evaluator: string;
    result: Json;
    comparison_key: string;
  }[];
  missing_required_evaluators: string[];
};
export type Creative = {
  id: string;
  parent_id: string | null;
  round: number;
  branch: number;
  status: string;
  creation_type: string;
  output_asset_id: string | null;
  input_asset_ids: string[];
  plan: { prompt: string; strategy: string; edit_intent: Json };
  generation: Json;
  rejection_reason: string | null;
  evidence: Evidence | null;
};
type Snapshot = {
  run: Run;
  creatives: Creative[];
  jobs: {
    id: string;
    kind: string;
    capability: string;
    started_at?: number | null;
    completed_at?: number | null;
    created_at?: number;
    status: string;
    error: Json | null;
    progress: Json;
    result?: Json | null;
  }[];
  events: { id: number; kind: string; detail: Json; created_at: number }[];
  decisions: {
    id: string;
    result: Json;
    applied_action: string;
    override_reason: string | null;
  }[];
  traces: {
    id: string;
    name: string;
    status: string;
    url: string | null;
    parent_id: string | null;
    error: string | null;
  }[];
};
type Detail = {
  campaign: Campaign;
  assets: Asset[];
  runs: Run[];
  feedback: Json[];
};
type Capabilities = {
  workers: {
    id: string;
    provider: string;
    online: boolean;
    capabilities: Record<
      string,
      {
        status: string;
        model?: string;
        version?: string;
        provenance?: { model: string; version: string };
        supports_regeneration?: boolean;
        supports_media_references?: boolean;
        loaded?: boolean;
        detail?: string;
      }
    >;
  }[];
  queue_depth: number;
  active_jobs: number;
  storage: string;
  database: string;
  weave: { status: string; delivered_traces: number };
  aria: Json;
  meta: Json;
};
const views = [
  "Overview",
  "Projects",
  "Library",
  "Compare",
  "Neuro AI",
  "Command Center",
  "Lineage",
  "Creative Lab",
  "Brain Lab",
  "Logs & Charts",
  "Publish Ads",
  "How to use",
  "Experiments",
  "Learning",
  "Settings",
] as const;
type View = (typeof views)[number];
const errorMessage = (e: unknown) =>
  e instanceof Error ? e.message : "Operation failed";
const short = (id: string) => id.slice(0, 8);
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v2${path}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
  if (!res.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data as T;
}
function Status({ value }: { value: string }) {
  return (
    <span className={`nl-status ${value.toLowerCase()}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
function Media({ creative, kind }: { creative: Creative; kind?: string }) {
  if (!creative.output_asset_id)
    return (
      <div className="nl-no-media" role="status" aria-busy={!["FAILED", "CANCELLED", "REJECTED"].includes(creative.status)}>
        {["FAILED", "CANCELLED", "REJECTED"].includes(creative.status) ? <Layers size={24} /> : <span className={liveStyles.waiting}><Loader2 size={24} /></span>}
        <span>
          {creative.status === "FAILED"
            ? "Generation failed — record preserved"
            : ["CANCELLED", "REJECTED"].includes(creative.status) ? "Generation stopped — record preserved" : "Waiting for generated media… Updates appear automatically."}
        </span>
      </div>
    );
  const url = `/api/v2/assets/${creative.output_asset_id}/content`;
  return kind === "image" ? (
    <img
      className="nl-media"
      src={url}
      alt={`Creative ${short(creative.id)}`}
    />
  ) : (
    <video className="nl-media" src={url} controls preload="metadata" />
  );
}
function JsonView({ value }: { value: unknown }) {
  return <pre className="nl-json">{JSON.stringify(value, null, 2)}</pre>;
}
export default function LoopWorkspace() {
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [token, setToken] = useState("");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]),
    [campaignId, setCampaignId] = useState(""),
    [detail, setDetail] = useState<Detail | null>(null);
  const [runId, setRunId] = useState(""),
    [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [caps, setCaps] = useState<Capabilities | null>(null);
  const [view, updateView] = useState<View>("Overview"),
    [creating, setCreating] = useState(false),
    [selectedId, setSelectedId] = useState(""),
    [comparisonId, setComparisonId] = useState("");
  const [feedback, setFeedback] = useState(""),
    [learning, setLearning] = useState<Json | null>(null),
    [refs, setRefs] = useState<string[]>([]);
  const [initial, setInitial] = useState(2),
    [rounds, setRounds] = useState(3),
    [beam, setBeam] = useState(2),
    [branches, setBranches] = useState(2),
    [budget, setBudget] = useState(10),
    [requireBrain, setRequireBrain] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [navigationReady, setNavigationReady] = useState(false);
  const setView = (next: View) => {
    updateView(next);
    setCreating(false);
    const url = new URL(window.location.href);
    url.searchParams.set(
      "view",
      navigation.find((n) => n.view === next)?.id || next,
    );
    window.history.pushState(null, "", url);
  };
  useEffect(() => {
    const restore = () => {
      const query = new URLSearchParams(window.location.search);
      setCampaignId(query.get("campaign") || "");
      setRunId(query.get("run") || "");
      setNavigationReady(true);
      const name =
        (query.get("view") === "connections" ? "Settings" : undefined) ||
        navigation.find((n) => n.id === query.get("view"))?.view ||
        (window.location.pathname === "/neuro" ? "Neuro AI" : undefined);
      updateView(
        name ||
          (views.includes(query.get("view") as View)
            ? (query.get("view") as View)
            : "Overview"),
      );
      if (query.get("view") === "upload") updateView("Library");
      if (query.get("view") === "connections") updateView("Settings");
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  useEffect(() => {
    if (!navigationReady) return;
    const url = new URL(window.location.href);
    for (const [key, value] of [
      ["campaign", campaignId],
      ["run", runId],
    ]) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", url);
  }, [campaignId, runId, navigationReady]);
  const [runSyncedAt, setRunSyncedAt] = useState<number>();
  const refresh = useCallback(async () => {
    const [cs, cap] = await Promise.all([
      api<Campaign[]>("/campaigns"),
      api<Capabilities>("/capabilities"),
    ]);
    setCampaigns(cs);
    setCaps(cap);
    setReady(true);
    return cs;
  }, []);
  useEffect(() => {
    void refresh().catch(() => setReady(false));
    const timer = setInterval(() => { void refresh().catch((e) => setError(errorMessage(e))); }, 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!ready || !campaignId) {
      setDetail(null);
      return;
    }
    let active = true;
    let firstLoad = true;
    const load = () =>
      api<Detail>(`/campaigns/${campaignId}`)
        .then((d) => {
          if (active) {
            setDetail(d);
            if (firstLoad) setRunId(previous => previous || d.runs[0]?.id || "");
            firstLoad = false;
          }
        })
        .catch((e) => {
          if (active) setError(errorMessage(e));
        });
    void load();
    const t = setInterval(load, 6000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [campaignId, ready]);
  useEffect(() => {
    if (!ready || !runId) {
      setSnapshot(null);
      return;
    }
    let active = true;
    let loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const d = await api<Snapshot>(`/runs/${runId}`);
        if (active) { setSnapshot(d); setRunSyncedAt(Date.now()); }
      } catch (e) {
        if (active) setError(errorMessage(e));
      } finally {
        loading = false;
      }
    };
    void load();
    const t = setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [runId, ready]);
  useEffect(() => {
    if (!ready) return;
    const t = setInterval(
      () => void refresh().catch((e) => setError(errorMessage(e))),
      10000,
    );
    return () => clearInterval(t);
  }, [ready, refresh]);
  useEffect(() => {
    if (view === "Learning" && ready)
      void api<Json>("/learning")
        .then(setLearning)
        .catch((e) => setError(errorMessage(e)));
  }, [view, ready, snapshot?.run.state]);
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const login = (local: boolean) =>
    perform(async () => {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(local ? { mode: "local" } : { token }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Sign in failed");
      setToken("");
      const cs = await refresh();
      if (cs.length) setCampaignId(cs[0].id);
    });
  const chooseCampaign = (id: string) => {
    setDetail(null);
    setCampaignId(id);
    setRunId("");
    setSnapshot(null);
    setSelectedId("");
    setComparisonId("");
    setRefs([]);
  };
  async function createCampaign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    await perform(async () => {
      const colors = String(form.get("colors") || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const c = await api<Campaign>("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          brief: form.get("brief"),
          brand: {
            name: form.get("brand"),
            product_description: form.get("product"),
            source_text: form.get("sources"),
            voice: form.get("voice"),
            colors,
            locked_requirements: ["product_identity"],
            approved_claims: [],
            prohibited_claims: String(form.get("prohibited") || "")
              .split("\n")
              .filter(Boolean),
          },
          media_kind: form.get("kind"),
          aspect_ratio: form.get("aspect"),
          duration_seconds: Number(form.get("duration")),
          objective: form.get("objective"),
          audience: form.get("audience"),
          platform: form.get("platform"),
        }),
      });
      chooseCampaign(c.id);
      setCreating(false);
      setView("Command Center");
      await refresh();
    });
  }
  const upload = (files: FileList | null) => {
    if (!files || !campaignId) return;
    void perform(async () => {
      for (const f of Array.from(files)) {
        const data = new FormData();
        data.set("file", f);
        const a = await api<Asset>(`/campaigns/${campaignId}/assets`, {
          method: "POST",
          body: data,
        });
        setRefs((old) => [...old, a.id]);
      }
      setDetail(await api<Detail>(`/campaigns/${campaignId}`));
    });
  };
  const start = () =>
    perform(async () => {
      const r = await api<Run>(`/campaigns/${campaignId}/runs`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          reference_asset_ids: refs,
          config: {
            initial_candidates: initial,
            max_rounds: rounds,
            beam_width: beam,
            branch_factor: branches,
            max_candidates: budget,
            required_evaluators: requireBrain
              ? ["vision", "tsam", "tribe"]
              : ["vision"],
            optional_evaluators: ["tsam", "tribe"],
          },
        }),
      });
      setRunId(r.id);
      setSelectedId("");
      setView("Command Center");
      setDetail(await api<Detail>(`/campaigns/${campaignId}`));
    });
  const compose = (request: ComposeRequest) =>
    perform(async () => {
      const campaign = await api<Campaign>("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          title: request.prompt.slice(0, 100),
          brief: request.prompt,
          brand: { name: request.brand },
          media_kind: request.kind,
          aspect_ratio: request.aspect,
          duration_seconds: request.duration,
        }),
      });
      chooseCampaign(campaign.id);
      await refresh();
      const references: string[] = [];
      try {
        for (const file of request.files) {
          const data = new FormData();
          data.set("file", file);
          const asset = await api<Asset>(`/campaigns/${campaign.id}/assets`, {
            method: "POST",
            body: data,
          });
          references.push(asset.id);
        }
        const run = await api<Run>(`/campaigns/${campaign.id}/runs`, {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({
            reference_asset_ids: references,
            config: {
              initial_candidates: 1,
              max_rounds: 3,
              max_candidates: 10,
            },
          }),
        });
        setRunId(run.id);
        setView("Command Center");
      } finally {
        setRefs(references);
        setDetail(await api<Detail>(`/campaigns/${campaign.id}`));
      }
    });
  const act = (action: string, body: Json = {}) =>
    perform(async () => {
      await api(`/runs/${runId}/${action}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSnapshot(await api<Snapshot>(`/runs/${runId}`));
    });
  const selected =
    snapshot?.creatives.find((c) => c.id === selectedId) ||
    snapshot?.creatives.find((c) => c.id === snapshot.run.champion_id) ||
    snapshot?.creatives.at(-1);
  const comparison = snapshot?.creatives.find((c) => c.id === comparisonId);
  const current = snapshot?.run;
  const activeJob = snapshot?.jobs.find((j) => j.status === "LEASED");
  const planReview = snapshot?.jobs.filter((job) => job.kind === "REVIEW_PLAN" && job.status === "SUCCEEDED").at(-1)?.result;
  const agentSummary = snapshot?.jobs.filter(job => job.kind === "SUMMARY" && job.status === "SUCCEEDED").at(-1)?.result;
  const latestDecision = snapshot?.decisions.at(-1);
  const outputProvenance = selected?.generation.provenance as Json | undefined;
  const summaryProvider = agentSummary?.provider_receipt as Json | undefined;
  const lowConfidencePlan = current?.stop_reason?.startsWith("TYPESAFE_PLAN") && planReview?.choice === "APPROVE";
  const submitFeedback = (kind: string) =>
    perform(async () => {
      if (!selected) throw new Error("Choose a generated candidate first");
      await api(`/campaigns/${campaignId}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          creative_id: selected.id,
          kind,
          text: feedback,
        }),
      });
      setFeedback("");
      setDetail(await api<Detail>(`/campaigns/${campaignId}`));
    });
  const selectCreative = (id: string) => {
    setSelectedId(id);
    setView("Creative Lab");
  };
  if (!ready)
    return <LoopLogin busy={busy} error={error} token={token} setToken={setToken} connect={login} />;
  return (
    <LoopShell
      view={view}
      navigate={(v) => setView(v as View)}
      create={() => setCreating(true)}
      refresh={() =>
        void perform(async () => {
          await refresh();
        })
      }
      logout={() =>
        void perform(async () => {
          const r = await fetch("/api/auth", { method: "DELETE" });
          if (!r.ok) throw new Error("Sign out failed");
          setReady(false);
          setDetail(null);
          setSnapshot(null);
          setCampaignId("");
          setRunId("");
        })
      }
      online={!!caps?.workers.some((w) => w.online)}
      active={caps?.active_jobs || 0}
    >
      <header className="nl-header">
        <div>
          <span className="nl-eyebrow">NEUROLOOP / {view.toUpperCase()}</span>
          <h1>{view}</h1>
        </div>
        <div className="nl-header-actions">
          <select
            aria-label="Current campaign"
            disabled={busy}
            value={campaignId}
            onChange={(e) => chooseCampaign(e.target.value)}
          >
            <option value="">Select a campaign</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.spec.title}
              </option>
            ))}
          </select>
          <button
            className="nl-button primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={16} /> New campaign
          </button>
        </div>
      </header>
      {error && (
        <div className="nl-error" role="alert">
          {error}
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {busy && (
        <div className="nl-busy" role="status">
          <Loader2 className="nl-spin" size={15} /> Saving real workspace state…
        </div>
      )}
      {!creating && view !== "How to use" && snapshot && snapshot.run.id === runId && (
        <RunProgress runId={runId} state={snapshot.run.state} stopReason={snapshot.run.stop_reason}
          jobs={snapshot.jobs} online={!!caps?.workers.some(w => w.online)} updatedAt={runSyncedAt}
          open={() => setView("Command Center")} />
      )}
      {!creating && view !== "How to use" && runId && (!snapshot || snapshot.run.id !== runId) && (
        <div className="nl-busy" role="status"><Loader2 className="nl-spin" size={15} /> Loading saved run progress…</div>
      )}
      {creating ? (
        <section className="nl-panel">
          <button className="nl-text-button" onClick={() => setCreating(false)}>
            <ArrowLeft size={16} /> Back
          </button>
          <h2>Create a campaign</h2>
          <p>
            Describe the product, references, audience, and objective. Claims
            remain unapproved until they have explicit source provenance.
          </p>
          <form className="nl-form" onSubmit={(e) => void createCampaign(e)}>
            <label>
              Campaign name
              <input name="title" required maxLength={160} />
            </label>
            <label>
              Brand name
              <input name="brand" required maxLength={120} />
            </label>
            <label className="wide">
              Creative brief
              <textarea
                name="brief"
                required
                minLength={3}
                maxLength={12000}
                rows={4}
                placeholder="What should this creative communicate and achieve?"
              />
            </label>
            <label className="wide">
              Product facts
              <textarea name="product" maxLength={6000} rows={3} />
            </label>
            <label>
              Objective
              <input name="objective" defaultValue="creative_quality" />
            </label>
            <label>
              Audience
              <input name="audience" />
            </label>
            <label>
              Format
              <select name="kind" aria-label="Format">
                <option value="video">Video</option>
                <option value="image">Image</option>
              </select>
            </label>
            <label>
              Aspect ratio
              <select name="aspect" aria-label="Aspect ratio">
                <option>9:16</option>
                <option>16:9</option>
                <option>1:1</option>
                <option>4:5</option>
              </select>
            </label>
            <label>
              Video duration (seconds)
              <input
                name="duration"
                type="number"
                min={2}
                max={15}
                defaultValue={15}
              />
            </label>
            <label>
              Platform
              <input name="platform" defaultValue="instagram_reels" />
            </label>
            <label>
              Voice
              <input name="voice" />
            </label>
            <label>
              Brand colors (comma-separated)
              <input name="colors" />
            </label>
            <label className="wide">
              Source brand information
              <textarea name="sources" rows={3} />
            </label>
            <label className="wide">
              Prohibited claims (one per line)
              <textarea name="prohibited" rows={2} />
            </label>
            <button className="nl-button primary" disabled={busy} type="submit">
              Create campaign <ChevronRight size={16} />
            </button>
          </form>
        </section>
      ) : view === "How to use" ? (
        <HelpGuide />
      ) : view === "Neuro AI" ? (
        <LoopComposer busy={busy} submit={compose} />
      ) : view === "Brain Lab" ? (
        <EvidenceStudio key={campaignId} campaignId={campaignId} />
      ) : view === "Logs & Charts" ? (
        <TelemetryPanel />
      ) : view === "Publish Ads" ? (
        <PublishAdsPanel assets={detail?.assets || []} campaign={detail?.campaign || null} campaignId={campaignId} preferredAssetId={selected?.output_asset_id} />
      ) : view === "Overview" || view === "Projects" ? (
        <CampaignCollection
          campaigns={campaigns}
          overview={view === "Overview"}
          queued={caps?.queue_depth || 0}
          active={caps?.active_jobs || 0}
          create={() => setCreating(true)}
          open={(id) => {
            chooseCampaign(id);
            setView("Command Center");
          }}
        />
      ) : view === "Library" ? (
        <MediaLibrary
          assets={detail?.assets || []}
          campaignId={campaignId}
          busy={busy}
          upload={upload}
        />
      ) : view === "Settings" ? (
        <>
          <section className="nl-panel">
            <h2>Models & connections</h2>
            <p>
              Configured does not mean verified. These statuses come from the
              application and worker heartbeat, not placeholder indicators.
            </p>
            <div className="nl-connection-grid">
              <article>
                <span>W&B Weave</span>
                <Status value={caps?.weave.status || "NOT_CONFIGURED"} />
                <p>
                  {caps?.weave.delivered_traces || 0} traces with readback
                  receipts
                </p>
              </article>
              <article>
                <span>Durable state</span>
                <strong>{caps?.database}</strong>
                <p>Media store: {caps?.storage}</p>
              </article>
              <article>
                <span>Meta advertising</span>
                <Status value={String(caps?.meta.status || "NOT_CONFIGURED")} />
                <p>
                  Activation disabled. Draft and approval gates are separate
                  from deployment.
                </p>
              </article>
              <article>
                <span>ARIA research</span>
                <strong>History export + proposal intake</strong>
                <p>No undocumented ARIA API is called.</p>
              </article>
            </div>
          </section>
          <section className="nl-panel">
            <h2>Shared notebook</h2>
            <p>
              Register real model callables in NeuroLab. The queue serializes
              execution; offloading must be configured when weights do not fit
              together.
            </p>
            {!caps?.workers.length ? (
              <div className="nl-empty">
                No notebook has registered. Campaigns can be created now; model
                jobs will wait.
              </div>
            ) : (
              caps.workers.map((w) => (
                <article className="nl-worker" key={w.id}>
                  <h3>
                    {w.id} <Status value={w.online ? "ONLINE" : "OFFLINE"} />
                  </h3>
                  <p>{w.provider}</p>
                  {Object.entries(w.capabilities).map(([k, v]) => (
                    <div className="nl-check" key={k}>
                      <div>
                        <strong>
                          {v.provenance?.model ||
                            v.model ||
                            k.replaceAll("_", " ")}
                        </strong>
                        <small className="nl-capability-detail">
                          {v.detail}
                          {k.startsWith("generate_") &&
                            (v.supports_regeneration
                              ? " · Media-conditioned regeneration"
                              : " · Text-based alternatives")}
                          {v.loaded ? " · Loaded" : ""}
                        </small>
                      </div>
                      <Status value={w.online ? v.status : "OFFLINE"} />
                    </div>
                  ))}
                </article>
              ))
            )}
            <button
              className="nl-button"
              onClick={() =>
                void perform(async () => {
                  await refresh();
                })
              }
            >
              <RefreshCw size={15} /> Refresh status
            </button>
          </section>
        </>
      ) : view === "Experiments" ? (
        <MetaPanel runId={runId} creativeId={selected?.id || ""} />
      ) : view === "Learning" ? (
        <section className="nl-panel">
          <h2>What the loop has actually learned.</h2>
          <p>
            Selection observations are brand-context evidence, not isolated
            causal effects or proven improvements in sales. Policy proposals are
            inactive until held-out replay and review.
          </p>
          {learning ? (
            <JsonView value={learning} />
          ) : (
            <div className="nl-empty">No learning evidence loaded.</div>
          )}
        </section>
      ) : !campaignId ? (
        <section className="nl-welcome">
          <p className="nl-eyebrow">FROM FIRST CONCEPT TO NEXT ITERATION</p>
          <h2>
            Create. Observe.
            <br />
            <em>Make the next decision better.</em>
          </h2>
          <p>
            Start with real brand assets. Watch each generation become an
            immutable branch, then follow the evidence behind every next action.
          </p>
          <button
            className="nl-button primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={16} /> Create your first campaign
          </button>
          <div className="nl-flow">
            BRIEF <ChevronRight /> GENERATE <ChevronRight /> EVALUATE{" "}
            <ChevronRight /> DECIDE <ChevronRight /> REGENERATE
          </div>
        </section>
      ) : (
        <>
          <div className="nl-runbar">
            <div>
              <strong>{detail?.campaign.spec.title}</strong>
              <span>{detail?.campaign.spec.brand.name}</span>
            </div>
            <select
              aria-label="Campaign run"
              value={runId}
              onChange={(e) => {
                setRunId(e.target.value);
                setSnapshot(null);
                setSelectedId("");
                setComparisonId("");
              }}
            >
              <option value="">New run / campaign inputs</option>
              {detail?.runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {short(r.id)} · {r.state} · round {r.round + 1}
                </option>
              ))}
            </select>
            {current && <Status value={current.state} />}
          </div>
          {!runId ? (
            <section className="nl-two-col">
              <div className="nl-panel">
                <h2>Campaign references</h2>
                <p>{detail?.campaign.spec.brief}</p>
                <label className="nl-upload">
                  <Upload size={22} />
                  <strong>Add product, brand, or creative references</strong>
                  <span>
                    Images, video, audio, PDF, DOCX, and text. Validated before
                    storage.
                  </span>
                  <input
                    type="file"
                    multiple
                    disabled={busy}
                    onChange={(e) => upload(e.target.files)}
                  />
                </label>
                <div className="nl-asset-list">
                  {detail?.assets.map((a) => (
                    <label key={a.id}>
                      <input
                        type="checkbox"
                        checked={refs.includes(a.id)}
                        onChange={(e) =>
                          setRefs((ids) =>
                            e.target.checked
                              ? [...ids, a.id]
                              : ids.filter((x) => x !== a.id),
                          )
                        }
                      />
                      <span>{a.name}</span>
                      <small>{a.kind}</small>
                    </label>
                  ))}
                </div>
              </div>
              <div className="nl-panel">
                <h2>Bound the search</h2>
                <p>
                  Every regeneration includes the parent creative and original
                  references. Nothing is overwritten.
                </p>
                <div className="nl-form">
                  <label>
                    Initial candidates
                    <input
                      type="number"
                      min={1}
                      max={3}
                      value={initial}
                      onChange={(e) => setInitial(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Maximum rounds
                    <input
                      type="number"
                      min={1}
                      max={6}
                      value={rounds}
                      onChange={(e) => setRounds(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Beam width
                    <input
                      type="number"
                      min={1}
                      max={3}
                      value={beam}
                      onChange={(e) => setBeam(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Children per parent
                    <input
                      type="number"
                      min={1}
                      max={3}
                      value={branches}
                      onChange={(e) => setBranches(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Candidate ceiling
                    <input
                      type="number"
                      min={initial}
                      max={30}
                      value={budget}
                      onChange={(e) => setBudget(Number(e.target.value))}
                    />
                  </label>
                  <label className="nl-checkbox">
                    <input
                      type="checkbox"
                      checked={requireBrain}
                      onChange={(e) => setRequireBrain(e.target.checked)}
                    />{" "}
                    Require TSAM and TRIBE
                  </label>
                </div>
                <p className="nl-note">
                  Default limits: 60 minutes of serialized model time, 2 hours
                  elapsed, 80 model calls. A dollar cap requires configured
                  conservative quotes for every provider; unknown prices are not
                  treated as zero.
                </p>
                <button
                  className="nl-button primary"
                  disabled={busy || budget < initial}
                  onClick={() => void start()}
                >
                  Start optimization <Send size={16} />
                </button>
              </div>
            </section>
          ) : (
            <>
              {current && (
                <>
                  <div className="nl-metrics">
                    <article>
                      <span>GENERATION ROUND</span>
                      <strong>{current.round + 1}</strong>
                      <small>Advances when the loop starts another generation.</small>
                    </article>
                    <article>
                      <span>CANDIDATES PRESERVED</span>
                      <strong>{snapshot?.creatives.length || 0}</strong>
                    </article>
                    <article>
                      <span>MODEL CALLS</span>
                      <strong>{current.stats.model_calls || 0}</strong>
                    </article>
                    <article>
                      <span>MODEL TIME / SECONDS</span>
                      <strong>
                        {Number(current.stats.gpu_seconds || 0).toFixed(1)}
                      </strong>
                    </article>
                  </div>
                  {current.stop_reason && (
                    <div className="nl-notice">
                      <strong>
                        {lowConfidencePlan ? "TYPESAFE PLAN: LOW CONFIDENCE" : current.stop_reason.replaceAll("_", " ")}
                      </strong>
                      <span>
                        {lowConfidencePlan
                          ? `TypeSafe chose APPROVE with confidence ${Number(planReview?.confidence).toFixed(2)}, below this run's required threshold. ${snapshot?.creatives.some(c => c.output_asset_id) ? "The next generation was not authorized; earlier outputs remain available." : "Generation has not been authorized."}`
                          : "Inspect the evidence and failure history before continuing."}
                      </span>
                    </div>
                  )}
                  <div className="nl-controls">
                    {!["COMPLETE", "CANCELLED", "FAILED"].includes(
                      current.state,
                    ) && (
                      <button
                        className="nl-button"
                        disabled={busy}
                        onClick={() => void act("cancel")}
                      >
                        <Square size={14} /> Stop run
                      </button>
                    )}
                    {current.state === "NEEDS_ATTENTION" && (
                      <button
                        className="nl-button"
                        disabled={busy}
                        onClick={() =>
                          void act("resume", {
                            acknowledge_uncertain_cost: false,
                          })
                        }
                      >
                        Retry resolved jobs
                      </button>
                    )}
                    {current.state === "READY_FOR_REVIEW" && (
                      <button
                        className="nl-button"
                        disabled={busy}
                        onClick={() => void act("finish")}
                      >
                        <Check size={15} /> Finish creative review
                      </button>
                    )}
                    <a
                      className="nl-text-button"
                      href={`/api/v2/runs/${runId}/export`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Inspect research export <ArrowUpRight size={14} />
                    </a>
                  </div>
                </>
              )}
              {view === "Compare" ? (
                <CreativeComparison
                  creatives={snapshot?.creatives || []}
                  kind={detail?.campaign.spec.media_kind || "video"}
                />
              ) : view === "Lineage" ? (
                <section className="nl-panel">
                  <h2>The regeneration tree</h2>
                  <p>
                    Parent-child relationships are preserved, including rejected
                    and failed branches. Select a node to inspect its prompt and
                    evidence.
                  </p>
                  <div className="nl-tree">
                    {Array.from(
                      new Set(snapshot?.creatives.map((c) => c.round) || []),
                    ).map((round) => (
                      <div className="nl-tree-round" key={round}>
                        <h3>Round {round + 1}</h3>
                        {snapshot?.creatives
                          .filter((c) => c.round === round)
                          .map((c) => (
                            <button
                              className="nl-node"
                              key={c.id}
                              onClick={() => selectCreative(c.id)}
                            >
                              <span>
                                {c.parent_id
                                  ? `↳ ${short(c.parent_id)} →`
                                  : "INITIAL"}{" "}
                                {short(c.id)}
                              </span>
                              <strong>{c.plan.strategy}</strong>
                              <Status value={c.status} />
                              <small>
                                {c.evidence?.quality
                                  ? `Quality proxy ${c.evidence.quality.value.toFixed(3)}`
                                  : "No quality score"}
                              </small>
                            </button>
                          ))}
                      </div>
                    ))}
                  </div>
                  {!snapshot?.creatives.length && (
                    <div className="nl-empty">
                      No generated branches yet. The reasoner job must complete
                      first.
                    </div>
                  )}
                </section>
              ) : view === "Creative Lab" ? (
                <section className="nl-two-col">
                  <div className="nl-panel">
                    <h2>Candidate inspection</h2>
                    <select
                      aria-label="Candidate"
                      value={selected?.id || ""}
                      onChange={(e) => setSelectedId(e.target.value)}
                    >
                      {snapshot?.creatives.map((c) => (
                        <option key={c.id} value={c.id}>
                          {short(c.id)} · {c.status} · round {c.round + 1}
                        </option>
                      ))}
                    </select>
                    {selected ? (
                      <>
                        <Media
                          creative={selected}
                          kind={detail?.campaign.spec.media_kind}
                        />
                        <Status value={selected.status} />
                        <p>{selected.rejection_reason}</p>
                        <h3>Generation prompt</h3>
                        <p className="nl-prompt">{selected.plan.prompt}</p>
                        <h3>Evidence-backed edit intent</h3>
                        <JsonView value={selected.plan.edit_intent} />
                        <h3>Your feedback</h3>
                        <textarea
                          aria-label="Creative feedback"
                          value={feedback}
                          onChange={(e) => setFeedback(e.target.value)}
                          placeholder="Describe what should improve or remain unchanged…"
                        />
                        <div className="nl-controls">
                          <button
                            className="nl-button"
                            onClick={() => void submitFeedback("like")}
                          >
                            Like
                          </button>
                          <button
                            className="nl-button"
                            onClick={() => void submitFeedback("dislike")}
                          >
                            Dislike
                          </button>
                          <button
                            className="nl-button"
                            onClick={() => void submitFeedback("prefer")}
                          >
                            Prefer
                          </button>
                          <button
                            className="nl-button"
                            onClick={() => void submitFeedback("annotation")}
                          >
                            Save note
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="nl-empty">
                        No candidate to inspect yet.
                      </div>
                    )}
                  </div>
                  <div className="nl-panel">
                    <h2>Evidence, not an unexplained score</h2>
                    {selected?.evidence ? (
                      <>
                        <p>
                          Deployment eligibility:{" "}
                          <strong>
                            {selected.evidence.eligible
                              ? "Evidence checks passed"
                              : "Not established"}
                          </strong>
                        </p>
                        {selected.evidence.hard_constraints.map((c) => (
                          <div className="nl-check" key={c.name}>
                            <span title={c.evidence}>{c.name}</span>
                            <Status value={c.status} />
                          </div>
                        ))}
                        {selected.evidence.evaluations.map((e) => (
                          <details key={e.id} className="nl-evaluator">
                            <summary>
                              {e.evaluator.toUpperCase()} ·{" "}
                              {String(e.result.status)}
                            </summary>
                            <JsonView value={e.result} />
                          </details>
                        ))}
                      </>
                    ) : (
                      <div className="nl-empty">
                        No evaluator result. Missing values are not scores of
                        zero.
                      </div>
                    )}
                    <h3>Side-by-side comparison</h3>
                    <select
                      aria-label="Compare candidate"
                      value={comparisonId}
                      onChange={(e) => setComparisonId(e.target.value)}
                    >
                      <option value="">Choose another candidate</option>
                      {snapshot?.creatives
                        .filter((c) => c.id !== selected?.id)
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {short(c.id)} · {c.status}
                          </option>
                        ))}
                    </select>
                    {comparison && (
                      <Media
                        creative={comparison}
                        kind={detail?.campaign.spec.media_kind}
                      />
                    )}
                    <p className="nl-note">
                      Stochastic regenerations are variant-level comparisons,
                      not isolated causal interventions.
                    </p>
                  </div>
                </section>
              ) : (
                <section className="nl-two-col">
                  <div>
                    <section className="nl-panel">
                      <h2>
                        {activeJob
                          ? `Running: ${activeJob.kind.toLowerCase()}`
                          : "Current creative"}
                      </h2>
                      <p>
                        {activeJob
                          ? `Notebook capability: ${activeJob.capability}`
                          : selected?.output_asset_id
                            ? "Generated output. Evaluation and revision results appear below as they finish."
                            : "Generated media will appear here as soon as the model saves its output."}
                      </p>
                      {selected ? (
                        <>
                          <Media
                            creative={selected}
                            kind={detail?.campaign.spec.media_kind}
                          />
                          {selected.output_asset_id && <div className="nl-check">
                            <span>{String(outputProvenance?.model || "Recorded model output")} · Round {selected.round + 1}</span>
                            <Status value={selected.status} />
                            <a href={`/api/v2/assets/${selected.output_asset_id}/content`} target="_blank" rel="noreferrer">Open original <ArrowUpRight size={13} /></a>
                          </div>}
                          {selected.rejection_reason && <p role="alert">This candidate needs correction: {selected.rejection_reason}</p>}
                          <button
                            className="nl-button"
                            onClick={() => selectCreative(selected.id)}
                          >
                            Inspect creative <ArrowUpRight size={15} />
                          </button>
                        </>
                      ) : (
                        <div className="nl-empty">
                          <BrainCircuit size={34} />
                          <h3>{current?.stop_reason ? "No creative was generated in this run." : activeJob ? "The loop is running." : caps?.workers.some((w) => w.online) ? "Waiting for the next model job." : "The loop is waiting for compute."}</h3>
                          <p>
                            {current?.stop_reason
                              ? "This run stopped before producing media. The recorded reason and job history explain what needs attention."
                              : activeJob
                              ? "The current model job is processing. Its output will appear here when it completes."
                              : caps?.workers.some((w) => w.online)
                                ? "The notebook is connected. Check the live trajectory and job state below for progress or missing model capabilities."
                                : "Open NeuroLab, register your models, and start the worker."}
                          </p>
                        </div>
                      )}
                      {!!snapshot?.jobs.filter(j => j.kind === "PLAN" && j.status === "SUCCEEDED").at(-1)?.result?.summary && <details className="nl-evaluator"><summary>Agent’s recorded plan</summary><p>{String(snapshot.jobs.filter(j => j.kind === "PLAN" && j.status === "SUCCEEDED").at(-1)!.result!.summary)}</p></details>}
                    </section>
                    <section className="nl-panel">
                      <h2>Latest decision</h2>
                      {agentSummary && <div><h3>Agent’s final response</h3>{summaryProvider?.model ? <p className="nl-note">{String(summaryProvider.model)} · Based on this run’s recorded evidence</p> : null}<p>{String(agentSummary.summary || "")}</p>{Array.isArray(agentSummary.next_steps) && <><h3>Next steps</h3><ul>{agentSummary.next_steps.map((step, index) => <li key={index}>{String(step)}</li>)}</ul></>}</div>}
                      {latestDecision ? (
                        <>
                          <div className="nl-check"><span>Applied decision</span><Status value={latestDecision.applied_action} /></div>
                          <p>Model recommendation: {String(latestDecision.result.decision || "Not recorded").replaceAll("_", " ").toLowerCase()}{typeof latestDecision.result.confidence === "number" ? ` · confidence ${latestDecision.result.confidence.toFixed(2)}` : ""}.</p>
                          {latestDecision.override_reason && <p role="status">{latestDecision.override_reason}</p>}
                          <details className="nl-evaluator"><summary>Inspect full decision receipt</summary><JsonView value={latestDecision} /></details>
                        </>
                      ) : (
                        <p>
                          The TypeSafe decision will appear after sufficient
                          comparable evidence is available.
                        </p>
                      )}
                    </section>
                  </div>
                  <div>
                    <LiveLogPanel title="Live trajectory" count={snapshot?.events.length ?? 0} updatedAt={runSyncedAt}>
                      <div className="nl-timeline">
                        {snapshot?.events
                          .slice()
                          .reverse()
                          .map((e) => (
                            <article key={e.id}>
                              <time>
                                {new Date(
                                  e.created_at * 1000,
                                ).toLocaleTimeString()}
                              </time>
                              <strong>{e.kind.replaceAll("_", " ")}</strong>
                              <p>
                                {String(
                                  e.detail.summary ||
                                    e.detail.reason ||
                                    e.detail.detail ||
                                    e.detail.job_type ||
                                    e.detail.action ||
                                    "",
                                )}
                              </p>
                              <details>
                                <summary>Inspect event</summary>
                                <JsonView value={e.detail} />
                              </details>
                            </article>
                          ))}
                      </div>
                    </LiveLogPanel>
                    <LiveLogPanel title="Weave traces" count={snapshot?.traces.length ?? 0} updatedAt={runSyncedAt}>
                      {snapshot?.traces.slice().reverse().map((t) => (
                        <details key={t.id}>
                        <summary className="nl-trace">
                          <span>
                            <ChevronRight size={13} aria-hidden="true" />{" "}
                            {t.parent_id ? "↳ " : ""}
                            {t.name}
                          </span>
                          <Status value={t.status} />
                        </summary>
                          {t.url ? (
                            <a href={t.url} target="_blank" rel="noreferrer">
                              Open <ArrowUpRight size={13} />
                            </a>
                          ) : <p className="nl-note">Waiting for verified upload.</p>}
                          <JsonView value={t} />
                        </details>
                      ))}
                      <p className="nl-note">
                        Links appear only after remote readback confirms the
                        trace. Pending local records are not proof of upload.
                      </p>
                    </LiveLogPanel>
                  </div>
                </section>
              )}
              <section className="nl-panel">
                <button
                  className="nl-text-button"
                  onClick={() => setShowRaw(!showRaw)}
                >
                  {showRaw ? "Hide" : "Inspect"} durable job state{" "}
                  <ChevronRight size={14} />
                </button>
                {showRaw && <JsonView value={snapshot?.jobs} />}
              </section>
            </>
          )}
        </>
      )}
      <footer className="nl-footer">
        <span>NeuroLoop — every iteration leaves evidence.</span>
        <span>
          Predictions are proxies. Human approval is mandatory for advertising
          deployment.
        </span>
      </footer>
    </LoopShell>
  );
}
