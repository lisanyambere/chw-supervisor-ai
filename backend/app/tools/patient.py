"""Patient-related tools."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.fhir import FhirClient
from app.tools.registry import tool


@tool(
    name="get_patient_summary",
    description=(
        "Fetch a compact summary for a single patient by OpenMRS UUID: "
        "name, gender, birth date, address ward, and the last few encounters."
    ),
    parameters={
        "type": "object",
        "properties": {
            "patient_uuid": {
                "type": "string",
                "description": "OpenMRS Patient UUID.",
            },
            "encounter_limit": {
                "type": "integer",
                "description": "How many recent encounters to include.",
                "default": 5,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["patient_uuid"],
    },
)
async def get_patient_summary(
    client: FhirClient, patient_uuid: str, encounter_limit: int = 5
) -> dict[str, Any]:
    patient = await client.read("Patient", patient_uuid)
    encounters = await client.search(
        "Encounter",
        params={
            "subject": patient_uuid,
            "_sort": "-date",
            "_count": encounter_limit,
        },
        max_pages=1,
    )

    name = _format_name(patient.get("name") or [])
    addr = (patient.get("address") or [{}])[0]
    return {
        "uuid": patient.get("id"),
        "name": name,
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
        "address": {
            "city": addr.get("city"),
            "district": addr.get("district"),
            "country": addr.get("country"),
        },
        "encounters": [
            {
                "uuid": e.get("id"),
                "type": _format_codeable(e.get("type") or []),
                "period_start": (e.get("period") or {}).get("start"),
                "period_end": (e.get("period") or {}).get("end"),
            }
            for e in encounters
        ],
    }


def _format_name(names: list[dict[str, Any]]) -> str:
    if not names:
        return ""
    n = names[0]
    given = " ".join(n.get("given") or [])
    family = n.get("family", "")
    return f"{given} {family}".strip()


def _format_codeable(types: list[dict[str, Any]]) -> str | None:
    for t in types:
        for c in t.get("coding") or []:
            if c.get("display"):
                return c["display"]
            if c.get("code"):
                return c["code"]
    return None


def _patient_summary(p: dict[str, Any]) -> dict[str, Any]:
    """Compact dict used by find_patient and recent_deaths."""
    addr = (p.get("address") or [{}])[0]
    deceased = p.get("deceasedBoolean") or p.get("deceasedDateTime")
    return {
        "uuid": p.get("id"),
        "name": _format_name(p.get("name") or []),
        "gender": p.get("gender"),
        "birth_date": p.get("birthDate"),
        "address": {
            "city": addr.get("city"),
            "district": addr.get("district"),
            "country": addr.get("country"),
        },
        "deceased": deceased if deceased else None,
    }


@tool(
    name="find_patient",
    description=(
        "Search for a patient by name (or partial name). Returns a short list "
        "of candidates with UUIDs the supervisor can then drill into via "
        "`get_patient_summary`. Use this when the supervisor mentions a patient "
        "by name rather than UUID."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Patient name fragment (given or family).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum candidates to return.",
                "default": 5,
                "minimum": 1,
                "maximum": 25,
            },
        },
        "required": ["query"],
    },
)
async def find_patient(
    client: FhirClient, query: str, limit: int = 5
) -> dict[str, Any]:
    if not query or not query.strip():
        return {"error": "query must not be empty"}
    patients = await client.search(
        "Patient",
        params={"name": query.strip(), "_count": limit},
        max_pages=1,
    )
    return {
        "query": query.strip(),
        "match_count": len(patients[:limit]),
        "patients": [_patient_summary(p) for p in patients[:limit]],
    }


@tool(
    name="recent_deaths",
    description=(
        "List patients recorded as deceased within the last N days. Use to "
        "surface mortality the supervisor may need to follow up on, and to "
        "explain sudden drops in a CHW's caseload."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Look-back window in days. Default 30.",
                "default": 30,
                "minimum": 1,
                "maximum": 365,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum patients to return.",
                "default": 25,
                "minimum": 1,
                "maximum": 200,
            },
        },
        "required": [],
    },
)
async def recent_deaths(
    client: FhirClient, days: int = 30, limit: int = 25
) -> dict[str, Any]:
    since = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    # OpenMRS FHIR2 supports `death-date` as a date search param on Patient.
    patients = await client.search(
        "Patient",
        params={"death-date": f"ge{since}", "_count": limit},
        max_pages=2,
    )
    rows = [_patient_summary(p) for p in patients[:limit]]
    return {
        "days": days,
        "since": since,
        "death_count": len(rows),
        "patients": rows,
    }
