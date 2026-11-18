import { describe, expect, it } from "vitest";

import type { StreamFrame, Verification } from "@/lib/api";
import { EMPTY_TEAM, applyFrame, type TeamRun } from "@/lib/team";

function run(frames: StreamFrame[]): TeamRun {
  return frames.reduce(applyFrame, EMPTY_TEAM);
}

const GROUNDED: Verification = {
  grounded: true,
  figures_checked: 4,
  ungrounded_numbers: [],
  ungrounded_chw_ids: [],
  revisions: 0,
};

describe("applyFrame", () => {
  it("queues a lane for each specialist the router engaged", () => {
    const team = run([
      { kind: "route", agents: ["team", "quality"], reason: "activity + records" },
    ]);
    expect(team.lanes.map((l) => [l.name, l.status])).toEqual([
      ["team", "queued"],
      ["quality", "queued"],
    ]);
    expect(team.reason).toBe("activity + records");
  });

  it("keeps parallel specialists' tool calls in their own lanes", () => {
    const team = run([
      { kind: "route", agents: ["team", "clinical"] },
      { kind: "agent_start", agent: "team" },
      { kind: "agent_start", agent: "clinical" },
      { kind: "tool_start", agent: "clinical", tool: "overdue_followups", args: "()" },
      { kind: "tool_start", agent: "team", tool: "team_activity_summary", args: "(days=30)" },
      { kind: "tool_done", agent: "team", tool: "team_activity_summary", args: "(days=30)", ms: 900, rows: 30 },
      { kind: "agent_done", agent: "team", ms: 4000 },
    ]);
    const [teamLane, clinical] = team.lanes;
    expect(teamLane.status).toBe("done");
    expect(teamLane.steps).toEqual([
      { tool: "team_activity_summary", args: "(days=30)", ms: 900, rows: 30, running: false },
    ]);
    expect(clinical.status).toBe("running");
    expect(clinical.steps[0].running).toBe(true);
  });

  it("finishes the oldest of two identical running calls", () => {
    const call = { agent: "team", tool: "list_chws", args: "()" } as const;
    const team = run([
      { kind: "route", agents: ["team"] },
      { kind: "tool_start", ...call },
      { kind: "tool_start", ...call },
      { kind: "tool_done", ...call, ms: 5, rows: 30 },
    ]);
    expect(team.lanes[0].steps.map((s) => s.running)).toEqual([false, true]);
  });

  it("marks the run as revising when the first draft fails the check", () => {
    const failed = { ...GROUNDED, grounded: false, ungrounded_numbers: ["777"] };
    const revising = run([{ kind: "verify", verification: failed }]);
    expect(revising.revising).toBe(true);

    const settled = applyFrame(revising, {
      kind: "verify",
      verification: { ...GROUNDED, revisions: 1 },
    });
    expect(settled.revising).toBe(false);
    expect(settled.verification?.grounded).toBe(true);
  });

  it("keeps the run's usage from the response frame", () => {
    const usage = {
      calls: 9,
      input_tokens: 12000,
      cached_input_tokens: 0,
      output_tokens: 3400,
      reasoning_tokens: 1200,
      cost_usd: 0.162,
    };
    const team = run([
      { kind: "route", agents: ["team"] },
      {
        kind: "response",
        answer: "",
        iterations: 3,
        tool_calls: 0,
        plan: [],
        trace_id: null,
        answer_doc: null,
        route: ["team"],
        route_reason: "",
        agents: [],
        verification: {},
        usage,
      },
    ]);
    expect(team.usage).toEqual(usage);
  });

  it("stops revising once the one allowed rewrite also fails", () => {
    const team = run([
      {
        kind: "verify",
        verification: { ...GROUNDED, grounded: false, ungrounded_numbers: ["888"], revisions: 1 },
      },
    ]);
    expect(team.revising).toBe(false);
  });
});
