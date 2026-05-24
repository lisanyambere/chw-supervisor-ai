"""Prometheus /metrics endpoint and service-level metrics.

prometheus_client auto-registers process, GC, and platform collectors on
import, so the default registry already carries useful baseline metrics
(memory, CPU, fd count, GC pauses). Service-level metrics defined here
register against the same default registry; the middleware in
`app.api.main` populates them.
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest

metrics_router = APIRouter()

# Request latency, labelled by method + matched path template + status.
# Path TEMPLATE (e.g. "/briefing"), never the raw URL — avoids cardinality
# blow-up from path params or query strings.
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by method, path template, and status",
    labelnames=("method", "path", "status"),
)

# Tool call latency, labelled by registered tool name and outcome.
# Cardinality is bounded by the size of the tool registry (~10) × 2 outcomes.
TOOL_CALL_DURATION = Histogram(
    "tool_call_duration_seconds",
    "Agent tool call latency by tool name and outcome",
    labelnames=("tool", "outcome"),
)


@metrics_router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
