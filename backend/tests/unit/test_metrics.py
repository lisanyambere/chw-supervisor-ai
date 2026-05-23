"""Smoke test for the /metrics Prometheus endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


def test_metrics_endpoint_returns_prometheus_text() -> None:
    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    # prometheus_client auto-registers these collectors on every platform.
    # (process_* metrics are Linux-only and intentionally not asserted.)
    assert "python_info" in body
    assert "python_gc_objects_collected_total" in body


def test_metrics_endpoint_is_hidden_from_openapi() -> None:
    # The endpoint exists for scrapers, not for the public API surface.
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema["paths"]
