"""ID map loader: synthea_uuid → openmrs_uuid for patients, chw-NNN → uuid for CHWs."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core import get_logger, get_settings

log = get_logger(__name__)


class IdMap:
    """Wraps the JSON map produced by `data/load_to_openmrs.py`."""

    def __init__(
        self,
        patients: dict[str, str],
        practitioners: dict[str, str],
        wards: dict[str, str] | None = None,
        chw_wards: dict[str, str] | None = None,
    ):
        self.patients = patients
        self.practitioners = practitioners
        # Ward name → OpenMRS Location uuid, and each CHW's home ward.
        self.wards = wards or {}
        self.chw_wards = chw_wards or {}
        self.openmrs_to_ward = {v: k for k, v in self.wards.items()}
        # Reverse maps for quick lookup the other direction.
        self.openmrs_to_synthea = {v: k for k, v in patients.items()}
        self.openmrs_to_chw = {v: k for k, v in practitioners.items()}

    @property
    def chw_ids(self) -> list[str]:
        return sorted(self.practitioners.keys())

    @property
    def chw_uuids(self) -> list[str]:
        return list(self.practitioners.values())


def _load(path: Path) -> IdMap:
    if not path.exists():
        log.warning("id_map.missing", path=str(path))
        return IdMap({}, {})
    data = json.loads(path.read_text(encoding="utf-8"))
    patients = data.get("patients") or {}
    practitioners = data.get("practitioners") or {}
    log.info(
        "id_map.loaded",
        patients=len(patients),
        practitioners=len(practitioners),
        path=str(path),
    )
    return IdMap(
        patients, practitioners, data.get("wards") or {}, data.get("chw_wards") or {}
    )


@lru_cache(maxsize=1)
def get_id_map() -> IdMap:
    return _load(get_settings().id_map_path)
