# Briefing traces — eval-and-demo

Exported from Langfuse on 2026-11-18: every briefing trace that started between 2026-11-18T05:06:44Z and 2026-11-18T05:30:00Z. Cost is Langfuse's, from its own model price table.

- Briefings: 7
- Agent time (router to verified answer, before the answer card is formatted): 23.5s median, 30.5s slowest
- Per briefing: 9.0 model calls, 7.1 tool calls, 11,342 input and 6,086 output tokens
- Cost per briefing: $0.239 on average ($0.202–$0.289); $1.68 in total

| Trace | Started (UTC) | Agent seconds | Model calls | Tool calls | Tokens in / out | Cost |
|---|---|---|---|---|---|---|
| `786a5688` | 05:06:45 | 22.9 | 9 | 7 | 11,268 / 6,911 | $0.264 |
| `95de4a13` | 05:07:53 | 20.7 | 9 | 7 | 10,908 / 4,914 | $0.202 |
| `07b9b8da` | 05:08:14 | 25.4 | 9 | 7 | 11,843 / 6,336 | $0.249 |
| `1a85e225` | 05:08:41 | 22.1 | 9 | 7 | 11,049 / 5,907 | $0.233 |
| `601eb379` | 05:09:01 | 30.5 | 9 | 8 | 11,968 / 7,653 | $0.289 |
| `73c88962` | 05:09:40 | 23.7 | 9 | 7 | 11,076 / 5,641 | $0.225 |
| `0f859946` | 05:10:35 | 23.5 | 9 | 7 | 11,281 / 5,240 | $0.214 |

## One trace, span by span (`07b9b8da`)

Langfuse: https://us.cloud.langfuse.com/project/cmsqgs40101crad0dn7qvoxbi/traces/07b9b8daa51bb6461105d791ef3e6cd2 (public: opens without a login)

- `agent.run_briefing` (agent, 25.4s)
  - `llm.router` (generation, 3.1s, 142 in / 89 out, $0.0034)
  - `agent.clinical` (agent, 11.4s)
    - `llm.clinical.iter1` (generation, 2.1s, 978 in / 137 out, $0.0090)
    - `tool.fever_cases_by_ward` (tool, 0.8s)
    - `tool.child_danger_signs` (tool, 0.2s)
    - `tool.overdue_followups` (tool, 0.3s)
    - `llm.clinical.iter2` (generation, 8.5s, 2,306 in / 921 out, $0.0392)
  - `agent.quality` (agent, 9.3s)
    - `llm.quality.iter1` (generation, 2.2s, 516 in / 111 out, $0.0059)
    - `tool.visits_after_death` (tool, 1.1s)
    - `tool.visits_missing_location` (tool, 1.4s)
    - `llm.quality.iter2` (generation, 5.7s, 1,512 in / 709 out, $0.0288)
  - `agent.team` (agent, 11.3s)
    - `llm.team.iter1` (generation, 2.4s, 1,143 in / 86 out, $0.0083)
    - `tool.team_activity_summary` (tool, 1.0s)
    - `tool.chw_activity_gaps` (tool, 2.1s)
    - `llm.team.iter2` (generation, 6.8s, 1,939 in / 581 out, $0.0271)
  - `llm.synthesize` (generation, 10.9s, 1,772 in / 1,295 out, $0.0477)
- `llm.format` (generation, 18.1s, 1,535 in / 2,407 out, $0.0799)
