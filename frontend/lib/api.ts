/**
 * Backend API contract — mirrors backend/app/api/schemas.py.
 *
 * The browser talks to the backend directly. Override the URL with
 * NEXT_PUBLIC_BACKEND_URL when running against a non-default host.
 */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// ─── /briefing ──────────────────────────────────────────────────────────────

export type DeltaTone = "ok" | "warn" | "alert" | "muted";
export type Tone = "ok" | "warn" | "alert";

export type Stat = {
  label: string;
  value: string;
  delta: string;
  deltaTone: DeltaTone;
  sub: string;
};

export type RankedItem = {
  id: string; // chw-NNN
  primary: string;
  secondary: string;
};

export type PanelRow = {
  left: string;
  mid: string;
  right: string;
};

export type Section =
  | { kind: "stat-row"; stats: Stat[] }
  | { kind: "callout"; tone: Tone; title: string; body: string; evidence: string[] }
  | { kind: "ranked"; title: string; tone: Tone; items: RankedItem[] }
  | { kind: "panel"; title: string; rows: PanelRow[] };

export type AnswerDoc = {
  headline: string;
  period: string;
  sections: Section[];
  sources: string[];
};

export type PlanStep = {
  tool: string;
  args: string;
  ms: number;
  rows: number;
};

export type BriefingResponse = {
  answer: string;
  iterations: number;
  tool_calls: number;
  trace_id: string | null;
  plan: PlanStep[];
  answer_doc: AnswerDoc | null;
};

export async function postBriefing(
  question: string,
  opts: { signal?: AbortSignal } = {},
): Promise<BriefingResponse> {
  const res = await fetch(`${BACKEND_URL}/briefing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal: opts.signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`briefing failed: ${res.status} ${detail.slice(0, 200)}`);
  }
  return (await res.json()) as BriefingResponse;
}

// ─── /healthz (liveness) ────────────────────────────────────────────────────

export type LivenessResponse = {
  status: "ok";
};

export async function getHealth(): Promise<LivenessResponse> {
  const res = await fetch(`${BACKEND_URL}/healthz`);
  if (!res.ok) throw new Error(`healthz failed: ${res.status}`);
  return (await res.json()) as LivenessResponse;
}

// ─── /readyz (downstream checks) ────────────────────────────────────────────
//
// Returns 200 when every required downstream is reachable, 503 otherwise.
// Both carry the same body shape so the caller can render a "Backend
// unavailable — OpenMRS unreachable" style message without retrying.

export type ReadinessResponse = {
  status: "ready" | "not_ready";
  openmrs: boolean;
  llm_provider: string;
  llm_model: string;
  patients_loaded: number;
  chws_loaded: number;
};

export async function getReady(): Promise<ReadinessResponse> {
  const res = await fetch(`${BACKEND_URL}/readyz`);
  if (res.status !== 200 && res.status !== 503) {
    throw new Error(`readyz failed: ${res.status}`);
  }
  return (await res.json()) as ReadinessResponse;
}

// ─── /briefing/stream (SSE) ─────────────────────────────────────────────────
//
// Mirrors backend/app/agents/briefing.py:StreamEvent. The wire format is
// SSE with named events: tool_start, tool_done, response, error. The
// `response` frame carries the same shape as POST /briefing's body so
// callers can render an AnswerDoc when the agent finishes.

export type ToolStartFrame = {
  kind: "tool_start";
  tool: string;
  args: string;
};

export type ToolDoneFrame = {
  kind: "tool_done";
  tool: string;
  args: string;
  ms: number;
  rows: number;
};

export type ResponseFrame = {
  kind: "response";
  answer: string;
  iterations: number;
  tool_calls: number;
  plan: PlanStep[];
  trace_id: string | null;
  answer_doc: AnswerDoc | null;
};

export type ErrorFrame = {
  kind: "error";
  message: string;
};

export type StreamFrame =
  | ToolStartFrame
  | ToolDoneFrame
  | ResponseFrame
  | ErrorFrame;

export type StreamHandlers = {
  onFrame: (frame: StreamFrame) => void;
  /** Fired once when the stream cleanly terminates (response or error). */
  onClose?: () => void;
  /** Fired on transport-level failures (network drop, 5xx, CORS). */
  onTransportError?: (event: Event) => void;
};

/**
 * Open an EventSource against /briefing/stream and forward parsed frames.
 *
 * Returns a `close()` thunk the caller can invoke on unmount / cancel.
 * EventSource itself is GET-only, no body, no custom headers — the SSE
 * endpoint is shaped to match.
 */
export function streamBriefing(
  question: string,
  handlers: StreamHandlers,
  opts: { lookbackDays?: number; maxIterations?: number } = {},
): () => void {
  const params = new URLSearchParams({ question });
  if (opts.lookbackDays !== undefined) {
    params.set("lookback_days", String(opts.lookbackDays));
  }
  if (opts.maxIterations !== undefined) {
    params.set("max_iterations", String(opts.maxIterations));
  }

  const es = new EventSource(`${BACKEND_URL}/briefing/stream?${params}`);
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
    handlers.onClose?.();
  };

  const kinds: StreamFrame["kind"][] = [
    "tool_start",
    "tool_done",
    "response",
    "error",
  ];
  for (const kind of kinds) {
    es.addEventListener(kind, (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as StreamFrame;
        handlers.onFrame(data);
        if (kind === "response" || kind === "error") close();
      } catch (e) {
        console.error("streamBriefing: frame parse failed", e);
      }
    });
  }

  es.onerror = (e) => {
    // EventSource fires `error` on both transient reconnect attempts AND
    // permanent failures. We treat any error after the stream is open as
    // terminal — the backend doesn't reconnect mid-agent-run cleanly.
    handlers.onTransportError?.(e);
    close();
  };

  return close;
}
