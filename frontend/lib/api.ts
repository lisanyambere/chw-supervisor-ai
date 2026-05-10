/**
 * Backend API contract — mirrors backend/app/api/schemas.py.
 *
 * The browser talks to the backend directly. Override the URL with
 * NEXT_PUBLIC_BACKEND_URL when running against a non-default host.
 */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8001";

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

// ─── /healthz ───────────────────────────────────────────────────────────────

export type HealthResponse = {
  status: "ok" | "degraded";
  openmrs: boolean;
  llm_provider: string;
  llm_model: string;
  patients_loaded: number;
  chws_loaded: number;
};

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BACKEND_URL}/healthz`);
  if (!res.ok) throw new Error(`healthz failed: ${res.status}`);
  return (await res.json()) as HealthResponse;
}
