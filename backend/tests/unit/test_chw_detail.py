"""GET /chws/{chw_id} endpoint tests (fake FHIR, no network)."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main
from app.api.main import app, get_fhir
from app.fhir.id_map import IdMap
from app.tools import chw as chw_tools


class _FakeFhir:
    """Counts 3 encounters for any single-day query and 12 for a window."""

    async def count(self, _rtype: str, params: dict[str, Any] | None = None) -> int:
        assert params is not None
        assert params.get("participant", "uuid-chw-1") == "uuid-chw-1"
        return 3 if isinstance(params["date"], list) else 12

    async def read(self, _rtype: str, rid: str) -> dict:
        assert rid == "uuid-chw-1"
        return {"name": [{"given": ["Mary"], "family": "Wanjiku"}]}

    async def search(
        self, _rtype: str, params: dict[str, Any] | None = None, *, max_pages: int = 5
    ) -> list[dict]:
        return [
            {"subject": {"reference": "Patient/p1"}, "period": {"start": "d2"}},
            {"subject": {"reference": "Patient/p1"}, "period": {"start": "d1"}},
            {"subject": {"reference": "Patient/p2"}, "period": {"start": "d1"}},
        ]


@pytest.fixture(autouse=True)
def _patch_id_map(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = IdMap(
        patients={},
        practitioners={"chw-001": "uuid-chw-1"},
        chw_wards={"chw-001": "Lurambi"},
    )
    monkeypatch.setattr(api_main, "get_id_map", lambda: fake)
    monkeypatch.setattr(chw_tools, "get_id_map", lambda: fake)


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[get_fhir] = lambda: _FakeFhir()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_fhir, None)


def test_chw_detail_combines_profile_and_activity(client: TestClient) -> None:
    resp = client.get("/chws/chw-001")

    assert resp.status_code == 200
    body = resp.json()
    assert body["chw_id"] == "chw-001"
    assert body["practitioner_uuid"] == "uuid-chw-1"
    assert body["name"] == "Mary Wanjiku"
    assert body["ward"] == "Lurambi"
    assert body["encounters_30d"] == 12
    assert body["encounters_7d"] == 21  # sum of the daily series
    assert body["patients_30d"] == 2
    assert [d["encounter_count"] for d in body["daily"]] == [3] * 7
    assert body["daily"] == sorted(body["daily"], key=lambda d: d["date"])


def test_daily_activity_returns_one_point_per_day(client: TestClient) -> None:
    resp = client.get("/activity/daily", params={"days": 14})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["series"]) == 14
    assert body["total"] == 3 * 14
    assert body["series"] == sorted(body["series"], key=lambda d: d["date"])


def test_chw_detail_unknown_id_is_404(client: TestClient) -> None:
    resp = client.get("/chws/chw-999")

    assert resp.status_code == 404


def test_roster_lists_every_chw_with_profile_and_counts(client: TestClient) -> None:
    resp = client.get("/chws")

    assert resp.status_code == 200
    [row] = resp.json()["chws"]
    assert row["chw_id"] == "chw-001"
    assert row["name"] == "Mary Wanjiku"
    assert row["ward"] == "Lurambi"
    assert row["encounters_30d"] == 12
    assert row["encounters_7d"] == 21


def test_anomalies_counts_what_needs_action_today(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def returns(value: dict[str, Any]) -> Any:
        async def tool(_fhir: Any, **_kwargs: Any) -> dict[str, Any]:
            return value

        return tool

    fevers = {
        "rows": [
            {"ward": "Lurambi", "case_count": 8},
            {"ward": "Lurambi-adjacent", "case_count": 5},  # not a known ward
            {"ward": "(no location recorded)", "case_count": 4},
            {"ward": "Butere", "case_count": 1},  # too few for a cluster
        ]
    }
    monkeypatch.setattr(
        api_main.get_id_map(), "wards", {"Lurambi": "loc-1", "Butere": "loc-2"}
    )
    monkeypatch.setattr(api_main, "fever_cases_by_ward", returns(fevers))
    monkeypatch.setattr(api_main, "child_danger_signs", returns({"children": [{}]}))
    monkeypatch.setattr(api_main, "overdue_followups", returns({"patients": [{}, {}]}))
    monkeypatch.setattr(api_main, "chw_activity_gaps", returns({"rows": [{}]}))
    monkeypatch.setattr(api_main, "visits_missing_location", returns({"rows": []}))
    monkeypatch.setattr(api_main, "visits_after_death", returns({"rows": [{}]}))

    body = client.get("/anomalies").json()

    assert [w["ward"] for w in body["fever_clusters"]] == ["Lurambi"]
    # 1 cluster + 1 child + 2 overdue + 1 CHW; data-quality records excluded.
    assert body["action_count"] == 5
