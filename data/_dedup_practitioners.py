#!/usr/bin/env python3
# One-off cleanup: collapse duplicate CHW Practitioner records.
#
# OpenMRS does not enforce Provider identifier uniqueness, so every pre-fix
# reseed created a fresh Practitioner per CHW. The loader's idempotency now
# searches identifiers before POST (see post_practitioners), but that only
# helps once there is a single record per identifier — otherwise the search
# returns an arbitrary duplicate that the freshly-loaded encounters do NOT
# reference, silently re-breaking the participant linkage on the next reseed.
#
# This script keeps exactly the UUIDs recorded in data/fixtures/id_map.json
# (the records the current encounters reference) and retires every other
# Practitioner that carries a CHW identifier AND has zero encounters. The
# zero-encounter guard means we can never orphan live data.
import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

FHIR_BASE = "http://localhost:8080/openmrs/ws/fhir2/R4"
USER, PW = "admin", "Admin123"
AUTH = "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()
HEADERS = {"Authorization": AUTH, "Accept": "application/fhir+json"}


def _get(url: str) -> dict:
    with urlopen(Request(url, headers=HEADERS), timeout=30) as resp:
        return json.loads(resp.read())


def search_practitioner_ids(chw_id: str) -> set[str]:
    data = _get(f"{FHIR_BASE}/Practitioner?identifier={chw_id}&_count=100")
    return {
        e["resource"]["id"]
        for e in (data.get("entry") or [])
        if (e.get("resource") or {}).get("id")
    }


def encounter_count(uuid: str) -> int:
    data = _get(f"{FHIR_BASE}/Encounter?participant={uuid}&_summary=count")
    return int(data.get("total", 0))


def delete_one(uuid: str) -> bool:
    try:
        with urlopen(
            Request(f"{FHIR_BASE}/Practitioner/{uuid}", headers=HEADERS, method="DELETE"),
            timeout=30,
        ):
            return True
    except Exception as exc:
        print(f"  delete failed {uuid}: {exc}")
        return False


def main() -> None:
    idmap = json.loads(Path("data/fixtures/id_map.json").read_text())
    practitioners = idmap["practitioners"]
    keepers = set(practitioners.values())

    # Collect every distinct practitioner that carries a CHW identifier.
    all_matches: set[str] = set()
    for chw_id in practitioners:
        all_matches |= search_practitioner_ids(chw_id)
    orphans = sorted(all_matches - keepers)
    print(f"Distinct CHW practitioners: {len(all_matches)}")
    print(f"  keepers (id_map): {len(keepers)}  orphans: {len(orphans)}")

    # Safety: never retire a record that still has encounters.
    deletable: list[str] = []
    skipped_live = 0
    for uuid in orphans:
        if encounter_count(uuid) == 0:
            deletable.append(uuid)
        else:
            skipped_live += 1
    if skipped_live:
        print(f"  SKIPPED {skipped_live} orphan(s) that still have encounters")
    if not deletable:
        print("Nothing to delete. Practitioner table already deduplicated.")
        return

    print(f"Deleting {len(deletable)} orphan practitioners...")
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(delete_one, u) for u in deletable]
        for fut in as_completed(futures):
            if fut.result():
                ok += 1
    print(f"Done. Retired {ok}/{len(deletable)} orphan practitioners.")


if __name__ == "__main__":
    main()
