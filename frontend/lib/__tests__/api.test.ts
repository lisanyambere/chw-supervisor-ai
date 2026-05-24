import { afterEach, describe, expect, it, vi } from "vitest";

import { postBriefing } from "@/lib/api";

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
