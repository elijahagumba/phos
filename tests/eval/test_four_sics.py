"""ADR 0177: the third 4SICS day stays closed, and alerts per hour use the clock."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.eval.four_sics import (
    LEARN_FILE,
    SCORE_FILE,
    FourSicsError,
    alerts_per_hour,
    refuse_held_back,
)


def test_the_held_back_day_is_refused_and_the_split_is_the_first_two() -> None:
    refuse_held_back(LEARN_FILE)
    refuse_held_back(SCORE_FILE)
    with pytest.raises(FourSicsError, match="held back"):
        refuse_held_back("4SICS-GeekLounge-151022.pcap")
    assert LEARN_FILE.endswith("151020.pcap")
    assert SCORE_FILE.endswith("151021.pcap")


def test_alerts_per_hour_is_findings_over_the_span() -> None:
    start = datetime(2015, 10, 21, tzinfo=UTC)
    assert alerts_per_hour(4, start, start + timedelta(hours=2)) == 2.0
    assert alerts_per_hour(4, start, start) is None
