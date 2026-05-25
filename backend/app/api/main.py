"""FastAPI app entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from app.agents import StreamEvent, format_answer, run_briefing
from app.api.schemas import (
    AnswerDocOut,
    BriefingRequest,
    BriefingResponse,
    LivenessResponse,
    PlanStepOut,
    ReadinessResponse,
    TraceEntry,
)
from app.core import configure_logging, get_logger, get_settings
from app.fhir import FhirClient, get_id_map
from app.llm import get_llm
from app.observability import aflush as langfuse_flush
from app.observability import get_langfuse, metrics_router
from app.observability.metrics import REQUEST_LATENCY

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

# Allow the Next.js dev server (and a future docker frontend) to call us
# from the browser without bouncing through a proxy. The list is small and
# explicit; production should override via an env var if needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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

    trace = (
        [TraceEntry(**vars(t)) for t in result.trace]
        if req.include_trace
        else []
    )

    answer_doc: AnswerDocOut | None = None
    if req.include_answer_doc:
        try:
            doc = await format_answer(result, req.question)
            answer_doc = AnswerDocOut(**doc.to_dict())
        except Exception as e:  # noqa: BLE001
            # Formatter is best-effort — never fail the whole request because
            # the second pass tripped. The caller still has `answer` (markdown)
            # and `plan` to render with.
            log.warning("formatter.failed", error=str(e))

    return BriefingResponse(
        answer=result.answer,
        iterations=result.iterations,
        tool_calls=result.tool_calls,
        trace=trace,
        plan=[PlanStepOut(**vars(s)) for s in result.plan],
        trace_id=result.trace_id,
        answer_doc=answer_doc,
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
        await queue.put(event.to_dict())

    async def run_agent() -> None:
        try:
            await run_briefing(
                question=question,
                fhir=fhir,
                max_iterations=max_iterations,
                lookback_days=lookback_days,
                on_event=on_event,
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
