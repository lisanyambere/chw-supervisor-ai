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
