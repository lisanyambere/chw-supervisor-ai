"""Scenario recall: did a briefing surface what was planted in the data?

The data generator writes `data/fixtures/scenarios.json`, one entry per
planted scenario with a plain-language `expect` and the ids involved. That
file is the ground truth. Two checks run against it:

- `mentions` is deterministic. It asks only whether the briefing names the
  things it would have to name (the CHW id, the ward, the patients). It can
  pass on a briefing that names the right CHW for the wrong reason.
- `judge_recall` asks an LLM whether the briefing conveys the finding
  itself. It is the stricter of the two and the one reported as recall.
"""
from __future__ import annotations

import json
from typing import Any

from app.evaluators.judge import JudgeFn, _default_judge_fn
from app.evaluators.scorers import EvalScore

Scenario = dict[str, Any]

# Words that show the briefing is talking about the right kind of problem.
_TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "fever_cluster": ("fever", "febrile", "malaria"),
    "overdue_anc": ("overdue", "missed", "follow-up", "return"),
    "missing_location": ("location",),
    "visits_after_death": ("deceased", "death", "died", "dead"),
    "child_danger_signs": ("breath", "respir", "danger"),
}


def mentions(
    scenario: Scenario, text: str, patient_names: dict[str, str]
) -> bool:
    """True when `text` names everything the scenario is about.

    `patient_names` maps the manifest's patient ids to full names.
    """
    haystack = text.lower()
    sid = scenario["id"]

    required: list[str] = []
    if sid in ("chw_disengagement", "baseline_trap"):
        required += scenario["chw_ids"]
    if sid == "fever_cluster":
        required.append(scenario["ward"])
    if sid in ("overdue_anc", "child_danger_signs"):
        required += [patient_names[p] for p in scenario["patient_ids"]]
    if sid == "missing_location":
        required.append(str(scenario["count"]))

    topic = _TOPIC_WORDS.get(sid)
    return all(r.lower() in haystack for r in required) and (
        topic is None or any(w in haystack for w in topic)
    )


_RECALL_SYSTEM = """\
You grade whether a briefing for a community health supervisor reports a
specific finding that is known to be true of the data.

Reply with one JSON object: {"score": 1 or 0, "reason": "<one short sentence>"}.

Score 1 only if the briefing states the finding clearly enough that the
supervisor would act on it, with the right people or places and no
contradiction of the facts given. Naming the right person for a different
reason scores 0. Missing or wrong details the finding depends on score 0.
"""


async def judge_recall(
    scenario: Scenario,
    briefing: str,
    patient_names: dict[str, str],
    *,
    judge_fn: JudgeFn | None = None,
) -> EvalScore:
    """1.0 if the briefing conveys the scenario's finding, else 0.0."""
    judge_fn = judge_fn or _default_judge_fn
    names = [patient_names[p] for p in scenario.get("patient_ids", [])]
    user = (
        f"FINDING ({scenario['title']}):\n{scenario['expect']}\n"
        + (f"Patients involved: {', '.join(names)}\n" if names else "")
        + f"\nBRIEFING:\n{briefing}"
    )
    payload = await judge_fn(_RECALL_SYSTEM, user)
    return EvalScore(
        f"recall_{scenario['id']}",
        1.0 if float(payload.get("score", 0.0)) >= 0.5 else 0.0,
        comment=str(payload.get("reason", "")),
    )


def flatten_answer_doc(doc: dict[str, Any]) -> str:
    """All text the supervisor sees on the answer card, as one string."""
    return json.dumps(doc, ensure_ascii=False)
