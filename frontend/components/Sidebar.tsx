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
import { useDebug } from "@/lib/debug";

type NavId = "brief" | "alert" | "team" | "patient" | "chart";

const NAV: { id: NavId; label: string; icon: React.ReactNode; badge?: string; tone?: "alert" }[] = [
  { id: "brief",   label: "Monday briefing", icon: <FileText size={14} /> },
  { id: "alert",   label: "Anomalies",       icon: <AlertTriangle size={14} />, badge: "2", tone: "alert" },
  { id: "team",    label: "CHW roster",      icon: <Users size={14} />,        badge: "30" },
  { id: "patient", label: "Patient lookup",  icon: <Search size={14} /> },
  { id: "chart",   label: "Activity charts", icon: <BarChart3 size={14} /> },
];

const OBS = [
  { label: "langfuse",   href: "http://localhost:3100" },
  { label: "grafana",    href: "http://localhost:3200" },
  { label: "openmrs",    href: "http://localhost:8080/openmrs" },
  { label: "prometheus", href: "http://localhost:9090" },
];

export function Sidebar({
  active,
  onSelect,
}: {
  active: NavId;
  onSelect: (id: NavId) => void;
}) {
  const { debug } = useDebug();
  return (
    <aside
      className="border-r border-[var(--line)] flex flex-col"
      style={{ background: "var(--surface-2)" }}
    >
      {/* Brand block */}
      <div className="px-4 pt-5 pb-4 flex items-center gap-2.5">
        <div
          className="w-[26px] h-[26px] rounded-md grid place-items-center text-[10px] font-mono font-semibold"
          style={{ background: "var(--ink)", color: "var(--bg)" }}
        >
          CH
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold">Field Briefing</div>
          <div className="text-[12px] font-mono text-[var(--ink-3)]">kakamega · v0.3</div>
        </div>
      </div>

      {/* Workspace nav */}
      <div className="px-3">
        <div className="text-[11px] font-mono uppercase tracking-[0.07em] text-[var(--ink-3)] px-2 mb-2">
          workspace
        </div>
        <nav className="flex flex-col gap-0.5">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => onSelect(n.id)}
              className={cn("nav-item", active === n.id && "nav-item--active")}
            >
              <span className="text-[var(--ink-3)]">{n.icon}</span>
              <span>{n.label}</span>
              {n.badge && (
                <span className={cn("nav-badge", n.tone === "alert" && "nav-badge--alert")}>
                  {n.badge}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Observability — developer links, hidden unless Debug Mode is on. */}
      {debug && (
        <div className="px-3 mt-6">
          <div className="text-[11px] font-mono uppercase tracking-[0.07em] text-[var(--ink-3)] px-2 mb-2">
            observability
          </div>
          <nav className="flex flex-col gap-0.5">
            {OBS.map((o) => (
              <a
                key={o.label}
                href={o.href}
                target="_blank"
                rel="noreferrer"
                className="nav-item font-mono text-[12px] text-[var(--ink-2)]"
              >
                <span>{o.label}</span>
                <ExternalLink size={11} className="ml-auto text-[var(--ink-4)]" />
              </a>
            ))}
          </nav>
        </div>
      )}

      {/* User block */}
      <div className="mt-auto px-4 py-4 border-t border-[var(--line)] flex items-center gap-2.5">
        <div
          className="w-7 h-7 rounded-full grid place-items-center text-[11px] font-mono font-semibold"
          style={{ background: "var(--accent-2)", color: "var(--accent-ink)" }}
        >
          MK
        </div>
        <div className="leading-tight">
          <div className="text-[12px] font-medium">Margaret Kimani</div>
          <div className="text-[11px] text-[var(--ink-3)]">Supervisor · Kakamega</div>
        </div>
      </div>
    </aside>
  );
}

export type { NavId };
