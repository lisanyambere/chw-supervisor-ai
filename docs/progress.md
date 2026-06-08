# Project Progress

This is a running log of what's been built. Each phase corresponds to a slice
of the architecture in the top-level `README.md`.

---

## Phase 0 — Infrastructure ✅

- `infra/docker-compose.yml` brings up OpenMRS (Tomcat + MariaDB), Postgres for
  the application database, Redis, Langfuse (web + worker + Clickhouse + minio),
  Grafana, Prometheus.
- OpenMRS heap tuned to `-Xms512m -Xmx1536m` (`infra/docker-compose.yml`) so the
  FHIR module survives bulk loads on small dev hosts.
- `make.ps1` / `Makefile` wrap the common workflows.

## Phase 1 — Synthetic data ✅

Goal: a believable Kakamega CHW dataset loaded into OpenMRS via FHIR R4 so the
agent has something real to reason over.

**Pipeline (`data/`):**
1. **Synthea generation** — `data/synthea/generate.sh` produces ~600 patient
   bundles.
2. **Kenyan localization** — Python post-processing rewrites names, addresses,
   phone numbers, and demographics to plausible Kakamega values. Outputs land in
   `data/fixtures/localized/`.
3. **CHW activity overlay** — `data/chw_overlay/generate_chw_activity.py`
   creates 30 CHW Practitioners and 7 seeded behavioral scenarios (top
   performers, defaulters, vacation absences, deceased patients, etc.) producing
   `data/fixtures/chw/chw-bundle-NNN.json`.
4. **Bulk load** — `data/load_to_openmrs.py` POSTs each resource individually
   (FHIR transaction bundles cannot upsert with client-supplied UUIDs in
   OpenMRS), captures server-assigned UUIDs, and writes
   `data/fixtures/id_map.json` mapping Synthea/local ids → OpenMRS UUIDs.

**Quirks discovered & worked around:**
- OpenMRS FHIR2 module's `fhir2.upsert.supported.resources` only applies to
  `Task` and `MedicationDispense` — not `Patient`/`Practitioner`/`Encounter`.
  Loader uses POST + UUID capture instead of PUT-with-id.
- `Patient.identifier` must include a `use=official` entry whose type is a real
  OpenMRS `PatientIdentifierType`. We use **"Legacy ID"** (no validator, no
  required Location) and stash the original Synthea UUID there.
- `Encounter.type[].coding[].code` must be the **UUID** of an existing
  `EncounterType` ("Visit Note").

**Result:** **581 patients · 30 CHWs · 4,649 encounters** loaded. The loader
rebases CHW encounter dates on each run so the newest visit lands on **today**
(as of the 2026-06-08 reseed the window is **14 May → 8 Jun 2026**), keeping the
agent's "last N days" tools and the activity chart non-empty. Reseeds are
idempotent — practitioners are searched by identifier before POST and encounters
by (patient, period.start), so a re-run no longer doubles rows or spawns orphan
providers. See `docs/data-loading.md` for operational details.

---

## Phase 2 — Backend agent + API ✅

Goal: a FastAPI service that can answer a supervisor's natural-language question
by tool-calling the OpenMRS FHIR layer through an LLM.

### Architecture

```
backend/app/
├── core/           Settings (Pydantic), structlog config
├── fhir/           Async FHIR client + IdMap loader
├── llm/            Provider-agnostic LLM (OpenRouter / Azure OpenAI)
├── tools/          @tool registry + chw + patient tools
├── agents/         ReAct-style briefing agent (LangGraph deferred to Phase 3)
├── observability/  Langfuse v4 OTel tracing
└── api/            FastAPI app — /healthz + /briefing
```

### Key decisions

- **OpenAI SDK for both providers.** OpenRouter and Azure OpenAI are both
  OpenAI-compatible, so we use a single `AsyncOpenAI` instance with the right
  `base_url`. No `langchain` until we have a clear need for graph-style
  orchestration.
- **Provider switch via env var.** `LLM_PROVIDER=openrouter|azure` is the only
  thing that changes between providers. Validated end-to-end with
  `moonshotai/kimi-k2.6` (OpenRouter) and `gpt-5.5` (Azure). Numbers match
  exactly across providers.
- **Tool registry pattern.** A `@tool(name, description, parameters)` decorator
  registers callables in a module-level registry; `Tool.to_openai()` emits the
  function-calling JSON schema. New tools = drop a file in `app/tools/` and
  re-export.
- **ReAct loop, not LangGraph (yet).** `app/agents/briefing.py` runs a bounded
  iteration loop: LLM → tool calls (parallel via `asyncio.gather`) → LLM. Cap
  is 6 turns. LangGraph can replace this when multi-agent reasoning lands in
  Phase 3.
- **Configurable lookback window.** The seeded data ends on 1 May 2026; today's
  date may not always intersect "last 7 days". `BRIEFING_DEFAULT_LOOKBACK_DAYS`
  (default 30) drives both the system prompt and the `days` arg the agent
  passes to tools.
- **Langfuse v4 with OTel.** `start_as_current_observation(as_type="agent" |
  "generation" | "tool")` wraps the agent root, each LLM iteration (with token
  usage), and each tool call. Disabled in tests. Auto-flush on FastAPI
  shutdown.
- **Provider quirks.** GPT-5 family rejects custom `temperature` ⇒ per-provider
  `default_temperature`; Azure builder uses `None` so the field is omitted.

### Tools (so far)

| Tool | Purpose |
|---|---|
| `list_chws` | Catalog of CHW ids and OpenMRS UUIDs |
| `count_chw_encounters(chw_id, days)` | FHIR `_summary=count` for a CHW over a window |
| `team_activity_summary(days)` | Per-CHW counts + min/max/mean/total stats |
| `get_patient_summary(patient_uuid, encounter_limit)` | Patient + recent encounters |

### API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | OpenMRS reachability + LLM provider/model + id_map sizes |
| `POST` | `/briefing` | Run the briefing agent; returns answer + trace |

### Tests

`pytest tests` — **11/11 passing**.

- `tests/unit/test_tools_chw.py` — tool registry behavior (4 tests)
- `tests/unit/test_fhir_client.py` — respx-mocked FHIR client: count, paging,
  max_pages cap, read, 4xx no-retry, 5xx-then-success (6 tests)
- `tests/integration/test_briefing_agent.py` — `run_briefing` driven by a
  scripted FakeLLM + FakeFhir, asserts trace shape + system-prompt templating
  (1 test)

### Live demo (10 May 2026, 30-day lookback)

> *"Quick supervisor check — name top 2 and bottom 2 CHWs."*
>
> - **Top 2:** chw-009 (140), chw-019 (140)
> - **Bottom 2:** chw-002 (16), chw-001 (99)
> - **Team mean:** ~125 encounters
> - **Action:** chw-002 is a major outlier; check on chw-001 next.

Same answer from both `moonshotai/kimi-k2.6` and `gpt-5.5`.

---

## Phase 3 — Evaluators + richer tracing 🚧

### What landed

- **Reasoning capture in Langfuse.** `backend/app/agents/briefing.py` now
  attaches `reasoning` / `reasoning_content` (when the model emits it), the
  per-iteration tool plan, and the iteration index as `metadata` on every
  `llm.chat.iterN` generation span. The agent root span gets a `tool_plan`
  array too, so the dashboard can filter on "any briefing that called
  `count_chw_encounters`". `BriefingResult` now carries `trace_id` so
  evaluator scores can be attached to the same Langfuse trace.
- **Langfuse container upgraded** to the current release after older traces
  weren't surfacing. New API keys live in `.env`; v4 SDK paths
  (`start_as_current_observation`, `create_score`) confirmed working.
- **Rule-based evaluators** in `backend/app/evaluators/`:

  | Scorer | What it catches | Notes |
  |---|---|---|
  | `numeric_fidelity` | Made-up counts / IDs in the answer | Allowlists tiny ints + the default lookback (30); strips thousands separators |
  | `entity_grounding` | `chw-NNN` ids cited but not present in any tool result | |
  | `plan_minimality` | Bloated plans, duplicate (name, args) tool calls | Per-question budget |
  | `conciseness` | Bullet count outside the 4–8 system-prompt range | Short single-fact prose answers (≤240 chars) get a pass |
  | `iteration_efficiency` | ReAct turns burned per answer | 1.0 at 1 iteration, 0.0 at the cap |

  All scorers are pure, LLM-free, and unit-tested (`tests/unit/test_evaluators.py`,
  18 tests). LLM-as-judge scorers can layer on later without changing this
  surface.
- **Golden-question runner** at `scripts/run_evals.py`:
  - 5 starter questions covering top/bottom, single-CHW lookup, anomaly
    detection, team mean, and roster size.
  - Runs `run_briefing()` against the live FastAPI/FHIR/LLM, prints a
    per-question score table, and pushes each `EvalScore` to Langfuse via
    `lf.create_score(trace_id=...)`.
  - Returns non-zero if any score < 0.5 → drop-in for CI.
- **Tests:** **29/29** passing (11 prior + 18 evaluator).

### First eval run (Azure `gpt-5.5`, 30-day lookback)

| question | numeric_fidelity | entity_grounding | plan_minimality | conciseness | iteration_efficiency |
|---|---|---|---|---|---|
| g1 top/bottom | 0.83 | 1.00 | 1.00 | 1.00 | 0.80 |
| g2 chw-002 count | 1.00 | 1.00 | 1.00 | 1.00 | 0.60 |
| g3 anomalies | 0.80 | 1.00 | 0.67 | 1.00 | 0.60 |
| g4 team mean | 0.80 | 1.00 | 1.00 | 1.00 | 0.80 |
| g5 list CHWs | 1.00 | 1.00 | 0.50 | 1.00 | 0.80 |

`numeric_fidelity` < 1.0 cases were the model rounding (`124.6` vs `124.57`) —
working as intended (strict). `plan_minimality` dings cases where the agent
called `list_chws` to resolve an id it could have inferred — useful signal
for a future system-prompt tweak.

### Tool surface — round 2 ✅

Five new tools landed in this slice. All registered via the existing `@tool`
decorator and wired into the briefing agent automatically.

| Tool | What it answers |
|---|---|
| `chw_inactivity(days, max_count=0)` | "Who hasn't logged anything?" — returns CHWs at or below a threshold. Parallel FHIR counts via `asyncio.gather` |
| `visits_by_day(days, chw_id?)` | Daily encounter histogram, team-wide or per-CHW. Catches Friday slumps, weekend gaps, sudden drops |
| `chw_patient_panel(chw_id, days, limit)` | Distinct patients a CHW has visited recently, with per-patient counts and last-encounter date |
| `find_patient(query, limit)` | Name-based Patient search so the supervisor can ask about people, not UUIDs |
| `recent_deaths(days, limit)` | Patients with `deceased` set in the window — explains caseload drops |

**Live verification (10 May 2026):**
- *"Which CHWs are completely inactive in the last 7 days, and what's the daily
  trend?"* → agent called `team_activity_summary` + `chw_inactivity` +
  `visits_by_day` in parallel and correctly diagnosed a team-wide stoppage on
  May 1 (the seeded data ends there). The `visits_by_day` series is what made
  the model reach the right conclusion instead of blaming individual CHWs.
- *"chw-009's patient panel last 30 days"* → 20 distinct patients with
  per-patient encounter counts and last-seen timestamps. Two-tool plan:
  `team_activity_summary` then `chw_patient_panel`.

**Data fix — deceased patient backfill (10 May 2026):** `recent_deaths`
initially returned 0 because the Phase-1 loader was silently stripping
`deceasedDateTime` to dodge the 422 — OpenMRS core's `PatientValidator`
requires a `causeOfDeath` concept whenever `dead=true`, but the FHIR R4
Patient resource (and the FHIR2 module's translator) has no such field, so
the validator can never be satisfied through FHIR alone. Fixed by making the
loader two-pass: POST the Patient via FHIR (alive), then POST `{dead,
deathDate, causeOfDeath}` to `/ws/rest/v1/person/{uuid}` with a default
"Death of unknown cause" concept (`142917AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`).
Re-ran loader: 81/81 deaths backfilled, FHIR `Patient?death-date=` now
returns the full set, and the agent answers *"Have there been any patient
deaths in the last year?"* with **7 deaths**, named, dated, and bucketed by
sub-county.

**LLM-as-judge scorers (10 May 2026):** added two judge metrics that
complement the deterministic ones — `judge_action_orientation` (does the
answer name a concrete next step?) and `judge_citation_discipline` (is every
claim traceable to the trace?). Implemented in `app/evaluators/judge.py`
as async scorers that call the configured LLM in JSON mode
(`response_format={"type": "json_object"}`); they share the agent's provider
so swapping to a stronger judge model is just an env change. Trace events
are summarised into a budgeted text block (per-result 2.5kB, total 8kB) so
the judge can verify list-style results without the prompt blowing up.
Unit-tested with an injectable `judge_fn` stub — no network required.

Live baseline across all 5 golden questions:

| metric | mean |
|---|---|
| numeric_fidelity        | 0.98 |
| entity_grounding        | 1.00 |
| plan_minimality         | 0.78 |
| conciseness             | 1.00 |
| iteration_efficiency    | 0.76 |
| **judge_action_orientation** | **0.98** |
| **judge_citation_discipline** | **0.98** |

Both judges correctly singled out the most complex question ("anything
unusual?") as the weakest at 0.90, while giving focused lookups 1.00 — the
rubric is calibrated, not just a thumbs-up generator. All 7 scores are
posted to Langfuse per trace via `lf.create_score(trace_id=...)`.

**Tests:** 55/55 passing (43 prior + 12 new in `test_evaluator_judges.py`).
*(Suite has since grown to **89/89** — see Phase 4/5.)*

---

## Phase 4 — Supervisor workspace frontend (in progress)

Goal: stand up the visible product. Until now the agent only existed as
`curl localhost:8001/briefing`; this phase ports the design-handoff
prototype (`docs/design_handoff/`) into a real Next.js app so the briefing,
the tool plan, and every CHW the model names are inspectable from a
browser.

**Backend changes shipped to support the UI** (commit `e31b4c2`):
- `TraceEvent.ms` + new `BriefingResult.plan` — every tool call is wall-clock
  timed via `time.perf_counter()` and paired with its `tool_result`. The
  derived `PlanStep(tool, args, ms, rows)` is what the UI's plan-timeline
  card consumes; no client-side derivation needed.
- New `app/agents/formatter.py` — second LLM pass that re-renders the
  agent's markdown answer into the typed schema from the design handoff
  (`headline / period / sections[stat-row|callout|ranked|panel] / sources`).
  Strict JSON mode, defensive parse, opt-out via `include_answer_doc=false`
  for cheap markdown-only runs. The markdown answer stays as a fallback so
  old callers keep working.
- `/briefing` now returns `{answer, answer_doc, plan, trace, trace_id, ...}`.
- CORS allowlist for `localhost:3000` + `127.0.0.1:3000`.

**Frontend** — Next.js 15 (App Router) + Tailwind 3 + self-hosted Inter
Tight / Source Serif 4 / JetBrains Mono via `next/font`. All design-handoff
oklch colour tokens wired through CSS variables and exposed to Tailwind.
Components landed so far, each in its own commit:

| commit | scope |
|---|---|
| `af640f2` | scaffold + design tokens |
| `d534ae5` | typed `/briefing` API client |
| `3a401a2` | app shell — sidebar + topbar |
| `bf589fc` | empty-state hero + suggestion grid |
| `b323d88` | sticky composer with auto-grow textarea |
| `ef591f0` | tool-plan timeline (running / done state machine) |
| `1de131a` | typed answer renderer (4 section kinds + chw chips + trace footer) |
| `0665b55` | conversation turns wired to live `/briefing` |

End-to-end works: clicking "Generate Monday briefing" hits the backend,
shows a placeholder thinking row, then swaps in the real plan card with
backend-measured ms timings and the structured answer with grounded
`chw-NNN` chips. Every answer card carries a `trace · {short_id} ↗` link
to the Langfuse trace it came from.

### Shipped since

- ✅ **SSE streaming** — `/briefing/stream` emits `tool_start` / `tool_done` /
  `response` (with `trace_id` + `answer_doc`); the frontend EventSource ticks
  the plan timeline live and swaps in the structured answer on the final frame.
- ✅ **Conversation persistence** — the reducer is mirrored to localStorage;
  only completed AI turns rehydrate, so a mid-run reload can't resurrect a
  stuck spinner.
- ✅ **CHW detail drawer** — a right-side drawer opens from any `chw-NNN` chip
  or ranked row, backed by a new `GET /chw/{id}` endpoint that fans out to
  `count_chw_encounters` + `chw_patient_panel`.
- ✅ **Backend test suite → 89/89** — added coverage for the SSE stream, the
  typed formatter, `/healthz`/`/readyz`, Prometheus metrics, patient tools,
  and tool-call metrics.

### Still open

- **Activity charts view** — 30-bar daily encounter chart with weekend
  tinting and red zero-day bars; first non-conversational view. *(in progress)*
- **CHW roster view** — full 30-row reuse of the ranked-row pattern.
- **Component tests** — vitest + api-client tests exist; the Composer busy
  state and the error-fallback UI are still uncovered.

## Phase 5 — Observability (done)

Prometheus + Grafana wired against the FastAPI backend.

**What landed:**
- `/metrics` endpoint exposing the default registry plus three service
  metrics: `http_request_duration_seconds` (labelled by method / path
  template / status), `tool_call_duration_seconds` (by tool / outcome),
  `llm_call_duration_seconds` (by provider / outcome).
- Request-latency middleware that bypasses `/metrics` itself and buckets
  unmatched paths under a single label.
- `prometheus.yml` scrapes the backend via `host.docker.internal:8000`
  (host-running backend; switches to `backend:8000` when it moves into
  compose).
- Provisioned Grafana datasource (uid `prometheus`) and dashboard
  `cha-ai-backend` with five panels: backend up, HTTP request rate by
  status, HTTP p95 by path, tool call rate, LLM call rate.
- Split `/healthz` (dependency-free liveness) from `/readyz`
  (probes OpenMRS + LLM, returns 503 when any required dep is down).
- Refactored LLM client to drop the redundant tenacity wrapper —
  `c75a356` revealed it was double-retrying with the openai SDK, and
  `4e8d769` collapsed everything onto SDK-native retries.

### Phase 6+ roadmap

- **More tools** — overdue ANC visits, immunization gaps, defaulters, time
  since last home visit, visits per day.
- **Multi-agent split** — supervisor briefing agent + patient lookup agent,
  orchestrated with LangGraph.
- **Docker packaging** — replace local uvicorn with a container in
  `infra/docker-compose.yml`; add a `frontend` service mapping `3000:3000`.
