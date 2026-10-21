"""The accumulator adds up persistent small departures, and forgets at the detrender's horizon."""

from __future__ import annotations

import numpy
import pytest

from phos.atlas.consistency import (
    ONSET_FRACTION,
    ONSET_LEVEL,
    THRESHOLD,
    ConsistencyModel,
    TrainFile,
    feature_scores,
    fit,
)
from phos.atlas.drift_consistency import (
    CONTRIBUTION_CAP,
    DriftModel,
    accumulate,
    augmented_scores,
    calibrate_drift,
    fit_drift,
    retention_for,
)


def _quiet(rows: int = 600, signals: int = 4, seed: int = 11) -> numpy.ndarray:
    """An attack-free run: each signal a slow sine with a little noise, all different periods."""
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    columns = [
        numpy.sin(t / (17.0 + 3.0 * j)) + 0.01 * rng.standard_normal(rows) for j in range(signals)
    ]
    return numpy.stack(columns, axis=1)


def _fitted(values: numpy.ndarray) -> ConsistencyModel:
    """The frozen model fitted on one attack-free run."""
    return fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])


# ----------------------------------------------------------------- the statistic


def test_a_persistent_small_excess_crosses_where_no_single_sample_does() -> None:
    """Thirty samples at 0.5, none alerting alone, accumulate past the threshold."""
    scores = numpy.full((30, 1), 0.5, dtype=numpy.float32)
    slack = numpy.zeros(1)
    tally = accumulate(scores, slack, retention=1.0)
    assert float(scores.max()) < THRESHOLD
    assert float(tally[-1, 0]) > THRESHOLD


def test_nothing_accumulates_below_the_slack() -> None:
    """A signal sitting under its allowance stays at zero however long it sits there."""
    scores = numpy.full((500, 1), 0.2, dtype=numpy.float32)
    tally = accumulate(scores, numpy.array([0.3]), retention=1.0)
    assert float(tally.max()) == 0.0


def test_the_tally_never_goes_negative() -> None:
    """Being quieter than normal earns no credit against a later departure."""
    scores = numpy.zeros((100, 1), dtype=numpy.float32)
    tally = accumulate(scores, numpy.array([0.5]), retention=1.0)
    assert float(tally.min()) == 0.0


def test_a_leaky_tally_is_bounded_and_an_unleaky_one_is_not() -> None:
    """Retention below one caps the tally; retention of one lets it grow without limit."""
    scores = numpy.full((4000, 1), 1.0, dtype=numpy.float32)
    slack = numpy.zeros(1)
    leaky = accumulate(scores, slack, retention=0.99)
    unleaky = accumulate(scores, slack, retention=1.0)
    assert float(leaky.max()) < 101.0
    assert float(unleaky[-1, 0]) == pytest.approx(4000.0, rel=1e-3)


def test_the_tally_re_arms_after_a_departure_ends() -> None:
    """A quiet stretch drains the accumulator, so a later departure starts from near zero."""
    scores = numpy.concatenate(
        [
            numpy.full((200, 1), 1.0, dtype=numpy.float32),
            numpy.zeros((4000, 1), dtype=numpy.float32),
        ]
    )
    tally = accumulate(scores, numpy.zeros(1), retention=retention_for(100))
    assert float(tally[199, 0]) > 10.0
    assert float(tally[-1, 0]) < 0.01


def test_the_recursion_is_exactly_what_the_docstring_says() -> None:
    """Three rows by hand, against the stated formula."""
    scores = numpy.array([[1.0], [0.5], [2.0]], dtype=numpy.float32)
    tally = accumulate(scores, numpy.array([0.25]), retention=0.5)
    first = max(0.0, 0.5 * 0.0 + 1.0 - 0.25)
    second = max(0.0, 0.5 * first + 0.5 - 0.25)
    third = max(0.0, 0.5 * second + 2.0 - 0.25)
    numpy.testing.assert_allclose(tally[:, 0], [first, second, third], rtol=1e-6)


def test_the_tally_keeps_one_column_per_signal() -> None:
    """Signals are never collapsed; that is lane 2's idea, not this one."""
    scores = numpy.zeros((37, 5), dtype=numpy.float32)
    assert accumulate(scores, numpy.zeros(5), retention=0.5).shape == (37, 5)


def test_each_signal_accumulates_on_its_own() -> None:
    """One departing signal does not move another signal's tally."""
    scores = numpy.zeros((50, 3), dtype=numpy.float32)
    scores[:, 1] = 1.0
    tally = accumulate(scores, numpy.zeros(3), retention=1.0)
    assert float(tally[-1, 1]) > 0.0
    assert float(tally[-1, 0]) == 0.0
    assert float(tally[-1, 2]) == 0.0


# ----------------------------------------------------------------- retention


def test_retention_memory_is_the_window() -> None:
    """A window of w samples gives 1 - 1/w, and a one-sample window gives no memory at all."""
    assert retention_for(3600) == pytest.approx(1.0 - 1.0 / 3600.0)
    assert retention_for(1) == 0.0


def test_a_window_below_one_sample_is_refused() -> None:
    """There is no sensible accumulator over a window of zero samples."""
    with pytest.raises(ValueError, match="at least one sample"):
        retention_for(0)


# ----------------------------------------------------------------- fitting


def test_a_mismatched_slack_is_refused() -> None:
    """One allowance per signal, or the caller has the wrong matrix."""
    with pytest.raises(ValueError, match="slack has 2 entries for 4 signals"):
        accumulate(numpy.zeros((10, 4), dtype=numpy.float32), numpy.zeros(2), retention=0.5)


def test_retention_out_of_range_is_refused() -> None:
    """A factor above one is not a leak and is not accepted."""
    with pytest.raises(ValueError, match=r"retention must be in \[0, 1\]"):
        accumulate(numpy.zeros((10, 2), dtype=numpy.float32), numpy.zeros(2), retention=1.5)


def test_a_fit_needs_a_training_run() -> None:
    """The slack and the divisors have nowhere to come from without one."""
    values = _quiet()
    with pytest.raises(ValueError, match="at least one attack-free run"):
        fit_drift(_fitted(values), [])


def test_a_bad_quantile_is_refused() -> None:
    """A quantile outside [0, 1] is a caller error, not something to clamp silently."""
    values = _quiet()
    with pytest.raises(ValueError, match=r"quantile must be in \[0, 1\]"):
        fit_drift(_fitted(values), [values], slack_quantile=1.5)


def test_the_fit_reads_only_attack_free_runs_and_the_engines_own_window() -> None:
    """Slack is one per signal, divisors are floored at one, retention is the detrend window's."""
    values = _quiet()
    model = _fitted(values)
    drift = fit_drift(model, [values])
    assert drift.slack.shape == (values.shape[1],)
    assert drift.divisors.shape == (values.shape[1],)
    assert float(drift.divisors.min()) >= 1.0
    assert drift.retention == pytest.approx(retention_for(model.windows.detrend_window))


def test_a_quiet_column_needs_no_scaling() -> None:
    """Fewer training peaks than the calibration rank leaves that divisor at one."""
    divisors = calibrate_drift([numpy.zeros((600, 3), dtype=numpy.float32)], 3, 60)
    numpy.testing.assert_array_equal(divisors, numpy.ones(3))


# ----------------------------------------------------------------- the augmented matrix


def test_the_augmented_matrix_doubles_the_columns_and_keeps_the_originals() -> None:
    """Every per-signal column is the frozen detector's own, untouched and in place."""
    values = _quiet()
    model = _fitted(values)
    drift = fit_drift(model, [values])
    plain = feature_scores(model, values)
    augmented = augmented_scores(drift, values)
    assert augmented.shape == (plain.shape[0], 2 * plain.shape[1])
    numpy.testing.assert_array_equal(augmented[:, : plain.shape[1]], plain)


def test_the_appended_columns_are_the_capped_tally_over_the_divisors() -> None:
    """The second half is the accumulator over its calibration, clipped at the cap, and no more."""
    values = _quiet()
    model = _fitted(values)
    drift = fit_drift(model, [values])
    n = values.shape[1]
    expected = numpy.minimum(
        accumulate(feature_scores(model, values), drift.slack, drift.retention) / drift.divisors,
        CONTRIBUTION_CAP,
    )
    numpy.testing.assert_allclose(augmented_scores(drift, values)[:, n:], expected, rtol=1e-6)


def test_no_accumulator_column_ever_exceeds_the_cap() -> None:
    """A long hard departure saturates the column instead of running into the hundreds."""
    values = _quiet()
    model = _fitted(values)
    drift = fit_drift(model, [values])
    hostile = values.copy()
    hostile[300:, 0] += 50.0
    appended = augmented_scores(drift, hostile)[:, values.shape[1] :]
    assert float(appended.max()) <= CONTRIBUTION_CAP


def test_the_cap_is_where_the_onset_level_stops_rising() -> None:
    """At the cap, `events`'s onset level is still its floor, so signals keep placing the alert."""
    assert CONTRIBUTION_CAP == ONSET_LEVEL / ONSET_FRACTION
    assert max(ONSET_LEVEL, ONSET_FRACTION * CONTRIBUTION_CAP) == ONSET_LEVEL


def test_the_frozen_detector_is_not_touched() -> None:
    """Scoring through this module leaves the per-signal scores bit-for-bit what they were."""
    values = _quiet()
    model = _fitted(values)
    drift = fit_drift(model, [values])
    before = feature_scores(model, values).copy()
    augmented_scores(drift, values)
    numpy.testing.assert_array_equal(feature_scores(model, values), before)


def test_a_drift_model_carries_the_base_model_unchanged() -> None:
    """The per-signal model is held, not copied into something else."""
    values = _quiet()
    model = _fitted(values)
    drift = DriftModel(
        base=model,
        slack=numpy.zeros(values.shape[1]),
        divisors=numpy.ones(values.shape[1]),
        retention=0.5,
    )
    assert drift.base is model
