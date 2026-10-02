"""The harness: fold splitting, per-attack scoring, and the fooled-Atlas acceptance case."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.breaking.conftest import RUN_START, ground_truth, true_state_record

from phos.atlas import DEFAULT_SETTLING_WINDOW, MahalanobisModel, PhaseConditionalModel
from phos.breaking.corpus import AttackCorpus
from phos.breaking.harness import (
    BreakingConfig,
    PrecomputedDetector,
    _covers,
    _detections_of,
    _fold_boundary,
    _model_for,
    _score_attack,
    _slice,
)
from phos.breaking.outcome import DetectionVerdict
from phos.breaking.truth import TrueStateRecord
from phos.eval import Dataset, Detection, LabelledInterval
from phos.ontology import Domain, Observation
from phos.synth import PlantDescription, RunSpec
from phos.synth.attacks import AttackGroundTruth, AttackManifest, AttackType

CALM = [10.0] * 48


def observations(
    n: int, *, step_minutes: float = 30.0, feature: str = "level_m"
) -> list[Observation]:
    """Build a run of observations at fixed spacing."""
    return [
        Observation(
            timestamp=RUN_START + timedelta(minutes=step_minutes * index),
            feature=feature,
            value=10.0,
            domain=Domain.ATLAS,
            entity_ids=["ent_test0000000001"],
        )
        for index in range(n)
    ]


def dataset(n: int = 48, intervals: tuple[LabelledInterval, ...] = ()) -> Dataset:
    """A corpus of ``n`` samples with the given labels."""
    return Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=observations(n),
        attack_intervals=list(intervals),
    )


def manifest(plant: PlantDescription, *truths: AttackGroundTruth) -> AttackManifest:
    """A minimal D2 manifest carrying the given ground truth."""
    return AttackManifest(
        name="fixture-attack-corpus",
        plant_id=plant.plant_id,
        flavour=truths[0].flavour,
        spec=RunSpec(
            seed=1,
            start=RUN_START,
            duration=timedelta(hours=24),
            sample_interval=timedelta(minutes=30),
        ),
        samples=48,
        description=plant,
        attacks=tuple(truths),
    )


def corpus(plant: PlantDescription, *truths: AttackGroundTruth, tmp: Path) -> AttackCorpus:
    """An in-memory attack corpus whose truth record the caller writes."""
    return AttackCorpus(
        manifest=manifest(plant, *truths),
        dataset=dataset(48, tuple(t.interval() for t in truths)),
        truth_path=tmp / "truth.csv",
        topology_path=tmp / "topology.toml",
        directory=tmp,
    )


# --- fold splitting ------------------------------------------------------


def test_the_fold_boundary_sits_at_the_midpoint_of_a_quiet_corpus() -> None:
    data = dataset()
    boundary = _fold_boundary(data, [])
    assert boundary is not None
    assert data.observations[0].timestamp < boundary < data.observations[-1].timestamp


def test_the_boundary_walks_out_of_an_attack_it_would_have_split() -> None:
    """Splitting inside an attack would leave it half in each fold and scored in neither."""
    straddling = LabelledInterval(
        start=RUN_START + timedelta(hours=11),
        end=RUN_START + timedelta(hours=13),
        label="attack",
    )
    boundary = _fold_boundary(dataset(48, (straddling,)), [straddling])
    assert boundary is not None
    assert not straddling.contains(boundary)
    assert boundary > straddling.end


def test_a_corpus_attacked_end_to_end_has_no_usable_boundary() -> None:
    covering = LabelledInterval(
        start=RUN_START, end=RUN_START + timedelta(hours=24), label="attack"
    )
    assert _fold_boundary(dataset(48, (covering,)), [covering]) is None


def test_an_empty_corpus_has_no_boundary() -> None:
    assert _fold_boundary(dataset(0), []) is None


def test_a_slice_keeps_only_its_own_span() -> None:
    data = dataset()
    midpoint = RUN_START + timedelta(hours=12)
    early = _slice(data, data.observations[0].timestamp, midpoint, "early")
    late = _slice(data, midpoint, data.observations[-1].timestamp + timedelta(seconds=1), "late")
    assert len(early.observations) + len(late.observations) == len(data.observations)
    assert all(o.timestamp < midpoint for o in early.observations)
    assert all(o.timestamp >= midpoint for o in late.observations)


def test_a_fold_covers_only_a_window_it_wholly_contains() -> None:
    data = dataset()
    inside = LabelledInterval(
        start=RUN_START + timedelta(hours=2), end=RUN_START + timedelta(hours=3), label="attack"
    )
    straddling = LabelledInterval(
        start=RUN_START + timedelta(hours=2), end=RUN_START + timedelta(hours=30), label="attack"
    )
    assert _covers(data, inside)
    assert not _covers(data, straddling)
    assert not _covers(dataset(0), inside)


# --- per-attack scoring --------------------------------------------------


def write_truth(tmp: Path, series: dict[str, list[float]]) -> TrueStateRecord:
    """Write a truth record to disk and return it, so the harness reads the same file it judges."""
    keys = list(series)
    rows = ["timestamp," + ",".join(keys)]
    for index in range(len(series[keys[0]])):
        stamp = (RUN_START + timedelta(minutes=30 * index)).isoformat()
        rows.append(stamp + "," + ",".join(f"{series[key][index]:.5f}" for key in keys))
    (tmp / "truth.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return true_state_record(series)


def test_an_attack_with_an_alert_in_its_window_is_caught(
    plant: PlantDescription, tmp_path: Path
) -> None:
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = write_truth(tmp_path, {"level_m": CALM})
    alerts = [
        Detection(
            timestamp=RUN_START + timedelta(hours=2),
            score=1.0,
            confidence=0.5,
            entity_ids=["ent_test0000000001"],
            feature="level_m",
        )
    ]
    outcome = _score_attack(
        truth, alerts, corpus(plant, truth, tmp=tmp_path), record, timedelta(minutes=1), 3.0
    )
    assert outcome.verdict is DetectionVerdict.CAUGHT
    assert outcome.n_alerts == 1
    assert outcome.latency_seconds == pytest.approx(3600.0)


def test_a_fooled_atlas_over_a_plant_driven_into_danger_scores_as_a_miss(
    plant: PlantDescription, tmp_path: Path
) -> None:
    """The acceptance case, end to end through the harness's own scoring path.

    A liar attack: the instruments reported calm, Atlas produced no alert, and D1's true-state
    record shows the tank really ran far outside anything unattacked operation produced. The
    harness must reach `MISSED_DANGEROUS` by consulting the true state, not the readings.
    """
    runaway = list(CALM)
    for index in range(2, 7):
        runaway[index] = 40.0
    truth = ground_truth("wt-liar", AttackType.LIAR, targets=("level_m",))
    record = write_truth(tmp_path, {"level_m": runaway})

    outcome = _score_attack(
        truth, [], corpus(plant, truth, tmp=tmp_path), record, timedelta(minutes=1), 3.0
    )
    assert not outcome.detected
    assert outcome.true_state.dangerous
    assert outcome.verdict is DetectionVerdict.MISSED_DANGEROUS
    assert outcome.is_miss


def test_the_same_silence_over_a_calm_plant_is_only_an_ordinary_miss(
    plant: PlantDescription, tmp_path: Path
) -> None:
    """The contrast that proves the true-state record is what decided the verdict above."""
    truth = ground_truth("wt-liar", AttackType.LIAR, targets=("level_m",))
    record = write_truth(tmp_path, {"level_m": CALM})
    outcome = _score_attack(
        truth, [], corpus(plant, truth, tmp=tmp_path), record, timedelta(minutes=1), 3.0
    )
    assert outcome.verdict is DetectionVerdict.MISSED


def test_an_alert_outside_the_window_and_its_tolerance_does_not_count(
    plant: PlantDescription, tmp_path: Path
) -> None:
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = write_truth(tmp_path, {"level_m": CALM})
    far = [
        Detection(
            timestamp=RUN_START + timedelta(hours=20),
            score=1.0,
            confidence=0.5,
            entity_ids=["ent_test0000000001"],
            feature="level_m",
        )
    ]
    outcome = _score_attack(
        truth, far, corpus(plant, truth, tmp=tmp_path), record, timedelta(minutes=1), 3.0
    )
    assert not outcome.detected
    assert outcome.n_alerts == 0


def test_an_alert_just_before_the_window_is_forgiven_by_the_grouping_tolerance(
    plant: PlantDescription, tmp_path: Path
) -> None:
    """A subsystem event is stamped at its earliest member, so exactly this much slack is right."""
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = write_truth(tmp_path, {"level_m": CALM})
    just_before = [
        Detection(
            timestamp=RUN_START + timedelta(hours=1) - timedelta(seconds=30),
            score=1.0,
            confidence=0.5,
            entity_ids=["ent_test0000000001"],
            feature="level_m",
        )
    ]
    outcome = _score_attack(
        truth, just_before, corpus(plant, truth, tmp=tmp_path), record, timedelta(minutes=1), 3.0
    )
    assert outcome.detected
    # Forgiven into the window, so it contributes no latency: there is no time-to-detect for an
    # alert that preceded the attack.
    assert outcome.latency_seconds is None


# --- config and plumbing -------------------------------------------------


def test_the_match_tolerance_is_the_grouping_window() -> None:
    config = BreakingConfig()
    assert config.match_tolerance == config.atlas.grouping_window


def test_a_negative_danger_margin_is_refused() -> None:
    with pytest.raises(ValueError):
        BreakingConfig(danger_margin=-1.0)


# --- which model a plant is measured with (ADR 0018) ---------------------


def test_a_plant_declaring_a_phase_register_is_modelled_phase_conditionally() -> None:
    model = _model_for("batch-reactor", BreakingConfig())

    assert isinstance(model, PhaseConditionalModel)
    assert model.phase_feature == "batch_phase"


def test_every_other_plant_keeps_the_pooled_joint_model() -> None:
    """The no-harm guarantee, asserted rather than argued: the fix cannot reach these plants."""
    settings = BreakingConfig()

    for plant in ("water-treatment", "power-generation"):
        assert isinstance(_model_for(plant, settings), MahalanobisModel)


def test_clearing_the_declaration_reproduces_the_pre_fix_arrangement() -> None:
    """How the before-and-after in A-FIX-1's report was measured, from one code path."""
    model = _model_for("batch-reactor", BreakingConfig(phase_features={}))

    assert isinstance(model, MahalanobisModel)


def test_the_declaration_is_recorded_on_the_config() -> None:
    """A map cannot be compared against another map without the model choice that produced it."""
    assert BreakingConfig().phase_features == {"batch-reactor": "batch_phase"}


# --- the settling allowance (ADR 0019) -----------------------------------


def test_the_phase_model_carries_the_runs_settling_window() -> None:
    """The window is a property of the run, so it must reach the model the run fits."""
    model = _model_for("batch-reactor", BreakingConfig(settling_window=timedelta(minutes=4)))

    assert isinstance(model, PhaseConditionalModel)
    assert model.settling_window == timedelta(minutes=4)


def test_the_settling_window_defaults_to_the_measured_one() -> None:
    """Ten minutes, where ADR 0019 measured the transient to end."""
    assert BreakingConfig().settling_window == DEFAULT_SETTLING_WINDOW
    assert DEFAULT_SETTLING_WINDOW == timedelta(minutes=10)


def test_clearing_the_settling_window_reproduces_the_a_fix_1_arrangement() -> None:
    """The before-and-after switch for this PART, from one code path."""
    model = _model_for("batch-reactor", BreakingConfig(settling_window=timedelta(0)))

    assert isinstance(model, PhaseConditionalModel)
    assert model.settling_window == timedelta(0)


def test_a_negative_settling_window_is_refused() -> None:
    """A negative window has no meaning, and silently clamping one would hide a caller's mistake."""
    with pytest.raises(ValueError):
        BreakingConfig(settling_window=timedelta(seconds=-1))


def test_the_precomputed_detector_replays_what_it_was_given() -> None:
    alerts = (
        Detection(
            timestamp=RUN_START,
            score=1.0,
            confidence=0.5,
            entity_ids=["ent_test0000000001"],
            feature="level_m",
        ),
    )
    detector = PrecomputedDetector(name="fixture", detections=alerts)
    assert detector.run(dataset()) == list(alerts)


def test_detections_carry_the_events_calibrated_weight() -> None:
    from phos.ontology import Evidence, EvidenceKind

    event = Evidence(
        kind=EvidenceKind.DEVIATION,
        domain=Domain.ATLAS,
        timestamp=RUN_START,
        summary="unit-a departed",
        weight=0.75,
        entity_ids=["ent_test0000000001"],
        source_id="dev_test0000000001",
    )
    detections = _detections_of([event])
    assert detections[0].score == pytest.approx(0.75)
    assert detections[0].confidence == pytest.approx(0.75)
