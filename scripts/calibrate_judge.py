"""Check the recall judge, against a person's ratings or other models.

Cross-check against other model families (no human needed):

       python scripts/calibrate_judge.py cross docs/evals/<run>.json \
           --model anthropic/claude-sonnet-5.5 --model google/gemini-3.8-flash

   Each judge (the project's own, plus every --model through OpenRouter)
   grades every briefing in the run against the 7 planted findings and 5
   decoys: false findings that change the one detail that matters. A judge
   worth trusting says "found" to the real ones and "not found" to the
   decoys. Writes <date>-judge-agreement.md and .json.

Or against a person:

1. Export a rating sheet from a scenario-eval run:

       python scripts/calibrate_judge.py export docs/evals/<run>.json

   This writes <run>-ratings.csv: one row per (briefing, planted finding),
   with the judge's verdict hidden. Open it in a spreadsheet, read each
   briefing, and put 1 in `human_found` if the briefing conveys the finding
   clearly enough to act on, 0 if not.

2. Score the judge against those ratings:

       python scripts/calibrate_judge.py score docs/evals/<run>-ratings.csv

   This prints raw agreement and Cohen's kappa, lists every disagreement, and
   writes <date>-judge-calibration.md next to the sheet, which the scenario
   eval report then cites.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.evaluators.calibration import agreement  # noqa: E402
from app.evaluators.judge import _judge_with_llm  # noqa: E402
from app.evaluators.recall import decoys, judge_recall, patient_names  # noqa: E402
from app.llm import LLM, get_llm  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

FIXTURES = _REPO_ROOT / "data" / "fixtures"

FIELDS = ["run", "scenario", "finding", "briefing", "human_found"]


def export(run_path: Path) -> Path:
    runs = json.loads(run_path.read_text())
    manifest = json.loads(
        (_REPO_ROOT / "data" / "fixtures" / "scenarios.json").read_text()
    )
    expect = {s["id"]: s["expect"] for s in manifest["scenarios"]}
    out = run_path.with_name(run_path.stem + "-ratings.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in runs:
            for sid in r["scenarios"]:
                w.writerow(
                    {
                        "run": r["run"],
                        "scenario": sid,
                        "finding": expect[sid],
                        "briefing": r["answer"],
                        "human_found": "",
                    }
                )
    return out


def score(sheet_path: Path) -> Path:
    run_path = sheet_path.with_name(sheet_path.stem.removesuffix("-ratings") + ".json")
    runs = {r["run"]: r for r in json.loads(run_path.read_text())}
    with sheet_path.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["human_found"].strip() in ("0", "1")]
    if not rows:
        raise SystemExit(f"No rows rated with 0 or 1 in {sheet_path}")

    pairs, disagreements = [], []
    for row in rows:
        verdict = runs[int(row["run"])]["scenarios"][row["scenario"]]
        judge, human = verdict["judged"], row["human_found"].strip() == "1"
        pairs.append((judge, human))
        if judge != human:
            disagreements.append(
                f"- Run {row['run']}, {row['scenario']}: judge said "
                f"{'found' if judge else 'missed'}, you said "
                f"{'found' if human else 'missed'}. Judge's reason: "
                f"{verdict['judge_reason']}"
            )

    a = agreement(pairs)
    kappa = (
        "undefined (both raters gave the same verdict throughout)"
        if a.kappa is None
        else f"{a.kappa:.2f}"
    )
    report = "\n".join(
        [
            f"# Recall judge calibration — {datetime.now(tz=UTC):%Y-%m-%d}",
            "",
            f"- Ratings: {sheet_path.name}, {a.n} rated rows",
            f"- Agreement: {a.agree}/{a.n} ({a.rate:.0%})",
            f"- Cohen's kappa: {kappa}",
            f"- Judge said found where the human did not: {a.judge_only}",
            f"- Human said found where the judge did not: {a.human_only}",
            "",
            "## Disagreements",
            "",
            *(disagreements or ["None."]),
            "",
        ]
    )
    out = sheet_path.with_name(f"{datetime.now(tz=UTC):%Y-%m-%d}-judge-calibration.md")
    out.write_text(report)
    print(report)
    return out


def _openrouter(model: str) -> LLM:
    s = get_settings()
    if not s.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    client = AsyncOpenAI(
        api_key=s.openrouter_api_key, base_url=s.openrouter_base_url, max_retries=2
    )
    return LLM(client=client, model=model, provider="openrouter", default_temperature=0)


async def _verdicts(
    llm: LLM, runs: list[dict], findings: list[dict], names: dict[str, str]
) -> dict[tuple[int, str], dict]:
    """(run, finding id) -> {"found", "reason"} for every pair."""
    sem = asyncio.Semaphore(6)

    async def one(run: dict, finding: dict) -> tuple[tuple[int, str], dict]:
        async with sem:
            score = await judge_recall(
                finding,
                run["answer"],
                names,
                judge_fn=lambda system, user: _judge_with_llm(llm, system, user),
            )
        return (run["run"], finding["id"]), {
            "found": bool(score.value),
            "reason": score.comment,
        }

    pairs = await asyncio.gather(*(one(r, f) for r in runs for f in findings))
    return dict(pairs)


def _verdict(v: dict) -> str:
    return "found" if v["found"] else "not found"


def cross(run_path: Path, models: list[str]) -> Path:
    runs = json.loads(run_path.read_text())
    manifest = json.loads((FIXTURES / "scenarios.json").read_text())
    real = manifest["scenarios"]
    id_map = json.loads((FIXTURES / "id_map.json").read_text())
    fakes = decoys(real, id_map["chw_wards"])
    names = patient_names(
        FIXTURES / "localized", {p for s in real for p in s.get("patient_ids", [])}
    )
    is_real = {s["id"]: True for s in real} | {d["id"]: False for d in fakes}

    own = get_llm()
    judges: dict[str, dict[tuple[int, str], dict]] = {}
    # The project's judge already graded the real findings in the eval run.
    own_label = f"{own.model} (project judge)"
    judges[own_label] = {
        (r["run"], sid): {"found": v["judged"], "reason": v["judge_reason"]}
        for r in runs
        for sid, v in r["scenarios"].items()
    } | asyncio.run(_verdicts(own, runs, fakes, names))
    for model in models:
        print(f"judging with {model}…")
        judges[model] = asyncio.run(
            _verdicts(_openrouter(model), runs, real + fakes, names)
        )

    keys = sorted(judges[own_label])
    lines = [
        f"# Recall judge cross-check — {datetime.now(tz=UTC):%Y-%m-%d}",
        "",
        f"The {len(runs)} briefings from `{run_path.name}`, each graded against the "
        f"{len(real)} planted findings and {len(fakes)} decoys (false findings that "
        "change the CHW, ward, count or reading the finding depends on). A judge "
        "worth trusting says *found* to the real findings and *not found* to the "
        "decoys. Every judge got the same prompt.",
        "",
        "| Judge | Real findings found | Decoys rejected "
        "| Agrees with project judge | Cohen's kappa |",
        "|---|---|---|---|---|",
    ]
    for label, verdicts in judges.items():
        real_found = sum(verdicts[k]["found"] for k in keys if is_real[k[1]])
        decoys_rejected = sum(
            not verdicts[k]["found"] for k in keys if not is_real[k[1]]
        )
        a = agreement(
            [(judges[own_label][k]["found"], verdicts[k]["found"]) for k in keys]
        )
        kappa = "—" if a.kappa is None else f"{a.kappa:.2f}"
        lines.append(
            f"| `{label}` | {real_found}/{len(runs) * len(real)} "
            f"| {decoys_rejected}/{len(runs) * len(fakes)} "
            f"| {a.agree}/{a.n} | {kappa} |"
        )
    lines += [
        "",
        "## Where the judges disagree",
        "",
    ]
    disagreements = [
        f"- Run {run}, {'decoy' if not is_real[fid] else 'finding'} `{fid}`: "
        + "; ".join(
            f"{label.split(' ')[0]} said {_verdict(v[(run, fid)])}"
            f" ({v[(run, fid)]['reason']})"
            for label, v in judges.items()
        )
        for run, fid in keys
        if len({v[(run, fid)]["found"] for v in judges.values()}) > 1
    ]
    lines += disagreements or [
        "None: every judge reached the same verdict on every item."
    ]
    lines += [
        "",
        "## What this shows, and what it does not",
        "",
        "- Agreement across model families means the recall score is not one model "
        "grading its own work generously, and the decoys show the judges do not "
        "simply say *found* to anything.",
        "- It is not a human check. Models can share blind spots, and nobody with "
        "community-health experience has rated these briefings.",
        "- The decoys are built from the planted findings, so they test whether a "
        "judge checks the specific detail, not every way a briefing could be wrong.",
        "",
    ]
    stem = f"{datetime.now(tz=UTC):%Y-%m-%d}-judge-agreement"
    out = run_path.with_name(f"{stem}.md")
    out.write_text("\n".join(lines))
    run_path.with_name(f"{stem}.json").write_text(
        json.dumps(
            {
                "run": run_path.name,
                "decoys": fakes,
                "verdicts": {
                    label: {f"{r}:{fid}": v for (r, fid), v in verdicts.items()}
                    for label, verdicts in judges.items()
                },
            },
            indent=2,
        )
    )
    print("\n".join(lines))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export").add_argument("run_json", type=Path)
    sub.add_parser("score").add_argument("ratings_csv", type=Path)
    c = sub.add_parser("cross")
    c.add_argument("run_json", type=Path)
    c.add_argument(
        "--model", action="append", default=[], help="OpenRouter model id (repeatable)"
    )
    args = p.parse_args()
    if args.cmd == "cross":
        print(f"Written to {cross(args.run_json, args.model)}")
    elif args.cmd == "export":
        print(f"Rating sheet written to {export(args.run_json)}")
    else:
        print(f"Written to {score(args.ratings_csv)}")


if __name__ == "__main__":
    main()
