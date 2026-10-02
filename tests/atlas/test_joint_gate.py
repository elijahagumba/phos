"""Joint-distance gating: the plant is the alert unit, not each instrument.

The distillation baseline (ADR 0025) posted 18.72 false positives per normal hour — about 449
alerts/day-equivalent — with pooled Mahalanobis. That number is a *per-signal* count: every
conditional residual past ``alert_threshold = 3`` is an alert, so a thermal flicker that slightly
breaks several correlations is counted once per instrument.

The plant-as-a-machine question is whether the *moment* left the learned manifold, measured by
Mahalanobis distance ``D_M``. Per-signal attribution still happens, but only on jointly unusual
moments. These tests pin that distinction on a hand-built plant whose per-signal and joint answers
disagree, so a passing suite cannot be a threshold that happened to work.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.atlas.multivariate import JointMomentDetector, MahalanobisFittedModel, MahalanobisModel
from phos.eval import Dataset, EvalConfig, evaluate
from phos.models import ModelDetector
from phos.ontology import Domain, Observation

T0 = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)
STEP = timedelta(seconds=30)
PLANT = "ent_0000000plant"
SPEED = "pump_speed"
HEADER = "header_flow"
OUTLET = "outlet_flow"
LEVEL = "tank_level"


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
    """One instant of a four-signal plant driven by a single latent demand."""
    outlet_flow = 100.0 + 10.0 * demand if outlet is None else outlet
    return [
        reading(row, SPEED, 50.0 + 5.0 * demand),
        reading(row, HEADER, 100.0 + 10.0 * demand),
        reading(row, OUTLET, outlet_flow),
        reading(row, LEVEL, level),
    ]


def plant_training(rows: int = 400, seed: int = 5) -> list[Observation]:
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


def ungated() -> MahalanobisFittedModel:
    fitted = MahalanobisModel().fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    return fitted


# --------------------------------------------------------------------------------------------
# Default is a no-op, so every number already on the experiment log stays comparable
# --------------------------------------------------------------------------------------------


def test_the_default_model_does_not_gate_on_joint_distance() -> None:
    """A shipped `MahalanobisModel()` is byte-comparable to the ungated baseline."""
    model = MahalanobisModel()
    assert model.joint_k == 0.0
    assert model.adaptive_joint_quantile is None
    fitted = ungated()
    assert fitted.joint_k == 0.0


def test_ungated_and_explicit_zero_gate_emit_the_same_deviations() -> None:
    probe = plant_row(9999, 0.0, 20.0, outlet=40.0)
    ungated_fitted = ungated()
    gated = MahalanobisModel(joint_k=0.0).fit(plant_training())
    assert [(d.observation_id, d.magnitude) for d in ungated_fitted.score(probe)] == [
        (d.observation_id, d.magnitude) for d in gated.score(probe)
    ]


# --------------------------------------------------------------------------------------------
# The gate: jointly ordinary moments stop multiplying into per-signal alerts
# --------------------------------------------------------------------------------------------


def test_a_small_independent_wiggle_is_jointly_ordinary() -> None:
    """Two sigma on the independent tank level is a candidate, not an off-manifold plant."""
    fitted = ungated()
    wiggle = plant_row(9999, 0.0, 22.0)
    distance = float(fitted.mahalanobis_distance(wiggle)[0])
    training = fitted.mahalanobis_distance(plant_training())
    assert distance < float(numpy.quantile(training, 0.99))
    assert fitted.score(wiggle)


def test_a_correlation_break_is_jointly_unusual() -> None:
    """One signal refuses to follow the others: the plant left the manifold."""
    fitted = ungated()
    broken = plant_row(9999, 0.0, 20.0, outlet=40.0)
    distance = float(fitted.mahalanobis_distance(broken)[0])
    training = fitted.mahalanobis_distance(plant_training())
    assert distance > float(numpy.quantile(training, 0.995))


def test_the_joint_gate_suppresses_per_signal_alerts_below_the_envelope() -> None:
    """A modest residual emits ungated and is silent once the moment is gated."""
    training = plant_training()
    ungated_fitted = MahalanobisModel().fit(training)
    assert isinstance(ungated_fitted, MahalanobisFittedModel)
    wiggle = plant_row(9999, 0.0, 22.0)
    distance = float(ungated_fitted.mahalanobis_distance(wiggle)[0])
    assert ungated_fitted.score(wiggle)

    gated = MahalanobisModel(joint_k=distance + 0.05).fit(training)
    assert isinstance(gated, MahalanobisFittedModel)
    assert gated.joint_k == pytest.approx(distance + 0.05)
    assert gated.score(wiggle) == []


def test_the_joint_gate_still_attributes_a_real_break_to_the_signal_that_broke() -> None:
    """Attribution survives the gate: the operator still reads which instrument departed."""
    gated = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(gated, MahalanobisFittedModel)
    broken = plant_row(9999, 0.0, 20.0, outlet=40.0)

    assert float(gated.mahalanobis_distance(broken)[0]) >= gated.joint_k
    features = {d.expected.feature for d in gated.score(broken)}
    assert OUTLET in features


def test_adaptive_joint_k_is_a_training_quantile_not_a_tuned_threshold() -> None:
    """The gate is a property of attack-free training, recovered from the stored `joint_k`."""
    training = plant_training()
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(training)
    assert isinstance(fitted, MahalanobisFittedModel)
    distances = fitted.mahalanobis_distance(training)
    expected = float(numpy.quantile(distances, 0.99))
    assert fitted.joint_k == pytest.approx(expected)
    assert fitted.joint_k > 0.0


def test_an_explicit_joint_k_is_used_when_no_quantile_is_declared() -> None:
    fitted = MahalanobisModel(joint_k=50.0).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    assert fitted.joint_k == 50.0
    ordinary = plant_row(9999, 0.0, 20.0)
    assert fitted.score(ordinary) == []


def test_a_quantile_overrides_an_explicit_joint_k_at_fit_time() -> None:
    """One source of truth: the learned envelope, not a number the caller happened to prefer."""
    fitted = MahalanobisModel(joint_k=50.0, adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    assert fitted.joint_k != 50.0
    training = fitted.mahalanobis_distance(plant_training())
    assert fitted.joint_k == pytest.approx(float(numpy.quantile(training, 0.99)))


# --------------------------------------------------------------------------------------------
# Phase-conditional: each phase learns its own joint envelope
# --------------------------------------------------------------------------------------------


def test_each_phase_learns_its_own_joint_gate() -> None:
    """A CHARGE moment is jointly ordinary *in CHARGE* and jointly unusual against IDLE."""
    from phos.atlas.phased import PhaseConditionalModel

    phase = "batch_phase"
    idle, charge = 0, 1
    observations: list[Observation] = []
    generator = numpy.random.default_rng(7)
    row = 0
    for _ in range(40):
        for _ in range(8):
            observations.append(reading(row, phase, float(idle)))
            observations.append(reading(row, "feed", generator.normal(0.0, 0.4)))
            observations.append(reading(row, "temp", generator.normal(20.0, 0.3)))
            row += 1
        for _ in range(8):
            observations.append(reading(row, phase, float(charge)))
            observations.append(reading(row, "feed", generator.normal(5000.0, 8.0)))
            observations.append(reading(row, "temp", generator.normal(80.0, 0.3)))
            row += 1

    inner = MahalanobisModel(adaptive_joint_quantile=0.99)
    wrapper = PhaseConditionalModel(phase_feature=phase, inner=inner, settling_window=timedelta(0))
    fitted = wrapper.fit(observations)
    idle_model = fitted.per_phase[idle]
    charge_model = fitted.per_phase[charge]
    assert isinstance(idle_model, MahalanobisFittedModel)
    assert isinstance(charge_model, MahalanobisFittedModel)
    assert idle_model.joint_k != charge_model.joint_k
    assert idle_model.joint_k > 0.0
    assert charge_model.joint_k > 0.0


# --------------------------------------------------------------------------------------------
# Actionable-alert unit: one detection per moment, scored by D_M
# --------------------------------------------------------------------------------------------


def test_the_joint_moment_detector_emits_one_alert_per_timestamp() -> None:
    """The SOC budget is moments, not instruments. Four signals at one instant are one alert."""
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    broken = plant_row(9999, 0.0, 20.0, outlet=40.0)
    per_signal = ModelDetector(fitted=fitted).run(
        Dataset(name="probe", domain=Domain.ATLAS, observations=broken, attack_intervals=[])
    )
    moments = JointMomentDetector(fitted=fitted).run(
        Dataset(name="probe", domain=Domain.ATLAS, observations=broken, attack_intervals=[])
    )
    assert len(per_signal) >= 1
    assert len(moments) == 1
    assert moments[0].feature is None
    assert moments[0].score == pytest.approx(float(fitted.mahalanobis_distance(broken)[0]))


def test_the_joint_moment_detector_is_silent_when_the_plant_is_on_the_manifold() -> None:
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    ordinary = plant_row(9999, 0.1, 20.0)
    detections = JointMomentDetector(fitted=fitted).run(
        Dataset(name="probe", domain=Domain.ATLAS, observations=ordinary, attack_intervals=[])
    )
    assert detections == []


def test_the_harness_scores_a_joint_moment_detector() -> None:
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    observations = plant_row(0, 0.0, 20.0) + plant_row(1, 0.0, 20.0, outlet=40.0)
    corpus = Dataset(
        name="two-moments",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
    )
    report = evaluate(
        JointMomentDetector(fitted=fitted),
        corpus,
        EvalConfig(alert_threshold=0.0, seed=11),
    )
    assert report.n_alerts == 1
    assert report.detector_name.startswith("joint-moment:")


# --------------------------------------------------------------------------------------------
# Dwell: a control room does not page a one-sample flicker
# --------------------------------------------------------------------------------------------


def _broken_then_ordinary(
    fitted: MahalanobisFittedModel, *, n_broken: int, n_after: int = 2
) -> Dataset:
    """Ordinary manifold, then ``n_broken`` correlation breaks, then ordinary again."""
    observations: list[Observation] = []
    row = 0
    for _ in range(4):
        observations.extend(plant_row(row, 0.1, 20.0))
        row += 1
    for _ in range(n_broken):
        observations.extend(plant_row(row, 0.0, 20.0, outlet=40.0))
        row += 1
    for _ in range(n_after):
        observations.extend(plant_row(row, 0.1, 20.0))
        row += 1
    broken = plant_row(4, 0.0, 20.0, outlet=40.0)
    assert float(fitted.mahalanobis_distance(broken)[0]) >= fitted.joint_k
    return Dataset(
        name="dwell-probe",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
    )


def test_default_dwell_is_a_no_op_against_the_ungated_name() -> None:
    """``dwell_samples=1`` must not rename the detector or change the ADR 0026 row."""
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    default = JointMomentDetector(fitted=fitted)
    assert default.dwell_samples == 1
    assert default.name == f"joint-moment:{fitted.name}"
    broken = plant_row(9999, 0.0, 20.0, outlet=40.0)
    corpus = Dataset(name="one", domain=Domain.ATLAS, observations=broken, attack_intervals=[])
    assert JointMomentDetector(fitted=fitted, dwell_samples=1).run(corpus) == default.run(corpus)


def test_a_two_sample_flicker_is_not_an_actionable_alert_at_dwell_three() -> None:
    """Two jointly unusual samples, then back on the manifold: dwell-3 is silent."""
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    corpus = _broken_then_ordinary(fitted, n_broken=2)
    assert JointMomentDetector(fitted=fitted).run(corpus)
    assert JointMomentDetector(fitted=fitted, dwell_samples=3).run(corpus) == []


def test_a_sustained_break_emits_only_after_the_dwell_is_reached() -> None:
    """Four consecutive breaks at dwell-3: silent, silent, alert, alert."""
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    corpus = _broken_then_ordinary(fitted, n_broken=4, n_after=0)
    detections = JointMomentDetector(fitted=fitted, dwell_samples=3).run(corpus)
    assert len(detections) == 2
    assert detections[0].timestamp == T0 + 6 * STEP
    assert "dwell-3" in JointMomentDetector(fitted=fitted, dwell_samples=3).name


def test_dwell_resets_when_the_plant_returns_to_the_manifold() -> None:
    """Two breaks, a normal moment, two more breaks: dwell-3 never accumulates across the gap."""
    fitted = MahalanobisModel(adaptive_joint_quantile=0.99).fit(plant_training())
    assert isinstance(fitted, MahalanobisFittedModel)
    observations: list[Observation] = []
    row = 0
    for _ in range(2):
        observations.extend(plant_row(row, 0.0, 20.0, outlet=40.0))
        row += 1
    observations.extend(plant_row(row, 0.1, 20.0))
    row += 1
    for _ in range(2):
        observations.extend(plant_row(row, 0.0, 20.0, outlet=40.0))
        row += 1
    corpus = Dataset(
        name="split-flicker", domain=Domain.ATLAS, observations=observations, attack_intervals=[]
    )
    assert JointMomentDetector(fitted=fitted).run(corpus)
    assert JointMomentDetector(fitted=fitted, dwell_samples=3).run(corpus) == []
