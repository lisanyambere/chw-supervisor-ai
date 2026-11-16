import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ChwDrawer } from "@/components/ChwDrawer";
import type { ChwDetail } from "@/lib/api";

const MARY: ChwDetail = {
  chw_id: "chw-000",
  practitioner_uuid: "f3a8c2d1-0000-0000-0000-00000000b21c",
  name: "Mary Wanjiku",
  ward: "Lurambi",
  encounters_30d: 97,
  encounters_7d: 0,
  patients_30d: 18,
  daily: [
    { date: "2026-11-10", encounter_count: 7 },
    { date: "2026-11-11", encounter_count: 0 },
  ],
};

function mockFetch(response: Partial<Response>) {
  const fn = vi.fn(async () => response as Response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChwDrawer", () => {
  it("does not fetch while closed", () => {
    const fetchFn = mockFetch({});
    render(<ChwDrawer chwId={null} onClose={() => {}} onAsk={() => {}} />);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("shows the CHW's profile and flags a week with no visits", async () => {
    mockFetch({ ok: true, status: 200, json: async () => MARY });
    render(<ChwDrawer chwId="chw-000" onClose={() => {}} onAsk={() => {}} />);

    expect(await screen.findByText("Mary Wanjiku")).toBeInTheDocument();
    expect(screen.getByText("Lurambi")).toBeInTheDocument();
    expect(screen.getByText("97")).toBeInTheDocument();
    expect(screen.getByText("no visits in 7 days")).toBeInTheDocument();
  });

  it("explains an unknown CHW instead of rendering empty rows", async () => {
    mockFetch({ ok: false, status: 404 });
    render(<ChwDrawer chwId="chw-999" onClose={() => {}} onAsk={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "chw-999 is not on the roster.",
    );
  });

  it("closes on Escape", async () => {
    mockFetch({ ok: true, status: 200, json: async () => MARY });
    const onClose = vi.fn();
    render(<ChwDrawer chwId="chw-000" onClose={onClose} onAsk={() => {}} />);
    await screen.findByText("Mary Wanjiku");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("asks the follow-up question and closes", async () => {
    mockFetch({ ok: true, status: 200, json: async () => MARY });
    const onClose = vi.fn();
    const onAsk = vi.fn();
    render(<ChwDrawer chwId="chw-000" onClose={onClose} onAsk={onAsk} />);

    fireEvent.click(await screen.findByText("Open patient panel"));
    expect(onAsk).toHaveBeenCalledWith("Show the patient panel for chw-000.");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
