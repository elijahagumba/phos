"""New rare links speak; shared or already-seen names do not."""

from datetime import UTC, datetime

from phos.sentiel.day_facts import DayFacts
from phos.sentiel.peer_links import PeerLinkRarity


def _day(user: str, hosts: tuple[str, ...], day: int = 1, role: str = "Sales") -> DayFacts:
    return DayFacts(
        user_id=user,
        day=datetime(2010, 1, day, tzinfo=UTC),
        role=role,
        hosts=hosts,
    )


def test_a_new_rare_host_outscores_a_host_the_role_already_uses() -> None:
    train = [
        _day("A", ("shared.example",), 1),
        _day("B", ("shared.example",), 1),
        _day("C", ("shared.example",), 1),
    ]
    model = PeerLinkRarity.fit(train)
    rare = model.score(_day("A", ("only-me.example",), 10))
    common = model.score(_day("A", ("shared.example",), 10))
    assert rare > 0.0
    assert common == 0.0


def test_no_role_peers_is_silent() -> None:
    train = [_day("A", ("x.example",), 1, role="Lonely")]
    model = PeerLinkRarity.fit(train)
    assert model.score(_day("A", ("new.example",), 10, role="Lonely")) == 0.0
    assert model.score(_day("A", ("new.example",), 10, role="unknown")) == 0.0
