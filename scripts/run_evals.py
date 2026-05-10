"""Run the briefing agent against a small set of golden questions, score the
results with the rule-based evaluators, and (optionally) push the scores to
Langfuse so they show up alongside the trace.

Usage (from repo root, with .env loaded by the backend automatically):

    python scripts/run_evals.py
    python scripts/run_evals.py --no-langfuse        # local-only
    python scripts/run_evals.py --question 1 3       # subset

Notes
-----
- The "expected" hints are not asserted equal to the answer text; they're a
  human reference. The deterministic scorers (numeric_fidelity, entity_grounding,
  plan_minimality, conciseness, iteration_efficiency) judge each answer.
- Scores are posted via `langfuse.score_current_trace()` if Langfuse is
  enabled, attached to the same trace as the agent run.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Make `app.*` importable when run from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.agents.briefing import run_briefing  # noqa: E402
from app.evaluators import (  # noqa: E402
    EvalScore,
    evaluate_briefing,
    evaluate_briefing_with_judges,
)
from app.observability import get_langfuse  # noqa: E402


@dataclass
class GoldenQuestion:
    id: str
    question: str
    expected_hint: str  # human-readable reference, not asserted
    expected_max_tool_calls: int = 2


GOLDEN: list[GoldenQuestion] = [
    GoldenQuestion(
        id="g1_top_bottom",
        question=(
            "Quick supervisor check — name the top 2 and bottom 2 CHWs by "
            "encounter count over the last 30 days, with a one-line action."
        ),
        expected_hint="top: chw-009 (140), chw-019 (140); bottom: chw-002 (16), chw-001 (99)",
        expected_max_tool_calls=1,
    ),
    GoldenQuestion(
        id="g2_chw002_count",
        question="How many encounters did chw-002 log in the last 30 days?",
        expected_hint="16 encounters",
        expected_max_tool_calls=2,  # may use list_chws to resolve id
    ),
    GoldenQuestion(
        id="g3_anomalies",
        question="Anything unusual in the team's activity over the last 30 days?",
        expected_hint="chw-002 critically low (16 vs mean ~125)",
        expected_max_tool_calls=2,
    ),
    GoldenQuestion(
        id="g4_team_mean",
        question="What is the team mean encounter count over the last 30 days?",
        expected_hint="124.57",
        expected_max_tool_calls=1,
    ),
    GoldenQuestion(
        id="g5_list_chws",
        question="How many CHWs are in the program?",
        expected_hint="30 CHWs",
        expected_max_tool_calls=1,
    ),
]


def _fmt_score(s: EvalScore) -> str:
    bar = "█" * int(round(s.value * 10)) + "·" * (10 - int(round(s.value * 10)))
    return f"  {s.name:<22} {bar} {s.value:.2f}  {s.comment}"


async def _run_one(
    q: GoldenQuestion,
    *,
    push_to_langfuse: bool,
    use_judges: bool,
) -> tuple[GoldenQuestion, list[EvalScore], str | None]:
    print(f"\n── {q.id} ───────────────────────────────────────")
    print(f"Q: {q.question}")
    print(f"hint: {q.expected_hint}")

    result = await run_briefing(question=q.question)
    print("\nA:")
    print(result.answer)
    print(
        f"\n[iterations={result.iterations}, tool_calls={result.tool_calls}, "
        f"trace_id={result.trace_id}]"
    )

    scores = evaluate_briefing(
        result, expected_max_tool_calls=q.expected_max_tool_calls
    )
    if use_judges:
        try:
            judge_scores = await evaluate_briefing_with_judges(
                result, question=q.question
            )
            scores = scores + judge_scores
        except Exception as e:  # noqa: BLE001
            print(f"  ↳ LLM judges failed: {e}")

    print("\nScores:")
    for s in scores:
        print(_fmt_score(s))

    if push_to_langfuse and result.trace_id:
        lf = get_langfuse()
        if lf is not None:
            try:
                for s in scores:
                    # v4 SDK signature: name, value, trace_id, comment
                    lf.create_score(
                        trace_id=result.trace_id,
                        name=s.name,
                        value=s.value,
                        comment=s.comment,
                    )
                lf.flush()
                print(f"  ↳ pushed {len(scores)} scores to Langfuse")
            except Exception as e:  # noqa: BLE001
                print(f"  ↳ langfuse score push failed: {e}")

    return q, scores, result.trace_id


def _print_summary(rows: list[tuple[GoldenQuestion, list[EvalScore], str | None]]) -> None:
    if not rows:
        return
    names = [s.name for s in rows[0][1]]
    print("\n\n══ Summary ══════════════════════════════════════")
    header = f"{'question':<22} " + " ".join(f"{n[:14]:<14}" for n in names) + "  trace"
    print(header)
    print("-" * len(header))
    totals: dict[str, list[float]] = {n: [] for n in names}
    for q, scores, tid in rows:
        cells = " ".join(f"{s.value:<14.2f}" for s in scores)
        print(f"{q.id:<22} {cells}  {tid or '-'}")
        for s in scores:
            totals[s.name].append(s.value)
    print("-" * len(header))
    means = " ".join(
        f"{(sum(v) / len(v) if v else 0.0):<14.2f}" for v in totals.values()
    )
    print(f"{'MEAN':<22} {means}")


async def _main_async(
    question_ids: list[str] | None,
    push_to_langfuse: bool,
    use_judges: bool,
) -> int:
    if question_ids:
        chosen = [q for q in GOLDEN if q.id in question_ids]
        if not chosen:
            # Allow indexing by position too (1-based).
            try:
                idx = {int(x) - 1 for x in question_ids}
                chosen = [GOLDEN[i] for i in idx if 0 <= i < len(GOLDEN)]
            except ValueError:
                print(f"No questions matched {question_ids}")
                return 2
    else:
        chosen = list(GOLDEN)

    rows = []
    for q in chosen:
        rows.append(
            await _run_one(
                q,
                push_to_langfuse=push_to_langfuse,
                use_judges=use_judges,
            )
        )
    _print_summary(rows)

    # Exit non-zero if any score is below 0.5 — useful in CI.
    worst = min((s.value for _, scores, _ in rows for s in scores), default=1.0)
    return 0 if worst >= 0.5 else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Run briefing-agent evaluators.")
    p.add_argument(
        "--question",
        nargs="*",
        default=None,
        help="Subset by id (e.g. g1_top_bottom) or 1-based index.",
    )
    p.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip pushing scores to Langfuse.",
    )
    p.add_argument(
        "--no-judges",
        action="store_true",
        help="Skip the LLM-as-judge scorers (deterministic only).",
    )
    args = p.parse_args()
    code = asyncio.run(
        _main_async(
            args.question,
            push_to_langfuse=not args.no_langfuse,
            use_judges=not args.no_judges,
        )
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
