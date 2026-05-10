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
    include_answer_doc: bool = Field(
        default=True,
        description=(
            "Also run the structured-answer formatter and return `answer_doc`. "
            "Adds one extra LLM call; turn off for cheap, markdown-only runs."
        ),
    )
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
    ms: int | None = None


class PlanStepOut(BaseModel):
    """Compact representation of one tool execution for the UI timeline."""

    tool: str
    args: str  # already-rendered, e.g. "(days=30)"
    ms: int
    rows: int


class AnswerDocOut(BaseModel):
    """Structured answer matching the design-handoff schema. The frontend
    renders this directly; the markdown `answer` field is kept as a fallback."""

    headline: str
    period: str = ""
    sections: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class BriefingResponse(BaseModel):
    answer: str
    iterations: int
    tool_calls: int
    trace: list[TraceEntry] = Field(default_factory=list)
    plan: list[PlanStepOut] = Field(default_factory=list)
    trace_id: str | None = None
    # New: structured answer for the UI. Optional so the endpoint can skip
    # the second LLM call (and its latency cost) when the caller asks.
    answer_doc: AnswerDocOut | None = None
