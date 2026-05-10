"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException

from app.agents import run_briefing
from app.api.schemas import (
    BriefingRequest,
    BriefingResponse,
    HealthResponse,
    TraceEntry,
)
from app.core import configure_logging, get_logger, get_settings
from app.fhir import FhirClient, get_id_map
from app.llm import get_llm
from app.observability import aflush as langfuse_flush
from app.observability import get_langfuse

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
    return BriefingResponse(
        answer=result.answer,
        iterations=result.iterations,
        tool_calls=result.tool_calls,
        trace=trace,
    )
