"""Monday-morning briefing: entry point and the tool-calling loop.

`run_briefing` runs the multi-agent graph in `app.agents.graph`:

    router → specialists (in parallel) → synthesizer → verifier

Each specialist is one `run_tool_agent` loop over its own subset of tools:
    1. system + user prompt → LLM
    2. if the LLM emits tool calls, execute them in parallel and loop
    3. otherwise return the assistant message as that specialist's findings
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
from app.tools import execute, get_tool

log = get_logger(__name__)

MAX_TOOL_ITERATIONS = 6


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
    # Which specialist produced the event; None for the final answer.
    agent: str | None = None


@dataclass
class StreamEvent:
    """One frame on the /briefing/stream wire.

    `kind` is one of:
      - "route"       — router chose specialists; `agents` + `reason` set
      - "agent_start" — a specialist began; `agent` set
      - "tool_start"  — a specialist decided to call a tool; `agent` + `tool`
                        + `args` set
      - "tool_done"   — tool returned; `agent` + `tool` + `args` + `ms` +
                        `rows` set
      - "agent_done"  — a specialist reported; `agent` + `ms` set
      - "verify"      — grounding check ran; `verification` set
      - "response"    — final answer ready; `answer` + `iterations` +
                        `tool_calls` + `plan` set
      - "error"       — fatal failure during the run; `message` set
    """

    kind: str
    # route
    agents: list[str] | None = None
    reason: str | None = None
    # agent_start / agent_done / tool_start / tool_done
    agent: str | None = None
    tool: str | None = None
    args: str | None = None
    ms: int | None = None
    rows: int | None = None
    # verify
    verification: dict[str, Any] | None = None
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
    agent: str | None = None  # the specialist that made the call


@dataclass
class AgentRun:
    """What one specialist did and concluded."""

    name: str
    findings: str
    trace: list[TraceEvent] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0
    ms: int = 0


@dataclass
class BriefingResult:
    answer: str
    trace: list[TraceEvent] = field(default_factory=list)
    # Total LLM calls across the router, specialists and synthesizer.
    iterations: int = 0
    tool_calls: int = 0
    # Langfuse trace id (when observability is enabled), so callers can attach
    # post-hoc evaluator scores to the same trace.
    trace_id: str | None = None
    # Link to that trace in the Langfuse UI.
    trace_url: str | None = None
    # Compact, ordered list of tool executions — derived from `trace` at
    # build time so /briefing consumers don't have to do it themselves.
    plan: list[PlanStep] = field(default_factory=list)
    # Specialists the router engaged, and why.
    route: list[str] = field(default_factory=list)
    route_reason: str = ""
    agents: list[AgentRun] = field(default_factory=list)
    # Outcome of the grounding check on the final answer; see graph.verify.
    verification: dict[str, Any] = field(default_factory=dict)


async def run_briefing(
    question: str,
    *,
    fhir: FhirClient | None = None,
    llm: LLM | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    lookback_days: int | None = None,
    on_event: OnEvent | None = None,
) -> BriefingResult:
    """Answer a supervisor question with the multi-agent briefing graph."""
    # Imported here: graph.py builds on the types and loop defined above.
    from app.agents.graph import run_graph

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
            result = await run_graph(
                question=question,
                fhir=fhir,
                llm=llm,
                max_iterations=max_iterations,
                lookback_days=lookback_days,
                lf=lf,
                on_event=on_event,
            )
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
                        result.trace_url = lf.get_trace_url(trace_id=str(tid))
                    if get_settings().langfuse_public_traces:
                        agent_span.set_trace_as_public()
                    tool_plan = [
                        f"{e.agent}:{e.name}"
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
                            "route": result.route,
                            "verification": result.verification,
                            "tool_plan": tool_plan,
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    log.debug("langfuse.agent_span_update_failed", error=str(e))
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
        for key in (
            "rows", "results", "items", "data", "chws", "patients",
            "children", "inactive_chws", "series",
        ):
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
                agent=ev.agent,
                tool=ev.name or "",
                args=_format_args(ev.arguments),
                ms=int(ev.ms or (result_ev.ms if result_ev else 0) or 0),
                rows=_row_count(result_ev.result if result_ev else None),
            )
        )
    return steps


async def traced_chat(
    llm: LLM,
    lf: Any | None,
    name: str,
    messages: list[ChatCompletionMessageParam],
    *,
    trace_id: str | None = None,
    **kwargs: Any,
) -> Any:
    """One LLM call, recorded as a Langfuse generation when tracing is on.

    Pass `trace_id` to attach the call to a trace that is no longer the
    current one, e.g. the answer formatter, which runs after the briefing.
    """
    if lf is None:
        return await llm.chat(messages=messages, **kwargs)
    with lf.start_as_current_observation(
        name=name,
        as_type="generation",
        model=llm.model,
        input=messages,
        metadata={"provider": llm.provider},
        **({"trace_context": {"trace_id": trace_id}} if trace_id else {}),
    ) as gen:
        completion = await llm.chat(messages=messages, **kwargs)
        try:
            msg_dump = completion.choices[0].message.model_dump(exclude_none=True)
            # Surface model "reasoning" if the provider returned it (gpt-5
            # family + o-series via Azure, some OpenRouter models), plus a
            # compact tool-plan for easy filtering in Langfuse.
            meta: dict[str, Any] = {"provider": llm.provider}
            plan = [
                tc["function"]["name"]
                for tc in msg_dump.get("tool_calls") or []
                if isinstance(tc, dict) and tc.get("function")
            ]
            if plan:
                meta["tool_plan"] = plan
            reasoning = msg_dump.get("reasoning") or msg_dump.get("reasoning_content")
            if reasoning:
                meta["reasoning"] = reasoning
            gen.update(
                output=msg_dump,
                metadata=meta,
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
            log.debug("langfuse.generation_update_failed", error=str(e))
        return completion


async def run_tool_agent(
    *,
    name: str,
    system_prompt: str,
    tool_names: list[str],
    question: str,
    fhir: FhirClient,
    llm: LLM,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    lf: Any | None = None,
    on_event: OnEvent | None = None,
) -> AgentRun:
    """Run one specialist: a bounded tool-calling loop over `tool_names`."""
    started = time.perf_counter()
    tools = [t.to_openai() for n in tool_names if (t := get_tool(n)) is not None]
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    run = AgentRun(name=name, findings="")

    for iteration in range(1, max_iterations + 1):
        log.info("agent.step", agent=name, iteration=iteration)
        run.iterations = iteration
        completion = await traced_chat(
            llm,
            lf,
            f"llm.{name}.iter{iteration}",
            messages,
            tools=tools,
            # On the last allowed turn the model must report what it has
            # rather than ask for another tool.
            tool_choice="none" if iteration == max_iterations else "auto",
        )
        msg = completion.choices[0].message

        if not msg.tool_calls:
            run.findings = msg.content or ""
            run.trace.append(
                TraceEvent(kind="assistant", content=run.findings, agent=name)
            )
            break

        # Persist the assistant tool-call message verbatim so the model has
        # the same context on the next turn.
        messages.append(msg.model_dump(exclude_none=True))

        calls = msg.tool_calls
        log.info("agent.tools", agent=name, count=len(calls))
        parsed = [_parse_args(call.function.arguments) for call in calls]

        if on_event is not None:
            # Fire all tool_start frames before any tool_done — preserves
            # the "agent decided to call all of these" semantics on the wire.
            for call, (args, _err) in zip(calls, parsed, strict=True):
                await on_event(
                    StreamEvent(
                        kind="tool_start",
                        agent=name,
                        tool=call.function.name,
                        args=_format_args(args),
                    )
                )

        async def _run(
            call: Any, args: dict[str, Any], arg_error: str | None
        ) -> tuple[str, str, dict[str, Any], Any, int]:
            t0 = time.perf_counter()
            if arg_error is not None:
                # Hand the parse failure back to the model so it can retry.
                result: Any = {"error": arg_error}
            elif call.function.name not in tool_names:
                result = {"error": f"tool not available to {name}"}
            elif lf is not None:
                with lf.start_as_current_observation(
                    name=f"tool.{call.function.name}",
                    as_type="tool",
                    input=args,
                ) as ts:
                    result = await execute(call.function.name, args, fhir)
                    try:
                        ts.update(output=result)
                    except Exception as e:  # noqa: BLE001
                        log.debug("langfuse.tool_update_failed", error=str(e))
            else:
                result = await execute(call.function.name, args, fhir)
            ms = int((time.perf_counter() - t0) * 1000)
            return call.id, call.function.name, args, result, ms

        results = await asyncio.gather(
            *(_run(c, a, err) for c, (a, err) in zip(calls, parsed, strict=True))
        )

        for call_id, tool_name, args, result, ms in results:
            run.tool_calls += 1
            run.trace.append(
                TraceEvent(
                    kind="tool_call", name=tool_name, arguments=args, ms=ms, agent=name
                )
            )
            run.trace.append(
                TraceEvent(
                    kind="tool_result", name=tool_name, result=result, ms=ms, agent=name
                )
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
                        agent=name,
                        tool=tool_name,
                        args=_format_args(args),
                        ms=ms,
                        rows=_row_count(result),
                    )
                )

    run.ms = int((time.perf_counter() - started) * 1000)
    return run


def _parse_args(raw: str | None) -> tuple[dict[str, Any], str | None]:
    """Tool arguments as a dict, or an error message for the model."""
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        return {}, f"arguments were not valid JSON: {e}"
    if not isinstance(args, dict):
        return {}, "arguments must be a JSON object"
    return args, None
