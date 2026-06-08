# TODO

Living list of outstanding work. Organised by phase (matches README + progress.md)
plus the cross-cutting things that don't slot neatly into a phase.

## Next up — recommended order

- **Best for portfolio polish:** Activity charts view (Phase 4 #3). First
  non-chat view, visually distinctive for a video/screenshot. Now unblocked —
  the 2026-06-08 reseed rebases CHW activity to the current date, so a 30-day
  chart actually has bars.
- **Natural follow-on:** CHW roster view (Phase 4 #4). Full 30-row reuse of
  the ranked-row pattern; pairs with the now-shipped detail drawer.
- **Phase 6 kickoff:** Production Dockerfiles + `docker-compose.prod.yml`
  so backend + frontend join the existing langfuse / prometheus / grafana
  stack. Unlocks the VM deploy runbook.

## Phase 4 — Supervisor frontend (in progress)

- [x] **SSE streaming** — `/briefing/stream` emits `tool_start` / `tool_done` /
  `response` events, frontend EventSource wired, plan timeline ticks live.
  Trace id + answer_doc included in final frame. (commits ba4656c, d7c6432, 41a8624)
- [x] **Conversation persistence** — reducer mirrored to localStorage; only
  completed AI turns rehydrate so a mid-run reload can't resurrect a stuck
  spinner. (commit ac7fbc6)
- [x] **CHW detail drawer** — right-side drawer opened by any `chw-NNN` chip
  or ranked row, backed by a new `GET /chw/{id}` endpoint
  (`count_chw_encounters` + `chw_patient_panel`). (commits 1d42d47, 7422b4b)
- [ ] **Activity charts view** — 30-bar daily encounter chart with weekend
  tinting and red zero-day bars. First non-conversational view.
- [ ] **CHW roster view** — full 30-row reuse of the ranked-row pattern.
- [~] **Frontend test infrastructure** — vitest + @testing-library/react
  scaffold landed with api-client tests (postBriefing / getHealth / getReady).
  Still missing: Composer busy state + error fallback component tests.
- [x] **Health check on mount** — calls `getReady()` once at app load with
  an AbortController, disables Composer with a reason-specific message
  ("OpenMRS unreachable" vs "cannot reach service") if it fails. Status
  pill flips to a red "backend down" pulse-dot.
- [x] **AbortController on requests** — `getHealth` / `getReady` now accept
  a `signal`, and the mount probe in `app/page.tsx` aborts on unmount.
  `streamBriefing` already had `closeStream.current` wired to unmount.
  `postBriefing` retains its existing `signal` param (no in-app caller yet).
- [ ] **Mobile pass** — composer / sidebar / drawer responsive.

## Phase 6 — Polish + deployment (not started)

- [ ] **Production Dockerfile for backend** — multi-stage, non-root user,
  pinned deps. Separate from the repo-level Silver-submission Dockerfile.
- [ ] **Frontend production Dockerfile** — Next.js standalone build.
- [ ] **`docker-compose.prod.yml`** — uncomments the `backend` and `frontend`
  services in the main compose. Wired to existing langfuse / prometheus /
  grafana.
- [ ] **GitHub Actions CI** — ruff, mypy, pytest on backend; tsc + vitest on
  frontend; build the docker images.
- [ ] **Deployment runbook** — section in README covering VM setup,
  env-var hand-off, OpenMRS first-boot cost, post-deploy smoke checks.
- [ ] **Configurable timeouts** — backend FHIR/LLM timeouts via env vars
  (currently hard-coded to 30s in the FHIR client).
- [ ] **Implement `scripts/reset-demo.sh`** — currently a 6-line stub.
- [ ] **Implement `scripts/run-demo.py`** — currently a 6-line stub that
  prints "not yet implemented".

## Known bugs / gaps (real, observed)

- [ ] **Practitioner count includes OpenMRS demo providers** — after the
  orphan dedup, `Practitioner?_summary=count` is 42 (30 CHWs + 12 distro
  demo providers). Harmless — the agent only uses the 30 in `id_map` — but a
  clean `docker compose down -v && up` would drop the demo 12.
- [ ] **MySQL → MariaDB alignment** — upstream OpenMRS distro 3.x uses
  `mariadb:10.11.7`, we use `mysql:8.0`. Drop the
  `--log_bin_trust_function_creators=1` workaround if we switch.
- [ ] **Env var name** — upstream uses `OMRS_CONFIG_CREATE_TABLES`; ours
  says `OMRS_CONFIG_CREATE_TABLES_AT_STARTUP`. Probably an alias still
  honoured by the image but worth aligning.

## Test coverage gaps

- [ ] **API integration tests** for `/briefing` and `/readyz` against the
  real router (currently only the agents/tools are tested in isolation).
- [ ] **`app/llm/client.py` config-validation paths** — missing env vars
  raising `RuntimeError` is untested.
- [ ] **`app/core/config.py` settings validation** — bounds (ge/le) untested.
- [ ] **`app/observability/langfuse.py`** — disabled-when-keys-missing path
  is untested.
- [ ] **`app/fhir/id_map.py`** — missing-fixture fallback is untested.

## Data / infra state to be aware of

- **Reseeded 2026-06-08 — now idempotent and current-dated.** OpenMRS holds
  631 patients (581 tracked in `id_map` + 50 demo), 42 practitioners (30 CHWs
  + 12 demo), 5,925 encounters (4,649 CHW + demo residue). The loader rebases
  CHW encounters so the newest visit lands on **today** — activity now spans
  **14 May → 8 Jun 2026**, which is what keeps the "last 7/30 days" tools and
  the activity chart non-empty. Re-running the loader is safe: practitioners
  are searched by identifier before POST and encounters by (patient, start),
  so no more doubling or orphan providers. (commits 9c30f00, 51f7a69)

## Recently shipped (for context)

- [x] `fix(data)`: idempotent current-date reseed — `rebase_encounter_dates()`
  shifts CHW visits so the newest lands on today; `post_practitioners()` now
  checks identifier-before-POST; smoke test samples by participant instead of
  the demo-polluted global feed; retired 36 orphan practitioners. (9c30f00,
  51f7a69)
- [x] `feat(data)`: encounter idempotency — search by (patient, period.start)
  before POST so a reload no longer doubles rows. (46ff66b)
- [x] `feat(frontend)`: CHW detail drawer + `GET /chw/{id}` endpoint. (1d42d47,
  7422b4b)
- [x] `feat(frontend)`: conversation persistence to localStorage. (ac7fbc6)
- [x] `fix(agents/tools)`: surfaced three swallowed exception paths — tool
  errors, Langfuse span-update failures, and unknown formatter section kinds
  now log instead of vanishing silently. (779538f, 723eab9, 26f75f1)
- [x] `feat`: SSE `/briefing/stream` end-to-end — backend emits
  `tool_start` / `tool_done` / `response` (with trace_id + answer_doc),
  frontend EventSource wired so plan timeline ticks live.
- [x] Phase 5 observability — `/metrics`, request/tool/LLM histograms,
  Grafana dashboard, Prometheus scrape target; `/healthz` vs `/readyz` split.
