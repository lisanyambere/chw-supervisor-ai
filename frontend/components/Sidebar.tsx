"use client";

import {
  AlertTriangle,
  BarChart3,
  ExternalLink,
  FileText,
  Search,
  Table2,
  Users,
} from "lucide-react";
import { cn } from "@/lib/cn";

type NavId = "brief" | "alert" | "team" | "patient" | "chart";

const NAV: { id: NavId; label: string; icon: React.ReactNode; tone?: "alert" }[] = [
  { id: "brief",   label: "Monday briefing", icon: <FileText size={14} /> },
  { id: "alert",   label: "Anomalies",       icon: <AlertTriangle size={14} />, tone: "alert" },
  { id: "team",    label: "CHW roster",      icon: <Users size={14} /> },
  { id: "patient", label: "Patient lookup",  icon: <Search size={14} /> },
  { id: "chart",   label: "Activity charts", icon: <BarChart3 size={14} /> },
];

// Local services from infra/docker-compose*.yml. Langfuse is Langfuse Cloud;
// its project link comes from the backend's /readyz.
const LOCAL_OBS = [
  { label: "grafana",    href: "http://localhost:3200" },
  { label: "openmrs",    href: "http://localhost:8081/openmrs/spa" },
  { label: "prometheus", href: "http://localhost:9090" },
];

export function Sidebar({
  active,
  onSelect,
  langfuseUrl,
  badges,
}: {
  active: NavId;
  onSelect: (id: NavId) => void;
  langfuseUrl: string | null;
  /** Counts shown beside nav items; absent until known. */
  badges: Partial<Record<NavId, number>>;
}) {
  const obs = langfuseUrl
    ? [{ label: "langfuse", href: langfuseUrl }, ...LOCAL_OBS]
    : LOCAL_OBS;
  return (
    <aside className="sidebar flex flex-col">
      {/* Brand block */}
      <div className="brand-block px-5 pt-6 pb-7 flex items-center gap-3">
        <div className="brand-mark" aria-hidden="true">
          <span>+</span>
        </div>
        <div className="leading-tight">
          <div className="brand-name">Field Briefing</div>
          <div className="brand-place">Kakamega County · 0.3</div>
        </div>
      </div>

      {/* Workspace nav */}
      <div className="sidebar-nav px-3">
        <div className="sidebar-label px-2 mb-2">
          Field desk
        </div>
        <nav className="flex flex-col gap-0.5">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => onSelect(n.id)}
              aria-label={n.label}
              aria-current={active === n.id ? "page" : undefined}
              className={cn("nav-item", active === n.id && "nav-item--active")}
            >
              <span className="nav-icon">{n.icon}</span>
              <span>{n.label}</span>
              {badges[n.id] !== undefined && (
                <span className={cn("nav-badge", n.tone === "alert" && "nav-badge--alert")}>
                  {badges[n.id]}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Observability */}
      <div className="sidebar-systems px-3 mt-6">
        <div className="sidebar-label px-2 mb-2">
          Systems
        </div>
        <nav className="flex flex-col gap-0.5">
          {obs.map((o) => (
            <a
              key={o.label}
              href={o.href}
              target="_blank"
              rel="noreferrer"
              className="nav-item nav-item--external font-mono text-[11px]"
            >
              <span>{o.label}</span>
              <ExternalLink size={11} className="ml-auto" />
            </a>
          ))}
        </nav>
      </div>

      {/* User block */}
      <div className="user-block mt-auto px-4 py-4 flex items-center gap-2.5">
        <div className="user-avatar">
          MK
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold">Margaret Kimani</div>
          <div className="user-role">County supervisor</div>
        </div>
      </div>
    </aside>
  );
}

export type { NavId };
