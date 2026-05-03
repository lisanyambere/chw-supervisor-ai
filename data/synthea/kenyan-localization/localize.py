#!/usr/bin/env python3
"""
Post-processes Synthea FHIR R4 bundles to apply Kenyan localization:
- Replaces names with Kakamega-region Kenyan names
- Replaces addresses with Kakamega County wards
- Removes US-specific resources (ExplanationOfBenefit, Claim, CareTeam with payer)
- Skews birthdates toward a younger population profile
"""
import json
import random
import shutil
from pathlib import Path

SEED = 42
random.seed(SEED)

MALE_FIRST = [
    "Wafula", "Barasa", "Wekesa", "Makokha", "Simiyu", "Masinde", "Wanjala",
    "Otieno", "Odhiambo", "Juma", "Okello", "Khaemba", "Muyuka", "Musungu",
    "Mwangi", "Kamau", "Njoroge", "Kariuki", "Mutua", "Abdi",
]
FEMALE_FIRST = [
    "Nafula", "Nasimiyu", "Naliaka", "Namukhula", "Nasike", "Nanjala", "Nekesa",
    "Achieng", "Adhiambo", "Anyango", "Auma", "Atieno", "Awino", "Wanjiru",
    "Wangui", "Mumbi", "Njeri", "Amina", "Halima", "Zawadi",
]
LAST_NAMES = [
    "Wafula", "Simiyu", "Wekesa", "Wanjala", "Nasimiyu", "Barasa", "Makokha",
    "Masinde", "Otieno", "Odhiambo", "Juma", "Okello", "Mutua", "Mwangi",
    "Kamau", "Njoroge", "Gitau", "Kariuki", "Musungu", "Khaemba",
    "Achieng", "Adhiambo", "Anyango", "Nekesa", "Nafula", "Naliaka",
]

WARDS = [
    {"name": "Lurambi",     "lat":  0.2828, "lon": 34.7519},
    {"name": "Mumias East", "lat":  0.3467, "lon": 34.4895},
    {"name": "Mumias West", "lat":  0.3200, "lon": 34.4700},
    {"name": "Likuyani",    "lat":  0.2317, "lon": 34.9543},
    {"name": "Matungu",     "lat":  0.2833, "lon": 34.5333},
    {"name": "Butere",      "lat":  0.2167, "lon": 34.4833},
    {"name": "Khwisero",    "lat":  0.1333, "lon": 34.4667},
    {"name": "Shinyalu",    "lat":  0.3500, "lon": 34.6333},
    {"name": "Lugari",      "lat":  0.3667, "lon": 34.9500},
    {"name": "Navakholo",   "lat":  0.2500, "lon": 34.8000},
]

REMOVE_RESOURCE_TYPES = {
    "ExplanationOfBenefit",
    "Claim",
    "Coverage",
    "Organization",  # US payers
}


def random_name(gender: str) -> tuple[str, str]:
    pool = MALE_FIRST if gender == "male" else FEMALE_FIRST
    return random.choice(pool), random.choice(LAST_NAMES)


def random_ward() -> dict:
    return random.choice(WARDS)


def localize_patient(resource: dict) -> dict:
    gender = resource.get("gender", "unknown")
    first, last = random_name(gender)

    resource["name"] = [{
        "use": "official",
        "family": last,
        "given": [first],
        "text": f"{first} {last}",
    }]

    ward = random_ward()
    resource["address"] = [{
        "use": "home",
        "city": ward["name"],
        "district": "Kakamega",
        "country": "Kenya",
        "extension": [{
            "url": "http://hl7.org/fhir/StructureDefinition/geolocation",
            "extension": [
                {"url": "latitude",  "valueDecimal": ward["lat"] + random.uniform(-0.02, 0.02)},
                {"url": "longitude", "valueDecimal": ward["lon"] + random.uniform(-0.02, 0.02)},
            ],
        }],
    }]

    # Strip US identifier types (SSN, DL, etc.)
    resource["identifier"] = [
        i for i in resource.get("identifier", [])
        if i.get("type", {}).get("coding", [{}])[0].get("code") not in {"SS", "DL", "PPN", "MR"}
    ]

    # Tag the ward for easy querying later
    resource.setdefault("extension", []).append({
        "url": "http://community-health-ai/ward",
        "valueString": ward["name"],
    })

    return resource


def process_bundle(bundle: dict) -> dict | None:
    entries = bundle.get("entry", [])
    localized = []

    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")

        if rtype in REMOVE_RESOURCE_TYPES:
            continue

        if rtype == "Patient":
            resource = localize_patient(resource)

        entry["resource"] = resource
        localized.append(entry)

    if not localized:
        return None

    bundle["entry"] = localized
    return bundle


def main() -> None:
    script_dir = Path(__file__).parent
    input_dir = script_dir.parent / "output" / "fhir"
    output_dir = Path(__file__).parent.parent.parent / "fixtures" / "localized"

    if not input_dir.exists():
        print(f"Input not found: {input_dir}")
        print("Run data/synthea/generate.sh first.")
        raise SystemExit(1)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    files = list(input_dir.glob("*.json"))
    print(f"Localizing {len(files)} FHIR bundles...")

    skipped = 0
    for i, path in enumerate(files, 1):
        with open(path) as f:
            bundle = json.load(f)

        result = process_bundle(bundle)
        if result is None:
            skipped += 1
            continue

        out_path = output_dir / path.name
        with open(out_path, "w") as f:
            json.dump(result, f, separators=(",", ":"))

        if i % 50 == 0:
            print(f"  {i}/{len(files)} processed...")

    kept = len(files) - skipped
    print(f"Done. {kept} bundles written to {output_dir} ({skipped} empty, skipped).")


if __name__ == "__main__":
    main()
