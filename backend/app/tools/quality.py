"""Data-quality tools: records that cannot be right as written."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
        "Visits in the last N days that were saved without a location, per CHW "
        "and per week (weeks start on Monday), so you can say whether they are "
        "recent. A visit with no location cannot be verified as having happened "
        "in the household, so a CHW with many of them needs a device or "
        "training check."
    ),
    parameters={"type": "object", "properties": {"days": _DAYS}, "required": []},
)
async def visits_missing_location(client: FhirClient, days: int = 7) -> dict[str, Any]:
    idmap = get_id_map()
    today = datetime.now(tz=UTC).date()
    since = today - timedelta(days=days)
    # Weeks overlapping the window, clipped to it: [(start, end_exclusive)].
    weeks: list[tuple[date, date]] = []
    start = since
    while start <= today:
        end = min(
            start + timedelta(days=7 - start.weekday()), today + timedelta(days=1)
        )
        weeks.append((start, end))
        start = end

    async def _missing(uuid: str, ward_uuid: str | None, lo: date, hi: date) -> int:
        window = {
            "participant": uuid,
            "date": [f"ge{lo}T00:00:00Z", f"lt{hi}T00:00:00Z"],
        }
        total = await client.count("Encounter", params=window)
        # Every located visit a CHW makes is in their home ward.
        located = (
            await client.count("Encounter", params={**window, "location": ward_uuid})
            if ward_uuid
            else 0
        )
        return total - located

    chws = sorted(idmap.practitioners.items())
    counts = await gather_bounded(
        _missing(uuid, idmap.wards.get(idmap.chw_wards.get(chw_id, "")), lo, hi)
        for chw_id, uuid in chws
        for lo, hi in weeks
    )

    rows: list[dict[str, Any]] = []
    for i, (chw_id, _) in enumerate(chws):
        per_week = counts[i * len(weeks) : (i + 1) * len(weeks)]
        if not any(per_week):
            continue
        rows.append(
            {
                "chw_id": chw_id,
                "ward": idmap.chw_wards.get(chw_id),
                "missing_location": sum(per_week),
                "weeks": {
                    lo.isoformat(): n
                    for (lo, _), n in zip(weeks, per_week, strict=True)
                    if n
                },
            }
        )
    rows.sort(key=lambda r: r["missing_location"], reverse=True)
    by_week = [
        {
            "week_start": lo.isoformat(),
            "week_end": (hi - timedelta(days=1)).isoformat(),
            "missing_location": sum(counts[j :: len(weeks)]),
        }
        for j, (lo, hi) in enumerate(weeks)
    ]
    return {
        "days": days,
        "since": since.isoformat(),
        "total_missing_location": sum(r["missing_location"] for r in rows),
        "by_week": by_week,
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
