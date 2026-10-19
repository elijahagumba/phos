"""Depth counting: one loud count can outscore many quiet ones."""

from datetime import UTC, datetime

from phos.sentiel.day_facts import DayFacts
from phos.sentiel.depth import COUNT_SCALE, CountDepth, breadth_and_depth


def _day(user: str, logons: int, day: int = 1) -> DayFacts:
    return DayFacts(
        user_id=user,
        day=datetime(2010, 1, day, tzinfo=UTC),
        role="Sales",
        logons=logons,
    )


def test_one_loud_signal_beats_many_capped_terms() -> None:
    breadth, depth, combined = breadth_and_depth((1.0, 1.0, 1.0, 1.0, 14.0))
    assert depth == 14.0 / COUNT_SCALE
    assert breadth < 5.0
    assert combined == depth


def test_quiet_history_is_not_anomalous() -> None:
    train = [_day("U", 1, day=index + 1) for index in range(8)]
    model = CountDepth.fit(train)
    assert model.score(_day("U", 1, day=20)) == 0.0
    assert model.score(_day("NEW", 40, day=20)) == 0.0


def test_a_jump_on_one_count_is_depth() -> None:
    train = [_day("U", 1, day=index + 1) for index in range(10)]
    model = CountDepth.fit(train)
    loud = model.score(_day("U", 20, day=20))
    assert loud > 1.0
