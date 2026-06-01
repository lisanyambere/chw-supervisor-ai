"""Monday-morning briefing agent.

Single-agent ReAct-style loop:
    1. system + user prompt → LLM
    2. if LLM emits tool calls, execute them in parallel and loop
    3. otherwise return the final assistant message

"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

from app.core import get_logger, get_settings
from app.fhir import FhirClient
from app.llm import LLM, get_llm
from app.observability import get_langfuse
from app.tools import all_tools, execute

log = get_logger(__name__)

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT_TEMPLATE = """\
You are the briefing assistant for a community health program supervisor in Kakamega, Kenya.
Your job is to help the supervisor understand what their team of Community Health Workers (CHWs) has been doing.

Default lookback window: {lookback_days} days. Use this when the supervisor does not name a specific date range.
Pass `days={lookback_days}` to tools that accept a `days` parameter unless the user asks for a different range.

Reasoning rules:
- ALWAYS gather data with tools before drawing conclusions. Do not guess numbers.
- Start with `team_activity_summary` to get a per-CHW workload picture.
- Use `count_chw_encounters` to dig into individuals when something looks off.
- Use `get_patient_summary` only when the supervisor asks about a specific patient.
- Be concrete: cite CHW ids and counts. Flag CHWs whose activity is well below the team mean.
- Keep the final briefing tight: 4–8 short bullets. No filler.
"""


def _build_system_prompt(lookback_days: int) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(lookback_days=lookback_days)


@dataclass
class TraceEvent:
    kind: str  # "tool_call" | "tool_result" | "assistant"
    name: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any = None
    content: str | None = None
    # Wall-clock duration of a tool call in milliseconds. Only populated on
    # `tool_result` events; the matched `tool_call` event mirrors it for
    # convenience when the UI iterates calls in order.
    ms: int | None = None


@dataclass
class StreamEvent:
    """One frame on the /briefing/stream wire.

    `kind` is one of:
      - "tool_start"  — agent decided to call a tool; `tool` + `args` set
      - "tool_done"   — tool returned; `tool` + `args` + `ms` + `rows` set
      - "response"    — final answer ready; `answer` + `iterations` +
                        `tool_calls` + `plan` set
      - "error"       — fatal failure during the run; `message` set
    """

    kind: str
    # tool_start / tool_done
    tool: str | None = None
    args: str | None = None
    ms: int | None = None
    rows: int | None = None
    # response
    answer: str | None = None
    iterations: int | None = None
    tool_calls: int | None = None
    plan: list[dict[str, Any]] | None = None
    # error
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a wire-friendly dict with None fields stripped."""
        return {k: v for k, v in asdict(self).items() if v is not None}


OnEvent = Callable[["StreamEvent"], Awaitable[None]]


@dataclass
class PlanStep:
    """One row of the live tool-execution timeline.

    Mirrors the design-handoff schema so the frontend can render a plan card
    without any client-side derivation.
    """

    tool: str
    args: str  # already-rendered, e.g. "(days=30)"
    ms: int
    rows: int  # best-effort row count of the tool result


@dataclass
class BriefingResult:
    answer: str
    trace: list[TraceEvent] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0
    # Langfuse trace id (when observability is enabled), so callers can attach
    # post-hoc evaluator scores to the same trace.
    trace_id: str | None = None
    # Compact, ordered list of tool executions — derived from `trace` at
    # build time so /briefing consumers don't have to do it themselves.
    plan: list[PlanStep] = field(default_factory=list)


async def run_briefing(
    question: str,
    *,
    fhir: FhirClient | None = None,
    llm: LLM | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    lookback_days: int | None = None,
    on_event: OnEvent | None = None,
) -> BriefingResult:
    """Answer a supervisor question by tool-calling the FHIR layer."""
    own_fhir = fhir is None
    fhir = fhir or FhirClient()
    llm = llm or get_llm()
    if lookback_days is None:
        lookback_days = get_settings().briefing_default_lookback_days

    lf = get_langfuse()
    if lf is not None:
        agent_cm = lf.start_as_current_observation(
            name="agent.run_briefing",
            as_type="agent",
            input={"question": question, "lookback_days": lookback_days},
        )
    else:
        agent_cm = _NullCM()

    try:
        with agent_cm as agent_span:
            result = await _run_briefing_inner(
                question=question,
                fhir=fhir,
                llm=llm,
                max_iterations=max_iterations,
                lookback_days=lookback_days,
                lf=lf,
                on_event=on_event,
            )
            # Always derive a plan, with or without Langfuse.
            result.plan = _derive_plan(result.trace)
            if on_event is not None:
                await on_event(
                    StreamEvent(
                        kind="response",
                        answer=result.answer,
                        iterations=result.iterations,
                        tool_calls=result.tool_calls,
                        plan=[asdict(p) for p in result.plan],
                    )
                )
            if agent_span is not None:
                try:
                    # Capture trace id so the caller can attach evaluator scores.
                    tid = getattr(agent_span, "trace_id", None)
                    if tid:
                        result.trace_id = str(tid)
                    tool_plan = [
                        e.name
                        for e in result.trace
                        if e.kind == "tool_call" and e.name
                    ]
                    agent_span.update(
                        output={
                            "answer": result.answer,
                            "iterations": result.iterations,
                            "tool_calls": result.tool_calls,
                            "tool_plan": tool_plan,
                        },
                        metadata={
                            "lookback_days": lookback_days,
                            "provider": llm.provider,
                            "model": llm.model,
                            "tool_plan": tool_plan,
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    log.debug(
                        "langfuse.span_update_failed", where="agent_span", error=str(e)
                    )
            return result
    finally:
        if own_fhir:
            await fhir.aclose()


class _NullCM:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def _format_args(args: dict[str, Any] | None) -> str:
    """Render tool arguments the way the design handoff shows them.

    Examples:
      {}                    -> "()"
      {"days": 30}          -> "(days=30)"
      {"chw_id": "chw-002"} -> '(chw_id="chw-002")'
    """
    if not args:
        return "()"
    parts: list[str] = []
    for k, v in args.items():
        if isinstance(v, str):
            parts.append(f'{k}="{v}"')
        else:
            parts.append(f"{k}={v}")
    return "(" + ", ".join(parts) + ")"


def _row_count(result: Any) -> int:
    """Best-effort row count for a tool result.

    Tools generally return either a list, a dict with a `rows`/`results`/`items`
    list, or a dict with `total`. Falls back to 1 for scalars.
    """
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        for key in ("rows", "results", "items", "data", "chws", "patients"):
            v = result.get(key)
            if isinstance(v, list):
                return len(v)
        if isinstance(result.get("total"), int):
            return int(result["total"])
        # Single-stat payloads still count as 1 row of evidence.
        return 1
    return 1


def _derive_plan(trace: list[TraceEvent]) -> list[PlanStep]:
    """Walk the trace and pair each tool_call with its tool_result.

    Order is preserved. We key by name + arguments to match the pair, which
    handles the common case of parallel calls with distinct args. If the
    same (name, args) is called twice in one turn, we just consume them in
    FIFO order — plan steps stay 1:1 with tool calls.
    """
    steps: list[PlanStep] = []
    pending_results: list[TraceEvent] = [
        e for e in trace if e.kind == "tool_result"
    ]
    by_name: dict[str, list[TraceEvent]] = {}
    for r in pending_results:
        by_name.setdefault(r.name or "", []).append(r)

    for ev in trace:
        if ev.kind != "tool_call":
            continue
        bucket = by_name.get(ev.name or "", [])
        result_ev = bucket.pop(0) if bucket else None
        steps.append(
            PlanStep(
                tool=ev.name or "",
                args=_format_args(ev.arguments),
                ms=int(ev.ms or (result_ev.ms if result_ev else 0) or 0),
                rows=_row_count(result_ev.result if result_ev else None),
            )
        )
    return steps


async def _run_briefing_inner(
    *,
    question: str,
    fhir: FhirClient,
    llm: LLM,
    max_iterations: int,
    lookback_days: int,
    lf: Any | None,
    on_event: OnEvent | None = None,
) -> BriefingResult:
    tools = [t.to_openai() for t in all_tools()]
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _build_system_prompt(lookback_days)},
        {"role": "user", "content": question},
    ]
    trace: list[TraceEvent] = []
    tool_calls = 0

    for iteration in range(1, max_iterations + 1):
        log.info("agent.step", iteration=iteration)
        if lf is not None:
            with lf.start_as_current_observation(
                name=f"llm.chat.iter{iteration}",
                as_type="generation",
                model=llm.model,
                input=messages,
                metadata={"iteration": iteration, "provider": llm.provider},
            ) as gen:
                completion = await llm.chat(messages=messages, tools=tools)
                try:
                    msg_dump = completion.choices[0].message.model_dump(
                        exclude_none=True
                    )
                    # Surface model "reasoning" if the provider returned it
                    # (gpt-5 family + o-series via Azure, some OpenRouter models),
                    # plus a compact tool-plan for easy filtering in Langfuse.
                    reasoning = (
                        msg_dump.get("reasoning")
                        or msg_dump.get("reasoning_content")
                    )
                    plan = [
                        tc["function"]["name"]
                        for tc in msg_dump.get("tool_calls") or []
                        if isinstance(tc, dict) and tc.get("function")
                    ]
                    gen_meta: dict[str, Any] = {
                        "iteration": iteration,
                        "provider": llm.provider,
                    }
                    if plan:
                        gen_meta["tool_plan"] = plan
                    if reasoning:
                        gen_meta["reasoning"] = reasoning
                    gen.update(
                        output=msg_dump,
                        metadata=gen_meta,
                        usage_details=(
                            {
                                "input": completion.usage.prompt_tokens,
                                "output": completion.usage.completion_tokens,
                                "total": completion.usage.total_tokens,
                            }
                            if completion.usage
                            else None
                        ),
                    )
                except Exception as e:  # noqa: BLE001
                    log.debug(
                        "langfuse.span_update_failed", where="generation", error=str(e)
                    )
        else:
            completion = await llm.chat(messages=messages, tools=tools)

        choice = completion.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            trace.append(TraceEvent(kind="assistant", content=msg.content or ""))
            return BriefingResult(
                answer=msg.content or "",
                trace=trace,
                iterations=iteration,
                tool_calls=tool_calls,
            )

        # Persist the assistant tool-call message verbatim so the model has
        # the same context on the next turn.
        messages.append(msg.model_dump(exclude_none=True))  # type: ignore[arg-type]

        calls = msg.tool_calls
        log.info("agent.tools", count=len(calls))

        if on_event is not None:
            # Fire all tool_start frames before any tool_done — preserves
            # the "agent decided to call all of these" semantics on the wire.
            for call in calls:
                try:
                    pre_args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    pre_args = {}
                await on_event(
                    StreamEvent(
                        kind="tool_start",
                        tool=call.function.name,
                        args=_format_args(pre_args),
                    )
                )

        async def _run(call: Any) -> tuple[str, str, dict[str, Any], Any, int]:
            args = json.loads(call.function.arguments or "{}")
            t0 = time.perf_counter()
            if lf is not None:
                with lf.start_as_current_observation(
                    name=f"tool.{call.function.name}",
                    as_type="tool",
                    input=args,
                ) as ts:
                    result = await execute(call.function.name, args, fhir)
                    try:
                        ts.update(output=result)
                    except Exception as e:  # noqa: BLE001
                        log.debug(
                            "langfuse.span_update_failed",
                            where="tool_span",
                            error=str(e),
                        )
            else:
                result = await execute(call.function.name, args, fhir)
            ms = int((time.perf_counter() - t0) * 1000)
            return call.id, call.function.name, args, result, ms

        results = await asyncio.gather(*(_run(c) for c in calls))

        for call_id, name, args, result, ms in results:
            tool_calls += 1
            trace.append(
                TraceEvent(kind="tool_call", name=name, arguments=args, ms=ms)
            )
            trace.append(
                TraceEvent(kind="tool_result", name=name, result=result, ms=ms)
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, default=str),
                }
            )
            if on_event is not None:
                await on_event(
                    StreamEvent(
                        kind="tool_done",
                        tool=name,
                        args=_format_args(args),
                        ms=ms,
                        rows=_row_count(result),
                    )
                )

    log.warning("agent.iteration_cap_hit")
    return BriefingResult(
        answer="(no final answer — iteration cap hit)",
        trace=trace,
        iterations=max_iterations,
        tool_calls=tool_calls,
    )
