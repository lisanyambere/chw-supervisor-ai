"use client";

import { ArrowRight } from "lucide-react";
import { getRoster, type ActivityPattern, type RosterRow } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { LoadNote, ViewHeader } from "@/components/ViewHeader";

export const PATTERN_LABELS: Record<ActivityPattern, string> = {
  stopped_early: "stopped early",
  started_late: "short history",
  no_visits: "no visits",
};

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

export function patternNote(pattern: ActivityPattern, lastActive: string | null) {
  if (pattern === "stopped_early" && lastActive) {
    return `last visit ${shortDate(lastActive)}`;
  }
  if (pattern === "started_late") return "low totals are not low effort";
  return "check in";
}

export function RosterView({ onSelectChw }: { onSelectChw: (id: string) => void }) {
  const state = useLoad((signal) => getRoster({ signal }));
  return (
    <div className="view">
      <ViewHeader
        kicker={
          state.status === "ready"
            ? `Roster · ${state.data.length} CHWs`
            : "Roster"
        }
        title="Community health workers"
      />
      <article className="ans ans--plain ans--flush mt-5">
        {state.status !== "ready" && (
          <div className="px-6 py-5">
            <LoadNote state={state} />
          </div>
        )}
        {state.status === "ready" &&
          // Workers whose pattern needs a look come first, then by ward.
          [...state.data]
            .sort(
              (a, b) =>
                Number(b.pattern !== null) - Number(a.pattern !== null) ||
                (a.ward ?? "").localeCompare(b.ward ?? "") ||
                a.chw_id.localeCompare(b.chw_id),
            )
            .map((row) => (
              <RosterLine key={row.chw_id} row={row} onSelect={onSelectChw} />
            ))}
      </article>
    </div>
  );
}

function RosterLine({
  row,
  onSelect,
}: {
  row: RosterRow;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      className="ranked__row roster-row text-left w-full"
      type="button"
      onClick={() => onSelect(row.chw_id)}
    >
      <span className="chip">{row.chw_id}</span>
      <div className="min-w-0">
        <div className="ranked__row__primary">
          {row.name ?? row.chw_id}
          {row.pattern && (
            <span className="roster-flag">
              {PATTERN_LABELS[row.pattern]} ·{" "}
              {patternNote(row.pattern, row.last_active)}
            </span>
          )}
        </div>
        <div className="ranked__row__secondary">
          {row.ward ?? "ward unknown"} · {row.encounters_30d} visits / 30d ·{" "}
          {row.encounters_7d} / 7d
        </div>
      </div>
      <ArrowRight size={14} className="text-[var(--ink-4)]" />
    </button>
  );
}
