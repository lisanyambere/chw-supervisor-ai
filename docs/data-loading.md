# Loading synthetic data into OpenMRS

This document describes how patient and Community Health Worker (CHW) data
is generated, localized, and loaded into the OpenMRS 3 reference application
that ships with this project's Docker stack.

## Pipeline overview

```
 Synthea (US)              Localizer                Loader
┌──────────────┐  raw    ┌──────────────┐  KE      ┌──────────────────┐
│  *.json      │ ──────▶ │ kenyan-      │ ───────▶ │ load_to_openmrs  │ ──▶ OpenMRS FHIR R4
│  bundles     │         │ localization │          │   (Python)       │
└──────────────┘         └──────────────┘          └──────────────────┘
                                                              ▲
                                                              │
                                                  ┌──────────────────┐
                                                  │ chw_overlay/     │
                                                  │ generate_chw_*   │ ──▶ CHW bundles
                                                  └──────────────────┘
```

Three stages, each independently re-runnable:

1. **Generate** — Synthea produces 581 FHIR R4 patient bundles in
   `data/synthea/output/fhir/`. The CHW overlay generator produces 24 bundles
   of CHW Practitioners and CHW Encounters in `data/fixtures/chw/` that
   reference Synthea patient UUIDs.
2. **Localize** — `data/synthea/kenyan-localization/localize.py` rewrites
   names, addresses (Kakamega wards), and drops US-only resource types
   (Coverage, Claim, ExplanationOfBenefit, Organization). Output: 581 bundles
   in `data/fixtures/localized/`.
3. **Load** — `data/load_to_openmrs.py` posts Patients, CHW Practitioners,
   and CHW Encounters into OpenMRS via the FHIR R4 module, rewriting
   cross-references to the server-assigned UUIDs.

## Quick start

Prerequisites: the full Docker stack from `infra/docker-compose.yml` and
`infra/docker-compose.openmrs.yml` is up and healthy. Verify:

```powershell
curl.exe -s -u admin:Admin123 http://localhost:8080/openmrs/ws/rest/v1/session
```

Run the full pipeline (assumes Synthea bundles already generated):

```powershell
# 1. Localize
python data/synthea/kenyan-localization/localize.py

# 2. Load into OpenMRS
python data/load_to_openmrs.py
```

Expected end state on a clean instance:

```
Patients      ok=581/581
Practitioners ok=30/30
Encounters    ok=4649/4649
```

The loader writes `data/fixtures/id_map.json` with two mappings used by the
backend:

```json
{
  "patients":      { "<synthea_uuid>": "<openmrs_uuid>", ... },
  "practitioners": { "chw-001": "<openmrs_uuid>", ... }
}
```

## Loader scope (Option B)

The current loader is intentionally narrow. It loads only what the agent
backend needs to answer supervisor questions:

| Resource     | Source                              | Loaded |
| ------------ | ----------------------------------- | ------ |
| Patient      | `data/fixtures/localized/`          | ✅     |
| Practitioner | `data/fixtures/chw/` (CHW overlay)  | ✅     |
| Encounter    | `data/fixtures/chw/` (CHW visits)   | ✅     |
| Observation  | Synthea bundles                     | ❌     |
| Condition    | Synthea bundles                     | ❌     |
| Immunization | Synthea bundles                     | ❌     |
| MedicationRequest, Procedure, etc. | Synthea           | ❌     |

If future evaluators need clinical observations or conditions, extend the
loader by adding new `shape_*` and `post_*` phases that follow the same
pattern as `shape_encounter` (rewrite subject and encounter references using
the maps built in earlier phases).

## Why is the loader so opinionated?

OpenMRS exposes FHIR R4 via the `fhir2` module, which is a partial
implementation of the spec with several quirks that aren't documented
externally. Each constraint in the loader corresponds to a specific failure
discovered while loading real Synthea data.

### 1. No transaction bundles

The `fhir2` module does not implement the `POST /` transaction endpoint.
Synthea bundles are `type: "transaction"` and assume the server can process
them atomically. We POST resources individually instead.

### 2. No client-supplied UUIDs

`PUT /<Type>/<uuid>` rejects unknown IDs with
`"Resource of type X with ID ... is not known"`. The
`fhir2.upsert.supported.resources` global property exists but only applies to
providers that extend `BaseUpsertFhirResourceProvider` — which is just `Task`
and `Medication`, **not** Patient, Practitioner, or Encounter.

We therefore POST without an `id` and capture the server-assigned UUID from
the response. A `patient_map` and `chw_map` are used to rewrite all
downstream `Patient/<...>` and `Practitioner/<...>` references in encounters.

### 3. Patient identifier shape

Setting `identifier.system` short-circuits OpenMRS's lookup to a system-URL
mapping (`FhirPatientServiceImpl.getPatientIdentifierTypeByIdentifier`). If
the URL isn't registered as a `FhirPatientIdentifierSystem`, the identifier
is silently discarded and validation fails with
`"Select a preferred identifier"`.

The loader therefore:

- Omits `identifier.system` so the lookup falls back to `type.text`.
- Sets `type.text = "Legacy ID"` and uses that PatientIdentifierType
  (UUID `22348099-3873-459e-a32e-d93b17eda533`).
- Avoids `Old Identification Number` and `OpenMRS Identification Number`,
  whose `locationBehavior` is null/required and would 422 with
  `"Identifier Location cannot be null"`.
- Avoids `OpenMRS ID`, whose validator rejects arbitrary values.

### 4. Patient fields stripped

Several Synthea fields trigger 500s or validator errors and are dropped:

- `telecom` — maps to a PersonAttribute type that isn't registered → 500
  `PersonAttribute.attributeType is null`.
- `maritalStatus` — same issue.
- `extension` — Synthea extensions (mothers maiden name, birthplace, DALY,
  QALY) and our `community-health-ai/ward` extension don't map to known
  attribute types.
- `deceasedBoolean` / `deceasedDateTime` — triggers OpenMRS validator
  requiring `causeOfDeath` to be set.
- `multipleBirthBoolean`, `communication`, `text`, `contact`, `id`.

### 5. Encounter type system URI

`FhirUtils.getOpenmrsEncounterType` only recognizes codings whose `system`
equals one of:

- `http://fhir.openmrs.org/code-system/encounter-type` → `Encounter`
- `http://fhir.openmrs.org/code-system/visit-type` → `Visit`

Without a recognized system the create call throws
`InvalidRequestException: Invalid type of request`. The loader hard-codes
the encounter-type system and uses the `Visit Note` encounter type
(UUID `d7151f82-c1f3-4152-a605-2f9ea7414a79`).

### 6. Encounter participant role required

Each `participant` entry must include a `type.coding[].code` referencing an
`EncounterRole` UUID, otherwise Hibernate throws
`EncounterProvider.encounterRole is null`. The loader uses the default
`Unknown` role (UUID `a0b03050-c99b-11e0-9572-0800200c9a66`).

### 7. Encounter fields stripped

- `class`, `reasonCode`, `location`, `extension`, `id`, `text` — none map
  cleanly to OpenMRS Encounter columns or attribute types.

### 8. Idempotency

Re-running the loader against an instance that already has data will see
`422 "Identifier ... already in use by another patient"`. The loader catches
this case and falls back to
`GET /Patient?identifier=<value>` (and the equivalent for Practitioner) to
recover the existing server UUID. This makes the loader safe to re-run
without resetting the database.

## Operational notes

- **Concurrency**: `WORKERS = 4` in `load_to_openmrs.py`. The OpenMRS
  backend tolerates this comfortably; raising it much higher tends to
  exhaust the connection pool.
- **Runtime**: a clean load takes roughly 8–12 minutes on a developer
  laptop (most of it spent on the 4,649 encounters).
- **Re-running cleanly**: to start fresh, reset the OpenMRS database
  volume — there is no FHIR2 bulk-delete operation. Use
  `docker compose down -v` for the OpenMRS stack and let it re-initialize.
- **Inspecting failures**: failed Patient posts are written to
  `data/fixtures/patient_failures.log` (tab-separated `synthea_uuid<TAB>error`).

## File reference

| Path | Purpose |
| --- | --- |
| `data/synthea/output/fhir/` | Raw Synthea bundles (gitignored) |
| `data/synthea/kenyan-localization/localize.py` | Stage 2 — localization |
| `data/fixtures/localized/` | Localized patient bundles (gitignored) |
| `data/chw_overlay/generate_chw_activity.py` | CHW overlay generator |
| `data/fixtures/chw/` | CHW Practitioner + Encounter bundles |
| `data/load_to_openmrs.py` | Stage 3 — FHIR R4 loader |
| `data/fixtures/id_map.json` | Output: synthea→openmrs UUID maps |

## Smoke-testing the load

After a successful load, these should all return non-zero counts:

```powershell
$base = "http://localhost:8080/openmrs/ws/fhir2/R4"
foreach ($t in 'Patient','Practitioner','Encounter') {
  $r = curl.exe -s -u admin:Admin123 "$base/$t?_summary=count"
  "$t : " + ($r | ConvertFrom-Json).total
}
```

A clean load shows `Patient: 581`, `Practitioner: 30`, `Encounter: 4649`.
Higher counts indicate prior debug runs left duplicates — reset the
OpenMRS DB volume to clean up.
