"""Role-hour peers stay silent for unknown roles and small buckets."""

from datetime import UTC, datetime

from phos.sentiel.day_facts import DayFacts
from phos.sentiel.role_hours import RoleHourPeers


def _day(user: str, role: str, connects: int, day: int, weekday: int = 0) -> DayFacts:
    # 2010-01-04 is a Monday.
    return DayFacts(
        user_id=user,
        day=datetime(2010, 1, 4 + day, tzinfo=UTC),
        role=role,
        removable_connects=connects,
    )


def test_unknown_role_and_thin_bucket_are_silent() -> None:
    train = [_day(f"P{index}", "Sales", 1, index) for index in range(8)]
    model = RoleHourPeers.fit(train)
    assert model.score(_day("X", "unknown", 40, 20)) == 0.0
    thin = RoleHourPeers.fit([_day("P0", "Sales", 1, 0)])
    assert thin.score(_day("P1", "Sales", 40, 1)) == 0.0


def test_excess_over_role_peers_in_the_same_hours_speaks() -> None:
    train = [_day(f"P{index}", "Sales", 1, index) for index in range(10)]
    model = RoleHourPeers.fit(train)
    assert model.score(_day("X", "Sales", 20, 7)) > 0.0
    assert model.score(_day("X", "Sales", 1, 8)) == 0.0
