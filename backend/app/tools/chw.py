"""CHW-related tools."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.fhir import FhirClient, get_id_map
from app.tools.registry import tool


@tool(
    name="list_chws",
    description=(
        "List all Community Health Workers known to the system. "
        "Returns the local CHW id (e.g. 'chw-001') and the OpenMRS Practitioner UUID. "
        "Use this when the supervisor refers to CHWs without specifying which one."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
async def list_chws(client: FhirClient) -> list[dict[str, str]]:  # noqa: ARG001
    idmap = get_id_map()
    return [
        {"chw_id": chw_id, "practitioner_uuid": uuid}
        for chw_id, uuid in sorted(idmap.practitioners.items())
    ]


@tool(
    name="count_chw_encounters",
    description=(
        "Count the number of Encounters a CHW has performed in the last N days. "
        "Use to spot inactive CHWs or compare workload across the team."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chw_id": {
                "type": "string",
                "description": "Local CHW id like 'chw-001' OR an OpenMRS Practitioner UUID.",
            },
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 7.",
                "default": 7,
                "minimum": 1,
                "maximum": 365,
            },
        },
        "required": ["chw_id"],
    },
)
async def count_chw_encounters(
    client: FhirClient, chw_id: str, days: int = 7
) -> dict[str, Any]:
    practitioner_uuid = _resolve_practitioner_uuid(chw_id)
    if practitioner_uuid is None:
        return {"error": f"unknown chw_id: {chw_id}"}

    since = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    total = await client.count(
        "Encounter",
        params={"participant": practitioner_uuid, "date": f"ge{since}"},
    )
    return {
        "chw_id": chw_id,
        "practitioner_uuid": practitioner_uuid,
        "days": days,
        "since": since,
        "encounter_count": total,
    }


@tool(
    name="team_activity_summary",
    description=(
        "Return a per-CHW encounter count for the last N days, sorted ascending. "
        "Useful as the first step of a Monday briefing — shows who is under- or "
        "over-active."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 7.",
                "default": 7,
                "minimum": 1,
                "maximum": 365,
            }
        },
        "required": [],
    },
)
async def team_activity_summary(
    client: FhirClient, days: int = 7
) -> dict[str, Any]:
    idmap = get_id_map()
    since = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows: list[dict[str, Any]] = []
    for chw_id, uuid in sorted(idmap.practitioners.items()):
        n = await client.count(
            "Encounter",
            params={"participant": uuid, "date": f"ge{since}"},
        )
        rows.append({"chw_id": chw_id, "encounter_count": n})

    rows.sort(key=lambda r: r["encounter_count"])
    if rows:
        counts = [r["encounter_count"] for r in rows]
        stats = {
            "min": min(counts),
            "max": max(counts),
            "mean": round(sum(counts) / len(counts), 2),
            "total": sum(counts),
        }
    else:
        stats = {"min": 0, "max": 0, "mean": 0.0, "total": 0}

    return {"days": days, "since": since, "rows": rows, "stats": stats}


def _resolve_practitioner_uuid(chw_id: str) -> str | None:
    idmap = get_id_map()
    if chw_id in idmap.practitioners:
        return idmap.practitioners[chw_id]
    # Already a UUID?
    if chw_id in idmap.openmrs_to_chw:
        return chw_id
    return None


@tool(
    name="chw_inactivity",
    description=(
        "List CHWs whose encounter count over the last N days is at or below "
        "`max_count` (default 0 = totally inactive). Use this to spot likely "
        "absences, defaulters, or data-sync issues — cheaper than a full "
        "team_activity_summary when the supervisor only cares about the bottom "
        "of the distribution."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 7.",
                "default": 7,
                "minimum": 1,
                "maximum": 365,
            },
            "max_count": {
                "type": "integer",
                "description": (
                    "Inclusive upper bound on encounter count. 0 = "
                    "completely inactive CHWs only."
                ),
                "default": 0,
                "minimum": 0,
            },
        },
        "required": [],
    },
)
async def chw_inactivity(
    client: FhirClient, days: int = 7, max_count: int = 0
) -> dict[str, Any]:
    idmap = get_id_map()
    since = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    async def _count_for(chw_id: str, uuid: str) -> tuple[str, int]:
        n = await client.count(
            "Encounter",
            params={"participant": uuid, "date": f"ge{since}"},
        )
        return chw_id, n

    pairs = sorted(idmap.practitioners.items())
    results = await asyncio.gather(
        *(_count_for(cid, uuid) for cid, uuid in pairs)
    )
    inactive = [
        {"chw_id": cid, "encounter_count": n}
        for cid, n in results
        if n <= max_count
    ]
    inactive.sort(key=lambda r: (r["encounter_count"], r["chw_id"]))
    return {
        "days": days,
        "since": since,
        "max_count": max_count,
        "inactive_chws": inactive,
        "inactive_count": len(inactive),
        "team_size": len(pairs),
    }


@tool(
    name="visits_by_day",
    description=(
        "Daily encounter counts over the last N days, optionally scoped to one "
        "CHW. Use this to spot trends — Friday slumps, weekend coverage gaps, "
        "or a CHW whose activity dropped off mid-week."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 14.",
                "default": 14,
                "minimum": 1,
                "maximum": 90,
            },
            "chw_id": {
                "type": "string",
                "description": (
                    "Optional CHW to scope to (local id or Practitioner UUID). "
                    "Omit for the whole team."
                ),
            },
        },
        "required": [],
    },
)
async def visits_by_day(
    client: FhirClient, days: int = 14, chw_id: str | None = None
) -> dict[str, Any]:
    practitioner_uuid: str | None = None
    if chw_id is not None:
        practitioner_uuid = _resolve_practitioner_uuid(chw_id)
        if practitioner_uuid is None:
            return {"error": f"unknown chw_id: {chw_id}"}

    today = datetime.now(tz=UTC).date()
    day_dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    async def _count_for(d: Any) -> tuple[str, int]:
        params: dict[str, Any] = {"date": [f"ge{d.isoformat()}", f"lt{(d + timedelta(days=1)).isoformat()}"]}
        if practitioner_uuid is not None:
            params["participant"] = practitioner_uuid
        n = await client.count("Encounter", params=params)
        return d.isoformat(), n

    pairs = await asyncio.gather(*(_count_for(d) for d in day_dates))
    series = [{"date": d, "encounter_count": n} for d, n in pairs]
    counts = [n for _, n in pairs]
    return {
        "days": days,
        "chw_id": chw_id,
        "series": series,
        "stats": {
            "min": min(counts) if counts else 0,
            "max": max(counts) if counts else 0,
            "mean": round(sum(counts) / len(counts), 2) if counts else 0.0,
            "total": sum(counts),
        },
    }


@tool(
    name="chw_patient_panel",
    description=(
        "List the distinct patients a CHW has had encounters with over the last "
        "N days. Use to scope a follow-up question to a specific CHW's caseload."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chw_id": {
                "type": "string",
                "description": "Local CHW id like 'chw-001' OR an OpenMRS Practitioner UUID.",
            },
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 30.",
                "default": 30,
                "minimum": 1,
                "maximum": 365,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum distinct patients to return.",
                "default": 25,
                "minimum": 1,
                "maximum": 200,
            },
        },
        "required": ["chw_id"],
    },
)
async def chw_patient_panel(
    client: FhirClient, chw_id: str, days: int = 30, limit: int = 25
) -> dict[str, Any]:
    practitioner_uuid = _resolve_practitioner_uuid(chw_id)
    if practitioner_uuid is None:
        return {"error": f"unknown chw_id: {chw_id}"}

    since = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    encounters = await client.search(
        "Encounter",
        params={
            "participant": practitioner_uuid,
            "date": f"ge{since}",
            "_sort": "-date",
            "_count": min(limit * 4, 200),
        },
        max_pages=3,
    )

    # Dedupe by subject UUID, keep first (most recent) seen.
    seen: dict[str, dict[str, Any]] = {}
    for e in encounters:
        subj_ref = (e.get("subject") or {}).get("reference") or ""
        if not subj_ref.startswith("Patient/"):
            continue
        puuid = subj_ref.split("/", 1)[1]
        if puuid in seen:
            seen[puuid]["encounter_count"] += 1
            continue
        if len(seen) >= limit:
            continue
        seen[puuid] = {
            "patient_uuid": puuid,
            "last_encounter_date": (e.get("period") or {}).get("start"),
            "encounter_count": 1,
        }

    return {
        "chw_id": chw_id,
        "days": days,
        "since": since,
        "patient_count": len(seen),
        "patients": list(seen.values()),
    }
