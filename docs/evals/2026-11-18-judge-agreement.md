# Recall judge cross-check — 2026-11-18

The 5 briefings from `2026-11-18-scenario-recall-cost.json`, each graded against the 7 planted findings and 5 decoys (false findings that change the CHW, ward, count or reading the finding depends on). A judge worth trusting says *found* to the real findings and *not found* to the decoys. Every judge got the same prompt.

| Judge | Real findings found | Decoys rejected | Agrees with project judge | Cohen's kappa |
|---|---|---|---|---|
| `gpt-5.5 (project judge)` | 35/35 | 25/25 | 60/60 | 1.00 |
| `anthropic/claude-haiku-5.5` | 35/35 | 25/25 | 60/60 | 1.00 |

## Where the judges disagree

None: every judge reached the same verdict on every item.

## What this shows, and what it does not

- Agreement across model families means the recall score is not one model grading its own work generously, and the decoys show the judges do not simply say *found* to anything.
- It is not a human check. Models can share blind spots, and nobody with community-health experience has rated these briefings.
- The decoys are built from the planted findings, so they test whether a judge checks the specific detail, not every way a briefing could be wrong.
