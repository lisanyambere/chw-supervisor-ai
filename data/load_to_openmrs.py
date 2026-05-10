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
from urllib.request import Request, urlopen

OPENMRS_BASE = "http://localhost:8080/openmrs"
FHIR_BASE    = f"{OPENMRS_BASE}/ws/fhir2/R4"
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

def shape_patient(patient: dict) -> tuple[str, dict]:
    """Strip server-assignable fields, ensure a preferred identifier.
    Returns (synthea_uuid, cleaned_resource).
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
    # Deceased flag triggers OpenMRS validator requiring causeOfDeath; drop it.
    patient.pop("deceasedBoolean", None)
    patient.pop("deceasedDateTime", None)
    return synthea_uuid, patient


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
    encounter.pop("extension", None)
    encounter.pop("location", None)
    return encounter


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
    practitioners, encounters = [], []
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
    return practitioners, encounters


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def post_patients(patients: list) -> dict:
    mapping: dict = {}
    failures: list = []

    def task(p):
        synthea_uuid, shaped = shape_patient(dict(p))
        ok, body, err = fhir_post("Patient", shaped)
        if ok and body:
            return synthea_uuid, body.get("id"), ""
        # Idempotency: if already loaded, look up existing UUID by identifier value
        if "already in use" in err:
            existing = fhir_search_first_id("Patient", {"identifier": synthea_uuid})
            if existing:
                return synthea_uuid, existing, ""
        return synthea_uuid, None, err

    print(f"  POST Patient x {len(patients)}")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(task, p) for p in patients]
        done = 0
        for fut in as_completed(futures):
            synthea_uuid, server_uuid, err = fut.result()
            if server_uuid:
                mapping[synthea_uuid] = server_uuid
            else:
                failures.append((synthea_uuid, err))
            done += 1
            if done % 50 == 0 or done == len(patients):
                print(f"    {done}/{len(patients)} ok={len(mapping)} fail={len(failures)}")

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
    return mapping


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


def post_encounters(encounters: list, patient_map: dict, chw_map: dict):
    skipped = ok = fail = 0
    failures: list = []

    shaped_list = []
    for enc in encounters:
        shaped = shape_encounter(dict(enc), patient_map, chw_map)
        if shaped is None:
            skipped += 1
        else:
            shaped_list.append(shaped)

    print(f"  POST Encounter x {len(shaped_list)} (skipped {skipped})")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(fhir_post, "Encounter", e) for e in shaped_list]
        done = 0
        for fut in as_completed(futures):
            success, _body, err = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
                if len(failures) < 3:
                    failures.append(err)
            done += 1
            if done % 100 == 0 or done == len(shaped_list):
                print(f"    {done}/{len(shaped_list)} ok={ok} fail={fail}")
    for f in failures:
        print(f"    Sample failure: {f}")
    return ok, fail, skipped


def smoke_test() -> None:
    print("\nSmoke tests:")
    endpoints = [
        ("Patient count",      f"{FHIR_BASE}/Patient?_summary=count"),
        ("Practitioner count", f"{FHIR_BASE}/Practitioner?_summary=count"),
        ("Encounter count",    f"{FHIR_BASE}/Encounter?_summary=count"),
    ]
    for label, url in endpoints:
        req = Request(url, headers={
            "Authorization": auth_header(),
            "Accept": "application/fhir+json",
        })
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                print(f"  {label}: {data.get('total', '?')}")
        except Exception as e:
            print(f"  {label}: ERROR - {e}")


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
    patient_map = post_patients(patients)

    print("\nPhase 2 - CHW Practitioners")
    practitioners, encounters = collect_chw_resources(chw_dir)
    chw_map = post_practitioners(practitioners)

    print("\nPhase 3 - CHW Encounters")
    enc_ok, enc_fail, enc_skip = post_encounters(encounters, patient_map, chw_map)

    out_path = fixtures / "id_map.json"
    out_path.write_text(json.dumps({
        "patients":      patient_map,
        "practitioners": chw_map,
    }, indent=2))
    print(f"\nID map written to {out_path}")

    print("\nSummary:")
    print(f"  Patients      ok={len(patient_map)}/{len(patients)}")
    print(f"  Practitioners ok={len(chw_map)}/{len(practitioners)}")
    print(f"  Encounters    ok={enc_ok}/{len(encounters)} (fail={enc_fail}, skipped={enc_skip})")

    smoke_test()


if __name__ == "__main__":
    main()
