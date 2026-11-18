import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ActivityView, classifyDays } from "@/components/ActivityView";

// Fri 13 Nov 2026 … Tue 17 Nov 2026 (today, still in progress)
const SERIES = [
  { date: "2026-11-13", encounter_count: 240 },
  { date: "2026-11-14", encounter_count: 0 },
  { date: "2026-11-15", encounter_count: 0 },
  { date: "2026-11-16", encounter_count: 0 },
  { date: "2026-11-17", encounter_count: 0 },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("classifyDays", () => {
  it("flags an empty weekday, but not a weekend or today", () => {
    expect(
      classifyDays(SERIES).map((d) => [d.weekend, d.missed]),
    ).toEqual([
      [false, false],
      [true, false],
      [true, false],
      [false, true],
      [false, false], // today is not over, so not missed
    ]);
  });
});

describe("ActivityView", () => {
  it("names the missed weekday and offers the same data as a table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ days: 30, series: SERIES, total: 240 }),
      })),
    );
    render(<ActivityView />);

    expect(
      await screen.findByText(
        "Monday 16 Nov is the only weekday with no visits.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText("Show as table"));
    expect(screen.getByText("0 — no visits")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(SERIES.length + 1);
  });

  it("says so when the backend cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 502 })),
    );
    render(<ActivityView />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Activity lookup failed: 502",
    );
  });
});
