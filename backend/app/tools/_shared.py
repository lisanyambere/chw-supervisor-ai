"""Helpers shared by the clinical and data-quality tools."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from app.fhir import FhirClient, get_id_map

T = TypeVar("T")

# OpenMRS runs on a small heap; cap how many FHIR requests one tool fans out.
_MAX_CONCURRENT = 8


def ciel(code: str) -> str:
    """CIEL concept uuid: the code right-padded with 'A' to 36 characters."""
    return code + "A" * (36 - len(code))


TEMPERATURE = ciel("5088")
RESPIRATORY_RATE = ciel("5242")
SYSTOLIC_BP = ciel("5085")
CURRENTLY_PREGNANT = ciel("1434")
RETURN_VISIT_DATE = ciel("5096")
MALARIA = ciel("116128")


def since_date(days: int) -> str:
    return (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


async def gather_bounded(coros: Iterable[Awaitable[T]]) -> list[T]:
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _run(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return list(await asyncio.gather(*(_run(c) for c in coros)))


def ref_id(reference: dict[str, Any] | None) -> str:
    """'Patient/abc' → 'abc'; '' when the reference is absent."""
    return ((reference or {}).get("reference") or "").split("/", 1)[-1]


def is_program_patient(patient_uuid: str) -> bool:
    """True for patients this program loaded. OpenMRS also ships demo patients
    with their own vitals, which must not leak into a briefing."""
    return patient_uuid in get_id_map().openmrs_to_synthea


def encounter_context(encounter: dict[str, Any]) -> dict[str, Any]:
    """Who made a visit and where, in program terms (chw id, ward name)."""
    idmap = get_id_map()
    chw_id = None
    for part in encounter.get("participant") or []:
        chw_id = idmap.openmrs_to_chw.get(ref_id(part.get("individual")))
        if chw_id:
            break
    ward = None
    for loc in encounter.get("location") or []:
        ward = idmap.openmrs_to_ward.get(ref_id(loc.get("location")))
        if ward:
            break
    return {
        "chw_id": chw_id,
        "ward": ward,
        "date": ((encounter.get("period") or {}).get("start") or "")[:10],
    }


async def observations(
    client: FhirClient, code: str, days: int, **params: Any
) -> list[dict[str, Any]]:
    """Observations of one concept in the window, for program patients only."""
    found = await client.search(
        "Observation",
        params={"code": code, "date": f"ge{since_date(days)}", "_count": 100, **params},
        max_pages=5,
    )
    return [o for o in found if is_program_patient(ref_id(o.get("subject")))]
