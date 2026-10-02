"""Tests for the plant-health metrics: do they measure what their names claim, and only that.

Two of these metrics are real, because process telemetry supports them. Two more were stubs that
raised, because they needed packets PHOS could not read — and PART P3, holding the packet adapter
that was their stated prerequisite, retired them rather than building them. The last two tests here
are what stops that from being a quiet deletion: they assert the stubs are gone *and* that the
signals they stood for are reachable as ordinary observations, which is where the argument for
retiring them lives.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.atlas import GRAPH_FINDING_FEATURES, packet, stability
from phos.atlas.multivariate import MahalanobisModel, PcaResidualModel
from phos.atlas.packet import UNEXPECTED_COMMAND_FUNCTION, function_count_feature
from phos.atlas.stability import (
    ProcessCycle,
    baseline_similarity,
    dominant_period,
    learn_process_cycle,
    process_cycle_deviation,
)
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
STEP = timedelta(seconds=30)
PLANT = "ent_0000000plant"
SPEED = "pump_speed"
HEADER = "header_flow"
CYCLIC = "process_value"
PERIOD = 24


def reading(row: int, feature: str, value: float) -> Observation:
    return Observation(
        id=f"obs_{row:08d}{feature[:4]}",
        entity_ids=[PLANT],
        feature=feature,
        value=value,
        timestamp=T0 + row * STEP,
        domain=Domain.ATLAS,
    )


def linked_plant(rows: int = 400, seed: int = 5) -> list[Observation]:
    """Two signals that move together, which is what a joint model has to learn."""
    generator = numpy.random.default_rng(seed)
    demand = generator.normal(0.0, 1.0, rows)
    jitter = generator.normal(0.0, 0.02, (rows, 2))
    observations: list[Observation] = []
    for row in range(rows):
        observations.append(reading(row, SPEED, 50.0 + 5.0 * demand[row] + jitter[row, 0]))
        observations.append(reading(row, HEADER, 100.0 + 10.0 * demand[row] + jitter[row, 1]))
    return observations


def cyclic_series(rows: int = 240, amplitude: float = 5.0, offset: float = 0.0) -> list[float]:
    angle = 2.0 * numpy.pi * numpy.arange(rows) / PERIOD
    return [100.0 + amplitude * float(numpy.sin(a)) + offset for a in angle]


def cyclic_observations(values: list[float], start_row: int = 0) -> list[Observation]:
    return [reading(start_row + index, CYCLIC, value) for index, value in enumerate(values)]


# --------------------------------------------------------------------------------------------
# Baseline similarity
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_window_that_looks_like_training_is_almost_perfectly_similar(
    model: PcaResidualModel | MahalanobisModel,
) -> None:
    training = linked_plant()
    fitted = model.fit(training)

    similarity = baseline_similarity(fitted, linked_plant(rows=100, seed=99))

    assert similarity is not None
    assert similarity > 0.95


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_window_that_breaks_the_learned_relationship_is_far_less_similar(
    model: PcaResidualModel | MahalanobisModel,
) -> None:
    fitted = model.fit(linked_plant())
    # The two signals now move in opposite directions, which they never did in training.
    generator = numpy.random.default_rng(1)
    demand = generator.normal(0.0, 1.0, 100)
    broken = [
        o
        for row in range(100)
        for o in (
            reading(900 + row, SPEED, 50.0 + 5.0 * demand[row]),
            reading(900 + row, HEADER, 100.0 - 10.0 * demand[row]),
        )
    ]

    normal_similarity = baseline_similarity(fitted, linked_plant(rows=100, seed=99))
    broken_similarity = baseline_similarity(fitted, broken)

    assert normal_similarity is not None
    assert broken_similarity is not None
    assert broken_similarity < normal_similarity - 0.3


def test_similarity_is_a_proportion() -> None:
    fitted = PcaResidualModel().fit(linked_plant())

    similarity = baseline_similarity(fitted, linked_plant(rows=50, seed=42))

    assert similarity is not None
    assert 0.0 <= similarity <= 1.0


def test_a_window_the_model_cannot_speak_about_reports_no_data_rather_than_perfect_health() -> None:
    """A dashboard must be able to tell "nothing measured" from "nothing wrong"."""
    fitted = PcaResidualModel().fit(linked_plant())

    assert baseline_similarity(fitted, []) is None
    assert baseline_similarity(fitted, [reading(900, "valve_position", 1.0)]) is None


def test_a_model_that_learned_nothing_reports_no_data() -> None:
    fitted = PcaResidualModel().fit([])

    assert baseline_similarity(fitted, linked_plant(rows=20)) is None


# --------------------------------------------------------------------------------------------
# Process cycle
# --------------------------------------------------------------------------------------------


def test_the_dominant_period_of_a_clean_cycle_is_found() -> None:
    assert dominant_period(cyclic_series()) == PERIOD


def test_a_cycle_survives_a_reasonable_amount_of_noise() -> None:
    generator = numpy.random.default_rng(11)
    noisy = [
        value + float(n)
        for value, n in zip(cyclic_series(), generator.normal(0, 1, 240), strict=True)
    ]

    assert dominant_period(noisy) == PERIOD


def test_a_signal_with_no_cycle_has_no_dominant_period() -> None:
    generator = numpy.random.default_rng(7)

    assert dominant_period([float(v) for v in generator.normal(0, 1, 240)]) is None


def test_a_constant_signal_has_no_dominant_period() -> None:
    assert dominant_period([5.0] * 240) is None


def test_too_short_a_series_has_no_dominant_period() -> None:
    assert dominant_period([1.0, 2.0, 1.0]) is None


def test_the_search_can_be_bounded_below_the_true_period() -> None:
    assert dominant_period(cyclic_series(), max_period=10) is None


def test_a_steady_trend_is_not_a_rhythm() -> None:
    """A ramp is correlated with itself at every lag, and repeats at none of them."""
    assert dominant_period([float(index) for index in range(240)]) is None


def test_a_signal_whose_correlation_never_turns_over_has_no_rhythm() -> None:
    """The search needs the autocorrelation to fall away before a peak means anything.

    Over the first twenty lags a long ramp stays above 0.75 correlated with itself and never dips.
    There is no trough, so there is no peak after one, so there is nothing to call a period — which
    is the correct answer, and not the "period of 1" that reading the raw maximum would give.
    """
    assert dominant_period([float(index) for index in range(240)], max_period=20) is None


def test_a_cyclic_signal_yields_a_learned_cycle() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))

    assert cycle is not None
    assert cycle.period == PERIOD
    assert cycle.feature == CYCLIC
    assert cycle.entity_id == PLANT
    assert cycle.strength > 0.5
    assert len(cycle.phase_mean) == PERIOD


def test_a_non_cyclic_signal_yields_no_cycle_rather_than_a_meaningless_one() -> None:
    generator = numpy.random.default_rng(7)
    wander = cyclic_observations([float(v) for v in generator.normal(100, 1, 240)])

    assert learn_process_cycle(wander) is None


def test_learning_a_cycle_from_more_than_one_signal_is_refused() -> None:
    mixed = [*cyclic_observations(cyclic_series(rows=48)), reading(0, SPEED, 50.0)]

    with pytest.raises(ValueError, match="one signal"):
        learn_process_cycle(mixed)


def test_learning_a_cycle_from_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="no observations"):
        learn_process_cycle([])


def test_a_burst_of_readings_with_no_time_between_them_has_no_placeable_cycle() -> None:
    """Phase is a function of the clock. Without one, a repeating shape is still not a rhythm."""
    simultaneous = [
        Observation(
            id=f"obs_burst{index:07d}",
            entity_ids=[PLANT],
            feature=CYCLIC,
            value=value,
            timestamp=T0,
            domain=Domain.ATLAS,
        )
        for index, value in enumerate(cyclic_series())
    ]

    assert learn_process_cycle(simultaneous) is None


def test_a_window_that_follows_the_learned_cycle_barely_deviates() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None
    continuation = cyclic_observations(cyclic_series(rows=48), start_row=240)

    assert process_cycle_deviation(cycle, continuation) < 1.0


def test_a_window_shifted_off_the_learned_cycle_deviates() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None
    on_cycle = cyclic_observations(cyclic_series(rows=48), start_row=240)
    # Half a period out of step: the plant is doing the right thing at the wrong time.
    shifted = cyclic_observations(cyclic_series(rows=48)[PERIOD // 2 :], start_row=240)

    assert process_cycle_deviation(cycle, shifted) > process_cycle_deviation(cycle, on_cycle)


def test_a_window_at_the_wrong_level_deviates() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None
    lifted = cyclic_observations(cyclic_series(rows=48, offset=20.0), start_row=240)

    assert process_cycle_deviation(cycle, lifted) > 5.0


def test_measuring_cycle_deviation_over_nothing_is_refused() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None

    with pytest.raises(ValueError, match="no observations"):
        process_cycle_deviation(cycle, [])


def test_measuring_a_different_signal_against_a_cycle_is_refused() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None

    with pytest.raises(ValueError, match="pump_speed"):
        process_cycle_deviation(cycle, [reading(300, SPEED, 50.0)])


def test_a_cycle_is_a_frozen_value_object_that_round_trips() -> None:
    cycle = learn_process_cycle(cyclic_observations(cyclic_series()))
    assert cycle is not None

    restored = ProcessCycle.model_validate_json(cycle.model_dump_json())

    assert restored == cycle


# --------------------------------------------------------------------------------------------
# The metrics that need packets PHOS cannot read yet
# --------------------------------------------------------------------------------------------


def test_the_two_stubs_are_retired_rather_than_left_raising() -> None:
    """P2 supplied the prerequisite both stubs named; P3 decided their fate, and it is retirement.

    Neither signal was lost, and that is the argument. Communication timing is now
    `COMMAND_INTERVAL_MEAN_MS` and `COMMAND_INTERVAL_CV`; protocol state is the per-function-code
    counts and the command graph's `UNEXPECTED_COMMAND_FUNCTION` — "a function code never seen from
    that master" being the retired stub's own worked example. Each of those is an `Observation`, so
    it is baselined, banded, promoted through the evidence boundary, calibrated and measured by the
    harness. A float returned from this module would have had none of that.
    """
    assert not hasattr(stability, "communication_timing_stability")
    assert not hasattr(stability, "protocol_state_stability")
    assert "communication_timing_stability" not in stability.__all__
    assert "protocol_state_stability" not in stability.__all__


def test_the_replacements_are_real_and_reachable() -> None:
    """A retirement that pointed nowhere would be a deletion. These are where the signals went."""
    assert {"COMMAND_INTERVAL_MEAN_MS", "COMMAND_INTERVAL_CV"} <= set(packet.__all__)
    assert function_count_feature(6) == "command_count_fn6"
    assert UNEXPECTED_COMMAND_FUNCTION in GRAPH_FINDING_FEATURES
