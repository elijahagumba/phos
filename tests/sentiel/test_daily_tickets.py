"""Hand fixtures for the 48-a-day rule. No CERT file is read."""

from datetime import UTC, date, datetime

import pytest

from phos.sentiel.bet001 import DayScore
from phos.sentiel.daily_tickets import (
    alerts_per_day,
    draw_and_people,
    draw_size,
    expected_distinct_insiders,
    s3_met,
    surfaced_user_ids,
)


def _day(user: str, score: float, day: int, hour: int = 0, *, malicious: bool = False) -> DayScore:
    return DayScore(
        user_id=user,
        day=datetime(2010, 7, day, hour, tzinfo=UTC),
        score=score,
        malicious=malicious,
    )


def test_each_calendar_day_has_its_own_budget_and_zeros_are_not_alerts() -> None:
    alerts = alerts_per_day(
        (
            _day("A", 2.0, 1, malicious=True),
            _day("B", 0.0, 1),
            _day("C", 1.0, 1),
            _day("D", 5.0, 2, malicious=True),
        ),
        budget=1,
    )
    assert [(item.user_id, item.day.day) for item in alerts] == [("A", 1), ("D", 2)]
    assert surfaced_user_ids(alerts) == ("A", "D")


def test_ties_break_on_user_id_then_timestamp() -> None:
    alerts = alerts_per_day(
        (
            _day("B", 3.0, 1, hour=2),
            _day("A", 3.0, 1, hour=9),
            _day("A", 3.0, 1, hour=1),
        ),
        budget=2,
    )
    assert [(item.user_id, item.day.hour) for item in alerts] == [("A", 1), ("A", 9)]


def test_a_benign_day_of_a_labelled_user_does_not_surface_them() -> None:
    alerts = alerts_per_day((_day("A", 4.0, 1, malicious=False),), budget=48)
    assert surfaced_user_ids(alerts) == ()


def test_draw_size_is_the_smaller_of_the_budget_and_the_day() -> None:
    assert draw_size(100, 48) == 48
    assert draw_size(10, 48) == 10


def test_presence_ignores_score_and_malicious() -> None:
    days = (
        _day("A", 9.0, 1, malicious=True),
        _day("B", 0.0, 1),
        _day("A", 1.0, 2),
    )
    flipped = (
        _day("A", 0.0, 1),
        _day("B", 9.0, 1, malicious=True),
        _day("A", 0.0, 2, malicious=True),
    )
    assert draw_and_people(days, budget=48) == draw_and_people(flipped, budget=48)
    n_draw, n_people = draw_and_people(days, budget=48)
    assert n_draw[date(2010, 7, 1)] == 2
    assert n_people[date(2010, 7, 1)] == 2
    assert n_draw[date(2010, 7, 2)] == 1


def test_expected_distinct_insiders_is_the_sum_product() -> None:
    # One insider, two days, draw 1 of 2 then 1 of 4: 1 - (1-0.5)*(1-0.25) = 0.625
    # Second insider, one day, draw 1 of 4: 0.25. Total 0.875.
    value = expected_distinct_insiders(
        {"ONE": (date(2010, 7, 1), date(2010, 7, 2)), "TWO": (date(2010, 7, 2),)},
        {date(2010, 7, 1): 1, date(2010, 7, 2): 1},
        {date(2010, 7, 1): 2, date(2010, 7, 2): 4},
    )
    assert value == pytest.approx(0.875)


def test_an_insider_with_no_malicious_day_contributes_zero() -> None:
    assert expected_distinct_insiders({"NONE": ()}, {}, {}) == 0.0


def test_a_draw_larger_than_the_people_present_is_refused() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        expected_distinct_insiders(
            {"ONE": (date(2010, 7, 1),)},
            {date(2010, 7, 1): 3},
            {date(2010, 7, 1): 2},
        )


def test_s3_requires_a_strict_increase() -> None:
    assert s3_met(3, 2) is True
    assert s3_met(2, 2) is False
    assert s3_met(1, 2) is False


def test_a_non_positive_budget_is_refused() -> None:
    with pytest.raises(ValueError, match="budget"):
        alerts_per_day((_day("A", 1.0, 1),), budget=0)
