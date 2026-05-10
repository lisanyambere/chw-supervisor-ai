"""Tool unit tests using a fake FHIR client (no network)."""
from __future__ import annotations

from typing import Any

import pytest

from app.fhir.id_map import IdMap
from app.tools import chw as chw_tools
from app.tools import patient as patient_tools


class FakeFhir:
    def __init__(
        self,
        counts: dict[tuple[str, frozenset], int] | None = None,
        reads: dict[tuple[str, str], dict] | None = None,
        searches: dict[tuple[str, frozenset], list[dict]] | None = None,
    ) -> None:
        self.counts = counts or {}
        self.reads = reads or {}
        self.searches = searches or {}
        self.calls: list[tuple[str, str, dict]] = []

    async def count(self, rtype: str, params: dict[str, Any] | None = None) -> int:
        key = (rtype, frozenset((params or {}).items()))
        self.calls.append(("count", rtype, params or {}))
        return self.counts.get(key, 0)

    async def read(self, rtype: str, rid: str) -> dict:
        self.calls.append(("read", rtype, {"id": rid}))
        return self.reads.get((rtype, rid), {})

    async def search(
        self, rtype: str, params: dict[str, Any] | None = None, *, max_pages: int = 5
    ) -> list[dict]:
        key = (rtype, frozenset((params or {}).items()))
        self.calls.append(("search", rtype, params or {}))
        return self.searches.get(key, [])


@pytest.fixture(autouse=True)
def _patch_id_map(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = IdMap(
        patients={"syn-001": "uuid-pat-1"},
        practitioners={"chw-001": "uuid-chw-1", "chw-002": "uuid-chw-2"},
    )
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake)
    monkeypatch.setattr(patient_tools, "_format_codeable", patient_tools._format_codeable)


async def test_list_chws_returns_sorted() -> None:
    fhir = FakeFhir()
    out = await chw_tools.list_chws(fhir)  # type: ignore[arg-type]
    assert out == [
        {"chw_id": "chw-001", "practitioner_uuid": "uuid-chw-1"},
        {"chw_id": "chw-002", "practitioner_uuid": "uuid-chw-2"},
    ]


async def test_count_chw_encounters_resolves_local_id() -> None:
    fhir = FakeFhir()
    # Make the fake return 5 regardless of the date param.
    async def fake_count(rtype: str, params: dict | None = None) -> int:
        assert rtype == "Encounter"
        assert params is not None
        assert params["participant"] == "uuid-chw-1"
        return 5

    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.count_chw_encounters(fhir, chw_id="chw-001", days=7)  # type: ignore[arg-type]
    assert out["encounter_count"] == 5
    assert out["practitioner_uuid"] == "uuid-chw-1"


async def test_count_chw_encounters_unknown_id() -> None:
    fhir = FakeFhir()
    out = await chw_tools.count_chw_encounters(fhir, chw_id="nope")  # type: ignore[arg-type]
    assert "error" in out


async def test_team_activity_summary_aggregates_and_sorts() -> None:
    counts_by_uuid = {"uuid-chw-1": 3, "uuid-chw-2": 9}

    async def fake_count(rtype: str, params: dict | None = None) -> int:
        return counts_by_uuid[params["participant"]]  # type: ignore[index]

    fhir = FakeFhir()
    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.team_activity_summary(fhir, days=7)  # type: ignore[arg-type]
    assert [r["chw_id"] for r in out["rows"]] == ["chw-001", "chw-002"]
    assert out["stats"] == {"min": 3, "max": 9, "mean": 6.0, "total": 12}
