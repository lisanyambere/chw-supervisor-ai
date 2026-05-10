"""Pure-function scorers for briefing agent outputs.

Design notes
------------
- All scores are in [0, 1] where 1.0 = best.
- Scorers must be deterministic and LLM-free so they can run on every commit.
- Each returns an `EvalScore` with a short `comment` to make trace review easy.
- They consume either a `BriefingResult` directly (preferred) or its parts,
  so they're trivially unit-testable without spinning up FHIR/LLM.

Currently implemented
---------------------
- numeric_fidelity     — every number cited in the answer must appear in a
                         tool result (catches fabricated counts / IDs / dates).
- entity_grounding     — every CHW id (chw-NNN) cited in the answer must
                         appear in a tool result.
- plan_minimality      — penalises bloated tool plans (1 = within budget).
- conciseness          — bullet count within the 4–8 range from the system
                         prompt (1 = within range, decay outside).
- iteration_efficiency — fewer ReAct turns is better; 1.0 at 1 turn,
                         decays toward 0 at MAX_TOOL_ITERATIONS.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Lazy import for type-only use to avoid a hard dependency from the scorers
# back into the agents package at import time.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.briefing import BriefingResult, TraceEvent


@dataclass
class EvalScore:
    """A single evaluator output."""

    name: str
    value: float  # in [0, 1]
    comment: str = ""

    def __post_init__(self) -> None:
        # Clamp defensively — keeps the Langfuse dashboard well-behaved.
        self.value = max(0.0, min(1.0, float(self.value)))


# ─── helpers ────────────────────────────────────────────────────────────────

# Match integers and decimals; we deliberately ignore the leading sign so
# "-5%" still extracts "5". Percent signs and units are stripped at compare time.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_CHW_RE = re.compile(r"chw-\d{2,4}", re.IGNORECASE)
# Strip thousands separators so e.g. "3,737" tokenises as the single number
# 3737 instead of "3" + "737".
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _normalise_for_numbers(text: str) -> str:
    return _THOUSANDS_RE.sub("", text or "")


def _flatten_strings(value: Any) -> Iterable[str]:
    """Yield every scalar in a nested structure as a string."""
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        yield str(value)
        return
    if isinstance(value, dict):
        for v in value.values():
            yield from _flatten_strings(v)
        return
    if isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _flatten_strings(v)
        return
    # Fallback — anything else, stringify so substring checks still work.
    yield str(value)


def _tool_results(trace: list["TraceEvent"]) -> list[Any]:
    return [e.result for e in trace if e.kind == "tool_result"]


def _extract_numbers(text: str) -> list[str]:
    """Extract numeric tokens from text, normalised (drop trailing .0)."""
    out: list[str] = []
    for m in _NUMBER_RE.findall(_normalise_for_numbers(text)):
        try:
            f = float(m)
            out.append(str(int(f)) if f.is_integer() else str(f))
        except ValueError:
            out.append(m)
    return out


def _numbers_in_results(results: Iterable[Any]) -> set[str]:
    """All numeric tokens that appear anywhere in the tool results."""
    nums: set[str] = set()
    for r in results:
        for s in _flatten_strings(r):
            for m in _NUMBER_RE.findall(_normalise_for_numbers(s)):
                try:
                    f = float(m)
                    nums.add(str(int(f)) if f.is_integer() else str(f))
                except ValueError:
                    nums.add(m)
    return nums


# Numbers that frequently appear as obvious literals from the system prompt or
# generic phrasing ("4–8 short bullets", "next 7 days", etc.). Counting these
# as ungrounded would generate noisy false positives.
_NUMBER_ALLOWLIST = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                     "30", "100"}


# ─── scorers ────────────────────────────────────────────────────────────────


def numeric_fidelity(answer: str, trace: list["TraceEvent"]) -> EvalScore:
    """Fraction of numbers in `answer` that appear in some tool result.

    Allowlist covers small integers and the default lookback (30) so we don't
    penalise normal language ("top 2 CHWs", "last 30 days").
    """
    nums = _extract_numbers(answer)
    interesting = [n for n in nums if n not in _NUMBER_ALLOWLIST]
    if not interesting:
        return EvalScore(
            "numeric_fidelity",
            1.0,
            comment="no non-trivial numbers cited",
        )
    grounded = _numbers_in_results(_tool_results(trace))
    hits = [n for n in interesting if n in grounded]
    score = len(hits) / len(interesting)
    missing = sorted(set(interesting) - set(hits))
    return EvalScore(
        "numeric_fidelity",
        score,
        comment=(
            f"{len(hits)}/{len(interesting)} numbers grounded"
            + (f"; missing={missing}" if missing else "")
        ),
    )


def entity_grounding(answer: str, trace: list["TraceEvent"]) -> EvalScore:
    """Every `chw-NNN` cited in the answer must appear in some tool result."""
    cited = sorted({m.lower() for m in _CHW_RE.findall(answer or "")})
    if not cited:
        return EvalScore(
            "entity_grounding", 1.0, comment="no CHW ids cited"
        )
    grounded_ids: set[str] = set()
    for r in _tool_results(trace):
        for s in _flatten_strings(r):
            for m in _CHW_RE.findall(s):
                grounded_ids.add(m.lower())
    hits = [c for c in cited if c in grounded_ids]
    score = len(hits) / len(cited)
    missing = sorted(set(cited) - set(hits))
    return EvalScore(
        "entity_grounding",
        score,
        comment=(
            f"{len(hits)}/{len(cited)} CHW ids grounded"
            + (f"; ungrounded={missing}" if missing else "")
        ),
    )


def plan_minimality(
    trace: list["TraceEvent"], *, expected_max: int = 2
) -> EvalScore:
    """Penalise bloated tool plans.

    1.0 if the agent used `<= expected_max` tool calls; otherwise scaled down
    proportionally. Repeated calls to the same tool with the same args are
    counted as a strict failure (they always indicate a planning mistake).
    """
    calls = [e for e in trace if e.kind == "tool_call"]
    n = len(calls)
    if n == 0:
        return EvalScore(
            "plan_minimality",
            0.0,
            comment="no tools called — answer likely ungrounded",
        )

    # Detect duplicate (name, args) pairs.
    seen: set[tuple[str, str]] = set()
    dupes = 0
    for c in calls:
        key = (c.name or "", repr(sorted((c.arguments or {}).items())))
        if key in seen:
            dupes += 1
        else:
            seen.add(key)

    if n <= expected_max and dupes == 0:
        return EvalScore(
            "plan_minimality", 1.0, comment=f"{n} tool call(s), no dupes"
        )
    base = expected_max / n  # decays as n grows
    penalty = 0.5 if dupes else 0.0
    score = max(0.0, base - penalty)
    return EvalScore(
        "plan_minimality",
        score,
        comment=f"{n} calls, {dupes} duplicate(s)",
    )


def conciseness(
    answer: str,
    *,
    min_bullets: int = 4,
    max_bullets: int = 8,
    short_answer_chars: int = 240,
) -> EvalScore:
    """Bullet count should land in the [min, max] range from the system prompt.

    Exception: very short single-fact answers (e.g. "chw-002 logged 16
    encounters") are not penalised for being prose — the bullet rule is for
    proper briefings, not one-shot lookups.
    """
    text = answer or ""
    # Count lines that look like a bullet (-, *, • or numbered).
    bullet_re = re.compile(r"(?m)^\s*(?:[-*•]|\d+\.)\s+\S")
    bullets = len(bullet_re.findall(text))
    if min_bullets <= bullets <= max_bullets:
        return EvalScore(
            "conciseness", 1.0, comment=f"{bullets} bullets (within range)"
        )
    if bullets == 0:
        # Short prose answer to a single-fact question — acceptable.
        if len(text.strip()) <= short_answer_chars:
            return EvalScore(
                "conciseness",
                1.0,
                comment=f"short prose ({len(text.strip())} chars, no bullets)",
            )
        return EvalScore(
            "conciseness", 0.0, comment="no bullets — prose-only answer"
        )
    # Linear decay outside the band; at 2x max or zero we hit 0.
    if bullets < min_bullets:
        score = bullets / min_bullets
    else:
        over = bullets - max_bullets
        score = max(0.0, 1.0 - over / max_bullets)
    return EvalScore(
        "conciseness", score, comment=f"{bullets} bullets (outside range)"
    )


def iteration_efficiency(
    iterations: int, *, max_iterations: int = 6
) -> EvalScore:
    """1.0 at a single iteration, decays linearly to 0 at the cap."""
    if iterations <= 1:
        return EvalScore(
            "iteration_efficiency", 1.0, comment="1 iteration"
        )
    if iterations >= max_iterations:
        return EvalScore(
            "iteration_efficiency",
            0.0,
            comment=f"hit cap ({max_iterations} iterations)",
        )
    span = max_iterations - 1
    score = 1.0 - (iterations - 1) / span
    return EvalScore(
        "iteration_efficiency",
        score,
        comment=f"{iterations} iterations",
    )


def evaluate_briefing(
    result: "BriefingResult",
    *,
    expected_max_tool_calls: int = 2,
    max_iterations: int = 6,
) -> list[EvalScore]:
    """Run every scorer and return the list of scores."""
    return [
        numeric_fidelity(result.answer, result.trace),
        entity_grounding(result.answer, result.trace),
        plan_minimality(result.trace, expected_max=expected_max_tool_calls),
        conciseness(result.answer),
        iteration_efficiency(result.iterations, max_iterations=max_iterations),
    ]
