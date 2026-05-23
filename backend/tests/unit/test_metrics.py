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


def test_request_latency_records_observation() -> None:
    with TestClient(app) as client:
        # 404 is fast and avoids touching FHIR / LLM at all.
        client.get("/this-path-does-not-exist")
        body = client.get("/metrics").text

    assert "http_request_duration_seconds_count" in body
    # Unmatched paths bucket under a single label, not the raw URL.
    assert 'path="unmatched"' in body
    assert 'method="GET"' in body
    assert 'status="404"' in body


def test_metrics_path_is_excluded_from_histogram() -> None:
    with TestClient(app) as client:
        # Hit /metrics a few times to confirm the middleware skips it.
        client.get("/metrics")
        client.get("/metrics")
        body = client.get("/metrics").text

    # The /metrics path itself must never appear as a histogram label —
    # otherwise every scrape would inflate the time series.
    assert 'path="/metrics"' not in body
