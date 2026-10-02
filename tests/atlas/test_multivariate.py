"""Tests for the joint models: does modelling the plant as one machine actually change the answer.

Every fixture here is built so that the *per-signal* answer and the *joint* answer differ, because
that difference is the whole of Atlas's modelling claim. Two shapes recur:

- A **correlation-preserving excursion** — several signals move together, exactly as they always
  have. Each one is individually extreme; the plant is behaving normally. A per-signal baseline
  raises an alarm per signal. A joint model must not.
- A **correlation-breaking excursion** — one signal fails to move with the others, or two move in
  a combination that has never occurred. Each reading is individually unremarkable; the plant is
  doing something impossible. A per-signal baseline sees nothing. A joint model must catch it, and
  must say *which signal* broke.

`GaussianBaseline` appears throughout as the control, and `is_out_of_band` is what "the per-signal
baseline sees nothing" is asserted with, rather than a magnitude: PART 4A settled that a magnitude
means something different in each model, and the bounds are the one common currency.
"""

import json
from datetime import UTC, datetime, timedelta

import numpy
import pytest
from pydantic import ValidationError

from phos.atlas.multivariate import (
    MahalanobisFittedModel,
    MahalanobisModel,
    PcaResidualFittedModel,
    PcaResidualModel,
)
from phos.atlas.vectorise import NO_OBSERVATION, SignalSpace, VectorisePolicy
from phos.eval import Dataset, EvalConfig, LabelledInterval, evaluate
from phos.models import (
    BehaviouralModel,
    FittedModel,
    GaussianBaseline,
    ModelDetector,
    PerKeyBehaviouralModel,
)
from phos.ontology import Deviation, Domain, Observation
from phos.reasoning import evidence_from_deviation, is_out_of_band

T0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
STEP = timedelta(seconds=30)
PLANT = "ent_0000000plant"

SPEED = "pump_speed"
HEADER = "header_flow"
OUTLET = "outlet_flow"
LEVEL = "tank_level"
DEMAND_SIGNALS = (SPEED, HEADER, OUTLET)
ALL_SIGNALS = (SPEED, HEADER, OUTLET, LEVEL)


# --------------------------------------------------------------------------------------------
# Fixtures: a small plant whose signals are genuinely related
# --------------------------------------------------------------------------------------------


def reading(row: int, feature: str, value: float) -> Observation:
    return Observation(
        id=f"obs_{row:08d}{feature[:4]}",
        entity_ids=[PLANT],
        feature=feature,
        value=value,
        timestamp=T0 + row * STEP,
        domain=Domain.ATLAS,
    )


def plant_row(
    row: int, demand: float, level: float, *, outlet: float | None = None
) -> list[Observation]:
    """One instant of a four-signal plant driven by a single latent demand.

    Three signals track ``demand`` and are therefore strongly correlated with each other; the tank
    level is independent of it. ``outlet`` overrides the outlet flow so a test can break the
    correlation on exactly one signal.
    """
    outlet_flow = 100.0 + 10.0 * demand if outlet is None else outlet
    return [
        reading(row, SPEED, 50.0 + 5.0 * demand),
        reading(row, HEADER, 100.0 + 10.0 * demand),
        reading(row, OUTLET, outlet_flow),
        reading(row, LEVEL, level),
    ]


def plant_training(rows: int = 400, seed: int = 5) -> list[Observation]:
    """An attack-free stretch of the plant running normally."""
    generator = numpy.random.default_rng(seed)
    demand = generator.normal(0.0, 1.0, rows)
    level = generator.normal(20.0, 1.0, rows)
    jitter = generator.normal(0.0, 0.02, (rows, 4))

    observations: list[Observation] = []
    for row in range(rows):
        observations.extend(
            [
                reading(row, SPEED, 50.0 + 5.0 * demand[row] + jitter[row, 0]),
                reading(row, HEADER, 100.0 + 10.0 * demand[row] + jitter[row, 1]),
                reading(row, OUTLET, 100.0 + 10.0 * demand[row] + jitter[row, 2]),
                reading(row, LEVEL, level[row] + jitter[row, 3]),
            ]
        )
    return observations


def deviations_by_feature(deviations: list[Deviation]) -> dict[str, Deviation]:
    return {deviation.expected.feature: deviation for deviation in deviations}


def correlated_pair(rows: int = 400, seed: int = 3, rho: float = 0.99) -> list[Observation]:
    """Two signals that are nearly the same measurement, both standard normal about their means."""
    generator = numpy.random.default_rng(seed)
    first = generator.normal(0.0, 1.0, rows)
    second = rho * first + numpy.sqrt(1.0 - rho**2) * generator.normal(0.0, 1.0, rows)

    observations: list[Observation] = []
    for row in range(rows):
        observations.append(reading(row, SPEED, 50.0 + 5.0 * float(first[row])))
        observations.append(reading(row, HEADER, 100.0 + 10.0 * float(second[row])))
    return observations


# --------------------------------------------------------------------------------------------
# Interface conformance — the payoff of the shared foundation
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_multivariate_model_is_a_behavioural_model(model: BehaviouralModel) -> None:
    assert isinstance(model, BehaviouralModel)


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_multivariate_model_is_deliberately_not_a_per_key_model(
    model: BehaviouralModel,
) -> None:
    """The point of Atlas: normal is a property of the plant, not of one signal at a time."""
    assert not isinstance(model, PerKeyBehaviouralModel)


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_fitting_returns_something_that_can_score_and_the_model_itself_cannot(
    model: BehaviouralModel,
) -> None:
    fitted = model.fit(plant_training())

    assert isinstance(fitted, FittedModel)
    assert not hasattr(model, "score")


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_the_part_two_harness_scores_it_without_modification(model: BehaviouralModel) -> None:
    fitted = model.fit(plant_training())
    observations = [o for row in range(20) for o in plant_row(row, 0.0, 20.0)]
    corpus = Dataset(
        name="joint-fixture",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[
            LabelledInterval(start=T0, end=T0 + 5 * STEP, label="attack"),
        ],
    )

    report = evaluate(ModelDetector(fitted=fitted), corpus, EvalConfig())

    assert report.detector_name == f"model:{fitted.name}"
    assert report.n_observations == len(observations)


# --------------------------------------------------------------------------------------------
# PCA: the core behaviour
# --------------------------------------------------------------------------------------------


def test_an_excursion_along_normal_correlations_is_not_flagged() -> None:
    """Three signals move together to +4 sigma. Individually extreme; jointly ordinary."""
    fitted = PcaResidualModel().fit(plant_training())
    consistent = plant_row(900, demand=4.0, level=20.0)

    out_of_band = [
        deviation
        for deviation in fitted.score(consistent)
        if any(is_out_of_band(deviation, o) for o in consistent if o.id == deviation.observation_id)
    ]

    assert out_of_band == []


def test_the_per_signal_baseline_flags_that_same_excursion_on_every_signal() -> None:
    """The control. This is the false-positive mechanism Atlas exists to remove."""
    fitted = GaussianBaseline().fit(plant_training())
    consistent = plant_row(900, demand=4.0, level=20.0)
    by_id = {o.id: o for o in consistent}

    flagged = {
        deviation.expected.feature
        for deviation in fitted.score(consistent)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    }

    assert flagged == set(DEMAND_SIGNALS)


def test_an_excursion_that_breaks_the_correlations_is_flagged() -> None:
    fitted = PcaResidualModel().fit(plant_training())
    # Everything says demand is high; the outlet flow says it is not.
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)
    by_id = {o.id: o for o in broken}

    flagged = [
        deviation
        for deviation in fitted.score(broken)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    ]

    assert flagged != []


def test_a_broken_correlation_is_attributed_to_the_signal_that_broke_it() -> None:
    fitted = PcaResidualModel().fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)

    by_feature = deviations_by_feature(fitted.score(broken))

    assert OUTLET in by_feature
    outlet_magnitude = by_feature[OUTLET].magnitude
    for other in (SPEED, HEADER, LEVEL):
        if other in by_feature:
            assert by_feature[other].magnitude < outlet_magnitude


def test_the_per_signal_baseline_misses_the_broken_correlation_entirely() -> None:
    """Every reading is individually normal. Only the combination is impossible."""
    fitted = GaussianBaseline().fit(plant_training())
    broken = plant_row(900, demand=0.0, level=20.0, outlet=120.0)
    by_id = {o.id: o for o in broken}

    flagged = {
        deviation.expected.feature
        for deviation in fitted.score(broken)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    }
    joint_flagged = {
        deviation.expected.feature
        for deviation in PcaResidualModel().fit(plant_training()).score(broken)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    }

    assert flagged == set()
    assert OUTLET in joint_flagged


def test_retaining_less_variance_keeps_fewer_components() -> None:
    training = plant_training()

    generous = PcaResidualModel(variance_retained=0.99).fit(training)
    frugal = PcaResidualModel(variance_retained=0.50).fit(training)

    assert isinstance(generous, PcaResidualFittedModel)
    assert isinstance(frugal, PcaResidualFittedModel)
    assert generous.n_components > frugal.n_components


def test_variance_retained_must_leave_something_unexplained() -> None:
    with pytest.raises(ValidationError):
        PcaResidualModel(variance_retained=1.0)
    with pytest.raises(ValidationError):
        PcaResidualModel(variance_retained=0.0)


# --------------------------------------------------------------------------------------------
# Mahalanobis: a joint anomaly no per-signal z-score can see
# --------------------------------------------------------------------------------------------


def test_a_jointly_impossible_point_of_individually_normal_readings_is_caught() -> None:
    """Two near-identical signals, one high and one low by the same modest amount.

    Each is 1.5 sigma from its own mean, comfortably inside a three-sigma band, so no per-signal
    baseline has anything to say. Together they are a combination that has never happened.
    """
    training = correlated_pair()
    joint_anomaly = [
        reading(900, SPEED, 50.0 + 5.0 * 1.5),
        reading(900, HEADER, 100.0 + 10.0 * -1.5),
    ]
    by_id = {o.id: o for o in joint_anomaly}

    per_signal = GaussianBaseline().fit(training)
    per_signal_flagged = [
        deviation
        for deviation in per_signal.score(joint_anomaly)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    ]

    joint = MahalanobisModel().fit(training)
    joint_flagged = [
        deviation
        for deviation in joint.score(joint_anomaly)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    ]

    assert per_signal_flagged == []
    assert {d.expected.feature for d in joint_flagged} == {SPEED, HEADER}


def test_the_joint_distance_separates_that_point_from_an_ordinary_one() -> None:
    fitted = MahalanobisModel().fit(correlated_pair())
    assert isinstance(fitted, MahalanobisFittedModel)

    ordinary = [reading(900, SPEED, 50.0 + 5.0 * 1.5), reading(900, HEADER, 100.0 + 10.0 * 1.5)]
    impossible = [reading(901, SPEED, 50.0 + 5.0 * 1.5), reading(901, HEADER, 100.0 + 10.0 * -1.5)]

    ordinary_distance = float(fitted.mahalanobis_distance(ordinary)[0])
    impossible_distance = float(fitted.mahalanobis_distance(impossible)[0])

    # Both points sit 1.5 sigma from each signal's own mean, so no marginal view can tell them
    # apart at all. The default shrinkage damps the ratio — at rho = 0.99 it is the difference
    # between a factor of five and a factor of thirty — which is the price of a stable inverse.
    assert impossible_distance > 4.0 * ordinary_distance


def test_the_expected_value_is_what_the_other_signals_imply() -> None:
    """Mahalanobis attribution is a conditional expectation, which is why it is explainable."""
    fitted = MahalanobisModel(shrinkage=0.0).fit(correlated_pair())
    joint_anomaly = [
        reading(900, SPEED, 50.0 + 5.0 * 1.5),
        reading(900, HEADER, 100.0 + 10.0 * -1.5),
    ]

    by_feature = deviations_by_feature(fitted.score(joint_anomaly))

    # The header read -1.5 sigma, so a signal correlated with it at rho ~= 0.99 was expected to
    # read about -1.5 sigma too: 50 + 5 * -1.5 = 42.5, near enough.
    assert by_feature[SPEED].expected.mean == pytest.approx(42.5, abs=1.0)


def plant_with_a_redundant_signal() -> list[Observation]:
    """The plant plus a total flow that is exactly the sum of two of its own signals.

    A derived signal carrying no information the plant does not already hold. Wide industrial
    corpora are full of them — a total that sums its branches, a level reported in two units — and
    each one makes the covariance exactly rank-deficient.
    """
    training = plant_training()
    total: dict[datetime, float] = {}
    for observation in training:
        if observation.feature in (HEADER, OUTLET):
            total[observation.timestamp] = total.get(observation.timestamp, 0.0) + observation.value
    redundant = [
        reading(row, "total_flow", value) for row, (_, value) in enumerate(sorted(total.items()))
    ]
    return [*training, *redundant]


def test_a_plant_with_a_redundant_signal_needs_shrinkage_and_is_told_so() -> None:
    """The point of the test is the message: a bare ``LinAlgError`` names no remedy."""
    with pytest.raises(ValueError, match="singular"):
        MahalanobisModel(shrinkage=0.0).fit(plant_with_a_redundant_signal())


def test_the_default_shrinkage_absorbs_a_redundant_signal() -> None:
    fitted = MahalanobisModel().fit(plant_with_a_redundant_signal())

    assert (PLANT, "total_flow") in fitted.expected_ranges


def test_shrinkage_must_be_a_proportion() -> None:
    with pytest.raises(ValidationError):
        MahalanobisModel(shrinkage=-0.1)
    with pytest.raises(ValidationError):
        MahalanobisModel(shrinkage=1.5)


# --------------------------------------------------------------------------------------------
# Explainability — a joint score that cannot be traced is not acceptable (Constitution 3.2)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_every_deviation_names_the_signal_it_is_about(model: BehaviouralModel) -> None:
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)

    deviations = fitted.score(broken)

    assert deviations != []
    for deviation in deviations:
        assert deviation.expected.entity_id == PLANT
        assert deviation.expected.feature in ALL_SIGNALS


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_every_deviation_traces_back_to_a_real_observation(model: BehaviouralModel) -> None:
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)
    by_id = {o.id: o for o in broken}

    for deviation in fitted.score(broken):
        observation = by_id[deviation.observation_id]
        assert observation.feature == deviation.expected.feature
        assert deviation.timestamp == observation.timestamp


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_the_reported_band_is_the_expected_value_plus_or_minus_the_learned_spread(
    model: BehaviouralModel,
) -> None:
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)

    for deviation in fitted.score(broken):
        expected = deviation.expected
        assert expected.low == pytest.approx(expected.mean - 3.0 * expected.stddev)
        assert expected.high == pytest.approx(expected.mean + 3.0 * expected.stddev)


def test_the_expected_value_moves_with_the_rest_of_the_plant() -> None:
    """The range is *dynamic*. A static band could not express "given the others, expect this"."""
    fitted = PcaResidualModel().fit(plant_training())
    low_demand = plant_row(900, demand=-3.0, level=20.0, outlet=100.0)
    high_demand = plant_row(901, demand=3.0, level=20.0, outlet=100.0)

    low = deviations_by_feature(fitted.score(low_demand))[OUTLET].expected
    high = deviations_by_feature(fitted.score(high_demand))[OUTLET].expected

    assert high.mean > low.mean + 10.0


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_the_magnitude_is_the_departure_measured_in_learned_spreads(
    model: BehaviouralModel,
) -> None:
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)
    by_id = {o.id: o for o in broken}

    for deviation in fitted.score(broken):
        observed = by_id[deviation.observation_id].value
        expected = deviation.expected
        assert deviation.magnitude == pytest.approx(abs(observed - expected.mean) / expected.stddev)


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_stored_baseline_exists_for_every_signal_the_model_spans(
    model: BehaviouralModel,
) -> None:
    fitted = model.fit(plant_training())

    for feature in ALL_SIGNALS:
        band = fitted.expected_ranges[(PLANT, feature)]
        assert band.stddev > 0.0
        assert band.low == pytest.approx(-3.0 * band.stddev)
        assert band.high == pytest.approx(3.0 * band.stddev)


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_signal_the_model_never_learned_has_no_baseline_to_fall_back_on(
    model: BehaviouralModel,
) -> None:
    """Unknown is not anomalous, and a joint model has nothing to reconstruct an outsider from."""
    fitted = model.fit(plant_training())
    stranger = reading(900, "valve_position", 0.5)

    assert fitted.feature_ranges == {}
    assert fitted.resolve_range(stranger) is None
    assert fitted.score([*plant_row(900, 0.0, 20.0), stranger]) == fitted.score(
        plant_row(900, 0.0, 20.0)
    )


def test_a_deviation_can_be_promoted_to_evidence_by_the_existing_boundary() -> None:
    """4A's boundary must accept a joint deviation with no special case for it."""
    fitted = PcaResidualModel().fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)
    by_id = {o.id: o for o in broken}

    deviation = deviations_by_feature(fitted.score(broken))[OUTLET]
    evidence = evidence_from_deviation(
        deviation,
        by_id[deviation.observation_id],
        0.8,
        summary="Outlet flow did not follow demand",
    )

    assert evidence.source_id == deviation.id
    assert evidence.entity_ids == [PLANT]


# --------------------------------------------------------------------------------------------
# What the model refuses to say
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_model_fitted_on_nothing_scores_nothing(model: BehaviouralModel) -> None:
    fitted = model.fit([])

    assert fitted.score(plant_row(0, 0.0, 20.0)) == []
    assert fitted.expected_ranges == {}


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_too_few_complete_rows_to_learn_from_yields_a_model_that_says_nothing(
    model: BehaviouralModel,
) -> None:
    fitted = model.fit(plant_training(rows=4))

    assert fitted.score(plant_row(900, 4.0, 20.0, outlet=100.0)) == []


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_signal_that_never_moved_in_training_is_left_out_of_the_space(
    model: BehaviouralModel,
) -> None:
    """A constant carries no correlation, so there is nothing to reconstruct it from or with."""
    training = plant_training()
    training += [reading(row, "mode_flag", 1.0) for row in range(400)]

    fitted = model.fit(training)

    assert isinstance(fitted, PcaResidualFittedModel | MahalanobisFittedModel)
    assert (PLANT, "mode_flag") not in fitted.signal_space.signals
    assert set(fitted.signal_space.signals) == {(PLANT, feature) for feature in ALL_SIGNALS}


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_plant_in_which_nothing_ever_moved_teaches_the_model_nothing(
    model: BehaviouralModel,
) -> None:
    """Every signal constant means no correlation anywhere, which is not a model of anything."""
    frozen_plant = [
        o for row in range(100) for o in plant_row(row, demand=0.0, level=20.0, outlet=100.0)
    ]

    fitted = model.fit(frozen_plant)

    assert fitted.expected_ranges == {}
    assert fitted.score(plant_row(900, demand=4.0, level=20.0)) == []


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_window_with_no_complete_moment_in_it_is_scored_as_nothing(
    model: BehaviouralModel,
) -> None:
    """Four signals were learned together; three of them is not a moment of this plant."""
    fitted = model.fit(plant_training())
    partial = [
        o for o in plant_row(900, demand=4.0, level=20.0, outlet=100.0) if o.feature != LEVEL
    ]

    assert fitted.score(partial) == []


def test_a_mahalanobis_model_that_learned_nothing_measures_no_distances() -> None:
    fitted = MahalanobisModel().fit([])
    assert isinstance(fitted, MahalanobisFittedModel)

    assert fitted.mahalanobis_distance(plant_row(0, 0.0, 20.0)).size == 0


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_carried_forward_reading_never_raises_a_deviation_about_itself(
    model: BehaviouralModel,
) -> None:
    """A stale value informs the reconstruction; it is not a measurement to be surprised by."""
    fitted = model.fit(plant_training())
    fresh = plant_row(900, demand=4.0, level=20.0, outlet=100.0)
    followup = [
        o for o in plant_row(901, demand=4.0, level=20.0, outlet=100.0) if o.feature != OUTLET
    ]

    deviations = fitted.score([*fresh, *followup])
    second_row = [d for d in deviations if d.timestamp == T0 + 901 * STEP]

    assert OUTLET not in {d.expected.feature for d in second_row}


# --------------------------------------------------------------------------------------------
# Determinism and serialisation (Constitution 3.7)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_the_same_training_data_produces_the_same_fit(model: BehaviouralModel) -> None:
    training = plant_training()

    first = model.fit(training)
    second = model.fit(training)

    assert first.model_dump() == second.model_dump()


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_the_same_fit_produces_the_same_scores(model: BehaviouralModel) -> None:
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)

    first = fitted.score(broken)
    second = fitted.score(broken)

    assert [d.magnitude for d in first] == [d.magnitude for d in second]
    assert [d.expected for d in first] == [d.expected for d in second]


@pytest.mark.parametrize(
    ("model", "fitted_type"),
    [(PcaResidualModel(), PcaResidualFittedModel), (MahalanobisModel(), MahalanobisFittedModel)],
)
def test_a_fitted_model_rebuilt_from_its_stored_parameters_scores_identically(
    model: BehaviouralModel, fitted_type: type[FittedModel]
) -> None:
    """A fitted model is stored parameters, not a live estimator — the PART 4A precedent."""
    fitted = model.fit(plant_training())
    broken = plant_row(900, demand=4.0, level=20.0, outlet=100.0)

    restored = fitted_type.model_validate(fitted.model_dump())

    assert restored == fitted
    assert [d.magnitude for d in restored.score(broken)] == [
        d.magnitude for d in fitted.score(broken)
    ]


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_a_fitted_model_serialises_to_json(model: BehaviouralModel) -> None:
    """Nothing in the fit is a live object, so all of it survives being written down.

    Reading it *back* from JSON is a separate matter and does not work — every `FittedModel` in
    PHOS keys `expected_ranges` by the ``(entity_id, feature)`` tuple, and JSON has no tuple keys,
    so they come back as one comma-joined string. That predates Atlas and is the same for
    `GaussianFittedModel`; whoever ships a model over the API in PART 8 owns it.
    """
    fitted = model.fit(plant_training())

    payload = json.loads(fitted.model_dump_json())

    assert payload["name"] == fitted.name
    assert payload["signal_space"]["signals"]


@pytest.mark.parametrize("model", [PcaResidualModel(), MahalanobisModel()])
def test_deviations_come_back_in_timestamp_then_signal_order(model: BehaviouralModel) -> None:
    fitted = model.fit(plant_training())
    two_rows = [
        *plant_row(900, demand=4.0, level=20.0, outlet=100.0),
        *plant_row(901, demand=-4.0, level=20.0, outlet=100.0),
    ]

    deviations = fitted.score(two_rows)

    assert [d.timestamp for d in deviations] == sorted(d.timestamp for d in deviations)


# --------------------------------------------------------------------------------------------
# The fill policy is the model's, and it travels with the fit
# --------------------------------------------------------------------------------------------


def test_the_fill_policy_used_at_fit_time_is_the_one_used_at_score_time() -> None:
    model = PcaResidualModel(fill_policy=VectorisePolicy(forward_fill_rows=0))

    fitted = model.fit(plant_training())

    assert isinstance(fitted, PcaResidualFittedModel)
    assert fitted.fill_policy.forward_fill_rows == 0


def test_an_empty_signal_space_is_a_model_with_nothing_to_say() -> None:
    fitted = PcaResidualFittedModel(
        name="atlas-pca",
        expected_ranges={},
        feature_ranges={},
        emit_k=1.0,
        band_k=3.0,
        signal_space=SignalSpace(),
        fill_policy=VectorisePolicy(),
        training_window=None,
        signal_mean=(),
        signal_scale=(),
        centre=(),
        components=(),
        residual_stddev=(),
    )

    assert fitted.score(plant_row(0, 0.0, 20.0)) == []


def test_the_source_index_sentinel_is_what_marks_an_uncredited_cell() -> None:
    assert NO_OBSERVATION < 0
