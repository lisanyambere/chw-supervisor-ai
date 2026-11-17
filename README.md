# Community Health AI Assistant

A multi-agent AI system that gives community health program supervisors a Monday-morning briefing
by reading patient and CHW activity data from OpenMRS 3, running it through a LangGraph pipeline,
and surfacing actionable summaries, flagged households, team anomalies, and data quality issues —
with full observability via Langfuse and Prometheus/Grafana.

> **Portfolio project — synthetic data only, no real patients.**

---

## Quick start

```powershell
cp .env.example .env
# Fill in OPENROUTER_API_KEY

# Windows (no make):
.\scripts\make.ps1 up

# With make:
make up
```

---

## Build status

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Infrastructure | **Done** | Docker stack up: OpenMRS 3, Postgres, Redis, Prometheus, Grafana; tracing via Langfuse Cloud |
| 1 — Synthetic data | **Done** | Synthea + Kenyan localization + CHW overlay + FHIR bulk load (deceased backfill included) |
| 2 — Backend agents | **Done** | FastAPI + multi-agent LangGraph briefing team, FHIR client, tool registry, Langfuse traces |
| 3 — Evaluator | **Done** | Rule-based scorers, LLM-as-judge, in-graph grounding verifier, scenario-recall evaluation |
| 4 — Supervisor frontend | **In progress** | Next.js 15 + Tailwind shell, live briefing-team timeline, structured answer renderer, CHW detail drawer |
| 5 — Observability | **Done** | Prometheus `/metrics`, request + tool + LLM histograms, Grafana dashboard, `/healthz` + `/readyz` |
| 6 — Polish + deployment | Not started | README, video, VM deploy |

---

## How a briefing is produced

```
question → router ─┬→ team activity ──┐
                   ├→ clinical signals ┼→ lead analyst → verifier → answer
                   └→ data quality ───┘        ↑            │
                                               └── rewrite ─┘  (at most once)
```

- **Router** engages only the specialists a question needs.
- **Specialists** run in parallel, each a tool-calling agent over its own FHIR
  tools: encounter counts and working-day gaps; fever cases by ward, child
  danger signs and overdue follow-ups; visits with no location or logged
  after a recorded death.
- **Lead analyst** merges their findings, most urgent first.
- **Verifier** is deterministic: every number and CHW id in the answer must
  appear in a tool result, or the draft goes back for one rewrite.

The graph is in `backend/app/agents/graph.py`. The frontend streams each step.

### Evaluation

The data generator plants seven scenarios (a fever cluster, a CHW who stops
mid-week, overdue pregnancy follow-ups, and so on) and records them in
`data/fixtures/scenarios.json`. `scripts/run_scenario_eval.py` runs the full
briefing several times and scores how many each briefing surfaces. Latest
run: **31 of 35** scenario findings judged conveyed over five runs, every
answer passing the grounding check, about 28 s per briefing. Reports, with
what the numbers do and do not show, are in [`docs/evals/`](docs/evals/).

---

## Running services (phase 0)

| Service | URL | Notes |
|---------|-----|-------|
| OpenMRS 3 backend | http://localhost:8080/openmrs | admin / Admin123 |
| OpenMRS 3 frontend | http://localhost:8081 | SPA |
| Langfuse Cloud | https://us.cloud.langfuse.com | Create a project; copy API keys to .env |
| Grafana | http://localhost:3200 | admin / admin |
| Prometheus | http://localhost:9090 | |
| Postgres | localhost:5432 | DB: community_health |
| Redis | localhost:6379 | |

---

## Phase 0 notes

**OpenMRS first-boot:** Takes 10-15 minutes on first `make up` — it runs hundreds of Liquibase
database migrations. Subsequent restarts are fast (2-3 min). The runtime properties file is
pre-mounted at `infra/openmrs/openmrs-runtime.properties` to bypass the setup wizard.

**Port conflict:** If Redis fails to start, check for other containers on port 6379
(`docker ps | grep 6379`) and stop them before running `make up`.

**Memory:** With 16GB RAM, bring up OpenMRS first and leave it running, then bounce the app
services separately to avoid pressure:
```powershell
.\scripts\make.ps1 openmrs-up   # once, leave running
.\scripts\make.ps1 up           # full stack
```

---

## Phase 0 verification results

| Check | Result |
|-------|--------|
| Postgres healthy | ✓ localhost:5432 |
| Redis healthy | ✓ localhost:6379 |
| Prometheus healthy | ✓ localhost:9090 |
| Grafana healthy | ✓ localhost:3200 |
| Langfuse Cloud reachable | ✓ us.cloud.langfuse.com |
| OpenMRS REST API | ✓ authenticated |
| OpenMRS FHIR R4 | ✓ CapabilityStatement, fhirVersion 4.0.1 |

## Before Phase 1

- [ ] Create a Langfuse Cloud project at `https://us.cloud.langfuse.com`, add its keys to `.env`
- [ ] Install Java 21: `winget install Microsoft.OpenJDK.21` (Java 8 on machine, Synthea needs 11+)

## Phase 1 — Synthetic data

- [x] Run Synthea (~500 patients, FHIR R4)
- [x] Kenyan localization post-processing (names, addresses, demographics)
- [x] CHW activity overlay with 7 seeded scenarios
- [x] FHIR bulk load into OpenMRS — see [`docs/data-loading.md`](docs/data-loading.md)
- [x] Smoke test: query REST + FHIR for expected patients/CHWs
