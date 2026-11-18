# Scenario recall — 2026-11-17

- Question: “Give me the Monday-morning briefing for the team.”
- Runs: 3, model `gpt-5.5` (azure); the judge is the same model
- Data: synthetic, demo week starting 2026-11-09, 7 planted scenarios

| Scenario | Judged found | Named in answer | Named on card |
|---|---|---|---|
| A CHW stopped visiting mid-week | 3/3 | 3/3 | 3/3 |
| A CHW with only two days of history | 2/3 | 2/3 | 2/3 |
| Fever cluster in one ward | 3/3 | 3/3 | 3/3 |
| Pregnant patients overdue for follow-up | 3/3 | 3/3 | 3/3 |
| Visits with no location recorded | 1/3 | 2/3 | 3/3 |
| Visits logged for deceased patients | 3/3 | 3/3 | 3/3 |
| Child under five with danger signs | 3/3 | 3/3 | 3/3 |
| **All scenarios** | **18/21** | **19/21** | **20/21** |

## Grounding and cost

- Answers that passed the grounding check: 3/3 (0 needed a rewrite first)
- Figures checked per answer: 40 on average
- Answer cards with a number not found in any tool result: 0/3
- Time per briefing: 25s on average (min 18s, max 34s)
- Per briefing: 8.0 LLM calls, 7.0 tool calls

## What this measures, and what it does not

- **Judged found** is recall against planted ground truth: the judge is told the finding and asked whether the briefing conveys it. It does not measure false alarms — a briefing that also reports things that are not there is not penalised here.
- **Named** columns are a deterministic lower bar (the right ids, wards and patient names appear). They can pass when the briefing names the right person for the wrong reason, which is why the judge is the headline.
- The judge is the same model that wrote the briefing and has not been calibrated against human ratings.
- The grounding check proves a figure appears in some tool result, not that it is attached to the right entity.
- The data is synthetic and the scenarios were planted by the same project that built the tools, so this shows the pipeline works end to end, not how it would do on real programme data.

## Misses

- Run 2, A CHW with only two days of history: The briefing does not mention chw-002 John Otieno or explain that his low total is due to only two days of history.
- Run 2, Visits with no location recorded: It reports 14 missing-location visits but does not state they occurred in the latest week.
- Run 3, Visits with no location recorded: The briefing does not mention the 14 latest-week visits saved without a location.
