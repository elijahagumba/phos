"""The breadth column counts how many signals depart, not how far one of them does."""

from __future__ import annotations

import numpy

from phos.atlas.breadth_consistency import (
    BreadthModel,
    augmented_scores,
    breadth_raw,
    calibrate_breadth,
)
from phos.atlas.consistency import THRESHOLD, TrainFile, feature_scores, fit


def _quiet(rows: int = 600, signals: int = 4, seed: int = 11) -> numpy.ndarray:
    """An attack-free run: each signal a slow sine with a little noise, all different periods."""
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    columns = [
        numpy.sin(t / (17.0 + 3.0 * j)) + 0.01 * rng.standard_normal(rows) for j in range(signals)
    ]
    return numpy.stack(columns, axis=1)


def test_one_huge_signal_cannot_drive_the_breadth_column() -> None:
    """A single signal far past the threshold contributes exactly one unit, not its own size."""
    one_big = numpy.array([[50.0, 0.0, 0.0, 0.0]], dtype=numpy.float32)
    assert float(breadth_raw(one_big)[0]) == THRESHOLD


def test_many_small_signals_add_up_where_none_alerts_alone() -> None:
    """Four signals at 0.9 each open no episode alone, and together exceed the threshold."""
    many_small = numpy.full((1, 4), 0.9, dtype=numpy.float32)
    assert float(many_small.max()) < THRESHOLD
    assert float(breadth_raw(many_small)[0]) > THRESHOLD


def test_breadth_is_the_capped_sum_exactly() -> None:
    """The statistic is the sum of per-signal scores each capped at the threshold."""
    scores = numpy.array([[0.25, 2.0, 0.5, 0.0]], dtype=numpy.float32)
    assert float(breadth_raw(scores)[0]) == 0.25 + THRESHOLD + 0.5 + 0.0


def test_breadth_has_one_value_per_row() -> None:
    """The statistic collapses signals, never rows."""
    scores = numpy.zeros((37, 5), dtype=numpy.float32)
    assert breadth_raw(scores).shape == (37,)


def test_a_quiet_statistic_needs_no_scaling() -> None:
    """Fewer training peaks than the calibration rank leaves the divisor at one."""
    values = _quiet()
    model = fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])
    divisor = calibrate_breadth(model, values, model.windows.feature_gap)
    assert divisor >= 1.0


def test_the_augmented_matrix_adds_exactly_one_column_and_keeps_the_others() -> None:
    """Every per-signal column is the frozen detector's own, untouched."""
    values = _quiet()
    model = fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])
    breadth = BreadthModel(base=model, divisor=2.0)
    plain = feature_scores(model, values)
    augmented = augmented_scores(breadth, values)
    assert augmented.shape == (plain.shape[0], plain.shape[1] + 1)
    numpy.testing.assert_array_equal(augmented[:, :-1], plain)


def test_the_breadth_column_is_the_statistic_over_its_divisor() -> None:
    """The last column is the raw statistic divided by the model's divisor, and nothing else."""
    values = _quiet()
    model = fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])
    breadth = BreadthModel(base=model, divisor=4.0)
    augmented = augmented_scores(breadth, values)
    expected = breadth_raw(feature_scores(model, values)) / numpy.float32(4.0)
    numpy.testing.assert_allclose(augmented[:, -1], expected, rtol=1e-6)


def test_the_frozen_detector_is_not_touched() -> None:
    """Scoring through this module leaves the per-signal scores bit-for-bit what they were."""
    values = _quiet()
    model = fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])
    before = feature_scores(model, values).copy()
    augmented_scores(BreadthModel(base=model, divisor=3.0), values)
    numpy.testing.assert_array_equal(feature_scores(model, values), before)
