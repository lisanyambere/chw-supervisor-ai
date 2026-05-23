"""Prometheus /metrics endpoint.

prometheus_client auto-registers process, GC, and platform collectors on
import, so the default registry already carries useful baseline metrics
(memory, CPU, fd count, GC pauses). Service-specific metrics
(request latency, tool calls, LLM calls) land in follow-up commits and
register against this same module-level registry.
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
