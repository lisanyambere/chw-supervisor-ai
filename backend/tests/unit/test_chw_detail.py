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
        assert params["participant"] == "uuid-chw-1"
        return 3 if isinstance(params["date"], list) else 12

    async def read(self, _rtype: str, rid: str) -> dict:
        assert rid == "uuid-chw-1"
        return {
            "name": [{"given": ["Mary"], "family": "Wanjiku"}],
            "extension": [
                {
                    "url": "http://community-health-ai/chw-ward",
                    "valueString": "Lurambi",
                }
            ],
        }

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
    fake = IdMap(patients={}, practitioners={"chw-001": "uuid-chw-1"})
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


def test_chw_detail_unknown_id_is_404(client: TestClient) -> None:
    resp = client.get("/chws/chw-999")

    assert resp.status_code == 404
