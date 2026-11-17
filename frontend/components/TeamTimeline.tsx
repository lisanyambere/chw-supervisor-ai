"use client";

import { AlertTriangle, Check, ShieldCheck } from "lucide-react";
import { AGENT_LABELS, type Lane, type TeamRun } from "@/lib/team";
import { cn } from "@/lib/cn";

/**
 * The briefing team at work: the router's choice, one lane per specialist
 * with its live tool calls, the lead analyst's write-up, and the grounding
 * check on the result.
 */
export function TeamTimeline({ team }: { team: TeamRun }) {
  const reported = team.routed && team.lanes.every((l) => l.status === "done");
  const totalMs = Math.max(0, ...team.lanes.map((l) => l.ms ?? 0));
  return (
    <div className="plan-card">
      <div className="team-head">
        <div>Briefing team</div>
        <div>
          {team.done ? (
            <span className="text-[var(--ok)]">
              specialists done in {(totalMs / 1000).toFixed(1)}s
            </span>
          ) : (
            <span className="flex items-center gap-2 text-[var(--accent-ink)]">
              <span className="pulse-dot" />
              working
            </span>
          )}
        </div>
      </div>

      <div className="team-stage">
        <StageBullet state={team.routed ? "done" : "running"} />
        <div>
          <span className="team-stage__name">Router</span>
          {team.routed ? (
            <span className="team-stage__note">
              {" "}
              engaged {team.lanes.length} of 3 specialists
              {team.reason && ` — ${team.reason}`}
            </span>
          ) : (
            <span className="team-stage__note"> reading the question…</span>
          )}
        </div>
      </div>

      {team.lanes.length > 0 && (
        <div className="team-lanes">
          {team.lanes.map((lane) => (
            <LaneColumn key={lane.name} lane={lane} />
          ))}
        </div>
      )}

      {reported && team.lanes.length > 1 && (
        <div className="team-stage">
          <StageBullet
            state={team.verification && !team.revising ? "done" : "running"}
          />
          <div>
            <span className="team-stage__name">Lead analyst</span>
            <span className="team-stage__note">
              {team.revising
                ? " rewriting — the check found figures with no source…"
                : team.verification
                  ? " merged the findings into one briefing"
                  : " merging the findings…"}
            </span>
          </div>
        </div>
      )}

      {team.verification && !team.revising && (
        <VerificationRow team={team} />
      )}
    </div>
  );
}

function LaneColumn({ lane }: { lane: Lane }) {
  return (
    <div className={cn("team-lane", lane.status === "queued" && "is-queued")}>
      <div className="team-lane__head">
        <StageBullet state={lane.status === "queued" ? "pending" : lane.status} />
        <span className="team-lane__name">
          {AGENT_LABELS[lane.name] ?? lane.name}
        </span>
        <span className="team-lane__ms">
          {lane.status === "done" && lane.ms !== null
            ? `${(lane.ms / 1000).toFixed(1)}s`
            : lane.status}
        </span>
      </div>
      {lane.steps.map((s, i) => (
        <div key={i} className="team-step">
          <div className="grid place-items-center">
            <StageBullet state={s.running ? "running" : "done"} small />
          </div>
          <div className="min-w-0">
            <div className="team-step__tool">
              {s.tool}
              <span className="text-[var(--ink-3)]"> {s.args}</span>
            </div>
            <div className="team-step__meta">
              {s.running ? "running…" : `${s.rows} rows · ${s.ms}ms`}
            </div>
          </div>
        </div>
      ))}
      {lane.status === "done" && lane.steps.length === 0 && (
        <div className="team-step__meta px-[14px] pb-3">no tools needed</div>
      )}
    </div>
  );
}

function VerificationRow({ team }: { team: TeamRun }) {
  const v = team.verification!;
  const unsourced = [...v.ungrounded_numbers, ...v.ungrounded_chw_ids];
  return (
    <div className={cn("team-verify", !v.grounded && "team-verify--warn")}>
      {v.grounded ? <ShieldCheck size={14} /> : <AlertTriangle size={14} />}
      <div>
        {v.grounded ? (
          <>
            <b>Verified.</b> All {v.figures_checked} figures in the answer
            trace to a tool result
            {v.revisions > 0 && " (after one rewrite removed unsourced figures)"}.
          </>
        ) : (
          <>
            <b>Check these figures.</b> No tool result contains:{" "}
            {unsourced.join(", ")}.
          </>
        )}
      </div>
    </div>
  );
}

function StageBullet({
  state,
  small,
}: {
  state: "pending" | "running" | "done";
  small?: boolean;
}) {
  if (state === "running") return <span className="spinner" />;
  if (state === "pending") return <span className="plan-bullet--pending" />;
  return (
    <span className="plan-bullet--done" style={small ? { width: 12, height: 12 } : undefined}>
      <Check size={small ? 8 : 9} strokeWidth={3} />
    </span>
  );
}
