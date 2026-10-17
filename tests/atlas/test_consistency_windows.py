"""The one rule that scales the consistency detector's windows to a sample period (ADR 0112)."""

from __future__ import annotations

from dataclasses import replace

import numpy
import pytest
from numpy.typing import NDArray

from phos.atlas import consistency
from phos.atlas.consistency_windows import (
    FROZEN_WINDOWS,
    Windows,
    scale_windows,
    windows_for_period,
)

START = 1_467_590_400.0  # 2016-07-04, BATADAL's first test hour


def test_one_second_is_the_frozen_windows_exactly() -> None:
    assert windows_for_period(1.0) == FROZEN_WINDOWS
    assert FROZEN_WINDOWS == Windows(
        lags=(0, 5, 15, 30, 60),
        fit_step=5,
        detrend_window=3600,
        detrend_step=60,
        feature_gap=60,
        event_window=300,
        event_span=600,
        second_alert_min_separation=30,
    )


def test_hourly_collapses_every_window_to_one_sample() -> None:
    assert windows_for_period(3600.0) == Windows(
        lags=(0, 1),
        fit_step=1,
        detrend_window=1,
        detrend_step=1,
        feature_gap=1,
        event_window=1,
        event_span=1,
        second_alert_min_separation=1,
    )


def test_ten_seconds_rounds_half_up() -> None:
    assert windows_for_period(10.0) == Windows(
        lags=(0, 1, 2, 3, 6),
        fit_step=1,
        detrend_window=360,
        detrend_step=6,
        feature_gap=6,
        event_window=30,
        event_span=60,
        second_alert_min_separation=3,
    )


@pytest.mark.parametrize("period", [0.0, -1.0, float("nan")])
def test_a_period_that_is_not_positive_is_refused(period: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        windows_for_period(period)


def _plant(rows: int, seed: int) -> NDArray[numpy.float64]:
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    driver = numpy.sin(2 * numpy.pi * t / 24.0) + 0.05 * rng.standard_normal(rows)
    response = 2.0 * numpy.roll(driver, 1) + 0.05 * rng.standard_normal(rows)
    walk = numpy.cumsum(0.01 * rng.standard_normal(rows))
    return numpy.column_stack([driver, response, walk, rng.standard_normal(rows)])


def test_explicit_frozen_windows_change_nothing() -> None:
    train = [consistency.TrainFile(values=_plant(9_000, 1), attack=numpy.zeros(9_000, numpy.bool_))]
    values = _plant(9_000, 2)
    values[4_000:4_300, 1] = values[3_999, 1]
    test = [consistency.ScoredFile(time=START + numpy.arange(9_000.0), values=values)]
    assert consistency.detect(train, test, windows_for_period(1.0)) == consistency.detect(
        train, test
    )


def test_an_hourly_plant_runs_and_the_model_keeps_its_windows() -> None:
    hourly = windows_for_period(3600.0)
    train = [consistency.TrainFile(values=_plant(4_000, 3), attack=numpy.zeros(4_000, numpy.bool_))]
    values = _plant(2_000, 4)
    values[1_000:1_012, 1] = values[999, 1]  # the response freezes for half a day
    time = START + 3600.0 * numpy.arange(2_000.0)
    model = consistency.fit(train, hourly)
    assert model.windows == hourly
    found = consistency.events(consistency.feature_scores(model, values), windows=model.windows)
    rows, columns, _scores = consistency.budget_alerts(found, time, model.windows)
    assert any(
        1_000 <= row <= 1_012 and column == 1 for row, column in zip(rows, columns, strict=True)
    )
    shifts = [int((time[row] - time[0]) // consistency.SHIFT_SECONDS) for row in rows]
    for shift in set(shifts):
        kept = [row for row, s in zip(rows, shifts, strict=True) if s == shift]
        assert len(kept) <= consistency.ALERTS_PER_SHIFT


@pytest.mark.parametrize("period", [0.5, 1.0, 2.0, 7.5, 10.0, 30.0, 60.0, 3600.0])
def test_scaling_the_frozen_set_is_adr_0112s_rule_exactly(period: float) -> None:
    assert scale_windows(FROZEN_WINDOWS, period) == windows_for_period(period)


def test_scaling_another_set_uses_the_same_rule() -> None:
    longer = replace(FROZEN_WINDOWS, lags=(0, 30, 300, 1200), detrend_window=21600)
    scaled = scale_windows(longer, 30.0)
    assert scaled.lags == (0, 1, 10, 40)
    assert scaled.detrend_window == 720
    assert scaled.fit_step == windows_for_period(30.0).fit_step


def test_scaling_refuses_a_non_positive_period() -> None:
    with pytest.raises(ValueError, match="positive"):
        scale_windows(FROZEN_WINDOWS, 0.0)
