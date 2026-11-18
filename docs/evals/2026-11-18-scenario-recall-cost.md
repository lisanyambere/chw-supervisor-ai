# Scenario recall — 2026-11-18

- Question: “Give me the Monday-morning briefing for the team.”
- Runs: 5, model `gpt-5.5` (azure); the judge is the same model
- Data: synthetic, demo week starting 2026-11-09, 7 planted scenarios

| Scenario | Judged found | Named in answer | Named on card |
|---|---|---|---|
| A CHW stopped visiting mid-week | 5/5 | 5/5 | 5/5 |
| A CHW with only two days of history | 5/5 | 5/5 | 5/5 |
| Fever cluster in one ward | 5/5 | 5/5 | 5/5 |
| Pregnant patients overdue for follow-up | 5/5 | 5/5 | 5/5 |
| Visits with no location recorded | 5/5 | 5/5 | 5/5 |
| Visits logged for deceased patients | 5/5 | 5/5 | 5/5 |
| Child under five with danger signs | 5/5 | 5/5 | 5/5 |
| **All scenarios** | **35/35** | **35/35** | **35/35** |

## Flags outside the planted set

- Problems raised per briefing: 7.6 on average
- Matching a planted scenario: 35 of 38
- The rest are listed under *Unplanted flags* below. Each is either a real feature of the generated data that nobody planted or a false alarm; the grounding check shows its figures came from the data, so telling the two apart takes a human read.

## Grounding and cost

- Answers that passed the grounding check: 5/5 (0 needed a rewrite first)
- Figures checked per answer: 81 on average
- Answer cards with a number not found in any tool result: 0/5
- Time per briefing: 23s on average (min 21s, max 24s)
- Per briefing: 9.0 LLM calls (including the answer card), 7.0 tool calls, 11,116 input and 5,723 output tokens
- Estimated cost per briefing: $0.227 (min $0.202, max $0.264) at $5 / $30 per million input / output tokens
- This evaluation: $1.14 for the briefings and $0.50 for the judges

## What this measures, and what it does not

- **Judged found** is recall against planted ground truth: the judge is told the finding and asked whether the briefing conveys it.
- **Flags outside the planted set** bound the false alarms from above: a flag matching no planted scenario may still be true of the data.
- **Named** columns are a deterministic lower bar (the right ids, wards and patient names appear). They can pass when the briefing names the right person for the wrong reason, which is why the judge is the headline.
- The judge is the same model that wrote the briefing. It has not yet been checked against human ratings (see scripts/calibrate_judge.py).
- The grounding check proves a figure appears in some tool result, not that it is attached to the right entity.
- The data is synthetic and the scenarios were planted by the same project that built the tools, so this shows the pipeline works end to end, not how it would do on real programme data.

## Misses

None.

## Unplanted flags

- Check workload balance based on uneven team encounter counts
- Check workload balance for CHWs with highest 30-day encounter totals
- Mumias East fever case has malaria diagnosis not recorded; confirm malaria testing/treatment
