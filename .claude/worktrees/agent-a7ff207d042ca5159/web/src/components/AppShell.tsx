import { ClipboardList, FileText, GitCommitHorizontal, Monitor, Moon, Network, Route, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useProjects, useSnapshots } from "../api/queries";
import { shortHash } from "../lib/status";
import { useTheme, type ThemeChoice } from "../lib/theme";
import { useSnapshotParam } from "../lib/useSnapshotParam";

const NAV = [
  { to: "/claims", label: "Claims", icon: ClipboardList },
  { to: "/changes", label: "Changes", icon: GitCommitHorizontal },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/planner", label: "Planner", icon: Route },
  { to: "/reports", label: "Reports", icon: FileText },
] as const;

const THEMES: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "system", label: "System", icon: Monitor },
  { value: "dark", label: "Dark", icon: Moon },
];

export const DISCLAIMER =
  "ReVal reports the state of recorded evidence against declared requirements. It does not certify safety.";

function Brand() {
  return (
    <div className="brand">
      <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="5" />
        <path d="M8 22V10h6.2a3.8 3.8 0 0 1 0 7.6H8m6.4 0L19 22m2.5-12 2.5 12 2.5-12" />
      </svg>
      <span className="brand-name">ReVal</span>
    </div>
  );
}

function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme">
      {THEMES.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          className={theme === value ? "is-on" : ""}
          onClick={() => setTheme(value)}
          title={`${label} theme`}
        >
          <Icon size={14} strokeWidth={1.75} aria-hidden="true" />
          <span className="sr-only">{label}</span>
        </button>
      ))}
    </div>
  );
}

function SnapshotPicker() {
  const snaps = useSnapshots();
  const [selected, setSelected] = useSnapshotParam();
  const rows = snaps.data ?? [];
  const current = selected ?? rows[0]?.id;
  return (
    <label className="snap-picker">
      <span className="snap-picker-label">Snapshot</span>
      <select
        value={current ?? ""}
        disabled={rows.length === 0}
        onChange={(e) => setSelected(e.target.value === rows[0]?.id ? undefined : e.target.value)}
      >
        {rows.length === 0 && <option value="">{snaps.isLoading ? "Loading…" : "None stored"}</option>}
        {rows.map((s, i) => (
          <option key={s.id} value={s.id}>
            {shortHash(s.id)} · {s.git_rev ? shortHash(s.git_rev, 7) : "working tree"}
            {i === 0 ? " (latest)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const projects = useProjects();
  const project = projects.data?.[0];
  const loc = useLocation();
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="rail">
        <Brand />
        <nav aria-label="Workspace">
          <ul role="list">
            {NAV.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink to={{ pathname: to, search: loc.search }} className={({ isActive }) => (isActive ? "nav-item is-active" : "nav-item")}>
                  <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="rail-foot">
          <ThemeSwitch />
          <p className="rail-disclaimer">{DISCLAIMER}</p>
        </div>
      </aside>
      <div className="stage">
        <header className="topbar">
          <div className="topbar-project">
            <span className="topbar-project-name">{project?.name ?? (projects.isError ? "Project unavailable" : " ")}</span>
            {project && <span className="topbar-project-meta">{project.claims} claims declared</span>}
          </div>
          <SnapshotPicker />
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <footer className="stage-foot">{DISCLAIMER}</footer>
      </div>
    </div>
  );
}
