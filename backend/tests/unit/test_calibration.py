"""Judge-vs-human agreement and the false-alarm audit."""
from __future__ import annotations

from typing import Any

import pytest

from app.evaluators.calibration import agreement
from app.evaluators.recall import judge_flags


def test_perfect_agreement_has_kappa_one() -> None:
    a = agreement([(True, True), (False, False), (True, True)])
    assert (a.n, a.agree, a.rate, a.kappa) == (3, 3, 1.0, 1.0)


def test_kappa_discounts_agreement_expected_by_chance() -> None:
    # 9 of 10 agree, but both raters say "found" almost every time.
    pairs = [(True, True)] * 9 + [(True, False)]
    a = agreement(pairs)
    assert a.rate == 0.9
    assert a.kappa == pytest.approx(0.0)
    assert (a.judge_only, a.human_only) == (1, 0)


def test_kappa_is_undefined_when_both_always_say_yes() -> None:
    assert agreement([(True, True), (True, True)]).kappa is None


async def test_flags_keep_only_known_finding_ids() -> None:
    async def judge(system: str, user: str) -> dict[str, Any]:
        assert "fever_cluster:" in user
        return {
            "flags": [
                {"flag": "8 fevers in Lurambi", "finding": "fever_cluster"},
                {"flag": "chw-010 below mean", "finding": None},
                {"flag": "made-up id", "finding": "not_a_scenario"},
            ]
        }

    scenarios = [{"id": "fever_cluster", "expect": "8 fevers"}]
    flags = await judge_flags("briefing", scenarios, judge_fn=judge)

    assert [f["finding"] for f in flags] == ["fever_cluster", None, None]


async def test_flags_judge_must_return_a_list() -> None:
    async def judge(system: str, user: str) -> dict[str, Any]:
        return {"oops": True}

    with pytest.raises(ValueError):
        await judge_flags("briefing", [], judge_fn=judge)
