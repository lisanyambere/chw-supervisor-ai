"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents import format_answer, run_briefing
from app.api.schemas import (
    AnswerDocOut,
    BriefingRequest,
    BriefingResponse,
    HealthResponse,
    PlanStepOut,
    TraceEntry,
)
from app.core import configure_logging, get_logger, get_settings
from app.fhir import FhirClient, get_id_map
from app.llm import get_llm
from app.observability import aflush as langfuse_flush
from app.observability import get_langfuse, metrics_router

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


def get_fhir() -> FhirClient:
    return app.state.fhir


@app.get("/healthz", response_model=HealthResponse)
async def healthz(fhir: FhirClient = Depends(get_fhir)) -> HealthResponse:
    s = get_settings()
    idmap = get_id_map()

    openmrs_ok = True
    try:
        await fhir.count("Patient", params={"_count": "0"})
    except Exception as e:  # noqa: BLE001
        log.warning("healthz.openmrs_unreachable", error=str(e))
        openmrs_ok = False

    try:
        llm = get_llm()
        provider, model = llm.provider, llm.model
    except RuntimeError:
        provider, model = s.llm_provider, "(unconfigured)"

    return HealthResponse(
        status="ok" if openmrs_ok else "degraded",
        openmrs=openmrs_ok,
        llm_provider=provider,
        llm_model=model,
        patients_loaded=len(idmap.patients),
        chws_loaded=len(idmap.practitioners),
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
