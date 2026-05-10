"""Monday-morning briefing agent.

Single-agent ReAct-style loop:
    1. system + user prompt → LLM
    2. if LLM emits tool calls, execute them in parallel and loop
    3. otherwise return the final assistant message

LangGraph can replace this when multi-agent reasoning lands in Phase 3.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
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


@dataclass
class BriefingResult:
    answer: str
    trace: list[TraceEvent] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0


async def run_briefing(
    question: str,
    *,
    fhir: FhirClient | None = None,
    llm: LLM | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    lookback_days: int | None = None,
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
            )
            if agent_span is not None:
                try:
                    agent_span.update(
                        output={
                            "answer": result.answer,
                            "iterations": result.iterations,
                            "tool_calls": result.tool_calls,
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
            return result
    finally:
        if own_fhir:
            await fhir.aclose()


class _NullCM:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


async def _run_briefing_inner(
    *,
    question: str,
    fhir: FhirClient,
    llm: LLM,
    max_iterations: int,
    lookback_days: int,
    lf: Any | None,
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
            ) as gen:
                completion = await llm.chat(messages=messages, tools=tools)
                try:
                    gen.update(
                        output=completion.choices[0].message.model_dump(
                            exclude_none=True
                        ),
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
                except Exception:  # noqa: BLE001
                    pass
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

        async def _run(call: Any) -> tuple[str, str, dict[str, Any], Any]:
            args = json.loads(call.function.arguments or "{}")
            if lf is not None:
                with lf.start_as_current_observation(
                    name=f"tool.{call.function.name}",
                    as_type="tool",
                    input=args,
                ) as ts:
                    result = await execute(call.function.name, args, fhir)
                    try:
                        ts.update(output=result)
                    except Exception:  # noqa: BLE001
                        pass
            else:
                result = await execute(call.function.name, args, fhir)
            return call.id, call.function.name, args, result

        results = await asyncio.gather(*(_run(c) for c in calls))

        for call_id, name, args, result in results:
            tool_calls += 1
            trace.append(
                TraceEvent(kind="tool_call", name=name, arguments=args)
            )
            trace.append(
                TraceEvent(kind="tool_result", name=name, result=result)
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, default=str),
                }
            )

    log.warning("agent.iteration_cap_hit")
    return BriefingResult(
        answer="(no final answer — iteration cap hit)",
        trace=trace,
        iterations=max_iterations,
        tool_calls=tool_calls,
    )
