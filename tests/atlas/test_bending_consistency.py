"""The hinge basis bends the prediction and nothing else; with no knots it is the frozen engine."""

from __future__ import annotations

import numpy
import pytest

from phos.atlas.bending_consistency import (
    KNOT_QUANTILES,
    bending_scores,
    fit_bending,
    hinge_basis,
    knots_from,
)
from phos.atlas.consistency import TrainFile, feature_scores, fit


def _quiet(rows: int = 900, signals: int = 4, seed: int = 11) -> numpy.ndarray:
    """An attack-free run: each signal a slow sine with a little noise, all different periods."""
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    columns = [
        numpy.sin(t / (17.0 + 3.0 * j)) + 0.01 * rng.standard_normal(rows) for j in range(signals)
    ]
    return numpy.stack(columns, axis=1)


def _train(values: numpy.ndarray) -> list[TrainFile]:
    return [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))]


# ----------------------------------------------------------------- the basis


def test_the_basis_is_the_linear_term_then_its_hinges() -> None:
    """One column, two knots, by hand."""
    columns = numpy.array([[-1.0], [0.0], [0.5], [2.0]])
    knots = numpy.array([[0.0, 1.0]])
    low = numpy.array([-10.0])
    high = numpy.array([10.0])
    got = hinge_basis(columns, knots, low, high)
    expected = numpy.array(
        [
            [-1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [2.0, 2.0, 1.0],
        ]
    )
    numpy.testing.assert_allclose(got, expected)


def test_no_knots_leaves_the_input_alone() -> None:
    """With an empty knot set the basis is the clamped input and nothing more."""
    columns = numpy.array([[-1.0], [0.5], [2.0]])
    got = hinge_basis(columns, numpy.zeros((1, 0)), numpy.array([-10.0]), numpy.array([10.0]))
    numpy.testing.assert_allclose(got, columns)


def test_inputs_are_clamped_so_the_predictor_saturates() -> None:
    """Beyond the training range the basis holds its edge instead of extrapolating."""
    columns = numpy.array([[100.0], [-100.0]])
    knots = numpy.array([[0.0]])
    got = hinge_basis(columns, knots, numpy.array([-1.0]), numpy.array([1.0]))
    numpy.testing.assert_allclose(got, numpy.array([[1.0, 1.0], [-1.0, 0.0]]))


def test_the_basis_groups_each_column_with_its_own_hinges() -> None:
    """Two inputs, one knot each: the width is p * (1 + k) and the order is per input."""
    columns = numpy.array([[2.0, 3.0]])
    knots = numpy.array([[1.0], [1.0]])
    low = numpy.array([-10.0, -10.0])
    high = numpy.array([10.0, 10.0])
    got = hinge_basis(columns, knots, low, high)
    assert got.shape == (1, 4)
    numpy.testing.assert_allclose(got, numpy.array([[2.0, 1.0, 3.0, 2.0]]))


def test_a_mismatched_knot_table_is_refused() -> None:
    """The knots must describe the columns they expand."""
    with pytest.raises(ValueError, match="knots describe 2 columns, not 1"):
        hinge_basis(numpy.zeros((3, 1)), numpy.zeros((2, 1)), numpy.zeros(1), numpy.ones(1))


def test_a_mismatched_clamp_is_refused() -> None:
    """So must the clamps."""
    with pytest.raises(ValueError, match="clamps describe"):
        hinge_basis(numpy.zeros((3, 2)), numpy.zeros((2, 1)), numpy.zeros(1), numpy.ones(1))


# ----------------------------------------------------------------- knots


def test_knots_come_from_the_training_distribution_and_ascend() -> None:
    """One ascending knot set per live signal, read from attack-free rows only."""
    values = _quiet()
    train = _train(values)
    model = fit(train)
    knots = knots_from(train, model.mean, model.spread, model.live)
    assert knots.shape == (model.live.size, len(KNOT_QUANTILES))
    for row in knots:
        assert list(row) == sorted(row)


def test_an_empty_quantile_set_gives_no_knots() -> None:
    """The degenerate case is representable, not an error."""
    values = _quiet()
    train = _train(values)
    model = fit(train)
    assert knots_from(train, model.mean, model.spread, model.live, ()).shape == (
        model.live.size,
        0,
    )


def test_a_quantile_outside_the_unit_interval_is_refused() -> None:
    """A caller error, not something to clamp silently."""
    values = _quiet()
    train = _train(values)
    model = fit(train)
    with pytest.raises(ValueError, match=r"quantile must be in \[0, 1\]"):
        knots_from(train, model.mean, model.spread, model.live, (0.5, 1.5))


# ----------------------------------------------------------------- faithfulness


def test_with_no_knots_it_is_the_frozen_detector() -> None:
    """The bend is the only difference. Collapse the basis and the scores must coincide.

    This is the lane's faithfulness pin: it proves the module reuses the frozen standardisation,
    residual quantile, detrending, range score and calibration rather than reimplementing them.
    """
    values = _quiet()
    train = _train(values)
    frozen = feature_scores(fit(train), values)
    bent = bending_scores(fit_bending(train, quantiles=()), values)
    numpy.testing.assert_allclose(bent, frozen, rtol=1e-6, atol=1e-6)


def test_the_bend_actually_changes_the_scores() -> None:
    """With knots the scores must differ from the frozen ones, or the basis is doing nothing."""
    values = _quiet()
    train = _train(values)
    frozen = feature_scores(fit(train), values)
    bent = bending_scores(fit_bending(train), values)
    assert bent.shape == frozen.shape
    assert not numpy.allclose(bent, frozen, rtol=1e-6, atol=1e-6)


def test_it_appends_no_column() -> None:
    """Lane 4 replaces the predictor; it does not widen the matrix (unlike lanes 1 to 3)."""
    values = _quiet()
    train = _train(values)
    assert bending_scores(fit_bending(train), values).shape == (
        values.shape[0],
        values.shape[1],
    )


def test_the_frozen_detector_is_not_touched() -> None:
    """Fitting and scoring here leaves the frozen scores bit-for-bit what they were."""
    values = _quiet()
    train = _train(values)
    model = fit(train)
    before = feature_scores(model, values).copy()
    bending_scores(fit_bending(train), values)
    numpy.testing.assert_array_equal(feature_scores(model, values), before)


# ----------------------------------------------------------------- the fit


def test_a_fit_needs_a_training_file() -> None:
    """There is nowhere for the knots, the scale or the divisors to come from without one."""
    with pytest.raises(ValueError, match="at least one training file"):
        fit_bending([])


def test_the_target_never_predicts_itself() -> None:
    """Every basis column derived from a signal is excluded when that signal is the target."""
    values = _quiet()
    model = fit_bending(_train(values))
    n_live = model.live.size
    per = 1 + model.knots.shape[1]
    for position in range(n_live):
        for lag_index in range(len(model.windows.lags)):
            for offset in range(per):
                column = (lag_index * n_live + position) * per + offset
                assert model.weights[column, position] == 0.0


def test_the_model_keeps_the_frozen_shape_of_every_learned_array() -> None:
    """Field for field with ConsistencyModel, plus the knots and the wider weights."""
    values = _quiet()
    model = fit_bending(_train(values))
    n_signals = values.shape[1]
    n_live = model.live.size
    width = n_live * len(model.windows.lags) * (1 + model.knots.shape[1])
    assert model.mean.shape == (n_signals,)
    assert model.spread.shape == (n_signals,)
    assert model.low.shape == (n_signals,)
    assert model.high.shape == (n_signals,)
    assert model.scale.shape == (n_signals,)
    assert model.divisor.shape == (n_signals,)
    assert model.weights.shape == (width + 1, n_live)
    assert float(model.divisor.min()) >= 1.0


def test_the_fit_is_deterministic() -> None:
    """Two fits on the same rows give the same weights; nothing here is seeded or shuffled."""
    values = _quiet()
    first = fit_bending(_train(values))
    second = fit_bending(_train(values))
    numpy.testing.assert_array_equal(first.weights, second.weights)
    numpy.testing.assert_array_equal(first.divisor, second.divisor)


def test_attack_rows_do_not_reach_the_knots_or_the_calibration() -> None:
    """A flagged stretch is excluded, so a poisoned run cannot move the learned shape."""
    values = _quiet()
    attack = numpy.zeros(values.shape[0], dtype=numpy.bool_)
    attack[400:500] = True
    poisoned = values.copy()
    poisoned[400:500] += 60.0
    clean = fit_bending([TrainFile(values=values, attack=attack)])
    dirty = fit_bending([TrainFile(values=poisoned, attack=attack)])
    numpy.testing.assert_allclose(clean.knots, dirty.knots, rtol=1e-9)
