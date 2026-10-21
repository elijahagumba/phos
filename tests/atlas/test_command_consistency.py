"""The three command components stay apart, and evidence accumulates rather than flagging."""

from __future__ import annotations

import numpy

from phos.atlas.command_consistency import (
    COMPONENTS,
    CommandModel,
    augmented_scores,
    component_series,
    fit_commands,
)
from phos.atlas.consistency import THRESHOLD, TrainFile, feature_scores, fit
from phos.atlas.icssim_adapter import Command


def _quiet(rows: int = 400, signals: int = 3, seed: int = 7) -> numpy.ndarray:
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    return numpy.stack(
        [
            numpy.sin(t / (13.0 + 2.0 * j)) + 0.01 * rng.standard_normal(rows)
            for j in range(signals)
        ],
        axis=1,
    )


def _model() -> tuple[CommandModel, numpy.ndarray, numpy.ndarray]:
    values = _quiet()
    times = numpy.arange(values.shape[0], dtype=numpy.float64)
    base = fit([TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))])
    training = (
        (
            values,
            times,
            (
                Command(at=10.0, role="plc1", function="read", tag="a", value=1.0),
                Command(at=20.0, role="operator", function="read", tag="a", value=1.0),
                Command(at=30.0, role="operator", function="write", tag="a", value=5.0),
            ),
        ),
    )
    return fit_commands(base, training), values, times


def test_training_learns_who_reads_and_who_writes() -> None:
    model, _values, _times = _model()
    assert model.readers == frozenset({"plc1", "operator"})
    assert model.writers == frozenset({"operator"})


def test_the_components_stay_in_order_and_apart() -> None:
    """command-ranking.md and ADR 0034 require a known station and an unknown master apart."""
    assert COMPONENTS == ("unknown_writer", "unknown_reader")


def test_an_unfamiliar_poll_counts_rather_than_flags() -> None:
    """A scan is overwhelming evidence; a flat score would lose the shift budget to signals."""
    model, values, times = _model()
    one = component_series(
        model,
        values,
        times,
        (Command(at=50.0, role="attacker", function="read", tag="a", value=0.0),),
    )
    many = component_series(
        model,
        values,
        times,
        tuple(
            Command(at=50.0, role="attacker", function="read", tag="a", value=0.0)
            for _ in range(40)
        ),
    )
    assert float(one[:, 1].max()) == THRESHOLD
    assert float(many[:, 1].max()) == THRESHOLD * 40


def test_a_familiar_poll_scores_nothing() -> None:
    model, values, times = _model()
    series = component_series(
        model, values, times, (Command(at=50.0, role="plc1", function="read", tag="a", value=0.0),)
    )
    assert float(series[:, 1].max()) == 0.0


def test_a_write_from_a_station_that_never_writes_scores_above_threshold() -> None:
    """A single deliberate act, so it does not need repetition to be strong evidence."""
    model, values, times = _model()
    series = component_series(
        model,
        values,
        times,
        (Command(at=60.0, role="attacker", function="write", tag="a", value=9.0),),
    )
    assert float(series[:, 0].max()) > THRESHOLD
    assert float(series[:, 1].max()) == 0.0


def test_a_known_station_writing_scores_nothing() -> None:
    """A known station's write scores nothing on either column.

    The response comparison was removed: the two events it targeted are physically identical,
    differing by under two training spreads on every one of 39 summary features.
    """
    model, values, times = _model()
    series = component_series(
        model,
        values,
        times,
        (Command(at=60.0, role="operator", function="write", tag="a", value=99.0),),
    )
    assert float(series.max()) == 0.0


def test_the_augmented_matrix_adds_two_columns_and_keeps_the_signals() -> None:
    model, values, times = _model()
    plain = feature_scores(model.base, values)
    augmented = augmented_scores(model, values, times, ())
    assert augmented.shape == (plain.shape[0], plain.shape[1] + 2)
    numpy.testing.assert_array_equal(augmented[:, : plain.shape[1]], plain)


def test_the_frozen_detector_is_not_touched() -> None:
    model, values, times = _model()
    before = feature_scores(model.base, values).copy()
    augmented_scores(model, values, times, ())
    numpy.testing.assert_array_equal(feature_scores(model.base, values), before)
