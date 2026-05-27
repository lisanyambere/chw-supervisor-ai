# Data Pipeline

End-to-end contract for getting synthetic patient + CHW activity into OpenMRS
and producing a usable `id_map.json` for the agent.

If you're here because the briefing agent is returning empty results, jump to
[Troubleshooting](#troubleshooting).

## Stages

```
Synthea -> kenyan-localization -> chw_overlay -> load_to_openmrs -> id_map.json
            (data/fixtures/localized)  (data/fixtures/chw)  (live OpenMRS)
```

Orchestrated by `scripts/seed.sh`. Each stage has a strict input/output
contract — if a downstream stage is misbehaving, check the upstream output
first.

### 1. Synthea generation

- **Script:** `data/synthea/generate.sh`
- **Reads:** Synthea config; runs Java synthea-with-load JAR.
- **Writes:** raw FHIR R4 bundles to `data/synthea/output/fhir/`.
- **Contract:** each bundle has one `Patient` plus N `Encounter` /
  `Observation` / `Condition` etc. resources. Encounter participants
  reference practitioners by NPI search ref:
  `Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|<npi>`. **These
  participants are discarded later** — the loader never imports them.
- **Tweakable:** patient count, seed, dates.

### 2. Kenyan localization

- **Script:** `data/synthea/kenyan-localization/localize.py`
- **Reads:** `data/synthea/output/fhir/*.json`
- **Writes:** `data/fixtures/localized/*.json`
- **Contract:** rewrites names, addresses, ward extensions in-place. Bundle
  shape and resource IDs are preserved. Encounter participants still carry
  the upstream NPI search refs (not rewritten — they're going to be
  discarded).

### 3. CHW activity overlay

- **Script:** `data/chw_overlay/generate_chw_activity.py`
- **Reads:** `data/fixtures/localized/*.json` (for the list of patient IDs only).
- **Writes:** `data/fixtures/chw/chw-bundle-NNN.json` (transaction bundles,
  200 resources per file).
- **Contract:** produces ~30 `Practitioner` resources with stable IDs
  (`chw-001` .. `chw-030`) and ~5,000 `Encounter` resources whose
  `participant[0].individual.reference` is `Practitioner/chw-NNN`. Also
  emits the 7 seeded demo scenarios (fever cluster, ANC overdue, etc.).
- **Seed:** `SEED = 42` — deterministic across runs.

### 4. Load to OpenMRS

- **Script:** `data/load_to_openmrs.py`
- **Reads:** `data/fixtures/localized/` for patients (Patient resources only);
  `data/fixtures/chw/` for practitioners and encounters.
- **Writes:** live OpenMRS via FHIR R4 POSTs and REST patches; emits
  `data/fixtures/id_map.json` with the `{chw_id|synthea_uuid -> openmrs_uuid}`
  mappings the agent uses at runtime.
- **Phases:**
  1. POST Patients (FHIR), capturing `synthea_uuid -> server_uuid`.
  2. Backfill deceased markers (REST — FHIR R4 Patient can't carry
     `causeOfDeath`).
  3. POST Practitioners (FHIR), capturing `chw_id -> server_uuid`.
  4. POST Encounters (FHIR). Each encounter is checked for an existing
     `(patient, period.start)` match first and skipped if present
     (idempotent re-runs).
- **Contract on output id_map:** every UUID in this file MUST resolve via
  a live `GET /<resource>/{uuid}` call. The smoke test verifies this.

## Mandatory reset procedure

**You MUST `down -v` the OpenMRS stack before re-seeding.** Anything else
risks the stale-UUID drift bug that broke this project once already:

```
docker compose -f infra/docker-compose.openmrs.yml down -v
docker compose -f infra/docker-compose.openmrs.yml up -d
# wait ~10-15 min for Liquibase migrations + first-boot setup
docker logs -f infra-openmrs-backend-1   # tail until "Started Spring Boot"
bash scripts/seed.sh
```

### Why `-v` is non-negotiable

OpenMRS persists state in a Docker volume. Without `-v`:

- Old `Patient` / `Practitioner` rows stay.
- Re-running the loader creates *new* server UUIDs for the same logical
  entities (the FHIR POSTs duplicate, idempotency only covers identifier
  conflicts).
- New encounters get posted referencing the *new* practitioner UUIDs.
- Old encounters (with old practitioner UUIDs) still exist but their
  participant references become dangling. OpenMRS silently scrubs them.
- `id_map.json` ends up reflecting whatever was POSTed last, but
  half the data behind it doesn't match. Smoke test will fail.

If you skipped `-v` and the smoke test reports `Participant round-trip:
<50%` or `Practitioner UUIDs resolve: <total`, you have to reset properly
and re-run.

## Smoke test

Runs automatically at the end of `data/load_to_openmrs.py`. Exits non-zero
on failure so `scripts/seed.sh` halts.

Checks:

| Check | Pass criterion | What a failure means |
|---|---|---|
| Counts | informational only | — |
| Participant round-trip | ≥50% of 20 sampled encounters have a `participant` block on FHIR readback | Encounters posted referencing non-existent practitioner UUIDs — almost always a stale-DB problem |
| Practitioner UUIDs resolve | 100% of `chw_map` reads back via `GET /Practitioner/{uuid}` | id_map points at UUIDs the DB doesn't have. Reset and reseed |
| Patient UUIDs resolve | 100% of 20 sampled patients read back | Same — drift between id_map and live DB |

## Troubleshooting

### Agent returns empty CHW activity, briefings are vague

Likely the smoke test was never run or was skipped. Verify manually:

```
python -c "
import asyncio
from app.fhir import FhirClient
from app.tools.chw import team_activity_summary
async def r():
    c = FhirClient()
    try:
        out = await team_activity_summary(c, days=30)
        print('total encounters across team:', out['stats']['total'])
    finally:
        await c.aclose()
asyncio.run(r())
"
```

If `total` is 0, encounter participants aren't being persisted. Reset the
OpenMRS volume and re-seed.

### Smoke test reports "Participant round-trip: 0/20"

Stale practitioner UUIDs. Reset with `docker compose ... down -v` and re-seed.

### Smoke test reports "Practitioner UUIDs resolve: <N>/30"

`id_map.json` is out of sync with the DB. Same fix: reset + reseed.

### `Patient is Required` 422 errors during load

The subject reference points at a patient UUID that doesn't exist in
OpenMRS. Always means an out-of-order load — Patients phase failed or was
skipped before Encounters ran.

### Encounters double on re-run

Should no longer happen — idempotency was added in `feat(data): encounter
idempotency`. If you see `dup=` counts, that's the dedup working. If you
see actual doubling (counts > expected), the `(patient, period.start)`
search isn't finding the prior load — file a bug.

## File reference

| Path | Purpose |
|---|---|
| `data/synthea/generate.sh` | Synthea generation |
| `data/synthea/kenyan-localization/localize.py` | Localization pass |
| `data/chw_overlay/generate_chw_activity.py` | Overlay (CHWs, visits, scenarios) |
| `data/load_to_openmrs.py` | Loader + smoke test |
| `data/fixtures/localized/*.json` | Localized Synthea bundles (gitignored) |
| `data/fixtures/chw/*.json` | Overlay bundles (gitignored) |
| `data/fixtures/id_map.json` | Runtime UUID map (gitignored — regen per seed) |
| `scripts/seed.sh` | Orchestrator |
