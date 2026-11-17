# TODO

Living list of outstanding work. Organised by phase (matches README + progress.md)
plus the cross-cutting things that don't slot neatly into a phase.

## Next up — recommended order

See `docs/portfolio-handover.md` for the portfolio plan. Remaining, in order:

- **Record the video and screenshots** (re-seed first so the demo week is current).
- **Draft the case-study text.**
- **Tell the supervisor when unlocated visits happened.** The scenario eval's
  one consistent miss: `visits_missing_location` reports how many, not which
  week, so the briefing cannot say they are recent.
- **Calibrate the recall judge** against a human rating of a sample, and add
  a false-alarm measure; the eval currently scores recall only.

## Phase 4 — Supervisor frontend (in progress)

- [x] **SSE streaming** — `/briefing/stream` emits `tool_start` / `tool_done` /
  `response` events, frontend EventSource wired, plan timeline ticks live.
  Trace id + answer_doc included in final frame. (commits ba4656c, d7c6432, 41a8624)
- [ ] **Conversation persistence** — drop the reducer into localStorage (start)
  or Postgres so reloads don't wipe history.
- [x] **CHW detail drawer** — opened by any `chw-NNN` chip or ranked row,
  backed by `GET /chws/{chw_id}`.
- [x] **Briefing-team timeline** — router, one lane per specialist, lead
  analyst and the grounding check, streamed live.
- [x] **Activity charts view** — 30-day chart backed by `GET /activity/daily`,
  weekends muted, missed weekdays marked, table view.
- [ ] **CHW roster view** — full 30-row reuse of the ranked-row pattern.
- [ ] **Frontend test infrastructure** — vitest + @testing-library/react. Zero
  tests today. At minimum cover `postBriefing` error path, Composer busy
  state, error fallback UI.
- [x] **Health check on mount** — calls `getReady()` once at app load with
  an AbortController, disables Composer with a reason-specific message
  ("OpenMRS unreachable" vs "cannot reach service") if it fails. Status
  pill flips to a red "backend down" pulse-dot.
- [x] **AbortController on requests** — `getHealth` / `getReady` now accept
  a `signal`, and the mount probe in `app/page.tsx` aborts on unmount.
  `streamBriefing` already had `closeStream.current` wired to unmount.
  `postBriefing` retains its existing `signal` param (no in-app caller yet).
- [x] **Mobile pass** — icon nav strip, team timeline, drawer, chart and
  composer checked at 390px.

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

- [ ] **Silent Langfuse exception handlers** in `agents/briefing.py:154,
  308, 343` — should `log.debug(...)` so trace failures aren't invisible.
- [ ] **Tool registry catches all errors with no log** in
  `tools/registry.py:78` — wrap with `log.warning("tool.failed", ...)`
  so stack traces aren't lost.
- [ ] **Formatter silently drops unknown section kinds** in
  `agents/formatter.py:305` — currently filters `None` out of the section
  list, so a new LLM-emitted kind vanishes. Either add a fallback shape
  or `log.warning`.
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

- The seeded demo week is the latest complete week before the day the data
  was generated (currently 9–15 Nov 2026). Tools look back from today, so
  re-seed (`down -v`, then `scripts/seed.sh`) shortly before recording.
- Six tests in `tests/unit/test_llm_client.py` fail with connection errors:
  the installed openai SDK no longer goes through the transport respx mocks.

## Recently shipped (for context — last 24h)

- [x] `feat`: SSE `/briefing/stream` end-to-end — backend emits
  `tool_start` / `tool_done` / `response` (with trace_id + answer_doc),
  frontend EventSource wired so plan timeline ticks live.
- [x] `fix(frontend)`: `BACKEND_URL` default 8001→8000; split `HealthResponse`
  into `LivenessResponse` + `ReadinessResponse` matching the backend, plus
  a `getReady()` function that doesn't throw on 503.
- [x] `feat(frontend)`: vitest + @testing-library scaffold, 9 tests covering
  postBriefing / getHealth / getReady.
- [x] Phase 5 observability — `/metrics`, request/tool/LLM histograms,
  Grafana dashboard, Prometheus scrape target.
- [x] `/healthz` (liveness) vs `/readyz` (downstream checks) split.
- [x] `fix(llm)`: disabled openai SDK internal retries, then collapsed
  the tenacity wrapper because the SDK already does it natively.
- [x] `fix(infra)`: OpenMRS docker healthcheck endpoint corrected from
  the 404 `/openmrs/health` to `/openmrs/` (matches upstream distro).
- [x] Repo-level Dockerfile + `.dockerignore` for containerised testing.
