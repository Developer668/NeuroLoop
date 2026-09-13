"use client";
import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Brain,
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

export const navigation = [
  { view: "Overview", id: "overview", icon: LayoutDashboard },
  { view: "Projects", id: "projects", icon: FolderOpen },
  { view: "Library", id: "library", icon: Images },
  { view: "Compare", id: "compare", icon: GitCompareArrows },
  { view: "Command Center", id: "runs", icon: FlaskConical },
  { view: "Brain Lab", id: "brain", icon: Brain },
  { view: "Lineage", id: "lineage", icon: GitBranch },
  { view: "Neuro AI", id: "neuro", icon: NeuroMark },
  { view: "Learning", id: "research", icon: ChartNoAxesCombined },
  { view: "Experiments", id: "advertising", icon: ArrowUpRight },
  { view: "Settings", id: "settings", icon: Plug },
] as const;

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
          {navigation.map(({ view: name, icon: Icon, id }) => (
            <a
              href={`/workspace?view=${id}`}
              key={id}
              className={`nav-item ${view === name ? "active" : ""}`}
              aria-current={view === name ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                navigate(name);
                setMobile(false);
              }}
            >
              <Icon size={16} />
              {name === "Command Center"
                ? "Experiments"
                : name === "Experiments"
                  ? "Advertising"
                  : name === "Settings"
                    ? "Connections & settings"
                    : name}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
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
          <strong>{view}</strong>
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
      <main className="main nl-content">{children}</main>
    </div>
  );
}
