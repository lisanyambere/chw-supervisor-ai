"""Unit tests for patient-side tools (find_patient, recent_deaths, get_patient_summary)."""
from __future__ import annotations

from typing import Any

import pytest

from app.tools import patient as patient_tools


class FakeFhir:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.search_results: list[dict] = []
        self.read_result: dict = {}

    async def search(
        self, rtype: str, params: dict[str, Any] | None = None, *, max_pages: int = 5
    ) -> list[dict]:
        self.calls.append(("search", rtype, params or {}))
        return self.search_results

    async def read(self, rtype: str, rid: str) -> dict:
        self.calls.append(("read", rtype, {"id": rid}))
        return self.read_result

    async def count(self, rtype: str, params: dict[str, Any] | None = None) -> int:
        self.calls.append(("count", rtype, params or {}))
        return 0


def _patient(uuid: str, given: str, family: str, **extra: Any) -> dict:
    return {
        "id": uuid,
        "name": [{"given": [given], "family": family}],
        "gender": "female",
        "birthDate": "1990-01-01",
        "address": [{"city": "Lurambi", "district": "Kakamega", "country": "KE"}],
        **extra,
    }


# ─── find_patient ───────────────────────────────────────────────────────────


async def test_find_patient_returns_summaries() -> None:
    fhir = FakeFhir()
    fhir.search_results = [
        _patient("u1", "Mary", "Wanjiku"),
        _patient("u2", "Mary", "Achieng"),
    ]

    out = await patient_tools.find_patient(fhir, query="Mary", limit=5)  # type: ignore[arg-type]
    assert out["match_count"] == 2
    assert {p["name"] for p in out["patients"]} == {"Mary Wanjiku", "Mary Achieng"}
    # Search must hit the FHIR `name` param.
    assert fhir.calls[0][2].get("name") == "Mary"


async def test_find_patient_truncates_to_limit() -> None:
    fhir = FakeFhir()
    fhir.search_results = [_patient(f"u{i}", "X", str(i)) for i in range(20)]
    out = await patient_tools.find_patient(fhir, query="X", limit=3)  # type: ignore[arg-type]
    assert out["match_count"] == 3
    assert len(out["patients"]) == 3


async def test_find_patient_rejects_empty_query() -> None:
    out = await patient_tools.find_patient(FakeFhir(), query="   ")  # type: ignore[arg-type]
    assert "error" in out


# ─── recent_deaths ──────────────────────────────────────────────────────────


async def test_recent_deaths_passes_death_date_param() -> None:
    fhir = FakeFhir()
    fhir.search_results = [
        _patient("u1", "Joseph", "Otieno", deceasedDateTime="2026-05-01T00:00:00Z"),
    ]

    out = await patient_tools.recent_deaths(fhir, days=30, limit=10)  # type: ignore[arg-type]
    assert out["death_count"] == 1
    assert out["patients"][0]["deceased"] == "2026-05-01T00:00:00Z"
    # Must use FHIR death-date search param.
    params = fhir.calls[0][2]
    assert "death-date" in params
    assert params["death-date"].startswith("ge")


async def test_recent_deaths_handles_no_results() -> None:
    out = await patient_tools.recent_deaths(FakeFhir(), days=7)  # type: ignore[arg-type]
    assert out["death_count"] == 0
    assert out["patients"] == []


# ─── get_patient_summary (existing tool, no test before) ────────────────────


async def test_get_patient_summary_combines_patient_and_encounters() -> None:
    fhir = FakeFhir()
    fhir.read_result = _patient("u1", "Mary", "Wanjiku")
    fhir.search_results = [
        {
            "id": "e1",
            "type": [{"coding": [{"display": "Visit Note"}]}],
            "period": {"start": "2026-05-09T10:00:00Z", "end": None},
        }
    ]

    out = await patient_tools.get_patient_summary(fhir, patient_uuid="u1", encounter_limit=5)  # type: ignore[arg-type]
    assert out["uuid"] == "u1"
    assert out["name"] == "Mary Wanjiku"
    assert len(out["encounters"]) == 1
    assert out["encounters"][0]["type"] == "Visit Note"
