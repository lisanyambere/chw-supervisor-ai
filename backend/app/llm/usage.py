"""Token usage and estimated cost of model calls.

Every `LLM.chat` call reports its token usage here. It always goes to the
Prometheus token counter; when a caller has opened a `metered()` block, it is
also added to that block's running total, so one briefing (or one evaluation
run) can report exactly what it consumed.

The meter lives in a context variable. asyncio tasks copy the context when
they are created, so the parallel specialists inside a `metered()` block all
add to the same total.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

from app.core import get_settings
from app.observability.metrics import LLM_TOKENS


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    # Subsets of the two totals above, as the provider reports them.
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    def cost_usd(self) -> float | None:
        """Estimated cost at the configured prices; None when unpriced."""
        s = get_settings()
        if s.llm_price_input_per_mtok is None or s.llm_price_output_per_mtok is None:
            return None
        return (
            self.input_tokens * s.llm_price_input_per_mtok
            + self.output_tokens * s.llm_price_output_per_mtok
        ) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        cost = self.cost_usd()
        return {**asdict(self), "cost_usd": None if cost is None else round(cost, 5)}


_current: ContextVar[Usage | None] = ContextVar("llm_usage", default=None)


@contextmanager
def metered() -> Iterator[Usage]:
    """Collect the usage of every model call made inside the block."""
    usage = Usage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def record(completion: Any, provider: str) -> None:
    """Count one completion's tokens. Tolerates providers that omit usage."""
    u = getattr(completion, "usage", None)
    input_tokens = int(getattr(u, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(u, "completion_tokens", 0) or 0)
    cached = int(
        getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    )
    reasoning = int(
        getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0)
        or 0
    )
    LLM_TOKENS.labels(provider=provider, kind="input").inc(input_tokens)
    LLM_TOKENS.labels(provider=provider, kind="output").inc(output_tokens)

    usage = _current.get()
    if usage is not None:
        usage.calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.cached_input_tokens += cached
        usage.reasoning_tokens += reasoning
