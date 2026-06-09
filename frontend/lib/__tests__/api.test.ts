import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BACKEND_URL,
  getActivity,
  getChws,
  getHealth,
  getReady,
  postBriefing,
} from "@/lib/api";

function mockFetch(response: Partial<Response>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response as Response),
  );
}

/** Like mockFetch, but returns the spy so tests can assert on the called URL. */
function mockFetchSpy(response: Partial<Response>) {
  const spy = vi.fn((..._args: unknown[]) =>
    Promise.resolve(response as Response),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("postBriefing", () => {
  it("returns the parsed BriefingResponse on 200", async () => {
    const body = {
      answer: "ok",
      iterations: 1,
      tool_calls: 0,
      trace_id: null,
      plan: [],
      answer_doc: null,
    };
    mockFetch({
      ok: true,
      status: 200,
      json: async () => body,
    });

    const result = await postBriefing("hello");
    expect(result).toEqual(body);
  });

  it("throws on a 4xx response, surfacing the response body", async () => {
    mockFetch({
      ok: false,
      status: 400,
      text: async () => "bad question",
    });

    await expect(postBriefing("oops")).rejects.toThrow(/400/);
    await expect(postBriefing("oops")).rejects.toThrow(/bad question/);
  });

  it("throws on a 5xx response", async () => {
    mockFetch({
      ok: false,
      status: 503,
      text: async () => "downstream unavailable",
    });

    await expect(postBriefing("hi")).rejects.toThrow(/503/);
  });
});

describe("BACKEND_URL default", () => {
  it("points at the backend's actual port (8000)", () => {
    // Guards against the regression of pointing at 8001 (an old plan).
    expect(BACKEND_URL).toMatch(/:8000(\/|$)/);
  });
});

describe("getHealth (liveness)", () => {
  it("returns {status: 'ok'} on 200", async () => {
    mockFetch({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok" }),
    });

    await expect(getHealth()).resolves.toEqual({ status: "ok" });
  });

  it("throws on a non-2xx response", async () => {
    mockFetch({
      ok: false,
      status: 500,
    });

    await expect(getHealth()).rejects.toThrow(/500/);
  });
});

describe("getReady (readiness)", () => {
  it("resolves with status='ready' on 200", async () => {
    const body = {
      status: "ready",
      openmrs: true,
      llm_provider: "openrouter",
      llm_model: "moonshotai/kimi-k2.6",
      patients_loaded: 581,
      chws_loaded: 30,
    };
    mockFetch({
      ok: true,
      status: 200,
      json: async () => body,
    });

    await expect(getReady()).resolves.toEqual(body);
  });

  it("resolves with status='not_ready' on 503 (still parseable)", async () => {
    // A 503 from /readyz carries the same body shape; the caller
    // decides how to render it. The function MUST NOT throw, or the
    // UI loses the diagnostic detail.
    const body = {
      status: "not_ready",
      openmrs: false,
      llm_provider: "openrouter",
      llm_model: "moonshotai/kimi-k2.6",
      patients_loaded: 0,
      chws_loaded: 0,
    };
    mockFetch({
      ok: false,
      status: 503,
      json: async () => body,
    });

    const result = await getReady();
    expect(result.status).toBe("not_ready");
    expect(result.openmrs).toBe(false);
  });

  it("throws on an unexpected status (e.g. 500)", async () => {
    mockFetch({
      ok: false,
      status: 500,
    });

    await expect(getReady()).rejects.toThrow(/500/);
  });
});

describe("getChws (roster)", () => {
  it("returns the parsed roster on 200", async () => {
    const body = [
      { chw_id: "chw-001", practitioner_uuid: "uuid-1" },
      { chw_id: "chw-002", practitioner_uuid: "uuid-2" },
    ];
    mockFetch({ ok: true, status: 200, json: async () => body });

    await expect(getChws()).resolves.toEqual(body);
  });

  it("throws on a non-2xx response", async () => {
    mockFetch({ ok: false, status: 500, text: async () => "boom" });

    await expect(getChws()).rejects.toThrow(/500/);
  });
});

describe("getActivity (daily series)", () => {
  const body = {
    days: 30,
    chw_id: null,
    series: [
      {
        date: "2026-05-11",
        weekday: "Mon",
        encounter_count: 12,
        is_weekend: false,
        is_zero: false,
      },
    ],
    stats: {
      min: 0,
      max: 12,
      mean: 6.0,
      total: 180,
      zero_days: 4,
      active_days: 26,
    },
  };

  it("returns the parsed ActivityResponse on 200", async () => {
    mockFetch({ ok: true, status: 200, json: async () => body });

    await expect(getActivity({ days: 30 })).resolves.toEqual(body);
  });

  it("encodes days and chwId into the query string", async () => {
    const spy = mockFetchSpy({ ok: true, status: 200, json: async () => body });

    await getActivity({ days: 14, chwId: "chw-007" });

    const url = String(spy.mock.calls[0][0]);
    expect(url).toContain("/activity?");
    expect(url).toContain("days=14");
    expect(url).toContain("chw_id=chw-007");
  });

  it("omits chw_id when scoped to the whole team", async () => {
    const spy = mockFetchSpy({ ok: true, status: 200, json: async () => body });

    await getActivity({ days: 30, chwId: null });

    const url = String(spy.mock.calls[0][0]);
    expect(url).not.toContain("chw_id");
  });

  it("surfaces a 404 for an unknown chw id", async () => {
    mockFetch({ ok: false, status: 404, text: async () => "unknown chw_id" });

    await expect(getActivity({ chwId: "chw-999" })).rejects.toThrow(/404/);
  });
});
