"""A sequential notion of normal: a commanded setpoint holds, or it jumps, but it does not slide.

Every fixture here is hand-made. Nothing in this file reads a corpus. The point of the module is
that its statistic is order-dependent, so the tests assert that directly: the same values in a
different order must produce a different answer.
"""

from __future__ import annotations

import numpy
import pytest

from phos.atlas.consistency import events
from phos.atlas.sequential_consistency import (
    SLID_TAG,
    SequentialModel,
    change_run,
    fit_sequential,
    sequential_scores,
)


def _matrix(column: list[float]) -> numpy.ndarray:
    """One two-column matrix: an unused signal beside the tag under test."""
    rows = numpy.asarray(column, dtype=numpy.float64)
    return numpy.column_stack([numpy.zeros(rows.shape[0], dtype=numpy.float64), rows])


def test_a_held_signal_never_runs() -> None:
    """A setpoint that does not move produces no run at all."""
    run = change_run(numpy.array([7.0, 7.0, 7.0, 7.0]))
    assert run.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_one_write_is_a_run_of_one_and_the_next_hold_resets_it() -> None:
    """A discrete command is one change; the samples after it are the value holding still."""
    run = change_run(numpy.array([7.0, 7.0, 6.8, 6.8, 6.8]))
    assert run.tolist() == [0.0, 0.0, 1.0, 0.0, 0.0]


def test_consecutive_changes_accumulate() -> None:
    """A value that moves at every sample builds a run one longer each sample."""
    run = change_run(numpy.array([6.5, 6.6, 6.7, 6.8]))
    assert run.tolist() == [0.0, 1.0, 2.0, 3.0]


def test_a_run_restarts_after_the_value_holds_again() -> None:
    """A pause ends the run, so two bursts are two runs and neither is their sum."""
    run = change_run(numpy.array([6.5, 6.6, 6.7, 6.7, 6.7, 6.8, 6.9]))
    assert run.tolist() == [0.0, 1.0, 2.0, 0.0, 0.0, 1.0, 2.0]


def test_the_same_values_in_another_order_have_another_run_profile() -> None:
    """This is the property that makes it sequential: a permutation changes the answer.

    Both arrays hold the same multiset. A per-sample comparison cannot tell them apart, because
    every sample's value is equally ordinary. The run profile can.
    """
    alternating = numpy.array([1.0, 2.0, 1.0, 2.0])
    grouped = numpy.array([1.0, 1.0, 2.0, 2.0])
    assert sorted(alternating.tolist()) == sorted(grouped.tolist())
    assert float(change_run(alternating).max()) == 3.0
    assert float(change_run(grouped).max()) == 1.0


def test_the_run_is_returned_as_a_float_column() -> None:
    """The column is fed to `events` beside float scores, so its dtype must match."""
    run = change_run(numpy.array([6.5, 6.6, 6.7]))
    assert run.dtype == numpy.float32
    assert run.shape == (3,)


def test_a_two_dimensional_series_is_refused() -> None:
    """The statistic is one series; a matrix is passed through `sequential_scores` instead."""
    with pytest.raises(ValueError, match="one-dimensional"):
        change_run(numpy.zeros((3, 2)))


def test_the_longest_run_is_learned_from_training() -> None:
    """The threshold is what attack-free operation actually did, not a number chosen by hand."""
    training = (_matrix([7.0, 7.0, 7.0, 7.0]), _matrix([7.0, 7.0, 6.9, 6.9]))
    model = fit_sequential(("tank_level_value", SLID_TAG), training)
    assert model.longest_run == 1
    assert model.column == 1


def test_training_that_never_moved_learns_a_run_of_zero() -> None:
    """A plant whose setpoint was never written sets the strictest possible bar."""
    model = fit_sequential(("tank_level_value", SLID_TAG), (_matrix([7.0, 7.0, 7.0]),))
    assert model.longest_run == 0


def test_a_fit_needs_at_least_one_training_run() -> None:
    """With nothing to learn from, the longest run is unset rather than assumed."""
    with pytest.raises(ValueError, match="at least one training run"):
        fit_sequential(("tank_level_value", SLID_TAG), ())


def test_a_missing_tag_is_a_refusal_that_names_the_tag() -> None:
    """A corpus without the column cannot be scored, and the message says which column."""
    with pytest.raises(ValueError, match=SLID_TAG):
        fit_sequential(("tank_level_value", "tank_level_min"), (_matrix([7.0, 7.0]),))


def test_scores_are_one_column_of_run_lengths() -> None:
    """`sequential_scores` returns the shape `events` expects: rows by one signal."""
    model = SequentialModel(column=1, longest_run=1)
    values = _matrix([7.0, 7.0, 6.9, 6.8])
    scores = sequential_scores(model, values)
    assert scores.shape == (4, 1)
    assert scores.dtype == numpy.float32
    assert scores[:, 0].tolist() == [0.0, 0.0, 1.0, 2.0]


def test_scores_ignore_every_column_that_is_not_the_tag() -> None:
    """Only the slid tag is read, so another signal moving leaves the score untouched."""
    model = SequentialModel(column=1, longest_run=1)
    quiet = numpy.column_stack(
        [numpy.zeros(4, dtype=numpy.float64), numpy.array([7.0, 7.0, 6.9, 6.8])]
    )
    noisy = numpy.column_stack(
        [numpy.arange(4, dtype=numpy.float64), numpy.array([7.0, 7.0, 6.9, 6.8])]
    )
    assert sequential_scores(model, quiet).tolist() == sequential_scores(model, noisy).tolist()


def test_a_slow_ramp_opens_an_episode_and_a_single_step_does_not() -> None:
    """The mechanism Q-0001 asks about, on a hand-made fixture.

    A ramp moves the value at every sample, so the run grows past what attack-free training ever
    produced. A single in-band step moves it once and holds, so the run never clears the learned
    threshold — the step is a larger jump than any single ramp increment, and is still not an
    event. That is the whole difference between a value comparison and a sequential one.
    """
    model = SequentialModel(column=0, longest_run=1)

    ramp = numpy.linspace(6.5, 7.5, 720).reshape(-1, 1)
    stepped = numpy.full((720, 1), 7.0)
    stepped[360:] = 7.4

    ramp_events = events(sequential_scores(model, ramp), threshold=float(model.longest_run))
    step_events = events(sequential_scores(model, stepped), threshold=float(model.longest_run))

    assert ramp_events, "a 720-step ramp must open an episode"
    assert step_events == [], "a single in-band step must not"


def test_the_ramp_alert_lands_early_inside_the_ramp() -> None:
    """The episode machinery places the alert at the onset fraction, not at the ramp's end."""
    model = SequentialModel(column=0, longest_run=1)
    ramp = numpy.linspace(6.5, 7.5, 720).reshape(-1, 1)
    found = events(sequential_scores(model, ramp), threshold=float(model.longest_run))
    assert len(found) == 1
    assert 0 < found[0].onset < 720
