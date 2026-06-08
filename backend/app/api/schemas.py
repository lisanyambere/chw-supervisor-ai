"""FastAPI request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Process is alive. No downstream probing — use /readyz for that."""

    status: str  # always "ok"


class ReadinessResponse(BaseModel):
    """Downstream checks. 503 when any required dep is unreachable."""

    status: str  # "ready" or "not_ready"
    openmrs: bool
    llm_provider: str
    llm_model: str
    patients_loaded: int
    chws_loaded: int


class ChwPatientRow(BaseModel):
    """One patient in a CHW's recent panel."""

    patient_uuid: str
    name: str
    last_encounter_date: str | None = None
    encounter_count: int


class ChwDetailResponse(BaseModel):
    """Detail for the CHW drawer: identity, recent load, and patient panel."""

    chw_id: str
    practitioner_uuid: str
    name: str
    days: int
    encounter_count: int
    patient_count: int
    patients: list[ChwPatientRow] = Field(default_factory=list)


class ChwRosterEntry(BaseModel):
    """One CHW in the roster — straight from the id_map, no FHIR reads."""

    chw_id: str
    practitioner_uuid: str


class ActivityDay(BaseModel):
    """One day in the activity chart."""

    date: str  # ISO yyyy-mm-dd
    weekday: str  # "Mon".."Sun"
    encounter_count: int
    is_weekend: bool
    is_zero: bool


class ActivityStats(BaseModel):
    min: int
    max: int
    mean: float
    total: int
    zero_days: int
    active_days: int


class ActivityResponse(BaseModel):
    """Daily CHW encounter series for the activity charts view."""

    days: int
    chw_id: str | None = None
    series: list[ActivityDay] = Field(default_factory=list)
    stats: ActivityStats


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
