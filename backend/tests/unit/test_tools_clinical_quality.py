"""Clinical and data-quality tools, against a fake FHIR server (no network).

The fake answers the searches these tools make by resource type and the
filter that matters (code, encounter, patient), which is enough to exercise
each tool's own logic: thresholds, grouping, and what counts as a problem.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.fhir.id_map import IdMap
from app.tools import _shared, clinical, quality
from app.tools._shared import (
    CURRENTLY_PREGNANT,
    MALARIA,
    RESPIRATORY_RATE,
    RETURN_VISIT_DATE,
    SYSTOLIC_BP,
    TEMPERATURE,
)

TODAY = datetime.now(tz=UTC).date()


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


IDMAP = IdMap(
    # The program's own patients; "demo-*" stand for OpenMRS demo patients.
    patients={f"syn-{i}": f"pat-{i}" for i in range(1, 9)},
    practitioners={"chw-001": "prac-1", "chw-002": "prac-2"},
    wards={"Lurambi": "loc-lurambi", "Butere": "loc-butere"},
    chw_wards={"chw-001": "Lurambi", "chw-002": "Butere"},
)


@pytest.fixture(autouse=True)
def _id_map(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (_shared, quality):
        monkeypatch.setattr(module, "get_id_map", lambda: IDMAP)


def obs(
    patient: str, code: str, encounter: str, when: str, **value: Any
) -> dict[str, Any]:
    return {
        "subject": {"reference": f"Patient/{patient}", "display": f"Name {patient}"},
        "code": {"coding": [{"code": code}]},
        "encounter": {"reference": f"Encounter/{encounter}"},
        "effectiveDateTime": f"{when}T09:00:00+00:00",
        **value,
    }


def encounter(
    when: str, chw: str = "prac-1", location: str | None = "loc-lurambi"
) -> dict[str, Any]:
    return {
        "period": {"start": f"{when}T09:00:00+00:00"},
        "participant": [{"individual": {"reference": f"Practitioner/{chw}"}}],
        "location": [{"location": {"reference": f"Location/{location}"}}]
        if location
        else [],
    }


class FakeFhir:
    def __init__(
        self,
        observations: list[dict[str, Any]] | None = None,
        encounters: dict[str, dict[str, Any]] | None = None,
        patients: dict[str, dict[str, Any]] | None = None,
        malaria: set[str] | None = None,
        visits_after: dict[str, list[str]] | None = None,
    ) -> None:
        self.observations = observations or []
        self.encounters = encounters or {}
        self.patients = patients or {}
        self.malaria = malaria or set()
        # patient -> visit dates, for "seen since" and "after death" checks
        self.visits_after = visits_after or {}

    async def read(self, rtype: str, rid: str) -> dict[str, Any]:
        return {"Encounter": self.encounters, "Patient": self.patients}[rtype][rid]

    async def search(
        self, rtype: str, params: dict[str, Any] | None = None, *, max_pages: int = 5
    ) -> list[dict[str, Any]]:
        p = params or {}
        if rtype == "Observation":
            found = [
                o
                for o in self.observations
                if o["code"]["coding"][0]["code"] == p["code"]
                and (
                    "encounter" not in p
                    or o["encounter"]["reference"].endswith(p["encounter"])
                )
                and (
                    "patient" not in p
                    or o["subject"]["reference"].endswith(p["patient"])
                )
            ]
            floor = p.get("value-quantity", "ge-1")[2:]
            return [
                o
                for o in found
                if "valueQuantity" not in o
                or o["valueQuantity"]["value"] >= float(floor)
            ]
        if rtype == "Patient":
            return list(self.patients.values())
        if rtype == "Encounter":
            return [encounter(d) for d in self.visits_after.get(p["patient"], [])]
        raise AssertionError(rtype)

    async def count(self, rtype: str, params: dict[str, Any] | None = None) -> int:
        p = params or {}
        if rtype == "Condition":
            return int(p["patient"] in self.malaria and p["code"] == MALARIA)
        if rtype == "Encounter":
            since = p["date"][2:12]
            return sum(d >= since for d in self.visits_after.get(p["patient"], []))
        raise AssertionError(rtype)


async def test_fever_cases_are_grouped_by_ward_with_malaria_counts() -> None:
    fevers = [
        obs("pat-1", TEMPERATURE, "e1", days_ago(3), valueQuantity={"value": 38.9}),
        obs("pat-2", TEMPERATURE, "e2", days_ago(1), valueQuantity={"value": 39.4}),
        obs("pat-3", TEMPERATURE, "e3", days_ago(2), valueQuantity={"value": 38.2}),
        # OpenMRS demo patient: must not reach a briefing.
        obs("demo-1", TEMPERATURE, "e4", days_ago(2), valueQuantity={"value": 40.0}),
    ]
    fhir = FakeFhir(
        observations=fevers,
        encounters={
            "e1": encounter(days_ago(3)),
            "e2": encounter(days_ago(1)),
            "e3": encounter(days_ago(2), chw="prac-2", location="loc-butere"),
        },
        malaria={"pat-1", "pat-2"},
    )

    out = await clinical.fever_cases_by_ward(fhir, days=7)  # type: ignore[arg-type]

    assert out["total_cases"] == 3
    lurambi, butere = out["rows"]
    assert lurambi["ward"] == "Lurambi"
    assert lurambi["case_count"] == 2
    assert lurambi["malaria_diagnosed"] == 2
    assert lurambi["chw_ids"] == ["chw-001"]
    assert (lurambi["first_date"], lurambi["last_date"]) == (days_ago(3), days_ago(1))
    assert butere["case_count"] == 1
    assert butere["malaria_diagnosed"] == 0


async def test_child_danger_signs_apply_imci_age_thresholds() -> None:
    def born(months: int) -> str:
        return (TODAY - timedelta(days=int(months * 30.5))).isoformat()

    rates = {"pat-1": 52.0, "pat-2": 45.0, "pat-3": 45.0, "pat-4": 70.0}
    fhir = FakeFhir(
        observations=[
            *(
                obs(
                    p,
                    RESPIRATORY_RATE,
                    f"e-{p}",
                    days_ago(1),
                    valueQuantity={"value": r},
                )
                for p, r in rates.items()
            ),
            obs(
                "pat-1",
                TEMPERATURE,
                "e-pat-1",
                days_ago(1),
                valueQuantity={"value": 39.0},
            ),
        ],
        encounters={f"e-{p}": encounter(days_ago(1)) for p in rates},
        patients={
            "pat-1": {"id": "pat-1", "birthDate": born(8)},  # infant, 52 >= 50
            "pat-2": {"id": "pat-2", "birthDate": born(8)},  # infant, 45 < 50
            "pat-3": {"id": "pat-3", "birthDate": born(30)},  # toddler, 45 >= 40
            "pat-4": {"id": "pat-4", "birthDate": born(84)},  # seven: out of scope
        },
    )

    out = await clinical.child_danger_signs(fhir, days=7)  # type: ignore[arg-type]

    flagged = {c["patient_uuid"]: c for c in out["children"]}
    assert set(flagged) == {"pat-1", "pat-3"}
    assert flagged["pat-1"]["temperature_c"] == 39.0
    assert flagged["pat-3"]["temperature_c"] is None


async def test_overdue_followups_skip_patients_seen_since_or_not_yet_due() -> None:
    def booked(patient: str, visit: int, due: int) -> dict[str, Any]:
        return obs(
            patient,
            RETURN_VISIT_DATE,
            f"e-{patient}",
            days_ago(visit),
            valueDateTime=f"{days_ago(due)}T00:00:00+00:00",
        )

    fhir = FakeFhir(
        observations=[
            booked("pat-1", 20, 13),  # overdue, never seen again
            booked("pat-2", 20, 13),  # overdue, but seen since
            booked("pat-3", 3, -4),  # return date still ahead
            obs(
                "pat-1", CURRENTLY_PREGNANT, "e-pat-1", days_ago(20), valueBoolean=True
            ),
            obs(
                "pat-1",
                SYSTOLIC_BP,
                "e-pat-1",
                days_ago(20),
                valueQuantity={"value": 145.0},
            ),
        ],
        encounters={f"e-pat-{i}": encounter(days_ago(20)) for i in (1, 2, 3)},
        visits_after={"pat-1": [days_ago(20)], "pat-2": [days_ago(20), days_ago(5)]},
    )

    out = await clinical.overdue_followups(fhir, days=60)  # type: ignore[arg-type]

    # The visit that booked the return date must not count as "seen since".
    assert [p["patient_uuid"] for p in out["patients"]] == ["pat-1"]
    row = out["patients"][0]
    assert row["days_overdue"] == 13
    assert row["pregnant"] is True
    assert row["last_systolic_bp"] == 145.0
    assert row["chw_id"] == "chw-001"


async def test_missing_location_is_counted_per_chw_and_week() -> None:
    # chw-001 makes 5 visits a week, 2 of them located only in the oldest week.
    class CountFhir:
        async def count(self, _rtype: str, params: dict[str, Any]) -> int:
            lo = date.fromisoformat(params["date"][0][2:12])
            oldest = lo == TODAY - timedelta(days=14)
            if params["participant"] == "prac-2":
                return 4
            if "location" not in params:
                return 5
            assert params["location"] == "loc-lurambi"
            return 2 if oldest else 5

    out = await quality.visits_missing_location(CountFhir(), days=14)  # type: ignore[arg-type]

    assert out["total_missing_location"] == 3
    assert [r["chw_id"] for r in out["rows"]] == ["chw-001"]
    assert out["rows"][0]["weeks"] == {days_ago(14): 3}
    assert out["by_week"][0]["missing_location"] == 3
    assert all(w["missing_location"] == 0 for w in out["by_week"][1:])
    # Weeks tile the window without gaps.
    for prev, nxt in zip(out["by_week"], out["by_week"][1:], strict=False):
        assert date.fromisoformat(prev["week_end"]) + timedelta(
            days=1
        ) == date.fromisoformat(nxt["week_start"])


async def test_visits_after_death_only_counts_later_visits_of_program_patients() -> (
    None
):
    def dead(pid: str, died: str) -> dict[str, Any]:
        return {
            "id": pid,
            "deceasedDateTime": f"{died}T00:00:00+00:00",
            "name": [{"given": ["Musungu"], "family": "Juma"}],
        }

    fhir = FakeFhir(
        patients={
            "pat-1": dead("pat-1", "2021-02-21"),
            "demo-1": dead("demo-1", "2020-01-01"),
        },
        visits_after={"pat-1": [days_ago(2)], "demo-1": [days_ago(2)]},
    )

    out = await quality.visits_after_death(fhir, days=7)  # type: ignore[arg-type]

    assert out["deceased_patients_checked"] == 1
    assert out["rows"] == [
        {
            "patient_uuid": "pat-1",
            "patient_name": "Musungu Juma",
            "death_date": "2021-02-21",
            "visit_date": days_ago(2),
            "chw_id": "chw-001",
            "ward": "Lurambi",
        }
    ]
