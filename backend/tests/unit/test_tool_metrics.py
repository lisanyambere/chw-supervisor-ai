"""Tool-call metrics recorded by app.tools.registry.execute()."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.main import app
from app.tools.registry import execute, tool


# Tools register themselves at import time. Two probes — one that
# succeeds, one that raises — so we can assert both outcome labels.


@tool(name="metric_probe_ok", description="probe", parameters={})
async def _probe_ok(client: Any) -> dict:  # noqa: ANN401 — fake client
    return {"ok": True}


@tool(name="metric_probe_error", description="probe", parameters={})
async def _probe_error(client: Any) -> dict:  # noqa: ANN401
    raise RuntimeError("boom")


async def test_ok_outcome_recorded() -> None:
    result = await execute("metric_probe_ok", {}, client=None)  # type: ignore[arg-type]
    assert result == {"ok": True}

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert "tool_call_duration_seconds_count" in body
    assert 'tool="metric_probe_ok"' in body
    assert 'outcome="ok"' in body


async def test_error_outcome_recorded() -> None:
    result = await execute("metric_probe_error", {}, client=None)  # type: ignore[arg-type]
    assert "error" in result

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert 'tool="metric_probe_error"' in body
    assert 'outcome="error"' in body


async def test_unknown_tool_not_recorded() -> None:
    result = await execute("does_not_exist", {}, client=None)  # type: ignore[arg-type]
    assert "error" in result

    with TestClient(app) as http:
        body = http.get("/metrics").text

    # Unknown tools never invoke any registered fn, so they don't get
    # timed — otherwise we'd be inventing cardinality from caller typos.
    assert 'tool="does_not_exist"' not in body
