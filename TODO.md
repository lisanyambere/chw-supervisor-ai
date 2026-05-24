# TODO

Living list of outstanding work. Organised by phase (matches README + progress.md)
plus the cross-cutting things that don't slot neatly into a phase.

## Phase 4 — Supervisor frontend (in progress)

- [ ] **SSE streaming** — replace the placeholder thinking row with `/briefing/stream`
  emitting `tool_start` / `tool_done` / `response` events so the plan timeline
  ticks live. Backend + frontend.
- [ ] **Conversation persistence** — drop the reducer into localStorage (start)
  or Postgres so reloads don't wipe history.
- [ ] **CHW detail drawer** — right-side `Sheet`, opened by any `chw-NNN` chip
  or `.ranked__row`. Pulls `count_chw_encounters` + `chw_patient_panel`.
- [ ] **Activity charts view** — 30-bar daily encounter chart with weekend
  tinting and red zero-day bars. First non-conversational view.
- [ ] **CHW roster view** — full 30-row reuse of the ranked-row pattern.
- [ ] **Frontend test infrastructure** — vitest + @testing-library/react. Zero
  tests today. At minimum cover `postBriefing` error path, Composer busy
  state, error fallback UI.
- [ ] **Health check on mount** — call `getHealth()` once at app load, disable
  Composer with "Backend unavailable" message if it fails.
- [ ] **AbortController on requests** — the signal param exists in `postBriefing`
  but is never wired to actual cancellation on unmount.
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

- [ ] **`BACKEND_URL` default is `http://localhost:8001` in `frontend/lib/api.ts`**
  — backend actually serves on `8000`. Frontend will fail out of the box
  unless `NEXT_PUBLIC_BACKEND_URL` is set. Likely a leftover from an
  earlier port plan.
- [ ] **`HealthResponse` type in `frontend/lib/api.ts` is stale** — backend
  split `/healthz` (liveness, returns `{status:"ok"}` only) from `/readyz`
  (the rich shape). The frontend type still expects the rich shape. Also,
  `getHealth()` is currently dead code (no caller).
- [ ] **Encounter idempotency** in `data/load_to_openmrs.py` — patients and
  practitioners are checked by identifier before POST, encounters are not.
  Re-running the loader doubles the encounter rows. Fix: search by
  (patient, period.start, type) before POSTing.
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

- [ ] **Synthea data was reloaded on 2026-05-24** — patient count is 681
  (581 Synthea + 100 OpenMRS demo) and encounter count is ~9952 (some
  residue from prior partial loads). Backend works fine since it filters
  by id_map, but a clean `docker compose down -v && up` would normalise
  this if it ever matters for a demo recording.

## Recently shipped (for context — last 24h)

- [x] Phase 5 observability — `/metrics`, request/tool/LLM histograms,
  Grafana dashboard, Prometheus scrape target.
- [x] `/healthz` (liveness) vs `/readyz` (downstream checks) split.
- [x] `fix(llm)`: disabled openai SDK internal retries, then collapsed
  the tenacity wrapper because the SDK already does it natively.
- [x] `fix(infra)`: OpenMRS docker healthcheck endpoint corrected from
  the 404 `/openmrs/health` to `/openmrs/` (matches upstream distro).
- [x] Repo-level Dockerfile + `.dockerignore` for containerised testing.
