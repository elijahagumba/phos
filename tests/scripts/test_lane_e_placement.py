"""ADR 0398: the harness reports all four bars, and judges them without flattering either engine."""

from __future__ import annotations

import pytest
from scripts.lane_e_placement import (
    BARS,
    Outcome,
    Reading,
    _median,
    judges,
    summarise,
)


def _outcome(
    kind: str,
    label: str = "attack",
    frozen: float | None = None,
    lane3: float | None = None,
    placed: float | None = None,
) -> Outcome:
    return Outcome(
        run="mixed2-96211",
        kind=kind,
        label=label,
        frozen_delay=frozen,
        lane3_delay=lane3,
        placed_delay=placed,
    )


def test_the_four_bars_are_the_ones_the_declaration_froze() -> None:
    """ADR 0398 repeats ADR 0397's four halves; the harness cannot invent a fifth."""
    assert BARS.floor_catches == 32
    assert BARS.ceiling_benign == 5
    assert BARS.ceiling_paired_delay == 1.0
    assert BARS.total_attacks == 70
    assert BARS.total_benign == 20


def test_an_event_is_caught_only_by_an_alert_inside_its_window() -> None:
    """The delay is the alert's offset from the window's start, and a miss is a miss."""
    reading = summarise(
        (
            _outcome("replay", frozen=0.0, lane3=0.0, placed=0.0),
            _outcome("replay", frozen=8.0, lane3=8.0, placed=8.0),
            _outcome("recon", frozen=None, lane3=None, placed=None),
        )
    )
    assert reading.frozen_caught == 2
    assert reading.placed_caught == 2
    assert reading.paired_n == 2
    assert reading.paired_frozen == 4.0
    assert reading.paired_placed == 4.0


def test_losing_one_attack_the_frozen_engine_catches_shrinks_the_paired_set() -> None:
    """The paired set is the intersection, so a lost catch is visible as a smaller n."""
    reading = summarise(
        (
            _outcome("replay", frozen=0.0, lane3=0.0, placed=5.0),
            _outcome("replay", frozen=2.0, lane3=2.0, placed=None),
        )
    )
    assert reading.frozen_caught == 2
    assert reading.placed_caught == 1
    assert reading.paired_n == 1
    assert reading.paired_placed == 5.0


def test_the_own_set_median_reads_each_engine_over_what_it_caught_itself() -> None:
    """The second definition: an engine is judged over its own caught set, not the shared one."""
    reading = summarise(
        (
            _outcome("replay", frozen=1.0, lane3=1.0, placed=1.0),
            _outcome("liar_freeze", frozen=None, lane3=900.0, placed=900.0),
        )
    )
    assert reading.own_frozen == 1.0
    assert reading.own_placed == 450.5
    assert reading.paired_n == 1


def test_a_tie_on_catches_is_not_a_pass() -> None:
    """Bar one is strictly more than the frozen count, so 32 catches against 32 fails."""
    reading = summarise(
        tuple(_outcome("replay", frozen=1.0, lane3=1.0, placed=1.0) for _ in range(32))
    )
    verdict = judges(reading)
    assert reading.placed_caught == 32
    assert verdict.strictly_more is False
    assert verdict.kept is False


def test_more_catches_with_later_delay_is_still_a_refusal() -> None:
    """Bars hold together. Buying catches with delay fails, which is the ADR 0286 shape."""
    outcomes = [_outcome("replay", frozen=1.0, lane3=1.0, placed=5.0) for _ in range(32)]
    outcomes += [_outcome("liar_freeze", frozen=None, lane3=None, placed=3.0) for _ in range(21)]
    reading = summarise(tuple(outcomes))
    verdict = judges(reading)
    assert reading.placed_caught == 53
    assert verdict.strictly_more is True
    assert verdict.paired_delay_ok is False
    assert verdict.kept is False


def test_buying_catches_with_benign_alerts_is_still_a_refusal() -> None:
    """Bar four is a ceiling, not a trade."""
    outcomes = [_outcome("replay", frozen=1.0, lane3=1.0, placed=1.0) for _ in range(32)]
    outcomes += [_outcome("liar_freeze", frozen=None, lane3=None, placed=1.0) for _ in range(21)]
    benign = [_outcome("maintenance", "benign", None, None, 4.0) for _ in range(8)]
    reading = summarise(tuple(outcomes + benign))
    verdict = judges(reading)
    assert reading.placed_benign == 8
    assert verdict.benign_ok is False
    assert verdict.kept is False


def test_a_partial_win_is_reported_as_a_refusal_with_every_half_beside_it() -> None:
    """No half is hidden because another failed. The verdict names each one."""
    outcomes = [_outcome("replay", frozen=1.0, lane3=1.0, placed=0.0) for _ in range(40)]
    reading = summarise(tuple(outcomes))
    verdict = judges(reading)
    assert verdict.strictly_more is True
    assert verdict.nothing_lost is True
    assert verdict.paired_delay_ok is True
    assert verdict.own_delay_ok is True
    assert verdict.benign_ok is True
    assert verdict.kept is True


def test_an_engine_that_catches_nothing_has_no_median_and_cannot_pass() -> None:
    """An empty set has no median. It is reported as none, and the bar is not met."""
    reading = summarise((_outcome("recon", frozen=None, lane3=None, placed=None),))
    assert reading.paired_placed is None
    verdict = judges(reading)
    assert verdict.paired_delay_ok is False
    assert verdict.kept is False


def test_the_median_of_an_even_set_is_the_midpoint() -> None:
    """`statistics.median` semantics, so the number is comparable with the earlier reports."""
    assert _median([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)
    assert _median([]) is None


def test_each_class_is_reported_separately() -> None:
    """The per-class tally is the point of the report, so the summary keeps it."""
    reading = summarise(
        (
            _outcome("replay", frozen=0.0, lane3=0.0, placed=0.0),
            _outcome("replay", frozen=None, lane3=5.0, placed=2.0),
            _outcome("creep_many", frozen=93.0, lane3=71.0, placed=71.0),
        )
    )
    assert isinstance(reading, Reading)
    assert reading.by_class[("attack", "replay")].frozen == 1
    assert reading.by_class[("attack", "replay")].lane3 == 2
    assert reading.by_class[("attack", "replay")].placed == 2
    assert reading.by_class[("attack", "creep_many")].frozen == 1
