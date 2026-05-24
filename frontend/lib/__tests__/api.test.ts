import { afterEach, describe, expect, it, vi } from "vitest";

import { BACKEND_URL, getHealth, getReady, postBriefing } from "@/lib/api";

function mockFetch(response: Partial<Response>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response as Response),
  );
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
