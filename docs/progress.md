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

**Result:** **581 patients · 30 CHWs · 4,649 encounters** loaded, spanning
**6 Apr → 1 May 2026**. See `docs/data-loading.md` for operational details.

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

## Phase 3 — Multi-agent + frontend (planned)

- **More tools** — overdue ANC visits, immunization gaps, defaulters, time
  since last home visit, visits per day.
- **Multi-agent split** — supervisor briefing agent + patient lookup agent,
  orchestrated with LangGraph.
- **Evaluators** — `app/evaluators/` scoring each response on groundedness,
  citation discipline, and tool-plan sanity. Push scores to Langfuse.
- **Frontend** — wire the existing `frontend/` Next.js scaffold to `/briefing`.
- **Docker packaging** — replace local uvicorn with a container in
  `infra/docker-compose.yml`.
