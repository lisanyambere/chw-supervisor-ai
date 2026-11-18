/**
 * Live state of one briefing run: which specialists the router engaged, what
 * each is doing, and whether the final answer passed the grounding check.
 * `applyFrame` folds one SSE frame into that state.
 */
import type { PlanStep, StreamFrame, Usage, Verification } from "@/lib/api";

export const AGENT_LABELS: Record<string, string> = {
  team: "Team activity",
  clinical: "Clinical signals",
  quality: "Data quality",
};

export type Step = PlanStep & { running: boolean };

export type Lane = {
  name: string;
  status: "queued" | "running" | "done";
  ms: number | null;
  steps: Step[];
};

export type TeamRun = {
  routed: boolean;
  reason: string;
  lanes: Lane[];
  verification: Verification | null;
  /** The first draft failed the grounding check and is being rewritten. */
  revising: boolean;
  done: boolean;
  /** Tokens and cost of the whole run, once it has finished. */
  usage: Usage | null;
};

export const EMPTY_TEAM: TeamRun = {
  routed: false,
  reason: "",
  lanes: [],
  verification: null,
  revising: false,
  done: false,
  usage: null,
};

function patchLane(
  team: TeamRun,
  name: string,
  patch: (lane: Lane) => Lane,
): TeamRun {
  return {
    ...team,
    lanes: team.lanes.map((l) => (l.name === name ? patch(l) : l)),
  };
}

export function applyFrame(team: TeamRun, frame: StreamFrame): TeamRun {
  switch (frame.kind) {
    case "route":
      return {
        ...team,
        routed: true,
        reason: frame.reason ?? "",
        lanes: frame.agents.map((name) => ({
          name,
          status: "queued",
          ms: null,
          steps: [],
        })),
      };
    case "agent_start":
      return patchLane(team, frame.agent, (l) => ({ ...l, status: "running" }));
    case "tool_start":
      return patchLane(team, frame.agent, (l) => ({
        ...l,
        steps: [
          ...l.steps,
          { tool: frame.tool, args: frame.args, ms: 0, rows: 0, running: true },
        ],
      }));
    case "tool_done":
      return patchLane(team, frame.agent, (l) => {
        // The same tool can run twice with the same arguments; finish the
        // oldest one still running.
        const idx = l.steps.findIndex(
          (s) => s.running && s.tool === frame.tool && s.args === frame.args,
        );
        if (idx === -1) return l;
        const steps = l.steps.slice();
        steps[idx] = { ...steps[idx], ms: frame.ms, rows: frame.rows, running: false };
        return { ...l, steps };
      });
    case "agent_done":
      return patchLane(team, frame.agent, (l) => ({
        ...l,
        status: "done",
        ms: frame.ms,
      }));
    case "verify":
      return {
        ...team,
        verification: frame.verification,
        revising: !frame.verification.grounded && frame.verification.revisions < 1,
      };
    case "response":
      return {
        ...team,
        // The backend's plan is the canonical order once the run is over.
        lanes: frame.route.map((name) => ({
          name,
          status: "done",
          ms: frame.agents.find((a) => a.name === name)?.ms ?? null,
          steps: frame.plan
            .filter((s) => s.agent === name)
            .map((s) => ({ ...s, running: false })),
        })),
        revising: false,
        done: true,
        usage: frame.usage ?? null,
      };
    case "error":
      return { ...team, revising: false, done: true };
  }
}
