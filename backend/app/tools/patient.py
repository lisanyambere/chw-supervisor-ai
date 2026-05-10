"""Patient-related tools."""
from __future__ import annotations

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
