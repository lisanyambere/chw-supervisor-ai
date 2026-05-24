"""Liveness and readiness endpoint tests."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.main import app, get_fhir


class _FakeFhirOk:
    async def count(self, _resource: str, params: dict[str, Any] | None = None) -> int:
        return 1


class _FakeFhirDown:
    async def count(self, _resource: str, params: dict[str, Any] | None = None) -> int:
        raise RuntimeError("openmrs is down")


def test_healthz_is_dependency_free() -> None:
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_returns_503_when_openmrs_unreachable() -> None:
    app.dependency_overrides[get_fhir] = lambda: _FakeFhirDown()
    try:
        with TestClient(app) as client:
            resp = client.get("/readyz")
    finally:
        app.dependency_overrides.pop(get_fhir, None)

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["openmrs"] is False


def test_readyz_returns_200_when_all_deps_ok() -> None:
    app.dependency_overrides[get_fhir] = lambda: _FakeFhirOk()
    try:
        with TestClient(app) as client:
            resp = client.get("/readyz")
    finally:
        app.dependency_overrides.pop(get_fhir, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["openmrs"] is True
