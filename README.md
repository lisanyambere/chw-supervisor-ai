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
| 0 — Infrastructure | **Done** | Docker stack up: OpenMRS 3, Postgres, Redis, Langfuse, Prometheus, Grafana |
| 1 — Synthetic data | **Done** | Synthea + Kenyan localization + CHW overlay + FHIR bulk load (deceased backfill included) |
| 2 — Backend agents | **Done** | FastAPI + LangGraph briefing agent, FHIR client, tool registry, Langfuse traces |
| 3 — Evaluator | **Done** | Rule-based scorers, LLM-as-judge (action + citations), golden-question runner |
| 4 — Supervisor frontend | **In progress** | Next.js 15 + Tailwind shell, typed `/briefing` client, plan timeline, structured answer renderer |
| 5 — Observability | **Done** | Prometheus `/metrics`, request + tool + LLM histograms, Grafana dashboard, `/healthz` + `/readyz` |
| 6 — Polish + deployment | Not started | README, video, VM deploy |

---

## Running services (phase 0)

| Service | URL | Notes |
|---------|-----|-------|
| OpenMRS 3 backend | http://localhost:8080/openmrs | admin / Admin123 |
| OpenMRS 3 frontend | http://localhost:8081 | SPA |
| Langfuse | http://localhost:3100 | Create account on first visit; copy API keys to .env |
| Grafana | http://localhost:3200 | admin / admin |
| Prometheus | http://localhost:9090 | |
| Postgres | localhost:5432 | DBs: community_health, langfuse |
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
| Langfuse healthy | ✓ localhost:3100 |
| OpenMRS REST API | ✓ authenticated |
| OpenMRS FHIR R4 | ✓ CapabilityStatement, fhirVersion 4.0.1 |

## Before Phase 1

- [ ] Create Langfuse account at `http://localhost:3100`, add keys to `.env`
- [ ] Install Java 21: `winget install Microsoft.OpenJDK.21` (Java 8 on machine, Synthea needs 11+)

## Phase 1 — Synthetic data

- [x] Run Synthea (~500 patients, FHIR R4)
- [x] Kenyan localization post-processing (names, addresses, demographics)
- [x] CHW activity overlay with 7 seeded scenarios
- [x] FHIR bulk load into OpenMRS — see [`docs/data-loading.md`](docs/data-loading.md)
- [x] Smoke test: query REST + FHIR for expected patients/CHWs
