"""Scenario-recall checks."""

from __future__ import annotations

from typing import Any

from app.evaluators.recall import judge_recall, mentions

NAMES = {"p1": "Amina Masinde", "p2": "Nafula Kamau"}

BASE = {"title": "t", "expect": "e"}
DISENGAGED = {**BASE, "id": "chw_disengagement", "chw_ids": ["chw-001"]}
CLUSTER = {**BASE, "id": "fever_cluster", "ward": "Lurambi"}
OVERDUE = {**BASE, "id": "overdue_anc", "patient_ids": ["p1", "p2"]}
UNLOCATED = {**BASE, "id": "missing_location", "count": 14}


def test_chw_scenario_needs_the_chw_id() -> None:
    assert mentions(DISENGAGED, "chw-001 stopped on Wednesday.", NAMES)
    assert not mentions(DISENGAGED, "One CHW stopped on Wednesday.", NAMES)


def test_cluster_needs_the_ward_and_the_illness() -> None:
    assert mentions(CLUSTER, "8 fever cases in Lurambi this week.", NAMES)
    assert not mentions(CLUSTER, "Lurambi had 164 visits.", NAMES)
    assert not mentions(CLUSTER, "8 fever cases across the county.", NAMES)


def test_overdue_needs_every_patient_named() -> None:
    assert mentions(OVERDUE, "Overdue: Amina Masinde and Nafula Kamau.", NAMES)
    assert not mentions(OVERDUE, "Overdue: Amina Masinde.", NAMES)


def test_missing_location_needs_the_count() -> None:
    assert mentions(UNLOCATED, "14 visits have no location.", NAMES)
    assert not mentions(UNLOCATED, "Some visits have no location.", NAMES)


async def test_judge_recall_is_binary_and_sees_patient_names() -> None:
    seen: dict[str, str] = {}

    async def judge(system: str, user: str) -> dict[str, Any]:
        seen["user"] = user
        return {"score": 0.4, "reason": "names the patient but not the delay"}

    score = await judge_recall(OVERDUE, "briefing text", NAMES, judge_fn=judge)

    assert score.name == "recall_overdue_anc"
    assert score.value == 0.0
    assert "Amina Masinde, Nafula Kamau" in seen["user"]


MANIFEST = [
    {
        **BASE,
        "id": "chw_disengagement",
        "chw_ids": ["chw-001"],
        "expect": "chw-001 (Mary) logged visits on Monday and Tuesday of the week of "
        "9 Nov and none from Wednesday to Friday.",
    },
    {**BASE, "id": "baseline_trap", "chw_ids": ["chw-002"]},
    {**BASE, "id": "fever_cluster", "chw_ids": ["chw-003"], "ward": "Lurambi"},
    {**BASE, "id": "missing_location", "count": 14},
    {**BASE, "id": "visits_after_death", "count": 3, "chw_ids": ["chw-016"]},
    {**BASE, "id": "child_danger_signs", "chw_ids": ["chw-005"]},
]
WARDS = {
    "chw-001": "Lurambi",
    "chw-002": "Lurambi",
    "chw-003": "Lurambi",
    "chw-004": "Butere",
    "chw-005": "Mumias East",
    "chw-016": "Butere",
}


def test_decoys_change_the_detail_each_finding_depends_on() -> None:
    from app.evaluators.recall import decoys

    by_id = {d["id"]: d["expect"] for d in decoys(MANIFEST, WARDS)}

    # A CHW in no scenario, in the same week as the real disengagement.
    assert by_id["decoy_wrong_chw_quiet"].startswith("chw-004 logged visits")
    assert "the week of 9 Nov" in by_id["decoy_wrong_chw_quiet"]
    # Neither the cluster's ward nor the sick child's.
    assert "Butere ward" in by_id["decoy_wrong_ward_cluster"]
    assert by_id["decoy_wrong_location_count"].startswith("20 visits")
    assert by_id["decoy_wrong_death_count"].startswith("5 visits")


def test_judge_reply_in_a_code_fence_still_parses() -> None:
    from app.evaluators.judge import _parse_judge_payload

    fenced = '```json\n{"score": 1, "reason": "states it"}\n```'
    assert _parse_judge_payload(fenced) == (1.0, "states it")
    assert _parse_judge_payload("no json here")[0] == 0.0
