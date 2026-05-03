#!/usr/bin/env python3
"""
Generates CHW activity overlay on top of localized Synthea FHIR data.

Creates:
- 30 CHW Practitioner resources assigned to Kakamega wards
- CHW visit Encounter resources linked to patients
- 7 seeded demo scenarios (see spec section 8)

Output: data/fixtures/chw/ as FHIR bundles
"""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEED = 42
random.seed(SEED)

# Demo week: Mon Apr 27 – Sun May 3, 2026 (relative to project date 2026-05-03)
DEMO_WEEK_START = datetime(2026, 4, 27, tzinfo=timezone.utc)
DEMO_WEEK_END   = datetime(2026, 5,  3, 23, 59, tzinfo=timezone.utc)
PREV_WEEK_START = DEMO_WEEK_START - timedelta(weeks=1)

WARDS = [
    "Lurambi", "Mumias East", "Mumias West", "Likuyani",
    "Matungu", "Butere", "Khwisero", "Shinyalu", "Lugari", "Navakholo",
]

WARD_COORDS: dict[str, tuple[float, float]] = {
    "Lurambi":     (0.2828, 34.7519),
    "Mumias East": (0.3467, 34.4895),
    "Mumias West": (0.3200, 34.4700),
    "Likuyani":    (0.2317, 34.9543),
    "Matungu":     (0.2833, 34.5333),
    "Butere":      (0.2167, 34.4833),
    "Khwisero":    (0.1333, 34.4667),
    "Shinyalu":    (0.3500, 34.6333),
    "Lugari":      (0.3667, 34.9500),
    "Navakholo":   (0.2500, 34.8000),
}

# 30 CHWs — names and ward assignments
CHWS = [
    {"id": f"chw-{i:03d}", "first": fn, "last": ln, "ward": ward, "gender": g}
    for i, (fn, ln, ward, g) in enumerate([
        ("Mary",     "Wanjiku",   "Lurambi",     "female"),  # chw-000: scenario 2 (disengagement)
        ("John",     "Otieno",    "Lurambi",     "male"),    # chw-001: scenario 5 (baseline trap)
        ("Grace",    "Nekesa",    "Lurambi",     "female"),
        ("Peter",    "Wafula",    "Mumias East", "male"),
        ("Agnes",    "Naliaka",   "Mumias East", "female"),
        ("Samuel",   "Barasa",    "Mumias East", "male"),
        ("Joyce",    "Achieng",   "Mumias West", "female"),
        ("David",    "Wekesa",    "Mumias West", "male"),
        ("Rose",     "Adhiambo",  "Mumias West", "female"),
        ("James",    "Makokha",   "Likuyani",    "male"),
        ("Lydia",    "Nasimiyu",  "Likuyani",    "female"),
        ("Moses",    "Simiyu",    "Likuyani",    "male"),
        ("Ruth",     "Anyango",   "Matungu",     "female"),
        ("Charles",  "Masinde",   "Matungu",     "male"),
        ("Esther",   "Nasike",    "Matungu",     "female"),
        ("Joseph",   "Odhiambo",  "Butere",      "male"),
        ("Hannah",   "Nanjala",   "Butere",      "female"),
        ("Daniel",   "Juma",      "Butere",      "male"),
        ("Sarah",    "Atieno",    "Khwisero",    "female"),
        ("Philip",   "Okello",    "Khwisero",    "male"),
        ("Naomi",    "Awino",     "Khwisero",    "female"),
        ("Timothy",  "Khaemba",   "Shinyalu",    "male"),
        ("Deborah",  "Auma",      "Shinyalu",    "female"),
        ("Stephen",  "Musungu",   "Shinyalu",    "male"),
        ("Miriam",   "Wanjiru",   "Lugari",      "female"),
        ("Andrew",   "Muyuka",    "Lugari",      "male"),
        ("Rebecca",  "Mumbi",     "Lugari",      "female"),
        ("Patrick",  "Mutua",     "Navakholo",   "male"),
        ("Christine","Njeri",     "Navakholo",   "female"),
        ("Francis",  "Mwangi",    "Navakholo",   "male"),
    ], 1)
]


def fhir_id() -> str:
    return str(uuid.uuid4())


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def gps_jitter(lat: float, lon: float, radius: float = 0.01) -> tuple[float, float]:
    return (
        lat + random.uniform(-radius, radius),
        lon + random.uniform(-radius, radius),
    )


def make_practitioner(chw: dict) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": chw["id"],
        "identifier": [{"system": "http://community-health-ai/chw-id", "value": chw["id"]}],
        "active": True,
        "name": [{"family": chw["last"], "given": [chw["first"]], "text": f"{chw['first']} {chw['last']}"}],
        "gender": chw["gender"],
        "extension": [
            {"url": "http://community-health-ai/chw-ward", "valueString": chw["ward"]},
        ],
    }


def make_encounter(
    patient_id: str,
    chw: dict,
    start: datetime,
    duration_minutes: int = 30,
    reason: str = "Community health visit",
    missing_gps: bool = False,
    observations: list[dict] | None = None,
    follow_up_flag: bool = False,
) -> dict:
    end = start + timedelta(minutes=duration_minutes)
    lat, lon = WARD_COORDS[chw["ward"]]
    jlat, jlon = gps_jitter(lat, lon)

    enc: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": fhir_id(),
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "HH", "display": "home health"},
        "type": [{"coding": [{"system": "http://snomed.info/sct", "code": "185460008", "display": "Home visit request by patient"}]}],
        "subject": {"reference": f"Patient/{patient_id}"},
        "participant": [{"individual": {"reference": f"Practitioner/{chw['id']}"}}],
        "period": {"start": ts(start), "end": ts(end)},
        "reasonCode": [{"text": reason}],
        "extension": [
            {"url": "http://community-health-ai/chw-id",   "valueString": chw["id"]},
            {"url": "http://community-health-ai/chw-ward",  "valueString": chw["ward"]},
            {"url": "http://community-health-ai/follow-up", "valueBoolean": follow_up_flag},
        ],
    }

    if not missing_gps:
        enc["extension"].append({
            "url": "http://hl7.org/fhir/StructureDefinition/geolocation",
            "extension": [
                {"url": "latitude",  "valueDecimal": jlat},
                {"url": "longitude", "valueDecimal": jlon},
            ],
        })

    return enc


def make_observation(patient_id: str, encounter_id: str, code: str, display: str,
                     value: float, unit: str, dt: datetime, abnormal: bool = False) -> dict:
    return {
        "resourceType": "Observation",
        "id": fhir_id(),
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": ts(dt),
        "valueQuantity": {"value": value, "unit": unit},
        "interpretation": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                        "code": "H" if abnormal else "N"}]}],
    }


def make_condition(patient_id: str, code: str, display: str, onset: datetime) -> dict:
    return {
        "resourceType": "Condition",
        "id": fhir_id(),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": ts(onset),
    }


def load_patient_ids(fixtures_dir: Path) -> list[str]:
    ids = []
    for path in (fixtures_dir / "localized").glob("*.json"):
        with open(path) as f:
            bundle = json.load(f)
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            if r.get("resourceType") == "Patient" and r.get("id"):
                ids.append(r["id"])
    return ids


def build_resources(patient_ids: list[str]) -> list[dict]:
    resources: list[dict] = []

    # Practitioner resources for all CHWs
    for chw in CHWS:
        resources.append(make_practitioner(chw))

    # Distribute patients across CHWs (roughly equal)
    chw_patients: dict[str, list[str]] = {chw["id"]: [] for chw in CHWS}
    for i, pid in enumerate(patient_ids):
        assigned = CHWS[i % len(CHWS)]
        chw_patients[assigned["id"]].append(pid)

    mary   = CHWS[0]   # scenario 2: disengagement
    john   = CHWS[1]   # scenario 5: baseline trap
    grace  = CHWS[2]   # scenario 1: fever cluster (Lurambi)

    # ── Regular visits (4 weeks, Mon–Fri, ~6-10 visits/day per CHW) ──────────
    for week_offset in range(4):
        week_start = DEMO_WEEK_START - timedelta(weeks=3 - week_offset)
        for day_offset in range(5):  # Mon–Fri
            visit_date = week_start + timedelta(days=day_offset)
            for chw in CHWS:
                # Scenario 2: Mary stops Wed–Fri of demo week
                is_demo_week = week_offset == 3
                if chw["id"] == mary["id"] and is_demo_week and day_offset >= 2:
                    continue
                # Scenario 5: John only gets data for last 4 days (Thu–Sun of demo week)
                if chw["id"] == john["id"] and not (is_demo_week and day_offset >= 3):
                    continue

                patients_for_chw = chw_patients[chw["id"]]
                daily_visits = random.randint(6, 10)
                day_patients = random.sample(patients_for_chw, min(daily_visits, len(patients_for_chw)))

                for pid in day_patients:
                    hour = random.randint(8, 16)
                    minute = random.randint(0, 59)
                    visit_time = visit_date.replace(hour=hour, minute=minute)
                    # Scenario 4: 14 visits with missing GPS across the demo week
                    missing = is_demo_week and len([r for r in resources if r.get("resourceType") == "Encounter"
                                                    and not any(e.get("url","").endswith("geolocation")
                                                                for e in r.get("extension",[]))]) < 14
                    enc = make_encounter(pid, chw, visit_time, missing_gps=missing and random.random() < 0.08)
                    resources.append(enc)

    # ── Scenario 1: Fever cluster in Lurambi (8 cases in 5 days) ─────────────
    lurambi_patients = random.sample(chw_patients[grace["id"]], min(8, len(chw_patients[grace["id"]])))
    for i, pid in enumerate(lurambi_patients):
        day = DEMO_WEEK_START + timedelta(days=i % 5)
        enc = make_encounter(pid, grace, day.replace(hour=9 + i % 6), reason="Fever complaint")
        fever_obs = make_observation(pid, enc["id"], "8310-5", "Body temperature", 38.5 + random.uniform(0, 1.2), "Cel", day, abnormal=True)
        enc.setdefault("extension", []).append({"url": "http://community-health-ai/fever-cluster", "valueBoolean": True})
        resources.extend([enc, fever_obs])
        # Malaria condition for cluster patients
        resources.append(make_condition(pid, "61462000", "Malaria", day - timedelta(days=1)))

    # ── Scenario 3: Overdue ANC — 3 pregnant patients, 1 with elevated BP ────
    anc_patients = random.sample(patient_ids, 3)
    for i, pid in enumerate(anc_patients):
        chw = CHWS[i % len(CHWS)]
        last_anc = DEMO_WEEK_START - timedelta(days=9 + i * 3)
        enc = make_encounter(pid, chw, last_anc.replace(hour=10), reason="ANC follow-up",
                             follow_up_flag=True)
        enc["extension"].append({"url": "http://community-health-ai/anc-overdue", "valueBoolean": True})
        resources.append(enc)
        resources.append(make_condition(pid, "77386006", "Pregnancy", last_anc - timedelta(weeks=20)))
        if i == 0:
            # Elevated BP for first ANC patient
            bp_obs = make_observation(pid, enc["id"], "8480-6", "Systolic blood pressure",
                                      145.0, "mm[Hg]", last_anc, abnormal=True)
            resources.append(bp_obs)

    # ── Scenario 4: 3 visits with conflicting age (DOB mismatch) ─────────────
    age_conflict_patients = random.sample(patient_ids, 3)
    for pid in age_conflict_patients:
        chw = random.choice(CHWS)
        day = DEMO_WEEK_START + timedelta(days=random.randint(0, 4))
        enc = make_encounter(pid, chw, day.replace(hour=11))
        enc["extension"].append({"url": "http://community-health-ai/dq-age-conflict", "valueBoolean": True})
        resources.append(enc)

    # ── Scenario 7: IMCI danger sign — child with fever + fast breathing ──────
    imci_patient = random.choice(patient_ids)
    imci_chw = CHWS[4]
    imci_day = DEMO_WEEK_START + timedelta(days=2, hours=14)
    imci_enc = make_encounter(imci_patient, imci_chw, imci_day, reason="Child sick visit")
    imci_enc["extension"].append({"url": "http://community-health-ai/imci-danger-sign", "valueBoolean": True})
    fever   = make_observation(imci_patient, imci_enc["id"], "8310-5", "Body temperature", 39.1, "Cel", imci_day, abnormal=True)
    breaths = make_observation(imci_patient, imci_enc["id"], "9279-1", "Respiratory rate",  62.0, "/min", imci_day, abnormal=True)
    resources.extend([imci_enc, fever, breaths])

    return resources


def bundle_resources(resources: list[dict]) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": r,
                "request": {
                    "method": "PUT" if r.get("id") else "POST",
                    "url": f"{r['resourceType']}/{r['id']}" if r.get("id") else r["resourceType"],
                },
            }
            for r in resources
        ],
    }


def main() -> None:
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    localized_dir = fixtures_dir / "localized"

    if not localized_dir.exists():
        print("Localized FHIR data not found. Run localize.py first.")
        raise SystemExit(1)

    print("Loading patient IDs from localized bundles...")
    patient_ids = load_patient_ids(fixtures_dir)
    if not patient_ids:
        print("No patients found in localized bundles.")
        raise SystemExit(1)
    print(f"Found {len(patient_ids)} patients.")

    print("Building CHW resources and seeded scenarios...")
    resources = build_resources(patient_ids)

    out_dir = fixtures_dir / "chw"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Split into chunks of 200 resources per bundle (OpenMRS transaction limit)
    chunk_size = 200
    chunks = [resources[i:i + chunk_size] for i in range(0, len(resources), chunk_size)]

    for i, chunk in enumerate(chunks):
        bundle = bundle_resources(chunk)
        out_path = out_dir / f"chw-bundle-{i:03d}.json"
        with open(out_path, "w") as f:
            json.dump(bundle, f, separators=(",", ":"))

    encounters = sum(1 for r in resources if r.get("resourceType") == "Encounter")
    observations = sum(1 for r in resources if r.get("resourceType") == "Observation")
    practitioners = sum(1 for r in resources if r.get("resourceType") == "Practitioner")
    print(f"Done: {practitioners} CHWs, {encounters} encounters, {observations} observations")
    print(f"Written {len(chunks)} bundles to {out_dir}")


if __name__ == "__main__":
    main()
