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
    # Langfuse project page; None when tracing is off.
    langfuse_url: str | None = None


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
    agent: str | None = None  # the specialist that made the call


class AgentRunOut(BaseModel):
    """One specialist's part in a briefing."""

    name: str
    findings: str
    tool_calls: int
    ms: int


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
    trace_url: str | None = None  # this run's trace in the Langfuse UI
    # New: structured answer for the UI. Optional so the endpoint can skip
    # the second LLM call (and its latency cost) when the caller asks.
    answer_doc: AnswerDocOut | None = None
    # Multi-agent detail: who the router engaged, what each specialist found,
    # and whether every figure in the answer traced back to a tool result.
    route: list[str] = Field(default_factory=list)
    route_reason: str = ""
    agents: list[AgentRunOut] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    # Tokens and estimated USD cost of every model call behind this answer,
    # including the answer formatter. See app.llm.usage.
    usage: dict[str, Any] = Field(default_factory=dict)


class DailyCount(BaseModel):
    date: str  # YYYY-MM-DD
    encounter_count: int


class RosterRow(BaseModel):
    chw_id: str
    name: str | None = None
    ward: str | None = None
    encounters_30d: int
    encounters_7d: int
    # From chw_activity_gaps over 14 days: "stopped_early", "started_late",
    # "no_visits", or None when the CHW keeps the team's working pattern.
    pattern: str | None = None
    last_active: str | None = None


class RosterResponse(BaseModel):
    chws: list[RosterRow]


class AnomaliesResponse(BaseModel):
    """What needs a supervisor's attention, straight from the tools (no model).

    Each field is the named tool's output over `days` (overdue follow-ups use
    a longer window, since a missed return date can be weeks old).
    `action_count` counts what needs someone today: fever clusters, children
    with danger signs, overdue patients and CHWs out of step with the team.
    """

    days: int
    action_count: int
    fever_clusters: list[dict[str, Any]]
    children: list[dict[str, Any]]
    overdue: list[dict[str, Any]]
    activity_gaps: dict[str, Any]
    missing_location: dict[str, Any]
    visits_after_death: dict[str, Any]


class DailyActivityResponse(BaseModel):
    """Team-wide encounters per day, for the activity chart."""

    days: int
    series: list[DailyCount]  # oldest first
    total: int


class ChwDetailResponse(BaseModel):
    """One CHW's profile and recent activity, for the detail drawer."""

    chw_id: str
    practitioner_uuid: str
    name: str | None = None  # from the OpenMRS Practitioner
    ward: str | None = None  # the CHW's home ward, from the id map
    encounters_30d: int
    encounters_7d: int
    patients_30d: int
    daily: list[DailyCount]  # last 7 days, oldest first
