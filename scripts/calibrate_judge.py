"""Check the recall judge against a person's ratings.

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
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.evaluators.calibration import agreement  # noqa: E402

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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export").add_argument("run_json", type=Path)
    sub.add_parser("score").add_argument("ratings_csv", type=Path)
    args = p.parse_args()
    if args.cmd == "export":
        print(f"Rating sheet written to {export(args.run_json)}")
    else:
        print(f"Written to {score(args.ratings_csv)}")


if __name__ == "__main__":
    main()
