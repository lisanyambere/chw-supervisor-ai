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
        self,
        rtype: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = 5,
        stop_after_page: Any = None,
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
    # The activity series memoizes by (days, chw_id) at module scope; clear it
    # so each test sees its own fake data rather than a prior test's cache.
    chw_tools.clear_activity_cache()


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


# ─── chw_inactivity ─────────────────────────────────────────────────────────


async def test_chw_inactivity_filters_by_threshold() -> None:
    counts_by_uuid = {"uuid-chw-1": 0, "uuid-chw-2": 5}

    async def fake_count(rtype: str, params: dict | None = None) -> int:
        return counts_by_uuid[params["participant"]]  # type: ignore[index]

    fhir = FakeFhir()
    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.chw_inactivity(fhir, days=7, max_count=0)  # type: ignore[arg-type]
    assert out["inactive_count"] == 1
    assert out["team_size"] == 2
    assert out["inactive_chws"] == [{"chw_id": "chw-001", "encounter_count": 0}]


async def test_chw_inactivity_max_count_inclusive() -> None:
    counts_by_uuid = {"uuid-chw-1": 0, "uuid-chw-2": 5}

    async def fake_count(rtype: str, params: dict | None = None) -> int:
        return counts_by_uuid[params["participant"]]  # type: ignore[index]

    fhir = FakeFhir()
    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.chw_inactivity(fhir, days=7, max_count=5)  # type: ignore[arg-type]
    assert out["inactive_count"] == 2  # both included


# ─── visits_by_day ──────────────────────────────────────────────────────────


async def test_visits_by_day_returns_one_row_per_day() -> None:
    fhir = FakeFhir()

    async def fake_count(rtype: str, params: dict | None = None) -> int:
        # Each day's bucket gets a 2-element date list (gtX, ltY).
        assert rtype == "Encounter"
        assert isinstance(params, dict)
        assert isinstance(params["date"], list) and len(params["date"]) == 2
        return 3

    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.visits_by_day(fhir, days=5)  # type: ignore[arg-type]
    assert len(out["series"]) == 5
    assert out["stats"]["total"] == 15
    # Series should be chronologically ordered (oldest → newest).
    dates = [row["date"] for row in out["series"]]
    assert dates == sorted(dates)


async def test_visits_by_day_scopes_to_chw_when_given() -> None:
    seen_params: list[dict] = []

    async def fake_count(rtype: str, params: dict | None = None) -> int:
        seen_params.append(params or {})
        return 1

    fhir = FakeFhir()
    fhir.count = fake_count  # type: ignore[assignment]

    out = await chw_tools.visits_by_day(fhir, days=2, chw_id="chw-001")  # type: ignore[arg-type]
    assert out["chw_id"] == "chw-001"
    assert all(p.get("participant") == "uuid-chw-1" for p in seen_params)


async def test_visits_by_day_unknown_chw() -> None:
    out = await chw_tools.visits_by_day(FakeFhir(), days=1, chw_id="nope")  # type: ignore[arg-type]
    assert "error" in out


# ─── chw_patient_panel ──────────────────────────────────────────────────────


async def test_chw_patient_panel_dedupes_subjects() -> None:
    encounters = [
        {"subject": {"reference": "Patient/p1"}, "period": {"start": "2026-05-09T10:00:00Z"}},
        {"subject": {"reference": "Patient/p1"}, "period": {"start": "2026-05-08T10:00:00Z"}},
        {"subject": {"reference": "Patient/p2"}, "period": {"start": "2026-05-07T10:00:00Z"}},
        {"subject": {"reference": "Group/x"}},  # ignored — not a Patient ref
    ]

    async def fake_search(rtype: str, params=None, *, max_pages=5):  # type: ignore[no-untyped-def]
        assert rtype == "Encounter"
        return encounters

    fhir = FakeFhir()
    fhir.search = fake_search  # type: ignore[assignment]

    out = await chw_tools.chw_patient_panel(fhir, chw_id="chw-001", days=30, limit=10)  # type: ignore[arg-type]
    assert out["patient_count"] == 2
    by_uuid = {p["patient_uuid"]: p for p in out["patients"]}
    assert by_uuid["p1"]["encounter_count"] == 2
    assert by_uuid["p1"]["last_encounter_date"] == "2026-05-09T10:00:00Z"


async def test_chw_patient_panel_respects_limit() -> None:
    encounters = [
        {"subject": {"reference": f"Patient/p{i}"}, "period": {"start": "2026-05-09T00:00:00Z"}}
        for i in range(50)
    ]

    async def fake_search(rtype: str, params=None, *, max_pages=5):  # type: ignore[no-untyped-def]
        return encounters

    fhir = FakeFhir()
    fhir.search = fake_search  # type: ignore[assignment]

    out = await chw_tools.chw_patient_panel(fhir, chw_id="chw-001", days=30, limit=5)  # type: ignore[arg-type]
    assert out["patient_count"] == 5


async def test_chw_patient_panel_unknown_chw() -> None:
    out = await chw_tools.chw_patient_panel(FakeFhir(), chw_id="nope")  # type: ignore[arg-type]
    assert "error" in out


# ─── activity_series (UI charts) ──────────────────────────────────────


async def test_activity_series_buckets_by_start_date() -> None:
    # chw-001 worked two of the three days; chw-002 worked one. The middle day
    # has zero encounters team-wide and must surface as a zero-day.
    today = chw_tools.datetime.now(tz=chw_tools.UTC).date()
    d0 = (today - chw_tools.timedelta(days=2)).isoformat()  # oldest
    d2 = today.isoformat()  # newest

    per_participant = {
        "uuid-chw-1": [
            {"period": {"start": f"{d0}T08:00:00Z"}},
            {"period": {"start": f"{d0}T11:00:00Z"}},
            {"period": {"start": f"{d2}T09:00:00Z"}},
        ],
        "uuid-chw-2": [
            {"period": {"start": f"{d2}T10:00:00Z"}},
        ],
    }

    async def fake_search(rtype, params=None, *, max_pages=8, stop_after_page=None):  # type: ignore[no-untyped-def]
        assert rtype == "Encounter"
        assert params["_sort"] == "-date"
        return per_participant.get(params["participant"], [])

    fhir = FakeFhir()
    fhir.search = fake_search  # type: ignore[assignment]

    out = await chw_tools.activity_series(fhir, days=3)  # type: ignore[arg-type]
    assert [s["encounter_count"] for s in out["series"]] == [2, 0, 2]
    assert out["series"][1]["is_zero"] is True
    assert out["stats"]["total"] == 4
    assert out["stats"]["zero_days"] == 1
    assert out["stats"]["active_days"] == 2
    # Each day carries a weekday label and weekend flag.
    assert all(s["weekday"] for s in out["series"])


async def test_activity_series_unknown_chw() -> None:
    out = await chw_tools.activity_series(FakeFhir(), days=7, chw_id="nope")  # type: ignore[arg-type]
    assert "error" in out


async def test_activity_series_memoizes_result() -> None:
    calls = {"n": 0}

    async def fake_search(rtype, params=None, *, max_pages=8, stop_after_page=None):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return []

    fhir = FakeFhir()
    fhir.search = fake_search  # type: ignore[assignment]

    first = await chw_tools.activity_series(fhir, days=5, chw_id="chw-001")  # type: ignore[arg-type]
    after_first = calls["n"]
    assert after_first > 0
    second = await chw_tools.activity_series(fhir, days=5, chw_id="chw-001")  # type: ignore[arg-type]
    # The second call is served from cache — no further FHIR searches.
    assert calls["n"] == after_first
    assert second is first

