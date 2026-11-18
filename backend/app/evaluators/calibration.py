"""Agreement between the recall judge and a human rater.

The judge's verdicts are only worth reporting if they match what a person
would say. `agreement` compares paired binary verdicts and reports raw
agreement and Cohen's kappa, which discounts the agreement two raters would
reach by chance given how often each says "yes".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Agreement:
    n: int
    agree: int
    kappa: float | None  # None when chance agreement is total (kappa undefined)
    judge_only: int  # judge said found, human said not
    human_only: int  # human said found, judge said not

    @property
    def rate(self) -> float:
        return self.agree / self.n if self.n else 0.0


def agreement(pairs: list[tuple[bool, bool]]) -> Agreement:
    """`pairs` is [(judge_found, human_found), ...]."""
    n = len(pairs)
    agree = sum(j == h for j, h in pairs)
    judge_only = sum(j and not h for j, h in pairs)
    human_only = sum(h and not j for j, h in pairs)
    if n == 0:
        return Agreement(0, 0, None, 0, 0)
    p_judge = sum(j for j, _ in pairs) / n
    p_human = sum(h for _, h in pairs) / n
    expected = p_judge * p_human + (1 - p_judge) * (1 - p_human)
    observed = agree / n
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return Agreement(n, agree, kappa, judge_only, human_only)
