"use client";
import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Brain,
  BookOpen,
  ChartNoAxesCombined,
  FlaskConical,
  FolderOpen,
  GitBranch,
  GitCompareArrows,
  Images,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Plug,
  Plus,
  RefreshCw,
  Settings,
  Sun,
} from "lucide-react";
import { Brand, ProfileAvatar } from "./UI";
import { NeuroMark } from "./Neuro";
import styles from "./WorkspaceNavigation.module.css";

export const navigation = [
  { view: "Overview", id: "overview", icon: LayoutDashboard },
  { view: "Projects", id: "projects", icon: FolderOpen },
  { view: "Library", id: "library", icon: Images },
  { view: "Compare", id: "compare", icon: GitCompareArrows },
  { view: "Command Center", id: "runs", icon: FlaskConical },
  { view: "Brain Lab", id: "brain", icon: Brain },
  { view: "Logs & Charts", id: "telemetry", icon: ChartNoAxesCombined },
  { view: "Publish Ads", id: "publish", icon: ArrowUpRight },
  { view: "Lineage", id: "lineage", icon: GitBranch },
  { view: "Neuro AI", id: "neuro", icon: NeuroMark },
  { view: "Learning", id: "research", icon: ChartNoAxesCombined },
  { view: "Experiments", id: "advertising", icon: ArrowUpRight },
  { view: "How to use", id: "docs", icon: BookOpen },
  { view: "Settings", id: "settings", icon: Plug },
] as const;

const hubs = [
  { id: "neuro", label: "Create", views: ["neuro"] },
  { id: "overview", label: "Campaigns", views: ["overview", "projects", "library", "runs", "compare", "lineage", "advertising"] },
  { id: "brain", label: "Brain & emotion", views: ["brain", "research"] },
  { id: "telemetry", label: "Logs & charts", views: ["telemetry"] },
  { id: "publish", label: "Publish Ads", views: ["publish"] },
];

function navigationLabel(name: string) {
  return name === "Command Center" ? "Runs"
    : name === "Experiments" ? "Advertising"
    : name === "Brain Lab" ? "Brain & emotion"
    : name === "Overview" || name === "Projects" ? "Campaign overview"
    : name === "Library" ? "Media library"
    : name === "Settings" ? "Connections & settings" : name;
}

export default function LoopShell({
  view,
  navigate,
  create,
  refresh,
  logout,
  online,
  active,
  children,
}: {
  view: string;
  navigate: (view: string) => void;
  create: () => void;
  refresh: () => void;
  logout: () => void;
  online: boolean;
  active: number;
  children: ReactNode;
}) {
  const [dark, setDark] = useState(false),
    [mobile, setMobile] = useState(false);
  const currentId = navigation.find((item) => item.view === view)?.id;
  const currentHub = hubs.find((hub) => currentId && hub.views.includes(currentId));
  useEffect(() => {
    try {
      setDark(localStorage.getItem("neuroloop-theme") === "dark");
    } catch {}
  }, []);
  function toggleTheme() {
    setDark((value) => {
      try {
        localStorage.setItem("neuroloop-theme", value ? "light" : "dark");
      } catch {}
      return !value;
    });
  }
  function navigationLink({ view: name, icon: Icon, id }: (typeof navigation)[number], label = navigationLabel(name), selected = view === name) {
    return (
      <a
        href={`/workspace?view=${id}`}
        key={id}
        className={`nav-item ${selected ? "active" : ""}`}
        aria-current={selected ? "page" : undefined}
        onClick={(event) => {
          if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          navigate(name);
          setMobile(false);
        }}
      >
        <Icon size={16} />
        {label}
      </a>
    );
  }
  return (
    <div className="app-shell nl-shell" data-theme={dark ? "dark" : "light"}>
      {mobile && (
        <button
          className="sidebar-scrim"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        />
      )}
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <Brand />
        <button className="sidebar-create" onClick={create}>
          <Plus size={16} />
          New campaign
          <ArrowUpRight size={14} />
        </button>
        <div className="nav-section">WORKSPACE</div>
        <nav className="side-nav" aria-label="Workspace navigation">
          {hubs.map((hub) => navigationLink(
            navigation.find((item) => item.id === hub.id)!,
            hub.label,
            currentHub === hub,
          ))}
        </nav>
        <div className="sidebar-bottom">
          <nav aria-label="Workspace settings">
            {navigationLink(navigation.find((item) => item.id === "docs")!)}
            {navigationLink(navigation.find((item) => item.id === "settings")!)}
          </nav>
          <button
            className="theme-toggle"
            aria-pressed={dark}
            onClick={toggleTheme}
          >
            {dark ? <Sun size={17} /> : <Moon size={17} />}{" "}
            {dark ? "Light" : "Dark"} appearance
          </button>
          <button
            className="sidebar-profile"
            onClick={() => navigate("Settings")}
          >
            <span className="avatar">
              <ProfileAvatar />
            </span>
            <span>
              My workspace
              <small>
                {online ? "Notebook connected" : "Notebook offline"}
              </small>
            </span>
            <Settings size={16} />
          </button>
        </div>
      </aside>
      <header className="topbar">
        <button
          className="icon-button mobile-menu"
          aria-label="Open navigation"
          onClick={() => setMobile(true)}
        >
          <Menu size={19} />
        </button>
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>{navigationLabel(view)}</strong>
        </div>
        <div className="topbar-right">
          <span className="connection-state">
            {active
              ? `${active} active jobs`
              : online
                ? "Ready for a run"
                : "Waiting for notebook"}
          </span>
          <button
            className="icon-button"
            aria-label="Refresh workspace"
            onClick={refresh}
          >
            <RefreshCw size={15} />
          </button>
          <button
            className="icon-button"
            aria-label="Sign out"
            onClick={logout}
          >
            <LogOut size={15} />
          </button>
        </div>
      </header>
      <main className="main nl-content">
        {currentHub && currentHub.views.length > 1 && (
          <nav className={styles.context} aria-label={`${currentHub.label} pages`}>
            {currentHub.views.filter((id) => id !== "projects").map((id) => {
              const item = navigation.find((entry) => entry.id === id)!;
              return navigationLink(item, navigationLabel(item.view), currentId === id || (id === "overview" && currentId === "projects"));
            })}
          </nav>
        )}
        {children}
      </main>
    </div>
  );
}
