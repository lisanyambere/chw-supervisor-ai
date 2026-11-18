"""Token metering and cost estimates."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core import get_settings
from app.llm.usage import Usage, metered, record


def completion(prompt: int, output: int, cached: int = 0, reasoning: int = 0) -> object:
    return SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=output,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        )
    )


async def test_parallel_calls_inside_a_block_add_to_one_total() -> None:
    async def call(prompt: int, output: int) -> None:
        await asyncio.sleep(0)
        record(completion(prompt, output, cached=10, reasoning=5), "fake")

    with metered() as usage:
        # Tasks copy the context, as LangGraph's parallel nodes do.
        await asyncio.gather(
            asyncio.create_task(call(1000, 100)),
            asyncio.create_task(call(2000, 300)),
        )

    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, 3000, 400)
    assert (usage.cached_input_tokens, usage.reasoning_tokens) == (20, 10)


def test_calls_outside_a_block_are_not_attributed() -> None:
    record(completion(500, 50), "fake")  # no block open: only Prometheus
    with metered() as usage:
        pass
    assert usage.calls == 0


def test_missing_usage_counts_the_call_with_zero_tokens() -> None:
    with metered() as usage:
        record(SimpleNamespace(usage=None), "fake")
    assert (usage.calls, usage.input_tokens) == (1, 0)


def test_cost_uses_the_configured_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "llm_price_input_per_mtok", 5.0)
    monkeypatch.setattr(s, "llm_price_output_per_mtok", 30.0)
    usage = Usage(calls=1, input_tokens=1_000_000, output_tokens=100_000)
    assert usage.cost_usd() == pytest.approx(8.0)
    assert usage.to_dict()["cost_usd"] == 8.0

    monkeypatch.setattr(s, "llm_price_output_per_mtok", None)
    assert usage.cost_usd() is None
