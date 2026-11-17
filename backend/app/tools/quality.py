"""Data-quality tools: records that cannot be right as written."""
from __future__ import annotations

from typing import Any

from app.fhir import FhirClient, get_id_map
from app.tools._shared import (
    encounter_context,
    gather_bounded,
    is_program_patient,
    since_date,
)
from app.tools.registry import tool

_DAYS = {
    "type": "integer",
    "description": "Look-back window in days. Default 7.",
    "default": 7,
    "minimum": 1,
    "maximum": 90,
}


@tool(
    name="visits_missing_location",
    description=(
        "Visits in the last N days that were saved without a location, per CHW. "
        "A visit with no location cannot be verified as having happened in the "
        "household, so a CHW with many of them needs a device or training check."
    ),
    parameters={"type": "object", "properties": {"days": _DAYS}, "required": []},
)
async def visits_missing_location(client: FhirClient, days: int = 7) -> dict[str, Any]:
    idmap = get_id_map()
    since = since_date(days)

    async def _for_chw(chw_id: str, uuid: str) -> dict[str, Any]:
        window = {"participant": uuid, "date": f"ge{since}"}
        total = await client.count("Encounter", params=window)
        # Every located visit a CHW makes is in their home ward.
        ward_uuid = idmap.wards.get(idmap.chw_wards.get(chw_id, ""))
        located = (
            await client.count("Encounter", params={**window, "location": ward_uuid})
            if ward_uuid
            else 0
        )
        return {
            "chw_id": chw_id,
            "ward": idmap.chw_wards.get(chw_id),
            "visits": total,
            "missing_location": total - located,
        }

    per_chw = await gather_bounded(
        _for_chw(chw_id, uuid) for chw_id, uuid in sorted(idmap.practitioners.items())
    )
    rows = [r for r in per_chw if r["missing_location"] > 0]
    rows.sort(key=lambda r: r["missing_location"], reverse=True)
    return {
        "days": days,
        "since": since,
        "total_visits": sum(r["visits"] for r in per_chw),
        "total_missing_location": sum(r["missing_location"] for r in rows),
        "rows": rows,
    }


@tool(
    name="visits_after_death",
    description=(
        "Visits in the last N days logged for a patient whose death was already "
        "recorded. Either the death record or the visit is wrong; each one needs "
        "checking with the CHW who logged it."
    ),
    parameters={"type": "object", "properties": {"days": _DAYS}, "required": []},
)
async def visits_after_death(client: FhirClient, days: int = 7) -> dict[str, Any]:
    since = since_date(days)
    deceased = [
        p
        for p in await client.search(
            "Patient", params={"death-date": f"lt{since_date(0)}", "_count": 100}
        )
        if is_program_patient(p.get("id", ""))
    ]

    async def _visits(patient: dict[str, Any]) -> list[dict[str, Any]]:
        died = (patient.get("deceasedDateTime") or "")[:10]
        encounters = await client.search(
            "Encounter",
            params={
                "patient": patient["id"],
                "date": [f"gt{max(died, since)}"],
            },
            max_pages=1,
        )
        name = (patient.get("name") or [{}])[0]
        return [
            {
                "patient_uuid": patient["id"],
                "patient_name": " ".join(
                    [*(name.get("given") or []), name.get("family") or ""]
                ).strip(),
                "death_date": died,
                "visit_date": ctx["date"],
                "chw_id": ctx["chw_id"],
                "ward": ctx["ward"],
            }
            for ctx in (encounter_context(e) for e in encounters)
        ]

    per_patient = await gather_bounded(_visits(p) for p in deceased)
    rows = [v for visits in per_patient for v in visits]
    rows.sort(key=lambda r: r["visit_date"])
    return {
        "days": days,
        "since": since,
        "deceased_patients_checked": len(deceased),
        "visit_count": len(rows),
        "rows": rows,
    }
