"use client";

import { Check } from "lucide-react";
import type { PlanStep } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Tool-execution timeline. Drives the live "agent thinking" state by
 * comparing each step's index against `activeIdx`:
 *   - i < activeIdx  → done (filled green disc + check + ms timing)
 *   - i === activeIdx → running (teal arc spinner)
 *   - i > activeIdx  → pending (dashed ring, no timing yet)
 *
 * If `activeIdx >= plan.length` the whole card flips to its "completed in
 * Nms" header and every row reads as done. This is the same state machine
 * the design handoff describes — the only thing the production version
 * adds is real timings from the backend.
 */
export function PlanTimeline({
  plan,
  activeIdx,
  done,
}: {
  plan: PlanStep[];
  activeIdx: number;
  done: boolean;
}) {
  const totalMs = plan.reduce((acc, s) => acc + s.ms, 0);
  return (
    <div className="plan-card">
      <div
        className="flex items-center justify-between px-[14px] py-2.5 border-b border-[var(--line)]"
        style={{ background: "var(--surface-2)" }}
      >
        <div className="font-mono text-[11px] uppercase tracking-[0.07em] text-[var(--ink-3)]">
          Tool plan
        </div>
        <div className="font-mono text-[11px]">
          {done ? (
            <span className="text-[var(--ok)]">
              completed in {totalMs}ms
            </span>
          ) : (
            <span className="flex items-center gap-2 text-[var(--accent-ink)]">
              <span className="pulse-dot" />
              running
            </span>
          )}
        </div>
      </div>
      <div>
        {plan.map((s, i) => {
          const status =
            i < activeIdx || done ? "done" : i === activeIdx && !done ? "running" : "pending";
          return (
            <div key={i} className="plan-row">
              <div className="grid place-items-center">
                {status === "done" && (
                  <span className="plan-bullet--done">
                    <Check size={9} strokeWidth={3} />
                  </span>
                )}
                {status === "running" && <span className="spinner" />}
                {status === "pending" && <span className="plan-bullet--pending" />}
              </div>
              <div className={cn(status === "pending" && "text-[var(--ink-3)]")}>
                <span className="text-[var(--ink)]">{s.tool}</span>
                <span className="text-[var(--ink-3)]"> {s.args}</span>
              </div>
              <div className="text-[var(--ink-3)] text-right">
                {status === "pending" ? "—" : `${s.rows} rows`}
              </div>
              <div className="text-[var(--ink-3)] text-right tabular-nums w-[60px]">
                {status === "pending" ? "—" : `${s.ms}ms`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
