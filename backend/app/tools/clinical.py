"""Clinical tools: what the visits recorded about patients, not how many there were."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.fhir import FhirClient
from app.tools._shared import (
    CURRENTLY_PREGNANT,
    MALARIA,
    RESPIRATORY_RATE,
    RETURN_VISIT_DATE,
    SYSTOLIC_BP,
    TEMPERATURE,
    encounter_context,
    gather_bounded,
    observations,
    ref_id,
    since_date,
)
from app.tools.registry import tool

_DAYS = {
    "type": "integer",
    "description": "Look-back window in days.",
    "minimum": 1,
    "maximum": 90,
}


def _patient_name(obs: dict[str, Any]) -> str:
    # FHIR2 puts "Given Family (OpenMRS ID: ...)" in subject.display.
    return ((obs.get("subject") or {}).get("display") or "").split(" (")[0]


def _value(obs: dict[str, Any]) -> float | None:
    v = (obs.get("valueQuantity") or {}).get("value")
    return float(v) if v is not None else None


async def _visit_context(client: FhirClient, obs: dict[str, Any]) -> dict[str, Any]:
    encounter = await client.read("Encounter", ref_id(obs.get("encounter")))
    return encounter_context(encounter)


@tool(
    name="fever_cases_by_ward",
    description=(
        "Patients recorded with a fever (temperature at or above `min_temp` C) "
        "in the last N days, grouped by ward. Each ward lists its cases, the "
        "CHWs who saw them, the date range and how many also carry a malaria "
        "diagnosis. Several cases in one ward within a few days is a possible "
        "outbreak."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {**_DAYS, "default": 7},
            "min_temp": {
                "type": "number",
                "description": "Fever threshold in Celsius. Default 38.0.",
                "default": 38.0,
            },
        },
        "required": [],
    },
)
async def fever_cases_by_ward(
    client: FhirClient, days: int = 7, min_temp: float = 38.0
) -> dict[str, Any]:
    fevers = await observations(
        client, TEMPERATURE, days, **{"value-quantity": f"ge{min_temp}"}
    )
    contexts = await gather_bounded(_visit_context(client, o) for o in fevers)
    malaria_counts = await gather_bounded(
        client.count(
            "Condition", params={"patient": ref_id(o.get("subject")), "code": MALARIA}
        )
        for o in fevers
    )

    wards: dict[str, dict[str, Any]] = {}
    for obs, ctx, malaria in zip(fevers, contexts, malaria_counts, strict=True):
        ward = wards.setdefault(
            ctx["ward"] or "(no location recorded)",
            {"cases": [], "chw_ids": set(), "malaria_diagnosed": 0},
        )
        ward["cases"].append(
            {
                "patient_uuid": ref_id(obs.get("subject")),
                "patient_name": _patient_name(obs),
                "temperature_c": _value(obs),
                "date": ctx["date"],
                "chw_id": ctx["chw_id"],
            }
        )
        if ctx["chw_id"]:
            ward["chw_ids"].add(ctx["chw_id"])
        if malaria:
            ward["malaria_diagnosed"] += 1

    rows = [
        {
            "ward": name,
            "case_count": len(w["cases"]),
            "malaria_diagnosed": w["malaria_diagnosed"],
            "chw_ids": sorted(w["chw_ids"]),
            "first_date": min(c["date"] for c in w["cases"]),
            "last_date": max(c["date"] for c in w["cases"]),
            "cases": sorted(w["cases"], key=lambda c: c["date"]),
        }
        for name, w in wards.items()
    ]
    rows.sort(key=lambda r: r["case_count"], reverse=True)
    return {
        "days": days,
        "since": since_date(days),
        "min_temp": min_temp,
        "total_cases": len(fevers),
        "rows": rows,
    }


def _age_months(birth_date: str, on: str) -> int:
    born, at = date.fromisoformat(birth_date), date.fromisoformat(on)
    return (at.year - born.year) * 12 + at.month - born.month - (at.day < born.day)


@tool(
    name="child_danger_signs",
    description=(
        "Children under five recorded with fast breathing in the last N days "
        "(IMCI thresholds: 50+ breaths/min under 12 months, 40+ from 12 to 59 "
        "months), with their temperature at the same visit. Fast breathing with "
        "fever is a danger sign that needs same-day referral."
    ),
    parameters={
        "type": "object",
        "properties": {"days": {**_DAYS, "default": 7}},
        "required": [],
    },
)
async def child_danger_signs(client: FhirClient, days: int = 7) -> dict[str, Any]:
    fast = await observations(
        client, RESPIRATORY_RATE, days, **{"value-quantity": "ge40"}
    )

    async def _assess(obs: dict[str, Any]) -> dict[str, Any] | None:
        patient = await client.read("Patient", ref_id(obs.get("subject")))
        ctx = await _visit_context(client, obs)
        if not patient.get("birthDate") or not ctx["date"]:
            return None
        months = _age_months(patient["birthDate"], ctx["date"])
        rate = _value(obs) or 0.0
        if months >= 60 or rate < (50 if months < 12 else 40):
            return None
        temps = await client.search(
            "Observation",
            params={"encounter": ref_id(obs.get("encounter")), "code": TEMPERATURE},
            max_pages=1,
        )
        return {
            "patient_uuid": patient.get("id"),
            "patient_name": _patient_name(obs),
            "age_months": months,
            "respiratory_rate": rate,
            "temperature_c": _value(temps[0]) if temps else None,
            **ctx,
        }

    children = [c for c in await gather_bounded(_assess(o) for o in fast) if c]
    return {
        "days": days,
        "since": since_date(days),
        "child_count": len(children),
        "children": children,
    }


@tool(
    name="overdue_followups",
    description=(
        "Patients who were given a return-visit date that has passed and who "
        "have not been seen since. Each row says how many days overdue, whether "
        "the patient is pregnant, and the systolic blood pressure at the last "
        "visit (140 or above in pregnancy is urgent)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {
                **_DAYS,
                "description": "How far back to look for the last visit. Default 60.",
                "default": 60,
            }
        },
        "required": [],
    },
)
async def overdue_followups(client: FhirClient, days: int = 60) -> dict[str, Any]:
    today = datetime.now(tz=UTC).date()
    booked = await observations(client, RETURN_VISIT_DATE, days)

    async def _assess(obs: dict[str, Any]) -> dict[str, Any] | None:
        due = date.fromisoformat((obs.get("valueDateTime") or "")[:10])
        if due >= today:
            return None
        patient_uuid = ref_id(obs.get("subject"))
        ctx = await _visit_context(client, obs)
        # OpenMRS treats `gt<day>` as "after the start of that day", which
        # would count the visit itself; ask from the next day instead.
        next_day = date.fromisoformat(ctx["date"]) + timedelta(days=1)
        seen_since = await client.count(
            "Encounter", params={"patient": patient_uuid, "date": f"ge{next_day}"}
        )
        if seen_since:
            return None
        pregnant = await client.search(
            "Observation",
            params={"patient": patient_uuid, "code": CURRENTLY_PREGNANT},
            max_pages=1,
        )
        pressures = await client.search(
            "Observation",
            params={
                "patient": patient_uuid,
                "code": SYSTOLIC_BP,
                "_sort": "-date",
                "_count": 1,
            },
            max_pages=1,
        )
        return {
            "patient_uuid": patient_uuid,
            "patient_name": _patient_name(obs),
            "last_visit": ctx["date"],
            "return_date": due.isoformat(),
            "days_overdue": (today - due).days,
            "pregnant": any(o.get("valueBoolean") for o in pregnant),
            "last_systolic_bp": _value(pressures[0]) if pressures else None,
            "chw_id": ctx["chw_id"],
            "ward": ctx["ward"],
        }

    overdue = [r for r in await gather_bounded(_assess(o) for o in booked) if r]
    overdue.sort(key=lambda r: r["days_overdue"], reverse=True)
    return {
        "days": days,
        "since": since_date(days),
        "overdue_count": len(overdue),
        "patients": overdue,
    }
