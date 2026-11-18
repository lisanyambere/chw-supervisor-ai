"""Scenario-recall evaluation: run the full briefing several times and score
how many of the planted scenarios each briefing surfaces.

Ground truth is `data/fixtures/scenarios.json`, written by the data generator.
Each run is scored three ways per scenario:

  judged   — an LLM judge says the briefing conveys the finding (strict; this
             is the number reported as recall)
  named    — the markdown answer names the people/places involved
             (deterministic; a lower bar than `judged`)
  on card  — the same deterministic check against the structured answer card
             the supervisor actually sees

It also lists every problem each briefing raises and matches it to a planted
scenario. Flags that match none are reported for review as possible false
alarms. `scripts/calibrate_judge.py` checks the recall judge against a
person's ratings.

Usage (from repo root, OpenMRS seeded and .env set):

    python scripts/run_scenario_eval.py                # 3 runs
    python scripts/run_scenario_eval.py --runs 5
    python scripts/run_scenario_eval.py --no-langfuse  # don't push scores
    python scripts/run_scenario_eval.py --label baseline

Writes docs/evals/<date>-scenario-recall.md and .json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.agents import format_answer, run_briefing  # noqa: E402
from app.evaluators.recall import (  # noqa: E402
    flatten_answer_doc,
    judge_flags,
    judge_recall,
    mentions,
)
from app.evaluators.scorers import ungrounded_numbers  # noqa: E402
from app.llm import get_llm  # noqa: E402
from app.observability import get_langfuse  # noqa: E402

QUESTION = "Give me the Monday-morning briefing for the team."
FIXTURES = _REPO_ROOT / "data" / "fixtures"


def _patient_names(patient_ids: set[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in sorted((FIXTURES / "localized").glob("*.json")):
        for entry in json.loads(path.read_text())["entry"]:
            r = entry["resource"]
            if r["resourceType"] == "Patient" and r["id"] in patient_ids:
                names[r["id"]] = r["name"][0]["text"]
    return names


async def _one_run(
    index: int, scenarios: list[dict[str, Any]], names: dict[str, str], push: bool
) -> dict[str, Any]:
    started = time.perf_counter()
    result = await run_briefing(QUESTION)
    seconds = time.perf_counter() - started
    doc = await format_answer(result, QUESTION)
    card_text = flatten_answer_doc(doc.to_dict())

    judged, flags = await asyncio.gather(
        asyncio.gather(*(judge_recall(s, result.answer, names) for s in scenarios)),
        judge_flags(result.answer, scenarios),
    )
    per_scenario = {
        s["id"]: {
            "judged": bool(j.value),
            "judge_reason": j.comment,
            "named": mentions(s, result.answer, names),
            "on_card": mentions(s, card_text, names),
        }
        for s, j in zip(scenarios, judged, strict=True)
    }

    lf = get_langfuse() if push else None
    if lf is not None and result.trace_id:
        for j in judged:
            lf.create_score(
                trace_id=result.trace_id, name=j.name, value=j.value, comment=j.comment
            )
        lf.flush()

    found = sum(v["judged"] for v in per_scenario.values())
    unplanted = sum(f["finding"] is None for f in flags)
    print(
        f"run {index}: {found}/{len(scenarios)} scenarios, "
        f"{unplanted}/{len(flags)} flags unplanted, {seconds:.0f}s, "
        f"{result.tool_calls} tool calls, grounded={result.verification['grounded']}"
    )
    return {
        "run": index,
        "trace_id": result.trace_id,
        "seconds": round(seconds, 1),
        "llm_calls": result.iterations,
        "tool_calls": result.tool_calls,
        "route": result.route,
        "verification": result.verification,
        "card_ungrounded_numbers": ungrounded_numbers(card_text, result.trace),
        "scenarios": per_scenario,
        "flags": flags,
        "answer": result.answer,
    }


def _report(
    runs: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> str:
    n = len(runs)
    llm = get_llm()
    lines = [
        f"# Scenario recall — {datetime.now(tz=UTC):%Y-%m-%d}",
        "",
        f"- Question: “{QUESTION}”",
        f"- Runs: {n}, model `{llm.model}` ({llm.provider}); "
        "the judge is the same model",
        f"- Data: synthetic, demo week starting {manifest['demo_week_start']}, "
        f"{len(scenarios)} planted scenarios",
        "",
        "| Scenario | Judged found | Named in answer | Named on card |",
        "|---|---|---|---|",
    ]
    totals = {"judged": 0, "named": 0, "on_card": 0}
    for s in scenarios:
        cells = []
        for key in totals:
            hits = sum(r["scenarios"][s["id"]][key] for r in runs)
            totals[key] += hits
            cells.append(f"{hits}/{n}")
        lines.append(f"| {s['title']} | {' | '.join(cells)} |")
    possible = n * len(scenarios)
    lines += [
        f"| **All scenarios** | **{totals['judged']}/{possible}** "
        f"| **{totals['named']}/{possible}** | **{totals['on_card']}/{possible}** |",
        "",
        "## Flags outside the planted set",
        "",
        f"- Problems raised per briefing: "
        f"{mean(len(r['flags']) for r in runs):.1f} on average",
        f"- Matching a planted scenario: "
        f"{sum(f['finding'] is not None for r in runs for f in r['flags'])} of "
        f"{sum(len(r['flags']) for r in runs)}",
        "- The rest are listed under *Unplanted flags* below. Each is either a "
        "real feature of the generated data that nobody planted or a false alarm; "
        "the grounding check shows its figures came from the data, so telling the "
        "two apart takes a human read.",
        "",
        "## Grounding and cost",
        "",
        f"- Answers that passed the grounding check: "
        f"{sum(r['verification']['grounded'] for r in runs)}/{n} "
        f"({sum(r['verification']['revisions'] for r in runs)} needed a rewrite first)",
        f"- Figures checked per answer: "
        f"{mean(r['verification']['figures_checked'] for r in runs):.0f} on average",
        f"- Answer cards with a number not found in any tool result: "
        f"{sum(bool(r['card_ungrounded_numbers']) for r in runs)}/{n}",
        f"- Time per briefing: {mean(r['seconds'] for r in runs):.0f}s on average "
        f"(min {min(r['seconds'] for r in runs):.0f}s, "
        f"max {max(r['seconds'] for r in runs):.0f}s)",
        f"- Per briefing: {mean(r['llm_calls'] for r in runs):.1f} LLM calls, "
        f"{mean(r['tool_calls'] for r in runs):.1f} tool calls",
        "",
        "## What this measures, and what it does not",
        "",
        "- **Judged found** is recall against planted ground truth: the judge is told "
        "the finding and asked whether the briefing conveys it.",
        "- **Flags outside the planted set** bound the false alarms from above: a "
        "flag matching no planted scenario may still be true of the data.",
        "- **Named** columns are a deterministic lower bar (the right ids, wards and "
        "patient names appear). They can pass when the briefing names the right "
        "person for the wrong reason, which is why the judge is the headline.",
        "- The judge is the same model that wrote the briefing. " + calibration_note(),
        "- The grounding check proves a figure appears in some tool result, not that "
        "it is attached to the right entity.",
        "- The data is synthetic and the scenarios were planted by the same project "
        "that built the tools, so this shows the pipeline works end to end, not how "
        "it would do on real programme data.",
        "",
        "## Misses",
        "",
    ]
    misses = [
        f"- Run {r['run']}, {s['title']}: {r['scenarios'][s['id']]['judge_reason']}"
        for r in runs
        for s in scenarios
        if not r["scenarios"][s["id"]]["judged"]
    ]
    lines += misses or ["None."]
    lines += ["", "## Unplanted flags", ""]
    unplanted = sorted(
        {f["flag"] for r in runs for f in r["flags"] if f["finding"] is None}
    )
    lines += [f"- {f}" for f in unplanted] or ["None."]
    return "\n".join(lines) + "\n"


def calibration_note() -> str:
    """The latest judge-vs-human agreement, if anyone has rated a sample."""
    reports = sorted((_REPO_ROOT / "docs" / "evals").glob("*-judge-calibration.md"))
    if not reports:
        return (
            "It has not yet been checked against human ratings "
            "(see scripts/calibrate_judge.py)."
        )
    return f"Its agreement with a human rater is in {reports[-1].name}."


async def _main(runs: int, push: bool, label: str) -> None:
    manifest = json.loads((FIXTURES / "scenarios.json").read_text())
    scenarios = manifest["scenarios"]
    names = _patient_names({p for s in scenarios for p in s.get("patient_ids", [])})

    # Sequential: each briefing already fans out to OpenMRS in parallel.
    results = [await _one_run(i + 1, scenarios, names, push) for i in range(runs)]

    out_dir = _REPO_ROOT / "docs" / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now(tz=UTC):%Y-%m-%d}-scenario-recall" + (
        f"-{label}" if label else ""
    )
    (out_dir / f"{stem}.json").write_text(json.dumps(results, indent=2))
    report = _report(results, scenarios, manifest)
    (out_dir / f"{stem}.md").write_text(report)
    print(f"\n{report}\nWritten to {out_dir / stem}.md")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--no-langfuse", action="store_true")
    p.add_argument("--label", default="", help="Suffix for the report filename.")
    args = p.parse_args()
    asyncio.run(_main(args.runs, push=not args.no_langfuse, label=args.label))


if __name__ == "__main__":
    main()
