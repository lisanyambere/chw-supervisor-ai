# Scenario recall — 2026-11-17

- Question: “Give me the Monday-morning briefing for the team.”
- Runs: 5, model `gpt-5.5` (azure); the judge is the same model
- Data: synthetic, demo week starting 2026-11-09, 7 planted scenarios

| Scenario | Judged found | Named in answer | Named on card |
|---|---|---|---|
| A CHW stopped visiting mid-week | 5/5 | 5/5 | 5/5 |
| A CHW with only two days of history | 5/5 | 5/5 | 3/5 |
| Fever cluster in one ward | 5/5 | 5/5 | 5/5 |
| Pregnant patients overdue for follow-up | 5/5 | 5/5 | 5/5 |
| Visits with no location recorded | 1/5 | 5/5 | 5/5 |
| Visits logged for deceased patients | 5/5 | 5/5 | 5/5 |
| Child under five with danger signs | 5/5 | 5/5 | 5/5 |
| **All scenarios** | **31/35** | **35/35** | **33/35** |

## Grounding and cost

- Answers that passed the grounding check: 5/5 (0 needed a rewrite first)
- Figures checked per answer: 75 on average
- Answer cards with a number not found in any tool result: 0/5
- Time per briefing: 28s on average (min 22s, max 38s)
- Per briefing: 8.0 LLM calls, 7.0 tool calls

## What this measures, and what it does not

- **Judged found** is recall against planted ground truth: the judge is told the finding and asked whether the briefing conveys it. It does not measure false alarms — a briefing that also reports things that are not there is not penalised here.
- **Named** columns are a deterministic lower bar (the right ids, wards and patient names appear). They can pass when the briefing names the right person for the wrong reason, which is why the judge is the headline.
- The judge is the same model that wrote the briefing and has not been calibrated against human ratings.
- The grounding check proves a figure appears in some tool result, not that it is attached to the right entity.
- The data is synthetic and the scenarios were planted by the same project that built the tools, so this shows the pipeline works end to end, not how it would do on real programme data.

## Misses

- Run 1, Visits with no location recorded: It reports 14 missing-location visits but does not state they occurred in the latest week.
- Run 2, Visits with no location recorded: The briefing reports 14 missing-location visits but not that they occurred in the latest week.
- Run 4, Visits with no location recorded: The briefing reports 14 missing-location visits but does not state that they occurred in the latest week.
- Run 5, Visits with no location recorded: The briefing reports 14 missing-location visits for the last 30 days, not the latest week.
