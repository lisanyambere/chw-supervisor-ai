#!/usr/bin/env python3
"""
Generates CHW activity overlay on top of localized Synthea FHIR data.

Creates:
- 30 CHW Practitioner resources assigned to Kakamega wards
- CHW visit Encounter resources linked to patients
- 7 seeded demo scenarios, recorded as ordinary clinical data (no flags)

Output: data/fixtures/chw/ as FHIR bundles, plus data/fixtures/scenarios.json,
the ground truth the evaluation scores briefings against
"""
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEED = 42
random.seed(SEED)

def _demo_week_start() -> datetime:
    # The backend tools look back from "now", so the demo week has to sit just
    # behind the day the data is generated: the most recent complete Mon–Sun
    # week. Set DEMO_WEEK_START=YYYY-MM-DD (a Monday) to pin it instead.
    pinned = os.environ.get("DEMO_WEEK_START")
    if pinned:
        start = datetime.strptime(pinned, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if start.weekday() != 0:
            raise SystemExit(f"DEMO_WEEK_START must be a Monday, got {pinned}")
        return start
    today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=today.weekday() + 7)


DEMO_WEEK_START = _demo_week_start()

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


CIEL = "https://cielterminology.org"
# CIEL concepts the OpenMRS reference application ships with.
TEMPERATURE       = "5088"    # Temperature (c)
RESPIRATORY_RATE  = "5242"
SYSTOLIC_BP       = "5085"
CURRENTLY_PREGNANT = "1434"   # Boolean
RETURN_VISIT_DATE = "5096"    # Date
MALARIA           = "116128"  # Diagnosis


def make_observation(patient_id: str, encounter_id: str, code: str, display: str,
                     dt: datetime, **value: Any) -> dict:
    """`value` is one FHIR value[x] field, e.g. valueQuantity={...}."""
    return {
        "resourceType": "Observation",
        "id": fhir_id(),
        "status": "final",
        "code": {"coding": [{"system": CIEL, "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": ts(dt),
        **value,
    }


def quantity(value: float, unit: str) -> dict:
    return {"value": round(value, 1), "unit": unit}


def make_condition(patient_id: str, code: str, display: str, onset: datetime) -> dict:
    return {
        "resourceType": "Condition",
        "id": fhir_id(),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "code": {"coding": [{"system": CIEL, "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "onsetDateTime": ts(onset),
    }


def load_patients(fixtures_dir: Path) -> list[dict]:
    """Patient id, birth date, gender and whether Synthea marked them deceased."""
    patients = []
    for path in sorted((fixtures_dir / "localized").glob("*.json")):
        with open(path) as f:
            bundle = json.load(f)
        for entry in bundle.get("entry", []):
            r = entry.get("resource", {})
            if r.get("resourceType") == "Patient":
                patients.append({
                    "id": r["id"],
                    "birth": datetime.strptime(r["birthDate"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    "gender": r.get("gender"),
                    "deceased": bool(r.get("deceasedDateTime") or r.get("deceasedBoolean")),
                })
    return patients


def age_years(patient: dict, at: datetime) -> float:
    return (at - patient["birth"]).days / 365.25


def strip_location(enc: dict) -> None:
    enc["extension"] = [
        e for e in enc["extension"] if not e.get("url", "").endswith("geolocation")
    ]


def build_resources(patients: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (FHIR resources, scenario manifest).

    The manifest is the ground truth the evaluation scores briefings against:
    each entry says what was planted and which ids a good briefing would name.
    """
    resources: list[dict] = [make_practitioner(chw) for chw in CHWS]
    scenarios: list[dict] = []

    living = [p for p in patients if not p["deceased"]]
    deceased = [p for p in patients if p["deceased"]]

    mary   = CHWS[0]   # scenario 2: disengagement
    john   = CHWS[1]   # scenario 5: baseline trap
    grace  = CHWS[2]   # scenario 1: fever cluster (Lurambi)

    # Scenario 3 patients are picked first and kept out of routine visits, so
    # their missed return date is not masked by a later visit.
    anc_patients = random.sample(
        [p for p in living if p["gender"] == "female" and 18 <= age_years(p, DEMO_WEEK_START) <= 40], 3
    )
    anc_ids = {p["id"] for p in anc_patients}

    # Distribute the remaining living patients across CHWs (roughly equal)
    chw_patients: dict[str, list[str]] = {chw["id"]: [] for chw in CHWS}
    for i, p in enumerate(p for p in living if p["id"] not in anc_ids):
        chw_patients[CHWS[i % len(CHWS)]["id"]].append(p["id"])

    # ── Routine visits (4 weeks, Mon–Fri, ~6-10 visits/day per CHW) ──────────
    demo_week_visits: list[dict] = []
    for week_offset in range(4):
        week_start = DEMO_WEEK_START - timedelta(weeks=3 - week_offset)
        is_demo_week = week_offset == 3
        for day_offset in range(5):  # Mon–Fri
            visit_date = week_start + timedelta(days=day_offset)
            for chw in CHWS:
                # Scenario 2: Mary stops Wed–Fri of demo week
                if chw["id"] == mary["id"] and is_demo_week and day_offset >= 2:
                    continue
                # Scenario 5: John only has data for Thu–Fri of demo week
                if chw["id"] == john["id"] and not (is_demo_week and day_offset >= 3):
                    continue

                patients_for_chw = chw_patients[chw["id"]]
                daily_visits = random.randint(6, 10)
                for pid in random.sample(patients_for_chw, min(daily_visits, len(patients_for_chw))):
                    visit_time = visit_date.replace(hour=random.randint(8, 16), minute=random.randint(0, 59))
                    enc = make_encounter(pid, chw, visit_time)
                    resources.append(enc)
                    if is_demo_week:
                        demo_week_visits.append(enc)

    scenarios.append({
        "id": "chw_disengagement",
        "title": "A CHW stopped visiting mid-week",
        "expect": f"{mary['id']} ({mary['first']} {mary['last']}) logged visits on Monday and Tuesday of the "
                  "latest week and none from Wednesday to Friday.",
        "chw_ids": [mary["id"]],
    })
    scenarios.append({
        "id": "baseline_trap",
        "title": "A CHW with only two days of history",
        "expect": f"{john['id']} ({john['first']} {john['last']}) has visits on only the last Thursday and Friday. "
                  "The low 30-day total reflects a short history, not disengagement; a good briefing says so "
                  "rather than ranking them as the worst performer.",
        "chw_ids": [john["id"]],
    })

    # ── Scenario 1: Fever cluster in Lurambi (8 cases in 5 days) ─────────────
    cluster = random.sample(chw_patients[grace["id"]], 8)
    for i, pid in enumerate(cluster):
        day = (DEMO_WEEK_START + timedelta(days=i % 5)).replace(hour=9 + i % 6)
        enc = make_encounter(pid, grace, day, reason="Fever complaint")
        resources.append(enc)
        resources.append(make_observation(
            pid, enc["id"], TEMPERATURE, "Temperature (c)", day,
            valueQuantity=quantity(38.5 + random.uniform(0, 1.2), "DEG C"),
        ))
        resources.append(make_condition(pid, MALARIA, "Malaria", day))
    scenarios.append({
        "id": "fever_cluster",
        "title": "Fever cluster in one ward",
        "expect": f"8 patients in {grace['ward']} ward had a temperature of 38.5 C or higher within five days, "
                  f"all seen by {grace['id']}, each with a malaria diagnosis.",
        "chw_ids": [grace["id"]],
        "ward": grace["ward"],
        "patient_ids": cluster,
    })

    # ── Scenario 3: Overdue ANC — 3 pregnant patients, 1 with elevated BP ────
    for i, p in enumerate(anc_patients):
        chw = CHWS[(i + 5) % len(CHWS)]
        last_anc = (DEMO_WEEK_START - timedelta(days=9 + i * 3)).replace(hour=10)
        enc = make_encounter(p["id"], chw, last_anc, reason="ANC follow-up", follow_up_flag=True)
        resources.append(enc)
        resources.append(make_observation(
            p["id"], enc["id"], CURRENTLY_PREGNANT, "Currently pregnant", last_anc, valueBoolean=True,
        ))
        resources.append(make_observation(
            p["id"], enc["id"], RETURN_VISIT_DATE, "Return visit date", last_anc,
            valueDateTime=ts(last_anc + timedelta(days=7)),
        ))
        if i == 0:
            resources.append(make_observation(
                p["id"], enc["id"], SYSTOLIC_BP, "Systolic blood pressure", last_anc,
                valueQuantity=quantity(145.0, "mmHg"),
            ))
    scenarios.append({
        "id": "overdue_anc",
        "title": "Pregnant patients overdue for follow-up",
        "expect": "3 pregnant patients missed their return visit date and have not been seen since. "
                  "One of them had a systolic blood pressure of 145 at her last visit.",
        "patient_ids": [p["id"] for p in anc_patients],
        "high_bp_patient_id": anc_patients[0]["id"],
    })

    # ── Scenario 4: 14 visits in the demo week with no location recorded ─────
    unlocated = random.sample(demo_week_visits, 14)
    for enc in unlocated:
        strip_location(enc)
    scenarios.append({
        "id": "missing_location",
        "title": "Visits with no location recorded",
        "expect": "14 visits in the latest week were saved without a location.",
        "count": 14,
    })

    # ── Scenario 6: 3 visits logged after the patient's recorded death ───────
    after_death = random.sample(deceased, 3)
    after_death_chws = []
    for p in after_death:
        chw = random.choice(CHWS[5:])
        day = DEMO_WEEK_START + timedelta(days=random.randint(0, 4), hours=11)
        resources.append(make_encounter(p["id"], chw, day))
        after_death_chws.append(chw["id"])
    scenarios.append({
        "id": "visits_after_death",
        "title": "Visits logged for deceased patients",
        "expect": "3 visits in the latest week were logged for patients whose death was recorded earlier.",
        "count": 3,
        "patient_ids": [p["id"] for p in after_death],
        "chw_ids": after_death_chws,
    })

    # ── Scenario 7: child under five with fever and fast breathing ───────────
    child = random.choice([p for p in living if age_years(p, DEMO_WEEK_START) < 5])
    child_chw = CHWS[4]
    child_day = DEMO_WEEK_START + timedelta(days=2, hours=14)
    enc = make_encounter(child["id"], child_chw, child_day, reason="Child sick visit")
    resources.append(enc)
    resources.append(make_observation(
        child["id"], enc["id"], TEMPERATURE, "Temperature (c)", child_day, valueQuantity=quantity(39.1, "DEG C"),
    ))
    resources.append(make_observation(
        child["id"], enc["id"], RESPIRATORY_RATE, "Respiratory rate", child_day,
        valueQuantity=quantity(62.0, "breaths/min"),
    ))
    scenarios.append({
        "id": "child_danger_signs",
        "title": "Child under five with danger signs",
        "expect": f"A child under five seen by {child_chw['id']} had a temperature of 39.1 C and a respiratory "
                  "rate of 62 breaths per minute, which needs urgent referral.",
        "chw_ids": [child_chw["id"]],
        "patient_ids": [child["id"]],
    })

    return resources, scenarios


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

    print("Loading patients from localized bundles...")
    patients = load_patients(fixtures_dir)
    if not patients:
        print("No patients found in localized bundles.")
        raise SystemExit(1)
    print(f"Found {len(patients)} patients.")

    print("Building CHW resources and seeded scenarios...")
    resources, scenarios = build_resources(patients)

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

    (fixtures_dir / "scenarios.json").write_text(json.dumps({
        "demo_week_start": DEMO_WEEK_START.strftime("%Y-%m-%d"),
        "scenarios": scenarios,
    }, indent=2))

    encounters = sum(1 for r in resources if r.get("resourceType") == "Encounter")
    observations = sum(1 for r in resources if r.get("resourceType") == "Observation")
    practitioners = sum(1 for r in resources if r.get("resourceType") == "Practitioner")
    conditions = sum(1 for r in resources if r.get("resourceType") == "Condition")
    print(
        f"Done: {practitioners} CHWs, {encounters} encounters, "
        f"{observations} observations, {conditions} conditions, {len(scenarios)} scenarios"
    )
    print(f"Written {len(chunks)} bundles to {out_dir}")


if __name__ == "__main__":
    main()
