"""CHW-related tools."""
from __future__ import annotations

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
