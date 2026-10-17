"""Event grouping is a shared wrapper. These tests score no corpus."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from phos.eval.baseline_table import G1_ALERTS_PER_SHIFT
from phos.eval.grouping import (
    EVENT_SPAN_SECONDS,
    EVENT_WINDOW_SECONDS,
    FEATURE_GAP_SECONDS,
    GROUPED_ALERTS_PER_SHIFT,
    ONSET_FRACTION,
    ONSET_LEVEL,
    group_published_alerts,
)

ORIGIN = datetime(2021, 1, 1, tzinfo=UTC)


def _times(n: int, step: timedelta) -> tuple[datetime, ...]:
    return tuple(ORIGIN + step * index for index in range(n))


def _rows(alerts: tuple[tuple[int, str, float], ...]) -> tuple[int, ...]:
    return tuple(row for row, _feature, _score in alerts)


def test_the_constants_are_the_ones_chosen_on_hai_20_07() -> None:
    """ADR 0096's sandbox constants, in seconds, with one alert per event."""
    assert FEATURE_GAP_SECONDS == 60
    assert EVENT_WINDOW_SECONDS == 300
    assert EVENT_SPAN_SECONDS == 600
    assert ONSET_FRACTION == 0.1
    assert ONSET_LEVEL == 2.0
    assert GROUPED_ALERTS_PER_SHIFT == 8
    assert GROUPED_ALERTS_PER_SHIFT == G1_ALERTS_PER_SHIFT


def test_a_sixty_second_gap_merges_and_a_sixty_one_second_gap_does_not() -> None:
    """Merging moves the episode onset, so the next onset can fall outside the window."""
    stamps = _times(400, timedelta(seconds=1))
    merged = group_published_alerts(
        stamps,
        ((0, "a", 3.0), (60, "a", 9.0), (361, "b", 8.0)),
    )
    split = group_published_alerts(
        stamps,
        ((0, "a", 3.0), (61, "a", 9.0), (361, "b", 8.0)),
    )
    assert _rows(merged) == (0, 361)
    assert merged[0][2] == 9.0
    assert _rows(split) == (0,)
    assert split[0][2] == 9.0


def test_hourly_samples_do_not_inherit_a_sixty_sample_gap() -> None:
    """Sixty seconds is not sixty hours. Adjacent hours stay two events."""
    stamps = _times(3, timedelta(hours=1))
    alerts = group_published_alerts(stamps, ((0, "a", 5.0), (1, "a", 5.0)))
    assert _rows(alerts) == (0, 1)


def test_onsets_chain_for_three_hundred_seconds_and_stop_at_six_hundred() -> None:
    """Two features one window apart are one event. A later onset past the span is another."""
    stamps = _times(800, timedelta(seconds=1))
    chained = group_published_alerts(
        stamps,
        ((0, "a", 5.0), (300, "b", 4.0)),
    )
    spanned = group_published_alerts(
        stamps,
        ((0, "a", 5.0), (300, "b", 4.0), (601, "c", 9.0)),
    )
    assert _rows(chained) == (0,)
    assert chained[0][1] == "a"
    assert chained[0][2] == 5.0
    assert _rows(spanned) == (0, 601)


def test_the_alert_moves_to_the_first_point_that_reaches_the_onset_level() -> None:
    """The peak stays put when the earlier point is below 2.0."""
    stamps = _times(20, timedelta(seconds=1))
    early = group_published_alerts(stamps, ((0, "a", 2.5), (10, "a", 20.0)))
    late = group_published_alerts(stamps, ((0, "a", 1.5), (10, "a", 20.0)))
    assert early == ((0, "a", 20.0),)
    assert late == ((10, "a", 20.0),)


def test_a_shift_keeps_the_eight_strongest_events_and_one_alert_each() -> None:
    """Nine separate events in one shift: the weakest is dropped. No second alert."""
    stamps = _times(4000, timedelta(seconds=1))
    cells = tuple((index * 301, "a", float(index + 1)) for index in range(9))
    alerts = group_published_alerts(stamps, cells)
    assert len(alerts) == 8
    assert min(score for _row, _feature, score in alerts) == 2.0
    assert all(row % 301 == 0 for row, _feature, _score in alerts)


def test_the_wrapper_does_not_name_a_detector() -> None:
    """The same cells are the same events whichever detector published them."""
    stamps = _times(10, timedelta(seconds=1))
    cells = ((1, "temperature", 3.0), (2, "pressure", 4.0))
    assert group_published_alerts(stamps, cells) == group_published_alerts(stamps, cells)


def test_grouping_does_not_read_a_corpus() -> None:
    """This module is the declaration. It does not score HAI or write a log."""
    source = Path("src/phos/eval/grouping.py").read_text(encoding="utf-8")
    assert "data/hai" not in source
    assert "eval_runs" not in source
    assert "measure_baseline" not in source
    assert "SECOND_ALERT" not in source
