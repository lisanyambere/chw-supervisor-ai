#!/usr/bin/env python3
# One-off cleanup: delete every Encounter linked to our CHW practitioners so
# the loader can repost them date-shifted. Demo-data encounters reference
# other providers and are left untouched.
import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

FHIR_BASE = "http://localhost:8080/openmrs/ws/fhir2/R4"
USER, PW = "admin", "Admin123"
AUTH = "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()


def _req(url: str, method: str = "GET") -> Request:
    return Request(
        url,
        headers={"Authorization": AUTH, "Accept": "application/fhir+json"},
        method=method,
    )


def collect_ids(practitioner_uuid: str) -> set[str]:
    ids: set[str] = set()
    url = f"{FHIR_BASE}/Encounter?participant={practitioner_uuid}&_count=200"
    while url:
        with urlopen(_req(url), timeout=30) as resp:
            bundle = json.loads(resp.read())
        for e in bundle.get("entry", []) or []:
            rid = (e.get("resource") or {}).get("id")
            if rid:
                ids.add(rid)
        url = None
        for link in bundle.get("link", []) or []:
            if link.get("relation") == "next":
                url = link.get("url")
    return ids


def delete_one(rid: str) -> bool:
    try:
        with urlopen(_req(f"{FHIR_BASE}/Encounter/{rid}", "DELETE"), timeout=30):
            return True
    except Exception as exc:
        print(f"  delete failed {rid}: {exc}")
        return False


def main() -> None:
    idmap = json.loads(Path("data/fixtures/id_map.json").read_text())
    pracs = list(idmap["practitioners"].values())
    all_ids: set[str] = set()
    for uuid in pracs:
        all_ids |= collect_ids(uuid)
    print(f"Encounters to delete: {len(all_ids)}")
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(delete_one, rid) for rid in all_ids]
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            if i % 200 == 0 or i == len(all_ids):
                print(f"  deleted {ok}/{len(all_ids)}")
    print(f"Done. Deleted {ok}/{len(all_ids)}.")


if __name__ == "__main__":
    main()
