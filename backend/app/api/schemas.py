"""FastAPI request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    openmrs: bool
    llm_provider: str
    llm_model: str
    patients_loaded: int
    chws_loaded: int


class BriefingRequest(BaseModel):
    question: str = Field(
        default="Give me the Monday-morning briefing for the team.",
        description="Free-form supervisor question.",
        min_length=1,
        max_length=2000,
    )
    max_iterations: int = Field(default=6, ge=1, le=12)
    include_trace: bool = Field(default=True)
    lookback_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description=(
            "Default look-back window the agent should assume when the "
            "question does not name a date range. Falls back to "
            "BRIEFING_DEFAULT_LOOKBACK_DAYS when omitted."
        ),
    )


class TraceEntry(BaseModel):
    kind: str
    name: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any | None = None
    content: str | None = None


class BriefingResponse(BaseModel):
    answer: str
    iterations: int
    tool_calls: int
    trace: list[TraceEntry] = Field(default_factory=list)
