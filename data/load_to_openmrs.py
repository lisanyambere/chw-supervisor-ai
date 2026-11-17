#!/usr/bin/env python3
"""
Loads localized Synthea Patients + CHW Practitioners + CHW Encounters into
OpenMRS via the FHIR R4 module.

OpenMRS FHIR2 module quirks this loader works around:
  - PUT-with-client-UUID is not supported for Patient/Practitioner/Encounter
    (the upsert global property only applies to Task and Medication providers).
    So we POST, let OpenMRS assign UUIDs, and capture them from the response.
  - Patient must have at least one identifier marked use=official with a
    known PatientIdentifierType (we use "Old Identification Number" and
    stash the original Synthea UUID there for traceability + cross-bundle
    reference rewriting).
  - Encounter.type[].coding[].code must be the UUID of an existing
    OpenMRS EncounterType (we use "Visit Note").
  - References to Patient/<synthea-uuid> and Practitioner/chw-NNN inside the
    CHW bundles are rewritten to the new server-assigned UUIDs.

Scope: deliberately narrow. Synthea's Observations, Conditions, Procedures,
CarePlans, etc. are skipped — the supervisor briefing demo only needs CHW
activity grounded in real patients. Add more resource types later if needed
by the LangGraph pipeline.
"""
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

OPENMRS_BASE = "http://localhost:8080/openmrs"
FHIR_BASE    = f"{OPENMRS_BASE}/ws/fhir2/R4"
REST_BASE    = f"{OPENMRS_BASE}/ws/rest/v1"
USERNAME     = "admin"
PASSWORD     = "Admin123"

# Concurrency per phase. OpenMRS JVM is heap-constrained; keep modest.
WORKERS = 4

# OpenMRS metadata UUIDs (look these up via /ws/rest/v1/* if you swap envs).
# Use "Legacy ID" — locationBehavior=NOT_USED, no validator. Other candidates
# ("Old Identification Number", "OpenMRS Identification Number") have
# locationBehavior=null which the FHIR2 translator interprets as REQUIRED →
# "Identifier Location cannot be null" 422. "OpenMRS ID" has a validator that
# rejects arbitrary values.
PATIENT_IDENTIFIER_TYPE_NAME = "Legacy ID"
PATIENT_IDENTIFIER_TYPE_UUID = "22348099-3873-459e-a32e-d93b17eda533"
ENCOUNTER_TYPE_VISIT_NOTE_UUID = "d7151f82-c1f3-4152-a605-2f9ea7414a79"
# OpenMRS default "Unknown" EncounterRole — required on every participant.
ENCOUNTER_ROLE_UNKNOWN_UUID = "a0b03050-c99b-11e0-9572-0800200c9a66"
# CIEL concept used as the default cause of death for Synthea-derived deaths.
# OpenMRS core's PatientValidator requires a non-null causeOfDeath whenever
# dead=true, but the FHIR R4 Patient resource has no equivalent field, so we
# can't satisfy the validator on the FHIR POST. Backfill via REST instead.
DEATH_CAUSE_UNKNOWN_UUID = "142917AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # "Death of unknown cause"

# "Chief complaint (text)" — holds the visit reason, which the FHIR2 module
# does not persist from Encounter.reasonCode.
CHIEF_COMPLAINT_TEXT_UUID = "160531AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
ROUTINE_VISIT_REASON = "Community health visit"
CHW_WARD_EXT = "http://community-health-ai/chw-ward"

SYNTHEA_ID_SYSTEM = "https://github.com/synthetichealth/synthea"
CHW_ID_SYSTEM     = "http://community-health-ai/chw-id"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def auth_header() -> str:
    creds = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    return f"Basic {creds}"


def fhir_post(rtype: str, resource: dict) -> tuple[bool, dict | None, str]:
    """POST a resource. Returns (ok, parsed_response_or_None, error_msg)."""
    url = f"{FHIR_BASE}/{rtype}"
    payload = json.dumps(resource).encode()
    req = Request(
        url,
        data=payload,
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read()
            return True, (json.loads(body) if body else None), ""
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        return False, None, f"HTTP {e.code}: {err_body[:2000]}"
    except URLError as e:
        return False, None, f"URLError: {e}"


def fhir_search_first_id(rtype: str, params: dict) -> str | None:
    """GET /<rtype>?<params> and return the first resource's id, or None."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{FHIR_BASE}/{rtype}?{qs}"
    req = Request(
        url,
        headers={
            "Authorization": auth_header(),
            "Accept": "application/fhir+json",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        for entry in (data.get("entry") or []):
            res = entry.get("resource") or {}
            if res.get("id"):
                return res["id"]
    except Exception:
        pass
    return None


def check_openmrs() -> bool:
    req = Request(
        f"{OPENMRS_BASE}/ws/rest/v1/session",
        headers={"Authorization": auth_header()},
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("authenticated", False)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Resource shaping
# ---------------------------------------------------------------------------

def shape_patient(patient: dict) -> tuple[str, dict, str | None]:
    """Strip server-assignable fields, ensure a preferred identifier.
    Returns (synthea_uuid, cleaned_resource, deceased_date_or_None).

    The deceasedDateTime is captured for a follow-up REST backfill
    (see post_death_info) and stripped from the FHIR payload, since OpenMRS
    core's PatientValidator rejects dead=true without a causeOfDeath value
    that the FHIR R4 Patient model can't carry.
    """
    synthea_uuid = patient.get("id", "")

    # NOTE: Do NOT set identifier.system. OpenMRS FhirPatientServiceImpl
    # short-circuits to a system-URL lookup when system is present and only
    # falls back to type.text matching when system is absent. We rely on
    # type.text to map to the existing PatientIdentifierType by name.
    patient["identifier"] = [{
        "use": "official",
        "type": {
            "coding": [{"code": PATIENT_IDENTIFIER_TYPE_UUID}],
            "text": PATIENT_IDENTIFIER_TYPE_NAME,
        },
        "value": synthea_uuid,
    }]

    patient.pop("id", None)
    patient.pop("multipleBirthBoolean", None)
    patient.pop("communication", None)
    patient.pop("text", None)
    patient.pop("contact", None)
    # Drop fields that map to PersonAttribute types not registered in this
    # OpenMRS instance (would 500 with "PersonAttribute.attributeType is null").
    patient.pop("telecom", None)
    patient.pop("maritalStatus", None)
    # Synthea + custom extensions don't map to known person attribute types.
    patient.pop("extension", None)
    # Capture and strip the deceased markers — we backfill via REST after
    # the FHIR POST succeeds, with a default causeOfDeath concept.
    deceased_date = patient.pop("deceasedDateTime", None)
    deceased_bool = patient.pop("deceasedBoolean", None)
    if not deceased_date and deceased_bool:
        # Synthea always carries a date when dead, but be defensive.
        deceased_date = ""  # marker = "dead but date unknown"
    return synthea_uuid, patient, deceased_date


def shape_practitioner(practitioner: dict) -> tuple[str, dict]:
    chw_id = practitioner.get("id", "")
    idents = practitioner.get("identifier") or []
    found = False
    for ident in idents:
        if ident.get("system") == CHW_ID_SYSTEM:
            ident["use"] = "official"
            found = True
            break
    if not found:
        idents.append({
            "use": "official",
            "system": CHW_ID_SYSTEM,
            "value": chw_id,
        })
    practitioner["identifier"] = idents
    practitioner.pop("id", None)
    practitioner.pop("text", None)
    return chw_id, practitioner


def shape_encounter(
    encounter: dict,
    patient_map: dict,
    chw_map: dict,
    ward_map: dict,
):
    """Rewrite refs and metadata. Returns None if any required ref unresolvable."""
    subj_ref = encounter.get("subject", {}).get("reference", "")
    if not subj_ref.startswith("Patient/"):
        return None
    synthea_uuid = subj_ref.split("/", 1)[1]
    new_pat_uuid = patient_map.get(synthea_uuid)
    if not new_pat_uuid:
        return None
    encounter["subject"] = {"reference": f"Patient/{new_pat_uuid}"}

    new_participants = []
    for p in encounter.get("participant", []):
        ind_ref = p.get("individual", {}).get("reference", "")
        if ind_ref.startswith("Practitioner/"):
            chw_id = ind_ref.split("/", 1)[1]
            new_uuid = chw_map.get(chw_id)
            if not new_uuid:
                return None
            new_participants.append({
                "type": [{
                    "coding": [{"code": ENCOUNTER_ROLE_UNKNOWN_UUID}]
                }],
                "individual": {"reference": f"Practitioner/{new_uuid}"}
            })
    encounter["participant"] = new_participants

    encounter["type"] = [{
        "coding": [{
            "system": "http://fhir.openmrs.org/code-system/encounter-type",
            "code": ENCOUNTER_TYPE_VISIT_NOTE_UUID,
        }]
    }]
    encounter.pop("id", None)
    encounter.pop("text", None)
    encounter.pop("class", None)
    encounter.pop("reasonCode", None)
    # Custom extensions don't map to OpenMRS encounter attributes by default.
    # The ward becomes a real OpenMRS Location. A visit generated without GPS
    # is stored with no location at all — that is the data-quality scenario.
    extensions = encounter.pop("extension", None) or []
    ward = next((e.get("valueString") for e in extensions if e.get("url") == CHW_WARD_EXT), None)
    has_gps = any(e.get("url", "").endswith("geolocation") for e in extensions)
    encounter.pop("location", None)
    if has_gps and ward in ward_map:
        encounter["location"] = [{"location": {"reference": f"Location/{ward_map[ward]}"}}]
    return encounter


def ciel_uuid(code: str) -> str:
    """CIEL concepts in OpenMRS use the code right-padded with 'A' to 36 chars."""
    return code + "A" * (36 - len(code))


def shape_clinical(resource: dict, patient_map: dict, enc_id_map: dict | None = None):
    """Rewrite an Observation/Condition for OpenMRS. None if a ref is unresolvable."""
    synthea_uuid = resource.get("subject", {}).get("reference", "").split("/", 1)[-1]
    patient_uuid = patient_map.get(synthea_uuid)
    if not patient_uuid:
        return None
    shaped = {k: v for k, v in resource.items() if k not in ("id", "text")}
    shaped["subject"] = {"reference": f"Patient/{patient_uuid}"}
    shaped["code"] = {"coding": [{"code": ciel_uuid(resource["code"]["coding"][0]["code"])}]}
    if "encounter" in resource:
        source_enc = resource["encounter"]["reference"].split("/", 1)[-1]
        server_enc = (enc_id_map or {}).get(source_enc)
        if not server_enc:
            return None
        shaped["encounter"] = {"reference": f"Encounter/{server_enc}"}
    return shaped


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect_patients(localized_dir: Path) -> list:
    out = []
    for path in sorted(localized_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            if r.get("resourceType") == "Patient":
                out.append(r)
    return out


def collect_chw_resources(chw_dir: Path):
    practitioners, encounters, observations, conditions = [], [], [], []
    for path in sorted(chw_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            t = r.get("resourceType")
            if t == "Practitioner":
                practitioners.append(r)
            elif t == "Encounter":
                encounters.append(r)
            elif t == "Observation":
                observations.append(r)
            elif t == "Condition":
                conditions.append(r)
    return practitioners, encounters, observations, conditions


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def post_patients(patients: list) -> tuple[dict, dict]:
    """POST patients via FHIR. Returns (synthea_uuid → server_uuid, server_uuid → death_date)."""
    mapping: dict = {}
    deaths: dict = {}
    failures: list = []

    def task(p):
        synthea_uuid, shaped, deceased_date = shape_patient(dict(p))
        ok, body, err = fhir_post("Patient", shaped)
        if ok and body:
            return synthea_uuid, body.get("id"), deceased_date, ""
        # Idempotency: if already loaded, look up existing UUID by identifier value
        if "already in use" in err:
            existing = fhir_search_first_id("Patient", {"identifier": synthea_uuid})
            if existing:
                return synthea_uuid, existing, deceased_date, ""
        return synthea_uuid, None, deceased_date, err

    print(f"  POST Patient x {len(patients)}")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, p) for p in patients]
        done = 0
        for fut in as_completed(futures):
            synthea_uuid, server_uuid, deceased_date, err = fut.result()
            if server_uuid:
                mapping[synthea_uuid] = server_uuid
                if deceased_date is not None:
                    deaths[server_uuid] = deceased_date
            else:
                failures.append((synthea_uuid, err))
            done += 1
            if done % 50 == 0 or done == len(patients):
                print(f"    {done}/{len(patients)} ok={len(mapping)} fail={len(failures)} dead={len(deaths)}")

    if failures:
        print(f"  Sample failure: {failures[0]}")
        # Persist all failures for inspection
        try:
            from pathlib import Path as _P
            _P("data/fixtures").mkdir(parents=True, exist_ok=True)
            with open("data/fixtures/patient_failures.log", "w", encoding="utf-8") as fh:
                for syn, e in failures:
                    fh.write(f"{syn}\t{e}\n")
        except Exception:
            pass
    return mapping, deaths


def rest_post(path: str, payload: dict) -> tuple[bool, str]:
    """POST to /ws/rest/v1/<path>. Returns (ok, error_msg)."""
    url = f"{REST_BASE}/{path.lstrip('/')}"
    body = json.dumps(payload).encode()
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            resp.read()
        return True, ""
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            err_body = ""
        return False, f"HTTP {e.code}: {err_body}"
    except URLError as e:
        return False, f"URLError: {e}"


def _normalise_death_date(value: str) -> str:
    """Coerce a FHIR deceasedDateTime to the ISO8601 form OpenMRS REST accepts.

    OpenMRS REST wants milliseconds + zone, e.g. 2012-12-19T05:40:47.000+0000.
    Accept whatever Synthea emits, including the date-only and offset forms.
    """
    from datetime import datetime
    if not value:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    s = value.strip()
    # Normalise trailing Z to +00:00 for fromisoformat.
    iso = s.replace("Z", "+00:00")
    try:
        # Date-only string: 1952-06-01
        if len(iso) == 10:
            dt = datetime.fromisoformat(iso + "T00:00:00+00:00")
        else:
            dt = datetime.fromisoformat(iso)
    except ValueError:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    # Render as UTC with the trailing-zero offset OpenMRS prefers.
    if dt.utcoffset() is not None:
        from datetime import timezone
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def post_death_info(deaths: dict) -> tuple[int, int]:
    """Backfill dead=true + deathDate + causeOfDeath via REST for the patients
    Synthea marked deceased. Idempotent: re-running on an already-dead patient
    is a no-op from the validator's perspective.
    """
    if not deaths:
        print("  (no deceased patients to backfill)")
        return 0, 0

    print(f"  REST POST person.dead x {len(deaths)}")
    ok = fail = 0
    failures: list = []

    def task(server_uuid: str, raw_date: str) -> tuple[str, bool, str]:
        payload = {
            "dead": True,
            "deathDate": _normalise_death_date(raw_date),
            "causeOfDeath": DEATH_CAUSE_UNKNOWN_UUID,
        }
        success, err = rest_post(f"person/{server_uuid}", payload)
        return server_uuid, success, err

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, uuid, d) for uuid, d in deaths.items()]
        done = 0
        for fut in as_completed(futures):
            uuid, success, err = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
                if len(failures) < 3:
                    failures.append((uuid, err))
            done += 1
            if done % 25 == 0 or done == len(deaths):
                print(f"    {done}/{len(deaths)} ok={ok} fail={fail}")
    for uuid, err in failures:
        print(f"    Sample failure: {uuid} → {err}")
    return ok, fail


def post_practitioners(practitioners: list) -> dict:
    mapping: dict = {}
    failures: list = []

    def task(p):
        chw_id, shaped = shape_practitioner(dict(p))
        ok, body, err = fhir_post("Practitioner", shaped)
        if ok and body:
            return chw_id, body.get("id"), ""
        if "already in use" in err or "duplicate" in err.lower():
            existing = fhir_search_first_id("Practitioner", {"identifier": chw_id})
            if existing:
                return chw_id, existing, ""
        return chw_id, None, err

    print(f"  POST Practitioner x {len(practitioners)}")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, p) for p in practitioners]
        for fut in as_completed(futures):
            chw_id, server_uuid, err = fut.result()
            if server_uuid:
                mapping[chw_id] = server_uuid
            else:
                failures.append((chw_id, err))
    print(f"    ok={len(mapping)} fail={len(failures)}")
    if failures:
        print(f"    Sample failure: {failures[0]}")
    return mapping


def encounter_already_exists(subject_uuid: str, period_start: str) -> bool:
    # OpenMRS Encounter search by (patient, date). The `date` param defaults
    # to eq when no prefix is given. We rely on exact period.start match —
    # the overlay generator stamps unique minute-resolution timestamps so
    # collisions across distinct encounters are vanishingly unlikely.
    qs = f"patient={subject_uuid}&date={period_start}"
    url = f"{FHIR_BASE}/Encounter?{qs}&_summary=count"
    req = Request(
        url,
        headers={
            "Authorization": auth_header(),
            "Accept": "application/fhir+json",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return int(data.get("total", 0)) > 0
    except Exception:
        # Treat lookup failures as "not present" so we don't lose data; a
        # silent dup is a much smaller problem than a silent drop.
        return False


def post_encounters(encounters: list, patient_map: dict, chw_map: dict, ward_map: dict):
    """Returns (ok, fail, skipped, duplicate, enc_id_map).

    enc_id_map maps generator encounter id → server uuid for encounters created
    in this run only, so a re-run does not attach a second set of observations
    to encounters that already exist.
    """
    skipped = ok = fail = duplicate = 0
    failures: list = []
    enc_id_map: dict = {}

    shaped_list = []
    for enc in encounters:
        reason = ((enc.get("reasonCode") or [{}])[0]).get("text")
        shaped = shape_encounter(dict(enc), patient_map, chw_map, ward_map)
        if shaped is None:
            skipped += 1
        else:
            shaped_list.append((enc.get("id"), reason, shaped))

    def task(item: tuple) -> tuple[bool, str, bool]:
        source_id, reason, e = item
        # Returns (success, error, was_duplicate). Duplicate short-circuits
        # the POST so re-running the seed against a partially-loaded
        # database doesn't double rows.
        subj_ref = e["subject"]["reference"]
        subj_uuid = subj_ref.split("/", 1)[1] if subj_ref.startswith("Patient/") else ""
        start = (e.get("period") or {}).get("start", "")
        if subj_uuid and start and encounter_already_exists(subj_uuid, start):
            return True, "", True
        success, body, err = fhir_post("Encounter", e)
        if success and body and body.get("id"):
            enc_id_map[source_id] = body["id"]
            if reason and reason != ROUTINE_VISIT_REASON:
                success, _body, err = fhir_post("Observation", {
                    "resourceType": "Observation",
                    "status": "final",
                    "code": {"coding": [{"code": CHIEF_COMPLAINT_TEXT_UUID}]},
                    "subject": e["subject"],
                    "encounter": {"reference": f"Encounter/{body['id']}"},
                    "effectiveDateTime": e["period"]["start"],
                    "valueString": reason,
                })
        return success, err, False

    print(f"  POST Encounter x {len(shaped_list)} (skipped {skipped})")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, e) for e in shaped_list]
        done = 0
        for fut in as_completed(futures):
            success, err, was_dup = fut.result()
            if was_dup:
                duplicate += 1
            elif success:
                ok += 1
            else:
                fail += 1
                if len(failures) < 3:
                    failures.append(err)
            done += 1
            if done % 100 == 0 or done == len(shaped_list):
                print(
                    f"    {done}/{len(shaped_list)} "
                    f"ok={ok} dup={duplicate} fail={fail}"
                )
    for f in failures:
        print(f"    Sample failure: {f}")
    return ok, fail, skipped, duplicate, enc_id_map


def ensure_ward_locations(wards: list) -> dict:
    """Create one OpenMRS Location per ward (or reuse it). Returns name → uuid."""
    ward_map: dict = {}
    for ward in wards:
        found = _fhir_get(f"{REST_BASE}/location?q={quote(ward)}&v=custom:(uuid,name)")
        match = next((r for r in (found or {}).get("results", []) if r["name"] == ward), None)
        if match is None:
            ok, err = rest_post("location", {"name": ward, "description": "Kakamega County ward"})
            if not ok:
                print(f"    Location {ward} failed: {err}")
                continue
            found = _fhir_get(f"{REST_BASE}/location?q={quote(ward)}&v=custom:(uuid,name)")
            match = next(r for r in found["results"] if r["name"] == ward)
        ward_map[ward] = match["uuid"]
    print(f"  Ward locations: {len(ward_map)}/{len(wards)}")
    return ward_map


def post_clinical(rtype: str, resources: list, patient_map: dict, enc_id_map: dict | None = None):
    """POST Observations or Conditions. Returns (ok, fail, skipped)."""
    ok = fail = skipped = 0
    for r in resources:
        shaped = shape_clinical(r, patient_map, enc_id_map)
        if shaped is None:
            skipped += 1
            continue
        if rtype == "Condition":
            # Conditions hang off the patient, not an encounter, so they need
            # their own duplicate check.
            subject_uuid = shaped["subject"]["reference"].split("/", 1)[1]
            code = shaped["code"]["coding"][0]["code"]
            if fhir_search_first_id("Condition", {"patient": subject_uuid, "code": code}):
                skipped += 1
                continue
        success, _body, err = fhir_post(rtype, shaped)
        if success:
            ok += 1
        else:
            fail += 1
            print(f"    {rtype} failed: {err[:300]}")
    print(f"  POST {rtype} x {len(resources)}: ok={ok} fail={fail} skipped={skipped}")
    return ok, fail, skipped


def _fhir_get(url: str) -> dict | None:
    req = Request(
        url,
        headers={
            "Authorization": auth_header(),
            "Accept": "application/fhir+json",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def smoke_test(patient_map: dict, chw_map: dict) -> bool:
    # Returns True on pass, False on fail. The caller decides whether to
    # exit non-zero — a failed smoke means the seed succeeded in posting
    # bytes but the data isn't usable by the agent, which is silently
    # worse than an outright failure.
    print("\nSmoke tests:")
    passed = True

    # Counts (informational, never fail).
    for label, path in [
        ("Patient count",      "Patient"),
        ("Practitioner count", "Practitioner"),
        ("Encounter count",    "Encounter"),
    ]:
        data = _fhir_get(f"{FHIR_BASE}/{path}?_summary=count")
        total = data.get("total", "?") if data else "ERROR"
        print(f"  {label}: {total}")

    # 1. Participants must survive round-trip. Sample 20 encounters; if <50%
    #    carry a participant block, the participant references were silently
    #    scrubbed (typically because of stale practitioner UUIDs). Sample from
    #    patients we loaded — the OpenMRS demo data ships its own encounters
    #    without participants and would otherwise fill the sample.
    sample_patients = ",".join(list(patient_map.values())[:10])
    page = _fhir_get(f"{FHIR_BASE}/Encounter?patient={sample_patients}&_count=20")
    entries = (page or {}).get("entry") or []
    if not entries:
        print("  Participant round-trip: SKIP (no encounters to sample)")
    else:
        with_part = sum(
            1 for e in entries if (e.get("resource") or {}).get("participant")
        )
        pct = (with_part / len(entries)) * 100
        verdict = "OK" if pct >= 50 else "FAIL"
        print(
            f"  Participant round-trip: {with_part}/{len(entries)} ({pct:.0f}%) {verdict}"
        )
        if pct < 50:
            print(
                "    Participants were stripped on persistence. "
                "Almost always caused by stale practitioner UUIDs in the "
                "encounter payload. Inspect chw_map vs live Practitioners."
            )
            passed = False

    # 2. id_map UUIDs must resolve. Every practitioner uuid is checked; a
    #    20-patient sample suffices to catch wholesale drift.
    bad_pracs = []
    for chw_id, uuid in chw_map.items():
        data = _fhir_get(f"{FHIR_BASE}/Practitioner/{uuid}")
        if not data or data.get("resourceType") == "OperationOutcome":
            bad_pracs.append((chw_id, uuid))
    print(f"  Practitioner UUIDs resolve: {len(chw_map) - len(bad_pracs)}/{len(chw_map)}")
    if bad_pracs:
        print(f"    Unreachable: {bad_pracs[:3]}{'...' if len(bad_pracs) > 3 else ''}")
        passed = False

    sample_pats = list(patient_map.values())[:20]
    bad_pats = []
    for uuid in sample_pats:
        data = _fhir_get(f"{FHIR_BASE}/Patient/{uuid}")
        if not data or data.get("resourceType") == "OperationOutcome":
            bad_pats.append(uuid)
    print(f"  Patient UUIDs resolve (sample): {len(sample_pats) - len(bad_pats)}/{len(sample_pats)}")
    if bad_pats:
        print(f"    Unreachable: {bad_pats[:3]}{'...' if len(bad_pats) > 3 else ''}")
        passed = False

    print()
    print("  Overall:", "PASS" if passed else "FAIL")
    return passed


def main() -> None:
    print("Checking OpenMRS connection...")
    if not check_openmrs():
        print("Cannot reach OpenMRS. Is the docker stack up?")
        sys.exit(1)
    print("Connected.\n")

    fixtures = Path(__file__).parent / "fixtures"
    localized_dir = fixtures / "localized"
    chw_dir       = fixtures / "chw"

    if not localized_dir.exists() or not any(localized_dir.glob("*.json")):
        print(f"Localized data missing at {localized_dir}")
        print("Run: python data/synthea/kenyan-localization/localize.py")
        sys.exit(1)
    if not chw_dir.exists() or not any(chw_dir.glob("*.json")):
        print(f"CHW data missing at {chw_dir}")
        print("Run: python data/chw_overlay/generate_chw_activity.py")
        sys.exit(1)

    print("Phase 1 - Patients")
    patients = collect_patients(localized_dir)
    patient_map, deaths = post_patients(patients)

    print("\nPhase 1b - Death backfill")
    death_ok, death_fail = post_death_info(deaths)

    print("\nPhase 2 - CHW Practitioners")
    practitioners, encounters, observations, conditions = collect_chw_resources(chw_dir)
    chw_wards = {
        p["id"]: next(
            e["valueString"] for e in p.get("extension", []) if e.get("url") == CHW_WARD_EXT
        )
        for p in practitioners
    }
    chw_map = post_practitioners(practitioners)
    ward_map = ensure_ward_locations(sorted(set(chw_wards.values())))

    print("\nPhase 3 - CHW Encounters")
    enc_ok, enc_fail, enc_skip, enc_dup, enc_id_map = post_encounters(
        encounters, patient_map, chw_map, ward_map
    )

    print("\nPhase 4 - Observations and Conditions")
    obs_ok, obs_fail, _ = post_clinical("Observation", observations, patient_map, enc_id_map)
    cond_ok, cond_fail, _ = post_clinical("Condition", conditions, patient_map)

    out_path = fixtures / "id_map.json"
    out_path.write_text(json.dumps({
        "patients":      patient_map,
        "practitioners": chw_map,
        "wards":         ward_map,
        "chw_wards":     chw_wards,
    }, indent=2))
    print(f"\nID map written to {out_path}")

    print("\nSummary:")
    print(f"  Patients      ok={len(patient_map)}/{len(patients)}")
    print(f"  Deaths        ok={death_ok}/{len(deaths)} (fail={death_fail})")
    print(f"  Practitioners ok={len(chw_map)}/{len(practitioners)}")
    print(
        f"  Encounters    ok={enc_ok}/{len(encounters)} "
        f"(dup={enc_dup}, fail={enc_fail}, skipped={enc_skip})"
    )
    print(f"  Observations  ok={obs_ok}/{len(observations)} (fail={obs_fail})")
    print(f"  Conditions    ok={cond_ok}/{len(conditions)} (fail={cond_fail})")

    if not smoke_test(patient_map, chw_map):
        # Non-zero exit so CI / Makefile / seed.sh halt loudly. The data is
        # in OpenMRS, but the agent will return garbage if we proceed.
        sys.exit(2)


if __name__ == "__main__":
    main()
