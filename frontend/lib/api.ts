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
  agent?: string | null; // the specialist that made the call
};

/** Did every figure in the answer trace back to a tool result? */
export type Verification = {
  grounded: boolean;
  figures_checked: number;
  ungrounded_numbers: string[];
  ungrounded_chw_ids: string[];
  revisions: number;
};

export type AgentRun = {
  name: string;
  findings: string;
  tool_calls: number;
  ms: number;
};

/** Model calls, tokens and estimated USD cost behind one answer. */
export type Usage = {
  calls: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number | null; // null when the backend has no prices configured
};

/** The multi-agent part of a briefing: who was engaged and what they found. */
export type TeamDetail = {
  route: string[];
  route_reason: string;
  agents: AgentRun[];
  verification: Verification | Record<string, never>;
  usage?: Usage;
};

export type BriefingResponse = {
  answer: string;
  iterations: number;
  tool_calls: number;
  trace_id: string | null;
  trace_url?: string | null; // this run's trace in the Langfuse UI
  plan: PlanStep[];
  answer_doc: AnswerDoc | null;
} & TeamDetail;

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

export async function getHealth(
  opts: { signal?: AbortSignal } = {},
): Promise<LivenessResponse> {
  const res = await fetch(`${BACKEND_URL}/healthz`, { signal: opts.signal });
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
  langfuse_url: string | null; // Langfuse project page; null when tracing is off
};

export async function getReady(
  opts: { signal?: AbortSignal } = {},
): Promise<ReadinessResponse> {
  const res = await fetch(`${BACKEND_URL}/readyz`, { signal: opts.signal });
  if (res.status !== 200 && res.status !== 503) {
    throw new Error(`readyz failed: ${res.status}`);
  }
  return (await res.json()) as ReadinessResponse;
}

// ─── /chws/{id} (detail drawer) ─────────────────────────────────────────────

export type DailyCount = {
  date: string; // YYYY-MM-DD
  encounter_count: number;
};

export type ChwDetail = {
  chw_id: string;
  practitioner_uuid: string;
  name: string | null;
  ward: string | null;
  encounters_30d: number;
  encounters_7d: number;
  patients_30d: number;
  daily: DailyCount[]; // last 7 days, oldest first
};

export async function getChwDetail(
  chwId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<ChwDetail> {
  const res = await fetch(
    `${BACKEND_URL}/chws/${encodeURIComponent(chwId)}`,
    { signal: opts.signal },
  );
  if (res.status === 404) throw new Error(`${chwId} is not on the roster.`);
  if (!res.ok) throw new Error(`CHW lookup failed: ${res.status}`);
  return (await res.json()) as ChwDetail;
}

// ─── /chws (roster) and /anomalies ──────────────────────────────────────────

export type ActivityPattern = "stopped_early" | "started_late" | "no_visits";

export type RosterRow = {
  chw_id: string;
  name: string | null;
  ward: string | null;
  encounters_30d: number;
  encounters_7d: number;
  pattern: ActivityPattern | null;
  last_active: string | null;
};

export async function getRoster(
  opts: { signal?: AbortSignal } = {},
): Promise<RosterRow[]> {
  const res = await fetch(`${BACKEND_URL}/chws`, { signal: opts.signal });
  if (!res.ok) throw new Error(`Roster lookup failed: ${res.status}`);
  return ((await res.json()) as { chws: RosterRow[] }).chws;
}

export type FeverCluster = {
  ward: string;
  case_count: number;
  malaria_diagnosed: number;
  chw_ids: string[];
  first_date: string;
  last_date: string;
};

export type DangerSignChild = {
  patient_name: string;
  age_months: number;
  respiratory_rate: number;
  temperature_c: number | null;
  chw_id: string | null;
  ward: string | null;
  date: string;
};

export type OverduePatient = {
  patient_name: string;
  last_visit: string;
  return_date: string;
  days_overdue: number;
  pregnant: boolean;
  last_systolic_bp: number | null;
  chw_id: string | null;
  ward: string | null;
};

export type ActivityGap = {
  chw_id: string;
  pattern: ActivityPattern;
  first_active: string | null;
  last_active: string | null;
  weekdays_missed_before_team_last_active: number;
};

export type Anomalies = {
  days: number;
  action_count: number;
  fever_clusters: FeverCluster[];
  children: DangerSignChild[];
  overdue: OverduePatient[];
  activity_gaps: { team_last_active: string | null; rows: ActivityGap[] };
  missing_location: {
    total_missing_location: number;
    rows: { chw_id: string; ward: string | null; missing_location: number; weeks: Record<string, number> }[];
  };
  visits_after_death: {
    rows: { patient_name: string; death_date: string; visit_date: string; chw_id: string | null; ward: string | null }[];
  };
};

export async function getAnomalies(
  opts: { signal?: AbortSignal } = {},
): Promise<Anomalies> {
  const res = await fetch(`${BACKEND_URL}/anomalies`, { signal: opts.signal });
  if (!res.ok) throw new Error(`Anomaly check failed: ${res.status}`);
  return (await res.json()) as Anomalies;
}

// ─── /activity/daily (activity chart) ───────────────────────────────────────

export type DailyActivity = {
  days: number;
  series: DailyCount[]; // oldest first
  total: number;
};

export async function getDailyActivity(
  days: number,
  opts: { signal?: AbortSignal } = {},
): Promise<DailyActivity> {
  const res = await fetch(`${BACKEND_URL}/activity/daily?days=${days}`, {
    signal: opts.signal,
  });
  if (!res.ok) throw new Error(`Activity lookup failed: ${res.status}`);
  return (await res.json()) as DailyActivity;
}

// ─── /briefing/stream (SSE) ─────────────────────────────────────────────────
//
// Mirrors backend/app/agents/briefing.py:StreamEvent. The wire format is
// SSE with named events: route, agent_start, tool_start, tool_done,
// agent_done, verify, response, error. The
// `response` frame carries the same shape as POST /briefing's body so
// callers can render an AnswerDoc when the agent finishes.

export type RouteFrame = {
  kind: "route";
  agents: string[];
  reason?: string;
};

export type AgentStartFrame = { kind: "agent_start"; agent: string };
export type AgentDoneFrame = { kind: "agent_done"; agent: string; ms: number };
export type VerifyFrame = { kind: "verify"; verification: Verification };

export type ToolStartFrame = {
  kind: "tool_start";
  agent: string;
  tool: string;
  args: string;
};

export type ToolDoneFrame = {
  kind: "tool_done";
  agent: string;
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
  trace_url?: string | null; // this run's trace in the Langfuse UI
  answer_doc: AnswerDoc | null;
} & TeamDetail;

export type ErrorFrame = {
  kind: "error";
  message: string;
};

export type StreamFrame =
  | RouteFrame
  | AgentStartFrame
  | AgentDoneFrame
  | VerifyFrame
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
    "route",
    "agent_start",
    "agent_done",
    "verify",
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
