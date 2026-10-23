"""ADR 0301's walk column: the pinned valve, per sample, inside the band unscored."""

from __future__ import annotations

import numpy
import pytest

from phos.atlas.consistency import ONSET_LEVEL, TrainFile, feature_scores, fit
from phos.atlas.walk_consistency import (
    VALVE_ABOVE_MAX,
    VALVE_BELOW_MIN,
    WalkModel,
    augmented_scores,
    count_later,
    fit_walk,
    raw_walk_column,
    walk_divisor,
)

KEYS = (
    "tank_level_value",
    "tank_level_min",
    "tank_level_max",
    "tank_input_valve_status",
)


def _values(
    level: float,
    low: float,
    high: float,
    valve: float,
    rows: int = 1,
) -> numpy.ndarray:
    return numpy.tile(
        numpy.array([level, low, high, valve], dtype=numpy.float64),
        (rows, 1),
    )


def _model(values: numpy.ndarray) -> WalkModel:
    trained = fit(
        [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))]
    )
    return fit_walk(trained, (values,), KEYS)


def test_the_pinned_valve_constants_are_the_plc1_literals() -> None:
    """ICSSim bcfd184 writes 0 above the max and the constant 1 below the min."""
    assert VALVE_ABOVE_MAX == 0.0
    assert VALVE_BELOW_MIN == 1.0


def test_a_valve_that_already_matches_the_pinned_line_scores_zero() -> None:
    above = raw_walk_column(*_values(7.0, 4.0, 6.0, VALVE_ABOVE_MAX).T)
    below = raw_walk_column(*_values(3.0, 4.0, 6.0, VALVE_BELOW_MIN).T)
    assert float(above[0]) == 0.0
    assert float(below[0]) == 0.0


def test_a_wrong_valve_outside_the_band_scores_the_onset_level() -> None:
    above = raw_walk_column(*_values(7.0, 4.0, 6.0, 1.0).T)
    below = raw_walk_column(*_values(3.0, 4.0, 6.0, 0.0).T)
    assert float(above[0]) == pytest.approx(ONSET_LEVEL)
    assert float(below[0]) == pytest.approx(ONSET_LEVEL)


def test_samples_inside_the_band_are_not_scored() -> None:
    """Equality with either end is inside: the pinned line uses strict inequalities."""
    inside = raw_walk_column(*_values(5.0, 4.0, 6.0, 1.0).T)
    at_max = raw_walk_column(*_values(6.0, 4.0, 6.0, 1.0).T)
    at_min = raw_walk_column(*_values(4.0, 4.0, 6.0, 0.0).T)
    assert float(inside[0]) == 0.0
    assert float(at_max[0]) == 0.0
    assert float(at_min[0]) == 0.0


def test_the_column_is_per_sample_and_not_a_running_sum() -> None:
    level = numpy.array([7.0, 7.0], dtype=numpy.float64)
    low = numpy.array([4.0, 4.0], dtype=numpy.float64)
    high = numpy.array([6.0, 6.0], dtype=numpy.float64)
    valve = numpy.array([1.0, 0.0], dtype=numpy.float64)
    found = raw_walk_column(level, low, high, valve)
    assert found.tolist() == pytest.approx([ONSET_LEVEL, 0.0])


def test_a_band_that_contains_the_level_on_both_sides_is_refused() -> None:
    with pytest.raises(ValueError, match="above max and below min"):
        raw_walk_column(*_values(5.0, 6.0, 4.0, 0.0).T)


def test_fewer_than_three_peaks_leave_the_divisor_at_one() -> None:
    assert walk_divisor(()) == 1.0
    assert walk_divisor((2.0, 4.0)) == 1.0


def test_the_divisor_is_the_third_largest_peak_and_at_least_one() -> None:
    assert walk_divisor((1.0, 2.0, 3.0, 4.0)) == 2.0
    assert walk_divisor((0.2, 0.4, 0.5)) == 1.0


def test_quiet_training_keeps_the_divisor_at_one() -> None:
    values = _values(5.0, 4.0, 6.0, 0.0, rows=80)
    model = _model(values)
    assert model.divisor == 1.0


def test_three_separated_disagreements_set_the_divisor_from_their_peaks() -> None:
    values = _values(5.0, 4.0, 6.0, 0.0, rows=200)
    for row in (10, 80, 150):
        values[row, 0] = 7.0
        values[row, 3] = 1.0
    model = _model(values)
    assert model.divisor == pytest.approx(ONSET_LEVEL)


def test_the_augmented_matrix_adds_one_column_and_leaves_the_frozen_scores() -> None:
    values = _values(5.0, 4.0, 6.0, 0.0, rows=80)
    model = _model(values)
    plain = feature_scores(model.base, values)
    augmented = augmented_scores(model, values)
    assert augmented.shape == (plain.shape[0], plain.shape[1] + 1)
    numpy.testing.assert_array_equal(augmented[:, :-1], plain)
    before = plain.copy()
    augmented_scores(model, values)
    numpy.testing.assert_array_equal(feature_scores(model.base, values), before)


def test_a_missing_signal_is_refused() -> None:
    values = _values(5.0, 4.0, 6.0, 0.0, rows=80)
    trained = fit(
        [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))]
    )
    with pytest.raises(ValueError, match="tank_level_value"):
        fit_walk(
            trained, (values,), ("tank_level_min", "tank_level_max", "tank_input_valve_status")
        )


def test_an_alert_that_lands_later_is_counted_and_a_one_sided_catch_is_not() -> None:
    windows = ((10.0, 20.0), (40.0, 50.0), (70.0, 80.0))
    assert count_later(windows, (12.0, 41.0), (12.0, 49.0, 71.0)) == 1
    assert count_later(windows, (12.0,), (11.0,)) == 0
    assert count_later(((10.0, 20.0),), (12.0,), ()) == 0
    assert count_later((), (1.0,), (2.0,)) == 0
