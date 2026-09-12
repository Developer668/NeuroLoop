"use client";
import { ProfileAvatar } from "./UI";
import Neuro, { NeuroMark } from "./Neuro";
import { PixelLoading } from "./ReleaseMotion";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  Images,
  GitCompareArrows,
  FlaskConical,
  Brain,
  ChartNoAxesCombined,
  Plug,
  Settings,
  Menu,
  X,
  Plus,
  ArrowUpRight,
  ArrowRight,
  RefreshCw,
  LogOut,
  Upload,
  FileText,
  ShieldCheck,
  Clock,
  Layers,
  Edit3,
  Play,
  Download,
  AlertCircle,
  Sun,
  Moon,
} from "lucide-react";
import {
  api,
  ApiError,
  Dashboard,
  Asset,
  Project,
  Run,
  size,
  seconds,
  score,
} from "@/lib/types";
import {
  Brand,
  Panel,
  Badge,
  Empty,
  AssetVisual,
  Modal,
  AnimatedNumber,
  errorText,
  dateText,
} from "./UI";
import { Activity } from "./Activity";
import {
  ConnectGate,
  UploadBox,
  ProjectDialog,
  ComposeDialog,
} from "./ProjectForms";
import RunForm from "./RunForm";
import RunDetail from "./RunDetail";
import BrainView from "./BrainView";
import dynamic from "next/dynamic";
const BrainCanvas = dynamic(() => import("./BrainCanvas"), { ssr: false });
import {
  CompareView,
  ConnectionsView,
  ResearchView,
  SettingsView,
} from "./ResearchViews";

const NAV = [
  { id: "overview", name: "Overview", icon: LayoutDashboard },
  { id: "projects", name: "Projects", icon: FolderOpen },
  { id: "library", name: "Library", icon: Images },
  { id: "compare", name: "Compare", icon: GitCompareArrows },
  { id: "runs", name: "Experiments", icon: FlaskConical },
  { id: "brain", name: "Brain lab", icon: Brain },
  { id: "research", name: "Logs & analytics", icon: ChartNoAxesCombined },
  { id: "neuro", name: "Neuro AI", icon: NeuroMark },
  { id: "connections", name: "MCP connections", icon: Plug },
  { id: "settings", name: "Settings", icon: Settings },
];
const HEADINGS: Record<string, [string, string, string]> = {
  upload: ["Workspace / upload", "Add a creative", "One source at a time. Preview it before creating an experiment."],
  neuro: ["Workspace / Neuro AI", "Neuro AI", "Your evidence, within reach."],
  overview: [
    "Workspace / overview",
    "Workspace overview",
    "Your creatives, experiments, and the evidence behind every decision.",
  ],
  projects: [
    "Workspace / projects",
    "Projects",
    "Keep each brief, original, reference set, and experiment together.",
  ],
  library: [
    "Workspace / creative library",
    "Your creative library",
    "Your original files stay unchanged. Every transformation becomes a new, traceable asset.",
  ],
  compare: [
    "Evidence / comparisons",
    "Compare responses",
    "Inspect numerical reference agreement between saved cortical responses.",
  ],
  runs: [
    "Evidence / experiments",
    "Experiments",
    "Follow the real hypotheses, controlled edits, rejections, and stopping reasons.",
  ],
  research: [
    "Research / experiment policy",
    "Logs & analytics",
    "Explore what changed, what failed, and whether experience is helping the search.",
  ],
  connections: [
    "Workspace / connections",
    "Connect your tools",
    "The same experiment engine, accessible through an authenticated MCP endpoint.",
  ],
  settings: [
    "Workspace / settings",
    "Workspace settings",
    "Model provenance, capability limits, and the actual state of each integration.",
  ],
};

type DialogState =
  | { kind: "project"; project?: Project; assetId?: string }
  | { kind: "compose"; asset: Asset }
  | { kind: "run"; project: Project }
  | { kind: "asset"; asset: Asset }
  | { kind: "transcript"; asset: Asset }
  | null;
export default function Workspace() {
  const router = useRouter(),
    search = useSearchParams();
  const view = search.get("view") || "overview",
    runId = search.get("run") || "",
    evaluationId = search.get("evaluation") || "";
  const [dark, setDark] = useState(false);
  useEffect(() => {
    try { setDark(localStorage.getItem("neuroloop-theme") === "dark"); } catch {}
  }, []);
  function toggleTheme() {
    setDark(current => {
      try { localStorage.setItem("neuroloop-theme", current ? "light" : "dark"); } catch {}
      return !current;
    });
  }
  const [preferences, setPreferences] = useState({
    workspace_name: "My workspace",
    display_name: "NeuroLoop",
    reduced_motion: false,
  });
  useEffect(() => {
    let alive = true;
    const update = (event: Event) =>
      setPreferences((event as CustomEvent).detail);
    window.addEventListener("neuroloop-preferences", update);
    api<typeof preferences>("preferences")
      .then((p) => {
        if (alive) {
          setPreferences(p);
          document.documentElement.dataset.motion = p.reduced_motion
            ? "reduced"
            : "full";
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
      window.removeEventListener("neuroloop-preferences", update);
    };
  }, []);
  const [data, setData] = useState<Dashboard | null>(null),
    [auth, setAuth] = useState<"checking" | "needed" | "ready">("checking"),
    [error, setError] = useState(""),
    [dialog, setDialog] = useState<DialogState>(null),
    [mobile, setMobile] = useState(false),
    [refreshing, setRefreshing] = useState(false),
    [filter, setFilter] = useState("all"),
    [assetQuery, setAssetQuery] = useState("");
  const load = useCallback(async () => {
    try {
      const [result, prefs] = await Promise.all([
        api<Dashboard>("dashboard"),
        api<typeof preferences>("preferences"),
      ]);
      setPreferences(prefs);
      document.documentElement.dataset.motion = prefs.reduced_motion
        ? "reduced"
        : "full";
      setData(result);
      setAuth("ready");
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAuth("needed");
        setData(null);
      } else {
        setError(errorText(e));
        setAuth((prev) => (prev === "checking" ? "needed" : prev));
      }
    }
  }, []);
  const reload = useCallback(() => {
    void load();
  }, [load]);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 8000);
    return () => clearInterval(timer);
  }, [load]);
  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }
  function go(next: string, extra = "") {
    setMobile(false);
    router.push("/workspace?view=" + next + extra);
  }
  function openRun(run: Run) {
    setDialog(null);
    reload();
    go("runs", "&run=" + encodeURIComponent(run.id));
  }
  function openBrain(id: string) {
    go("brain", "&evaluation=" + encodeURIComponent(id));
  }
  async function logout() {
    const response = await fetch("/api/auth", { method: "DELETE" });
    if (!response.ok) {
      setError(
        "Could not revoke this session. Check the backend and retry sign out.",
      );
      return;
    }
    setAuth("needed");
    setData(null);
  }
  const assetName = (id?: string | null) =>
    data?.assets.find((a) => a.id === id)?.name || "No original selected";
  if (auth === "checking")
    return (
      <div className="page-loading">
        <PixelLoading label="Opening NeuroLoop" />
      </div>
    );
  if (auth === "needed" || !data) return <ConnectGate onConnected={reload} />;
  const nav = (view === "upload" ? {name: "Upload"} : NAV.find((n) => n.id === view)) || NAV[0],
    heading = HEADINGS[view] || HEADINGS.overview;
  const activeRuns = data.runs.filter((r) =>
    ["queued", "running"].includes(r.status),
  );
  const latestEvaluation = data.evaluations[0];
  const newProject = () => setDialog({ kind: "project" });
  const cards = data.assets.filter(
    (a) =>
      (filter === "all" || a.kind === filter) &&
      a.name.toLowerCase().includes(assetQuery.toLowerCase()),
  );
  const runTable = (runs: Run[]) =>
    runs.length ? (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Project / run</th>
              <th>Mode</th>
              <th>Evaluations</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.id}
                className="selectable"
                onClick={() => go("runs", "&run=" + r.id)}
              >
                <td>
                  <span className="cell-title">
                    {data.projects.find((p) => p.id === r.project_id)?.name ||
                      r.project_id.slice(0, 8)}
                  </span>
                  <span className="cell-sub">{r.stage}</span>
                </td>
                <td>{r.mode}</td>
                <td className="mono-cell">
                  {r.evaluations_used} / {r.max_evaluations}
                </td>
                <td>
                  <Badge value={r.status} />
                </td>
                <td className="nowrap">{dateText(r.created_at)}</td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={"Open run " + r.id.slice(0, 8)}
                    onClick={(e) => {
                      e.stopPropagation();
                      go("runs", "&run=" + r.id);
                    }}
                  >
                    <ArrowUpRight size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty
        title="An open page for evidence"
        text="Start an analysis or a controlled experiment from a project. Every run appears here, including failures."
        action={
          <button className="button" onClick={() => go("projects")}>
            Open projects
            <ArrowRight size={14} />
          </button>
        }
        icon={<FlaskConical size={22} />}
      />
    );
  return (
    <div className="app-shell" data-theme={dark ? "dark" : "light"}>
      {mobile && (
        <button
          className="sidebar-scrim"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        />
      )}
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <Brand />
        <Link href="/workspace?view=upload" className="sidebar-create">
          <Plus size={16} />
          Add a creative
          <ArrowUpRight size={14} />
        </Link>
        <div className="nav-section">WORKSPACE</div>
        <nav className="side-nav">
          {NAV.slice(0, 6).map((n) => (
            <Link
              href={"/workspace?view=" + n.id}
              key={n.id}
              onClick={() => setMobile(false)}
              className={"nav-item " + (view === n.id ? "active" : "")}
              aria-current={view === n.id ? "page" : undefined}
            >
              <n.icon size={16} />
              {n.name}
              {n.id === "runs" && activeRuns.length > 0 && (
                <span className="nav-end">{activeRuns.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="nav-section">TOOLS & CONNECTIONS</div>
        <nav className="side-nav">
          {NAV.slice(6).map((n) => (
            <Link
              href={"/workspace?view=" + n.id}
              key={n.id}
              onClick={() => setMobile(false)}
              className={"nav-item " + (view === n.id ? "active" : "")}
              aria-current={view === n.id ? "page" : undefined}
            >
              <n.icon size={16} />
              {n.name}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="theme-toggle" onClick={toggleTheme} aria-pressed={dark}>
            {dark ? <Sun size={17} /> : <Moon size={17} />} {dark ? "Light appearance" : "Dark appearance"}
          </button>
          {data.capabilities.execution?.paused && <Link className="hold-compact" href="/workspace?view=settings" title="GPU execution remains paused pending graphics-crash diagnosis."><AlertCircle size={14} /> Model execution paused ↗</Link>}
          <Link href="/workspace?view=settings" className="sidebar-profile">
            <span className="avatar">
              <ProfileAvatar />
            </span>
            <span>
              {preferences.workspace_name}
              <small>{preferences.display_name}</small>
            </span>
            <Settings size={16} />
          </Link>
        </div>
      </aside>
      <header className="topbar">
        <button
          className="icon-button mobile-menu"
          onClick={() => setMobile(true)}
          aria-label="Open navigation"
        >
          <Menu size={19} />
        </button>
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>{nav.name}</strong>
        </div>
        <div className="topbar-right">
          <span className="connection-state">
            {data.capabilities.execution?.paused
              ? "Evidence review · execution paused"
              : activeRuns.length
                ? "Analysis in progress"
                : "Workspace connected"}
          </span>
          <button
            className="icon-button"
            onClick={() => void refresh()}
            disabled={refreshing}
            aria-label="Refresh workspace"
          >
            <RefreshCw size={15} />
          </button>
          <button
            className="icon-button"
            onClick={() => void logout()}
            aria-label="Sign out"
          >
            <LogOut size={15} />
          </button>
          <button
            className="avatar"
            onClick={() => go("settings")}
            aria-label="Workspace settings"
          >
            <ProfileAvatar />
          </button>
        </div>
      </header>
      <main className="main">
        {!(view === "runs" && runId) &&
          view !== "brain" &&
          view !== "neuro" && (
            <div className="page-title" key={view}>
              <div>
                <span className="eyebrow">{heading[0]}</span>
                <h1>{heading[1]}</h1>
                <p>{heading[2]}</p>
              </div>
              <div className="button-row">
                {["overview", "projects", "library"].includes(view) && (
                  <>
                    <button className="button" onClick={() => go("upload")}>
                      <Upload size={14} />
                      Upload creative
                    </button>
                    <button className="button primary" onClick={newProject}>
                      <Plus size={14} />
                      New project
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        {error && (
          <div className="notice error" role="alert">
            <AlertCircle size={16} />
            {error}
            <button
              className="icon-button"
              onClick={() => setError("")}
              aria-label="Dismiss error"
            >
              <X size={14} />
            </button>
          </div>
        )}
        {view === "overview" && (
          <>
            <div className="stats">
              {[
                [
                  FolderOpen,
                  "Projects",
                  data.projects.length,
                  "Briefs with a fixed objective",
                ],
                [
                  Images,
                  "Creative assets",
                  data.counts.assets,
                  "Source files & derived versions",
                ],
                [
                  Brain,
                  "Neural evaluations",
                  data.counts.evaluations,
                  "Saved model-response records",
                ],
                [
                  GitCompareArrows,
                  "Experiments",
                  data.counts.experiments,
                  "Proposed and measured changes",
                ],
              ].map(([Icon, label, value, description], i) => {
                const Component = Icon as typeof FolderOpen;
                return (
                  <div className="stat" key={i}>
                    <div className="stat-label">
                      <Component size={13} />
                      {String(label)}
                    </div>
                    <strong>
                      {Number.isFinite(Number(value)) ? (
                        <AnimatedNumber value={Number(value)} />
                      ) : (
                        String(value)
                      )}
                    </strong>
                    <small>{String(description)}</small>
                  </div>
                );
              })}
            </div>
            <div className="overview-columns">
              <div className="stack">
                {!data.projects.length ? (
                  <section className="panel workspace-intro">
                    <div className="intro-copy">
                      <span className="eyebrow">Your first experiment</span>
                      <h2>Good creative deserves a closer look.</h2>
                      <p>
                        Start with something you made. Add a reference. Test the
                        smallest change that could matter.
                      </p>
                      <button className="button primary" onClick={newProject}>
                        Create a project
                        <ArrowRight size={14} />
                      </button>
                    </div>
                    <div className="intro-art" aria-hidden="true">
                      <span className="specimen">N</span>
                      <span className="plate-label">
                        NEUROLOOP / FIELD NOTES
                      </span>
                    </div>
                  </section>
                ) : (
                  <Panel
                    title="Recent projects"
                    action={
                      <button
                        className="link-text"
                        onClick={() => go("projects")}
                      >
                        All projects
                        <ArrowUpRight size={13} />
                      </button>
                    }
                  >
                    <div className="panel-body data-list">
                      {data.projects.slice(0, 4).map((p, i) => (
                        <div className="data-row" key={p.id}>
                          <span className="row-index">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <div className="row-copy">
                            <strong>{p.name}</strong>
                            <small>
                              {assetName(p.asset_id)} · {p.reference_ids.length}{" "}
                              references
                            </small>
                          </div>
                          <button
                            className="button small"
                            disabled={!p.asset_id}
                            onClick={() =>
                              setDialog({ kind: "run", project: p })
                            }
                          >
                            Run
                            <ArrowRight size={13} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}
                <div className="overview-shortcuts">
                  <button onClick={() => go("upload")}>
                    <Upload size={18} />
                    <span>
                      Bring a new creative
                      <small>Add video, audio, an image, or timed text.</small>
                    </span>
                    <ArrowUpRight size={16} />
                  </button>
                  <button onClick={() => go("compare")}>
                    <GitCompareArrows size={18} />
                    <span>
                      Compare recorded responses
                      <small>
                        Use saved evidence without another model call.
                      </small>
                    </span>
                    <ArrowUpRight size={16} />
                  </button>
                </div>
              </div>
              <Panel
                title="The cortical surface"
                action={
                  <button className="link-text" onClick={() => go("brain")}>
                    Open brain lab
                    <ArrowUpRight size={13} />
                  </button>
                }
                footer={
                  latestEvaluation
                    ? "Saved prediction · not a measured person’s brain."
                    : "Anatomy only. Activity appears after a real evaluation."
                }
              >
                <BrainCanvas evaluationId={latestEvaluation?.id} />
                <div
                  className="panel-body"
                  style={{ paddingTop: 15, paddingBottom: 15 }}
                >
                  <div className="data-row" style={{ padding: 0 }}>
                    <div className="row-copy">
                      <strong>
                        {latestEvaluation
                          ? "Latest cortical prediction"
                          : "Ready for a closer look"}
                      </strong>
                      <small>
                        {latestEvaluation
                          ? assetName(latestEvaluation.asset_id)
                          : "fsaverage5 · two hemispheres · 20,484 vertices"}
                      </small>
                    </div>
                    <Badge
                      value={latestEvaluation ? "recorded" : "anatomy_only"}
                    />
                  </div>
                </div>
              </Panel>
            </div>
            <Activity data={data} />
            <Panel
              title="Recent experiment runs"
              action={
                <button className="link-text" onClick={() => go("runs")}>
                  View all runs
                  <ArrowUpRight size={13} />
                </button>
              }
            >
              {runTable(data.runs.slice(0, 5))}
            </Panel>
          </>
        )}
        {view === "upload" && <div className="upload-page"><UploadBox onUploaded={() => { reload(); go("library"); }} /><Link className="text-link" href="/workspace?view=library">Back to library ↗</Link></div>}
        {view === "library" && (
          <div className="stack">

            <div className="button-row">
              <div className="pill-tabs">
                {["all", "video", "image", "audio", "text"].map((k) => (
                  <button
                    key={k}
                    className={filter === k ? "selected" : ""}
                    onClick={() => setFilter(k)}
                  >
                    {k.charAt(0).toUpperCase() + k.slice(1)}
                  </button>
                ))}
              </div>
              <span className="spacer" />
              <input
                className="region-search library-search"
                aria-label="Search creative library"
                placeholder="Search your creatives…"
                value={assetQuery}
                onChange={(e) => setAssetQuery(e.target.value)}
              />
              <small>{cards.length} assets</small>
            </div>
            {cards.length ? (
              <div className="asset-grid">
                {cards.map((a) => (
                  <article className="asset-card" key={a.id}>
                    <AssetVisual asset={a} />
                    <div className="asset-meta">
                      <strong title={a.name}>{a.name}</strong>
                      <div className="metadata">
                        <span>
                          {size(a.size)}
                          {a.details.duration
                            ? ` · ${a.details.duration.toFixed(1)}s`
                            : ""}
                        </span>
                        <span>
                          {new Date(a.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <div className="asset-actions">
                      <button
                        className="button small quiet"
                        onClick={() => setDialog({ kind: "asset", asset: a })}
                      >
                        Inspect
                        <ArrowUpRight size={12} />
                      </button>
                      {["image", "video"].includes(a.kind) && (
                        <button
                          className="button small quiet"
                          onClick={() =>
                            setDialog({ kind: "compose", asset: a })
                          }
                        >
                          Compose
                        </button>
                      )}
                      <span className="spacer" />
                      <button
                        className="icon-button"
                        onClick={() =>
                          setDialog({ kind: "project", assetId: a.id })
                        }
                        aria-label={"Create project with " + a.name}
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Panel title="Your creative library">
                <Empty
                  title="The work starts here."
                  text="Upload an original creative. It stays private on this deployment, and no model runs until you request one."
                />
              </Panel>
            )}
          </div>
        )}
        {view === "projects" &&
          (data.projects.length ? (
            <div className="project-grid">
              {data.projects.map((p) => {
                const original = data.assets.find((a) => a.id === p.asset_id);
                return (
                  <article className="project-card" key={p.id}>
                    <div className="project-strip">
                      {original?.details.preview ? (
                        <img
                          src={`/api/assets/${original.id}/preview`}
                          alt=""
                        />
                      ) : (
                        <span className="project-initial">
                          {p.name.charAt(0)}
                        </span>
                      )}
                      <span className="eyebrow">
                        {original?.kind || "BRIEF"} / PROJECT
                      </span>
                    </div>
                    <div className="project-content">
                      <h3>{p.name}</h3>
                      <p className="brief">
                        {p.brief ||
                          "A new creative question, ready to explore."}
                      </p>
                      <div className="project-meta">
                        <span>{p.reference_ids.length} references</span>
                        <span>
                          {
                            data.runs.filter((r) => r.project_id === p.id)
                              .length
                          }{" "}
                          runs
                        </span>
                        <span>
                          {new Date(p.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <div className="button-row">
                      <button
                        className="button small quiet"
                        onClick={() =>
                          setDialog({ kind: "project", project: p })
                        }
                      >
                        <Edit3 size={13} />
                        Edit brief
                      </button>
                      <span className="spacer" />
                      <button
                        className="button small primary"
                        disabled={!p.asset_id}
                        onClick={() => setDialog({ kind: "run", project: p })}
                      >
                        Start run
                        <Play size={12} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <Panel title="Projects">
              <Empty
                title="A question, a reference, an experiment."
                text="Create a project to keep the original creative, your brief, and reference assets in one place."
                action={
                  <button className="button primary" onClick={newProject}>
                    <Plus size={14} />
                    Create project
                  </button>
                }
                icon={<FolderOpen size={23} />}
              />
            </Panel>
          ))}
        {view === "runs" &&
          (runId ? (
            <RunDetail
              id={runId}
              assets={data.assets}
              projects={data.projects}
              onBack={() => go("runs")}
              onBrain={openBrain}
              onUpdate={reload}
            />
          ) : (
            <Panel
              title="Experiment ledger"
              description="All statuses are preserved. Failed and cancelled runs remain inspectable."
            >
              {runTable(data.runs)}
            </Panel>
          ))}
        {view === "brain" && (
          <BrainView
            evaluations={data.evaluations}
            assets={data.assets}
            selected={evaluationId}
            onSelect={openBrain}
          />
        )}
        {view === "compare" && <CompareView data={data} />}
        {view === "connections" && <ConnectionsView />}
        {view === "research" && <ResearchView data={data} />}
        {view === "settings" && <SettingsView data={data} />}
        {view === "neuro" && <Neuro />}
      </main>
      {dialog?.kind === "project" && (
        <ProjectDialog
          assets={data.assets}
          project={dialog.project}
          initialAsset={dialog.assetId}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            reload();
            go("projects");
          }}
        />
      )}
      {dialog?.kind === "compose" && (
        <ComposeDialog
          asset={dialog.asset}
          onClose={() => setDialog(null)}
          onSaved={(a) => {
            reload();
            setDialog({ kind: "project", assetId: a.id });
          }}
        />
      )}
      {dialog?.kind === "run" && (
        <RunForm
          project={dialog.project}
          assets={data.assets}
          capabilities={data.capabilities}
          onClose={() => setDialog(null)}
          onCreated={openRun}
        />
      )}
      {dialog?.kind === "asset" && (
        <Modal title="Creative record" onClose={() => setDialog(null)}>
          <div className="dialog-content">
            <AssetVisual asset={dialog.asset} play />
            <h3
              className="section-space"
              style={{ fontFamily: "var(--font)", fontSize: 24 }}
            >
              {dialog.asset.name}
            </h3>
            <dl className="metrics-list">
              <div>
                <dt>Media</dt>
                <dd>{dialog.asset.kind}</dd>
              </div>
              <div>
                <dt>Size</dt>
                <dd>{size(dialog.asset.size)}</dd>
              </div>
              <div>
                <dt>Dimensions</dt>
                <dd>
                  {dialog.asset.details.width
                    ? `${dialog.asset.details.width} × ${dialog.asset.details.height}`
                    : "Not applicable"}
                </dd>
              </div>
              <div>
                <dt>SHA-256</dt>
                <dd className="mono">{dialog.asset.sha256}</dd>
              </div>
              <div>
                <dt>Saved</dt>
                <dd>{dateText(dialog.asset.created_at)}</dd>
              </div>
            </dl>
            <div className="button-row section-space">
              <a
                className="button"
                href={`/api/assets/${dialog.asset.id}/content?download=true`}
              >
                <Download size={13} />
                Original file
              </a>
              {(dialog.asset.details.has_audio ||
                dialog.asset.kind === "text") && (
                <button
                  className="button"
                  onClick={() =>
                    setDialog({ kind: "transcript", asset: dialog.asset })
                  }
                >
                  <FileText size={13} />
                  Timed transcript
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}
      {dialog?.kind === "transcript" && (
        <TranscriptDialog
          asset={dialog.asset}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
function TranscriptDialog({
  asset,
  onClose,
  onSaved,
}: {
  asset: Asset;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const words = JSON.parse(text);
      if (!Array.isArray(words))
        throw new Error("Expected an array of timed words");
      await api("assets/" + asset.id + "/transcript", {
        method: "PUT",
        body: JSON.stringify({ words }),
      });
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Attach timed words" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="modal-subtitle">
          {asset.name}. Supply word timings in seconds for the actual media.
          This metadata does not modify the source file.
        </p>
        {error && <div className="notice error">{error}</div>}
        <label className="field">
          <span>Timed transcript JSON</span>
          <textarea
            required
            rows={8}
            className="mono"
            placeholder={'[{"text":"Introducing","start":0.2,"end":0.8}]'}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <div className="dialog-footer">
          <button className="button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save transcript"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
