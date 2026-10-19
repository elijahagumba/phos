"""Bet 001's ranking is fixed before any labelled CERT score."""

from datetime import UTC, datetime

import pytest

from phos.sentiel.bet001 import (
    BUDGET,
    DayScore,
    chance_malicious_days,
    insiders_in_budget,
    rank_days,
    top_budget,
)

_DAY = datetime(2010, 7, 1, tzinfo=UTC)


def _day(user: str, score: float, *, malicious: bool = False, hour: int = 0) -> DayScore:
    return DayScore(
        user_id=user,
        day=_DAY.replace(hour=hour),
        score=score,
        malicious=malicious,
    )


def test_budget_is_the_published_48() -> None:
    assert BUDGET == 48


def test_rank_ignores_the_malicious_flag() -> None:
    quiet = _day("ZZZ", 1.0, malicious=False)
    loud = _day("AAA", 1.0, malicious=True)
    ranked = rank_days((quiet, loud))
    assert [item.user_id for item in ranked] == ["AAA", "ZZZ"]


def test_tie_break_is_user_then_time_and_does_not_widen_the_budget() -> None:
    days = (
        _day("MNO", 5.0, malicious=True, hour=2),
        _day("ABC", 5.0, malicious=False, hour=1),
        _day("ABC", 5.0, malicious=True, hour=3),
        _day("ZZZ", 9.0, malicious=True),
    )
    taken = top_budget(days, budget=2)
    assert [item.user_id for item in taken] == ["ZZZ", "ABC"]
    assert insiders_in_budget(days, budget=2) == frozenset({"ZZZ"})


def test_a_benign_day_does_not_count_as_finding_the_insider() -> None:
    days = (
        _day("INS", 10.0, malicious=False),
        _day("OTH", 1.0, malicious=True),
    )
    assert insiders_in_budget(days, budget=1) == frozenset()


def test_chance_is_the_hypergeometric_expectation() -> None:
    assert chance_malicious_days(100, 10, budget=48) == pytest.approx(4.8)


def test_chance_refuses_an_impossible_count() -> None:
    with pytest.raises(ValueError):
        chance_malicious_days(10, 11, budget=4)
