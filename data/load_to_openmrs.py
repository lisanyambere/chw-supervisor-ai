#!/usr/bin/env python3
"""
Bulk-loads localized FHIR bundles and CHW overlay into OpenMRS.

Loads in order: localized patient bundles → CHW overlay bundles.
Skips bundles that fail and reports a summary at the end.
"""
import json
import sys
import time
import base64
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

OPENMRS_BASE = "http://localhost:8080/openmrs"
FHIR_BASE    = f"{OPENMRS_BASE}/ws/fhir2/R4"
USERNAME     = "admin"
PASSWORD     = "Admin123"

# OpenMRS FHIR transaction endpoint has a practical limit; individual resource
# POSTs are more reliable for large patient bundles.
CHUNK_PATIENT_BUNDLE = True


def auth_header() -> str:
    creds = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
    return f"Basic {creds}"


def post_bundle(bundle: dict, label: str) -> bool:
    payload = json.dumps(bundle).encode()
    req = Request(
        f"{FHIR_BASE}",
        data=payload,
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            result = json.loads(body)
            issues = [e for e in result.get("entry", []) if e.get("response", {}).get("status", "").startswith("4")]
            if issues:
                print(f"  [WARN] {label}: {len(issues)} entries had 4xx responses")
            return True
    except HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  [FAIL] {label}: HTTP {e.code} — {body}")
        return False
    except URLError as e:
        print(f"  [FAIL] {label}: {e.reason}")
        return False


def post_resource(resource: dict, label: str) -> bool:
    rtype = resource.get("resourceType")
    rid   = resource.get("id")
    url   = f"{FHIR_BASE}/{rtype}/{rid}" if rid else f"{FHIR_BASE}/{rtype}"
    method = "PUT" if rid else "POST"

    payload = json.dumps(resource).encode()
    req = Request(
        url,
        data=payload,
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as resp:
            resp.read()
            return True
    except HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  [FAIL] {label} {rtype}/{rid}: HTTP {e.code} — {body}")
        return False
    except URLError as e:
        print(f"  [FAIL] {label}: {e.reason}")
        return False


def check_openmrs() -> bool:
    req = Request(
        f"{OPENMRS_BASE}/ws/rest/v1/session",
        headers={"Authorization": auth_header()},
    )
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("authenticated", False)
    except Exception:
        return False


# Resources must be posted parent-before-child to avoid 404s on references.
LOAD_ORDER = ["Patient", "Practitioner", "Organization", "Location",
              "Encounter", "Condition", "Observation", "Procedure",
              "MedicationRequest", "DiagnosticReport", "ImagingStudy"]


def sort_entries_by_dependency(entries: list[dict]) -> list[dict]:
    def rank(entry: dict) -> int:
        rtype = entry.get("resource", {}).get("resourceType", "")
        try:
            return LOAD_ORDER.index(rtype)
        except ValueError:
            return len(LOAD_ORDER)
    return sorted(entries, key=rank)


def load_directory(bundle_dir: Path, label: str) -> tuple[int, int]:
    files = sorted(bundle_dir.glob("*.json"))
    ok = 0
    fail = 0

    for i, path in enumerate(files, 1):
        with open(path) as f:
            bundle = json.load(f)

        entries = bundle.get("entry", [])
        print(f"  [{i}/{len(files)}] {path.name} ({len(entries)} entries)...", end=" ", flush=True)

        # Post each resource individually, parents before children
        if CHUNK_PATIENT_BUNDLE and bundle.get("type") == "transaction":
            file_ok = file_fail = 0
            for entry in sort_entries_by_dependency(entries):
                resource = entry.get("resource", {})
                if not resource:
                    continue
                if post_resource(resource, path.name):
                    file_ok += 1
                else:
                    file_fail += 1
                time.sleep(0.05)  # gentle rate limit
            ok += file_ok
            fail += file_fail
            print(f"ok={file_ok} fail={file_fail}")
        else:
            if post_bundle(bundle, path.name):
                ok += len(entries)
                print("ok")
            else:
                fail += len(entries)

    return ok, fail


def smoke_test() -> None:
    print("\nSmoke tests...")

    endpoints = [
        ("Patient count",      f"{FHIR_BASE}/Patient?_summary=count"),
        ("Encounter count",    f"{FHIR_BASE}/Encounter?_summary=count"),
        ("Practitioner count", f"{FHIR_BASE}/Practitioner?_summary=count"),
        ("Observation count",  f"{FHIR_BASE}/Observation?_summary=count"),
    ]

    for label, url in endpoints:
        req = Request(url, headers={"Authorization": auth_header(), "Accept": "application/fhir+json"})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                total = data.get("total", "?")
                print(f"  {label}: {total}")
        except Exception as e:
            print(f"  {label}: ERROR — {e}")


def main() -> None:
    print("Checking OpenMRS connection...")
    if not check_openmrs():
        print("Cannot reach OpenMRS. Is it running? Check docker compose ps.")
        sys.exit(1)
    print("Connected.\n")

    fixtures_dir = Path(__file__).parent / "fixtures"
    localized_dir = fixtures_dir / "localized"
    chw_dir       = fixtures_dir / "chw"

    if not localized_dir.exists():
        print(f"Localized data not found at {localized_dir}")
        print("Run: python data/synthea/kenyan-localization/localize.py")
        sys.exit(1)

    if not chw_dir.exists():
        print(f"CHW data not found at {chw_dir}")
        print("Run: python data/chw_overlay/generate_chw_activity.py")
        sys.exit(1)

    print("Loading patient bundles...")
    p_ok, p_fail = load_directory(localized_dir, "patients")

    print("\nLoading CHW overlay bundles...")
    c_ok, c_fail = load_directory(chw_dir, "chw")

    print(f"\nLoad complete — resources ok: {p_ok + c_ok}, failed: {p_fail + c_fail}")

    smoke_test()


if __name__ == "__main__":
    main()
