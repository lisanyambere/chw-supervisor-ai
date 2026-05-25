import { afterEach, describe, expect, it, vi } from "vitest";

import { streamBriefing, type StreamFrame } from "@/lib/api";

// ─── MockEventSource ───────────────────────────────────────────────────────
// EventSource isn't available in jsdom. We stand up a tiny shim that records
// the constructed URL, lets the test push frames via `emit()`, and exposes a
// `closed` flag so we can assert cleanup.

type Listener = (ev: MessageEvent) => void;

class MockEventSource {
  static last: MockEventSource | null = null;

  url: string;
  closed = false;
  onerror: ((e: Event) => void) | null = null;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.last = this;
  }

  addEventListener(kind: string, fn: Listener) {
    (this.listeners[kind] ??= []).push(fn);
  }

  emit(frame: StreamFrame) {
    const ev = { data: JSON.stringify(frame) } as MessageEvent;
    for (const fn of this.listeners[frame.kind] ?? []) fn(ev);
  }

  emitError() {
    this.onerror?.({} as Event);
  }

  close() {
    this.closed = true;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockEventSource.last = null;
});

function install() {
  vi.stubGlobal("EventSource", MockEventSource);
}

describe("streamBriefing", () => {
  it("encodes question + lookback_days into the URL", () => {
    install();
    streamBriefing("hello world", { onFrame: () => {} }, { lookbackDays: 14 });

    const es = MockEventSource.last!;
    expect(es.url).toContain("/briefing/stream?");
    expect(es.url).toContain("question=hello+world");
    expect(es.url).toContain("lookback_days=14");
  });

  it("forwards tool_start, tool_done, response frames in order", () => {
    install();
    const frames: StreamFrame[] = [];
    streamBriefing("q", { onFrame: (f) => frames.push(f) });

    const es = MockEventSource.last!;
    es.emit({ kind: "tool_start", tool: "team_activity_summary", args: "(days=30)" });
    es.emit({
      kind: "tool_done",
      tool: "team_activity_summary",
      args: "(days=30)",
      ms: 412,
      rows: 30,
    });
    es.emit({
      kind: "response",
      answer: "done",
      iterations: 2,
      tool_calls: 1,
      plan: [{ tool: "team_activity_summary", args: "(days=30)", ms: 412, rows: 30 }],
      trace_id: "t-1",
      answer_doc: null,
    });

    expect(frames.map((f) => f.kind)).toEqual([
      "tool_start",
      "tool_done",
      "response",
    ]);
  });

  it("auto-closes and fires onClose on the response frame", () => {
    install();
    const onClose = vi.fn();
    streamBriefing("q", { onFrame: () => {}, onClose });

    const es = MockEventSource.last!;
    es.emit({
      kind: "response",
      answer: "ok",
      iterations: 1,
      tool_calls: 0,
      plan: [],
      trace_id: null,
      answer_doc: null,
    });

    expect(es.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("auto-closes on an error frame and onClose fires exactly once", () => {
    install();
    const onClose = vi.fn();
    const frames: StreamFrame[] = [];
    streamBriefing("q", { onFrame: (f) => frames.push(f), onClose });

    const es = MockEventSource.last!;
    es.emit({ kind: "error", message: "boom" });

    expect(frames).toEqual([{ kind: "error", message: "boom" }]);
    expect(es.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("treats a transport error as terminal: notifies and closes", () => {
    install();
    const onTransportError = vi.fn();
    const onClose = vi.fn();
    streamBriefing("q", {
      onFrame: () => {},
      onClose,
      onTransportError,
    });

    const es = MockEventSource.last!;
    es.emitError();

    expect(onTransportError).toHaveBeenCalledTimes(1);
    expect(es.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("returns a close() thunk the caller can use to cancel", () => {
    install();
    const onClose = vi.fn();
    const close = streamBriefing("q", { onFrame: () => {}, onClose });

    const es = MockEventSource.last!;
    expect(es.closed).toBe(false);

    close();
    expect(es.closed).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);

    // Idempotent — calling close() twice doesn't double-fire onClose.
    close();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
