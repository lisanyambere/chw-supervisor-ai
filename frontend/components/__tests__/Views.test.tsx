import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AnomaliesView } from "@/components/AnomaliesView";
import { RosterView } from "@/components/RosterView";
import type { Anomalies, RosterRow } from "@/lib/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function row(chw_id: string, ward: string, pattern: RosterRow["pattern"] = null): RosterRow {
  return {
    chw_id,
    name: `Name ${chw_id}`,
    ward,
    encounters_30d: 150,
    encounters_7d: 30,
    pattern,
    last_active: pattern === "stopped_early" ? "2026-11-10" : null,
  };
}

describe("RosterView", () => {
  it("lists workers who need a look first and opens the drawer on click", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          chws: [row("chw-003", "Butere"), row("chw-001", "Lurambi", "stopped_early")],
        }),
      })),
    );
    const onSelect = vi.fn();
    render(<RosterView onSelectChw={onSelect} />);

    const rows = await screen.findAllByRole("button");
    expect(rows[0]).toHaveTextContent("chw-001");
    expect(rows[0]).toHaveTextContent("stopped early · last visit 10 Nov");

    fireEvent.click(rows[1]);
    expect(onSelect).toHaveBeenCalledWith("chw-003");
  });
});

const QUIET: Anomalies = {
  days: 14,
  action_count: 1,
  fever_clusters: [],
  children: [],
  overdue: [
    {
      patient_name: "Namukhula Adhiambo",
      last_visit: "2026-10-31",
      return_date: "2026-11-07",
      days_overdue: 11,
      pregnant: true,
      last_systolic_bp: 145,
      chw_id: "chw-006",
      ward: "Mumias East",
    },
  ],
  activity_gaps: { team_last_active: "2026-11-13", rows: [] },
  missing_location: { total_missing_location: 0, rows: [] },
  visits_after_death: { rows: [] },
};

describe("AnomaliesView", () => {
  it("shows each finding with its CHW, and says when a group is clear", () => {
    const onSelect = vi.fn();
    render(
      <AnomaliesView
        state={{ status: "ready", data: QUIET }}
        onSelectChw={onSelect}
        onAsk={() => {}}
      />,
    );

    expect(
      screen.getByText("Namukhula Adhiambo: 11 days overdue, pregnant, last BP 145"),
    ).toBeInTheDocument();
    expect(screen.getByText("No ward has three or more fever cases.")).toBeInTheDocument();
    expect(screen.getByText("No records out of line.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("chw-006"));
    expect(onSelect).toHaveBeenCalledWith("chw-006");
  });

  it("hands off to the briefing team", () => {
    const onAsk = vi.fn();
    render(
      <AnomaliesView
        state={{ status: "ready", data: QUIET }}
        onSelectChw={() => {}}
        onAsk={onAsk}
      />,
    );
    fireEvent.click(screen.getByText("Ask the briefing team to rank these"));
    expect(onAsk).toHaveBeenCalledOnce();
  });
});

describe("UsageNote", () => {
  it("shows calls, tokens and cost, and leaves cost out when unpriced", async () => {
    const { UsageNote } = await import("@/components/TeamTimeline");
    const usage = {
      calls: 9,
      input_tokens: 12000,
      cached_input_tokens: 0,
      output_tokens: 3400,
      reasoning_tokens: 0,
      cost_usd: 0.162,
    };
    const { rerender } = render(<UsageNote usage={usage} />);
    expect(screen.getByText("9 model calls · 15.4k tokens · ≈ $0.16")).toBeInTheDocument();

    rerender(<UsageNote usage={{ ...usage, cost_usd: null }} />);
    expect(screen.getByText("9 model calls · 15.4k tokens")).toBeInTheDocument();
  });
});
