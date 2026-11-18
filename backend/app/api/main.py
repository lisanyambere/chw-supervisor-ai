"""FastAPI app entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from app.agents import BriefingResult, StreamEvent, format_answer, run_briefing
from app.api.schemas import (
    AgentRunOut,
    AnomaliesResponse,
    AnswerDocOut,
    BriefingRequest,
    BriefingResponse,
    ChwDetailResponse,
    DailyActivityResponse,
    DailyCount,
    LivenessResponse,
    PlanStepOut,
    ReadinessResponse,
    RosterResponse,
    RosterRow,
    TraceEntry,
)
from app.core import configure_logging, get_logger, get_settings
from app.fhir import FhirClient, get_id_map
from app.llm import get_llm, metered
from app.observability import aflush as langfuse_flush
from app.observability import get_langfuse, langfuse_project_url, metrics_router
from app.observability.metrics import REQUEST_LATENCY
from app.tools._shared import gather_bounded
from app.tools.chw import (
    chw_activity_gaps,
    chw_patient_panel,
    count_chw_encounters,
    visits_by_day,
)
from app.tools.clinical import (
    child_danger_signs,
    fever_cases_by_ward,
    overdue_followups,
)
from app.tools.quality import visits_after_death, visits_missing_location

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level)
    # Build a single shared FHIR client for the app lifetime.
    app.state.fhir = FhirClient()
    # Eagerly warm caches so config errors fail fast at startup.
    get_id_map()
    try:
        get_llm()
    except RuntimeError as e:
        log.warning("llm.unconfigured", error=str(e))
    get_langfuse()  # initialize tracing if keys present
    log.info("api.startup")
    try:
        yield
    finally:
        await app.state.fhir.aclose()
        await langfuse_flush()
        log.info("api.shutdown")


app = FastAPI(
    title="Community Health AI Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Next.js frontend to call us from the browser without bouncing
# through a proxy. Defaults to the dev server; override with CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Prometheus scrape endpoint.
app.include_router(metrics_router)


@app.middleware("http")
async def record_request_latency(
    request: Request, call_next: object
) -> Response:
    # Don't record the scrape endpoint itself — would create a self-reference
    # loop in the time series every time Prometheus polls.
    if request.url.path == "/metrics":
        return await call_next(request)  # type: ignore[operator]

    start = time.perf_counter()
    response: Response = await call_next(request)  # type: ignore[operator]
    elapsed = time.perf_counter() - start

    # Use the matched route's path template, not the raw URL. Unmatched
    # paths (404s) bucket under a single label to keep cardinality bounded.
    route = request.scope.get("route")
    template = (
        route.path if route is not None and hasattr(route, "path") else "unmatched"
    )

    REQUEST_LATENCY.labels(
        method=request.method,
        path=template,
        status=str(response.status_code),
    ).observe(elapsed)
    return response


def get_fhir() -> FhirClient:
    return app.state.fhir


@app.get("/healthz", response_model=LivenessResponse)
async def healthz() -> LivenessResponse:
    # Liveness probe: just confirms the process is up and able to respond.
    # No downstream calls — those belong on /readyz.
    return LivenessResponse(status="ok")


@app.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readyz(fhir: FhirClient = Depends(get_fhir)) -> Response:
    s = get_settings()
    idmap = get_id_map()

    openmrs_ok = True
    try:
        await fhir.count("Patient", params={"_count": "0"})
    except Exception as e:  # noqa: BLE001
        log.warning("readyz.openmrs_unreachable", error=str(e))
        openmrs_ok = False

    llm_ok = True
    try:
        llm = get_llm()
        provider, model = llm.provider, llm.model
    except RuntimeError:
        llm_ok = False
        provider, model = s.llm_provider, "(unconfigured)"

    ready = openmrs_ok and llm_ok
    body = ReadinessResponse(
        status="ready" if ready else "not_ready",
        openmrs=openmrs_ok,
        llm_provider=provider,
        llm_model=model,
        patients_loaded=len(idmap.patients),
        chws_loaded=len(idmap.practitioners),
        langfuse_url=langfuse_project_url(),
    )
    return JSONResponse(
        content=body.model_dump(),
        status_code=200 if ready else 503,
    )


@app.post("/briefing", response_model=BriefingResponse)
async def briefing(
    req: BriefingRequest,
    fhir: FhirClient = Depends(get_fhir),
) -> BriefingResponse:
    with metered() as usage:
        try:
            result = await run_briefing(
                req.question,
                fhir=fhir,
                max_iterations=req.max_iterations,
                lookback_days=req.lookback_days,
            )
        except RuntimeError as e:
            # Most likely missing LLM credentials.
            raise HTTPException(status_code=503, detail=str(e)) from e
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"upstream: {e}") from e

        answer_doc: AnswerDocOut | None = None
        if req.include_answer_doc:
            try:
                doc = await format_answer(result, req.question)
                answer_doc = AnswerDocOut(**doc.to_dict())
            except Exception as e:  # noqa: BLE001
                # Formatter is best-effort — never fail the whole request
                # because the second pass tripped. The caller still has
                # `answer` (markdown) and `plan` to render with.
                log.warning("formatter.failed", error=str(e))

    trace = (
        [TraceEntry(**vars(t)) for t in result.trace]
        if req.include_trace
        else []
    )
    return BriefingResponse(
        answer=result.answer,
        iterations=result.iterations,
        tool_calls=result.tool_calls,
        trace=trace,
        plan=[PlanStepOut(**vars(s)) for s in result.plan],
        trace_id=result.trace_id,
        trace_url=result.trace_url,
        answer_doc=answer_doc,
        usage=usage.to_dict(),
        **_team_detail(result),
    )


def _team_detail(result: BriefingResult) -> dict[str, Any]:
    """The multi-agent part of a result, shared by /briefing and the stream."""
    return {
        "route": result.route,
        "route_reason": result.route_reason,
        "agents": [
            AgentRunOut(
                name=a.name, findings=a.findings, tool_calls=a.tool_calls, ms=a.ms
            ).model_dump()
            for a in result.agents
        ],
        "verification": result.verification,
    }


def _practitioner_name(practitioner: dict[str, Any]) -> str | None:
    for name in practitioner.get("name") or []:
        if name.get("text"):
            return str(name["text"])
        parts = [*(name.get("given") or []), name.get("family")]
        joined = " ".join(p for p in parts if p)
        if joined:
            return joined
    return None


# A fever "cluster" for the anomalies view: this many cases in one ward.
FEVER_CLUSTER_MIN_CASES = 3


@app.get("/chws", response_model=RosterResponse)
async def roster(fhir: FhirClient = Depends(get_fhir)) -> RosterResponse:
    idmap = get_id_map()

    async def _row(chw_id: str, uuid: str) -> RosterRow:
        practitioner, month, week = await asyncio.gather(
            fhir.read("Practitioner", uuid),
            count_chw_encounters(fhir, chw_id, days=30),
            visits_by_day(fhir, days=7, chw_id=chw_id),
        )
        return RosterRow(
            chw_id=chw_id,
            name=_practitioner_name(practitioner),
            ward=idmap.chw_wards.get(chw_id),
            encounters_30d=month["encounter_count"],
            encounters_7d=week["stats"]["total"],
        )

    try:
        rows, gaps = await asyncio.gather(
            gather_bounded(
                _row(chw_id, uuid)
                for chw_id, uuid in sorted(idmap.practitioners.items())
            ),
            chw_activity_gaps(fhir, days=14),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}") from e

    by_id = {g["chw_id"]: g for g in gaps["rows"]}
    for row in rows:
        if gap := by_id.get(row.chw_id):
            row.pattern = gap["pattern"]
            row.last_active = gap["last_active"]
    return RosterResponse(chws=rows)


@app.get("/anomalies", response_model=AnomaliesResponse)
async def anomalies(
    days: int = Query(14, ge=7, le=90),
    fhir: FhirClient = Depends(get_fhir),
) -> AnomaliesResponse:
    try:
        fevers, children, overdue, gaps, unlocated, after_death = await asyncio.gather(
            fever_cases_by_ward(fhir, days=days),
            child_danger_signs(fhir, days=days),
            overdue_followups(fhir, days=max(days, 60)),
            chw_activity_gaps(fhir, days=days),
            visits_missing_location(fhir, days=days),
            visits_after_death(fhir, days=days),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}") from e

    # A ward name, not "(no location recorded)": an outbreak needs a place.
    wards = get_id_map().wards
    clusters = [
        w
        for w in fevers["rows"]
        if w["case_count"] >= FEVER_CLUSTER_MIN_CASES and w["ward"] in wards
    ]
    return AnomaliesResponse(
        days=days,
        action_count=(
            len(clusters)
            + len(children["children"])
            + len(overdue["patients"])
            + len(gaps["rows"])
        ),
        fever_clusters=clusters,
        children=children["children"],
        overdue=overdue["patients"],
        activity_gaps=gaps,
        missing_location=unlocated,
        visits_after_death=after_death,
    )


@app.get("/activity/daily", response_model=DailyActivityResponse)
async def daily_activity(
    days: int = Query(30, ge=7, le=90),
    fhir: FhirClient = Depends(get_fhir),
) -> DailyActivityResponse:
    try:
        daily = await visits_by_day(fhir, days=days)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}") from e
    return DailyActivityResponse(
        days=days,
        series=[DailyCount(**d) for d in daily["series"]],
        total=daily["stats"]["total"],
    )


@app.get("/chws/{chw_id}", response_model=ChwDetailResponse)
async def chw_detail(
    chw_id: str,
    fhir: FhirClient = Depends(get_fhir),
) -> ChwDetailResponse:
    idmap = get_id_map()
    practitioner_uuid = idmap.practitioners.get(chw_id)
    if practitioner_uuid is None:
        raise HTTPException(status_code=404, detail=f"unknown chw_id: {chw_id}")

    try:
        practitioner, month, daily, panel = await asyncio.gather(
            fhir.read("Practitioner", practitioner_uuid),
            count_chw_encounters(fhir, chw_id, days=30),
            visits_by_day(fhir, days=7, chw_id=chw_id),
            chw_patient_panel(fhir, chw_id, days=30, limit=200),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}") from e

    return ChwDetailResponse(
        chw_id=chw_id,
        practitioner_uuid=practitioner_uuid,
        name=_practitioner_name(practitioner),
        ward=idmap.chw_wards.get(chw_id),
        encounters_30d=month["encounter_count"],
        # Summed from the daily series so the figure always matches the chart.
        encounters_7d=daily["stats"]["total"],
        patients_30d=panel["patient_count"],
        daily=[DailyCount(**d) for d in daily["series"]],
    )


# Sentinel emitted by the run-agent task to signal stream completion to
# the SSE generator. Not part of the public event schema.
_STREAM_DONE = "__done__"


@app.get("/briefing/stream")
async def briefing_stream(
    question: str = Query(..., min_length=1, max_length=2000),
    max_iterations: int = Query(6, ge=1, le=12),
    lookback_days: int | None = Query(None, ge=1, le=365),
    fhir: FhirClient = Depends(get_fhir),
) -> StreamingResponse:
    """Server-Sent Events stream of the briefing agent's progress.

    Emits events as tools start and finish, plus one final `response`
    event with the full answer. EventSource-friendly (GET, no body).
    """
    queue: asyncio.Queue[dict | str] = asyncio.Queue()

    async def on_event(event: StreamEvent) -> None:
        # Suppress the inner `response` frame — we emit an enriched one
        # below that also carries `trace_id` and a formatted `answer_doc`.
        if event.kind == "response":
            return
        await queue.put(event.to_dict())

    async def run_agent() -> None:
        try:
            with metered() as usage:
                result = await run_briefing(
                    question=question,
                    fhir=fhir,
                    max_iterations=max_iterations,
                    lookback_days=lookback_days,
                    on_event=on_event,
                )
                answer_doc_dict: dict[str, Any] | None = None
                try:
                    doc = await format_answer(result, question)
                    answer_doc_dict = doc.to_dict()
                except Exception as e:  # noqa: BLE001
                    # Same best-effort posture as POST /briefing — keep
                    # streaming even if the second-pass formatter trips.
                    log.warning("formatter.failed", error=str(e))
            await queue.put(
                {
                    "kind": "response",
                    "answer": result.answer,
                    "iterations": result.iterations,
                    "tool_calls": result.tool_calls,
                    "plan": [vars(p) for p in result.plan],
                    "trace_id": result.trace_id,
                    "trace_url": result.trace_url,
                    "answer_doc": answer_doc_dict,
                    "usage": usage.to_dict(),
                    **_team_detail(result),
                }
            )
        except Exception as e:  # noqa: BLE001
            await queue.put(
                {"kind": "error", "message": f"{type(e).__name__}: {e}"}
            )
        finally:
            await queue.put(_STREAM_DONE)

    async def event_generator() -> AsyncIterator[str]:
        task = asyncio.create_task(run_agent())
        try:
            while True:
                evt = await queue.get()
                if evt == _STREAM_DONE:
                    break
                assert isinstance(evt, dict)
                yield f"event: {evt['kind']}\ndata: {json.dumps(evt)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
