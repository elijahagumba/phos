"""The whole Atlas vertical: industrial readings in, competing explanations out.

This is the part where everything built for Atlas has to work together — 5A's joint model, 4A's
evidence boundary and calibrator, 5B's declared topology, this PART's grouping and OT templates,
and 4B's reasoning engine — so most of what is asserted here is about the *seams* rather than about
any one component, all of which have their own tests already.

Four seams carry the weight:

- **Grouping happens before reasoning.** Every hypothesis must rest on subsystem events, never on
  the per-signal evidence underneath them, or the confidences would be built by counting one plant
  event as many.
- **Traceability survives the whole chain.** A test walks narrative to subsystem event to member
  evidence to deviation to observation, because that is the path an operator takes and Constitution
  §3.2 says it must exist.
- **The stale-cell invariant from 5A still holds.** A carried-forward reading may inform a
  reconstruction and may never itself raise a deviation. The engine checks it rather than assuming
  the model upheld it, and both the check and the property are tested.
- **The honesty guards are present.** A logged report that omitted them would make the grouping
  number read as a detection win and the hypothesis confidences read as calibrated. Both are
  asserted.

Everything above runs on hand-built fixtures and passes on a fresh clone. The worked end-to-end
test at the bottom drives real HAI data through the vertical and skips when the corpus is absent.
"""

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

import numpy
import pytest
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from phos.atlas import (
    ATLAS_VERTICAL_CAVEATS,
    COARSE_MAP_CAVEAT,
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    UNKNOWN_COMMAND_RELATIONSHIP,
    AtlasConfig,
    AtlasEngine,
    MahalanobisModel,
    Subsystem,
    SubsystemMap,
    annotate_with_caveats,
    atlas_library,
    graph_finding_marker,
    is_subsystem_event,
    load_topology,
    member_evidence_ids,
)
from phos.atlas.command_evidence import CommandDeparture, CommandEvidence, GraphChange
from phos.eval import (
    Dataset,
    EvaluationReport,
    LabelledCsvAdapter,
    LatencySummary,
)
from phos.models import FittedModel
from phos.ontology import (
    Deviation,
    Domain,
    Evidence,
    EvidenceStore,
    ExpectedRange,
    Hypothesis,
    InMemoryEvidenceStore,
    Narrative,
    Observation,
)
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    CalibrationSplitPolicy,
    FittedCalibrator,
    IsotonicCalibrator,
    ReasoningConfig,
    evidence_from_deviation,
    evidence_from_relationship_change,
    scores_and_labels_from,
    train_calib_test_split,
)

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
ENTITY = "ent_plant00001"
STEP = timedelta(seconds=10)

PUMP_SIGNALS = ("FT01", "FT01Z", "PT01")
TANK_SIGNALS = ("LT01", "LT01Z")
ALL_SIGNALS = (*PUMP_SIGNALS, *TANK_SIGNALS)


def topology() -> SubsystemMap:
    """Return a two-unit fixture map over five signals."""
    return SubsystemMap(
        [
            Subsystem(
                subsystem_id="pump-a",
                label="Pump A",
                signals=frozenset(PUMP_SIGNALS),
                source="test fixture",
            ),
            Subsystem(
                subsystem_id="tank-b",
                label="Tank B",
                signals=frozenset(TANK_SIGNALS),
                source="test fixture",
            ),
        ],
        frozenset(ALL_SIGNALS),
    )


def _reading(signal: str, row: int) -> float:
    """Return one deterministic, correlated reading.

    Every signal is driven by the same slow cycle, with a per-signal gain and a small per-signal
    wobble so the plant is correlated without being collinear — collinear signals leave the
    covariance singular and the conditional spreads meaningless.
    """
    cycle = 100.0 + 5.0 * math.sin(row / 6.0)
    wobble = ((row * 37 + len(signal) * 13) % 11 - 5) * 0.01
    gains = {"FT01": 1.0, "FT01Z": 0.5, "PT01": -0.2, "LT01": 0.2, "LT01Z": 0.1}
    offsets = {"FT01": 0.0, "FT01Z": 3.0, "PT01": 40.0, "LT01": 20.0, "LT01Z": 7.0}
    return gains[signal] * cycle + offsets[signal] + wobble


def corpus(
    n_rows: int,
    *,
    start: datetime = EPOCH,
    surge: Mapping[str, float] | None = None,
    surge_rows: range = range(0),
    omit: frozenset[tuple[int, str]] = frozenset(),
    name: str = "fixture",
) -> Dataset:
    """Build a deterministic multi-signal corpus, optionally with a surge and a missing reading."""
    observations: list[Observation] = []
    for row in range(n_rows):
        for column, signal in enumerate(ALL_SIGNALS):
            if (row, signal) in omit:
                continue
            value = _reading(signal, row)
            if surge and row in surge_rows:
                value += surge.get(signal, 0.0)
            observations.append(
                Observation(
                    id=f"obs_r{row:05d}c{column:02d}",
                    entity_ids=[ENTITY],
                    feature=signal,
                    value=value,
                    timestamp=start + row * STEP,
                    domain=Domain.ATLAS,
                )
            )
    return Dataset(name=name, domain=Domain.ATLAS, observations=observations)


class ProportionalCalibrator(BaseModel):
    """Test calibrator: a fixed, monotone score-to-probability map. Not fitted on anything."""

    model_config = ConfigDict(frozen=True)

    name: str = "proportional"
    scale: float = 20.0

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Map scores onto ``[0, 1]`` by clipping ``score / scale``."""
        return numpy.clip(numpy.asarray(scores, dtype=float) / self.scale, 0.0, 1.0)


class OutOfRangeCalibrator(BaseModel):
    """Test calibrator that breaks its contract, to prove the engine checks rather than trusts."""

    model_config = ConfigDict(frozen=True)

    name: str = "out-of-range"

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Return values well outside ``[0, 1]``."""
        return numpy.asarray(scores, dtype=float) + 5.0


class WrongShapeCalibrator(BaseModel):
    """Test calibrator that answers a different number of questions than it was asked."""

    model_config = ConfigDict(frozen=True)

    name: str = "wrong-shape"

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        """Return one probability whatever it was given."""
        return numpy.zeros(1, dtype=float)


class ScriptedModel(FittedModel):
    """Test model that emits exactly the deviations it was handed, whatever the corpus says."""

    model_config = ConfigDict(frozen=True)

    scripted: tuple[Deviation, ...] = ()

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Return the scripted deviations, ignoring ``observations``."""
        return list(self.scripted)


def scripted(*deviations: Deviation) -> ScriptedModel:
    """Return a `ScriptedModel` emitting ``deviations``."""
    return ScriptedModel(
        name="scripted", expected_ranges={}, feature_ranges={}, emit_k=0.0, scripted=deviations
    )


def band(signal: str, low: float, high: float) -> ExpectedRange:
    """Return an expected range on ``signal`` for hand-built deviations."""
    return ExpectedRange(
        feature=signal,
        entity_id=ENTITY,
        low=low,
        high=high,
        mean=(low + high) / 2.0,
        stddev=1.0,
        learned_from_window=(EPOCH, EPOCH),
    )


def vertical(
    fitted: FittedModel,
    *,
    calibrator: FittedCalibrator | None = None,
    config: AtlasConfig | None = None,
) -> AtlasEngine:
    """Return an engine over the fixture topology and the real OT template library."""
    return AtlasEngine(
        fitted=fitted,
        calibrator=ProportionalCalibrator() if calibrator is None else calibrator,
        subsystem_map=topology(),
        config=config,
    )


def fitted_on_clean_plant(**kwargs: object) -> FittedModel:
    """Return a Mahalanobis model fitted on forty rows of undisturbed operation."""
    return MahalanobisModel.model_validate(kwargs).fit(corpus(40).observations)


def resolved_evidence(store: EvidenceStore, evidence_id: str) -> Evidence:
    """Return the evidence with this id, failing the test rather than returning ``None``."""
    evidence = store.get_evidence(evidence_id)
    assert evidence is not None, evidence_id
    return evidence


def resolved_hypothesis(store: EvidenceStore, hypothesis_id: str) -> Hypothesis:
    """Return the hypothesis with this id, failing the test rather than returning ``None``."""
    hypothesis = store.get_hypothesis(hypothesis_id)
    assert hypothesis is not None, hypothesis_id
    return hypothesis


def shape(narratives: Sequence[Narrative], store: EvidenceStore) -> list[object]:
    """Project narratives onto everything about them that is a function of the input.

    Identifiers and ``created_at`` stamps are deliberately excluded: they are a uuid and a clock,
    so two runs over one corpus can never share them, and comparing them would test the wrong
    thing.
    """
    return [
        (
            narrative.title,
            narrative.overall_confidence,
            [resolved_evidence(store, item).summary for item in narrative.evidence_ids],
            [
                (
                    resolved_hypothesis(store, item).template_id,
                    resolved_hypothesis(store, item).confidence,
                    resolved_hypothesis(store, item).status,
                )
                for item in narrative.hypothesis_ids
            ],
            len(narrative.causal_edges),
        )
        for narrative in narratives
    ]


# ------------------------------------------------------------------------------------------------
# The vertical
# ------------------------------------------------------------------------------------------------


def test_the_vertical_turns_readings_into_a_set_of_competing_explanations() -> None:
    """The headline: real observations in, a narrative holding rivals out — never one verdict."""
    engine = vertical(fitted_on_clean_plant())

    narratives = engine.run(
        corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0, "PT01": -8.0}, surge_rows=range(40, 46))
    )

    assert narratives
    for narrative in narratives:
        assert narrative.domain is Domain.ATLAS
        templates = {
            resolved_hypothesis(engine.store, item).template_id for item in narrative.hypothesis_ids
        }
        assert len(templates) > 1, "a narrative with one explanation is a verdict"
        assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in templates


def test_the_reasoning_engine_only_ever_weighs_subsystem_events() -> None:
    """Grouping precedes reasoning, and this is what that ordering has to mean.

    If a hypothesis rested on the per-signal evidence as well, one plant event would be counted
    once per instrument and every confidence downstream would be inflated by the size of the
    instrumentation.
    """
    engine = vertical(fitted_on_clean_plant())
    engine.run(corpus(60, surge=dict.fromkeys(PUMP_SIGNALS, 30.0), surge_rows=range(40, 46)))

    cited = {
        item
        for hypothesis in engine.store.hypotheses()
        for item in (*hypothesis.supporting, *hypothesis.contradictory)
    }

    assert cited
    for item in cited:
        assert is_subsystem_event(resolved_evidence(engine.store, item))


def test_a_narrative_drills_all_the_way_back_down_to_the_measurements() -> None:
    """Constitution §3.2 end to end: narrative, event, member evidence, deviation, observation."""
    engine = vertical(fitted_on_clean_plant())
    narratives = engine.run(
        corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    )
    store = engine.store

    walked = 0
    for narrative in narratives:
        for event_id in narrative.evidence_ids:
            event = resolved_evidence(store, event_id)
            reached: set[str] = set()
            for member_id in member_evidence_ids(event):
                member = resolved_evidence(store, member_id)
                deviation = store.get_deviation(member.source_id)
                assert deviation is not None
                observation = store.get_observation(deviation.observation_id)
                assert observation is not None
                reached.add(observation.feature)
                walked += 1
            assert sorted(reached) == event.entity_ids

    assert walked, "no narrative had any evidence to walk"


def test_the_engine_stores_every_object_it_produced() -> None:
    """Nothing the run produced is left dangling.

    A narrative whose parts are not in the store cannot be reconstructed — and
    `InMemoryEvidenceStore` refuses a dangling reference on write anyway, so this also proves the
    engine writes its objects in an order that satisfies referential integrity.
    """
    engine = vertical(fitted_on_clean_plant())
    narratives = engine.run(
        corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    )

    assert engine.store.deviations()
    assert engine.store.evidence(Domain.ATLAS)
    assert engine.store.hypotheses(Domain.ATLAS)
    assert [narrative.id for narrative in engine.store.narratives()] == [
        narrative.id for narrative in narratives
    ]
    for narrative in narratives:
        assert narrative.timeline(engine.store)


def test_a_quiet_plant_produces_no_narrative_at_all() -> None:
    engine = vertical(fitted_on_clean_plant())

    assert engine.run(corpus(20)) == []
    assert engine.store.evidence() == []


def test_the_same_corpus_twice_produces_the_same_narratives() -> None:
    """Determinism (Constitution §3.7), asserted on everything except identity and the clock."""
    disturbed = corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    first = vertical(fitted_on_clean_plant())
    second = vertical(fitted_on_clean_plant())

    assert shape(first.run(disturbed), first.store) == shape(second.run(disturbed), second.store)


def test_everything_the_vertical_produces_serialises() -> None:
    engine = vertical(fitted_on_clean_plant())
    narratives = engine.run(
        corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    )

    for narrative in narratives:
        assert json.loads(narrative.model_dump_json())["domain"] == "ATLAS"
    for evidence in engine.store.evidence():
        assert json.loads(evidence.model_dump_json())["kind"] == "DEVIATION"
    for hypothesis in engine.store.hypotheses():
        assert 0.0 <= json.loads(hypothesis.model_dump_json())["confidence"] <= 1.0


def test_the_default_library_is_the_ot_one() -> None:
    engine = AtlasEngine(
        fitted=fitted_on_clean_plant(),
        calibrator=ProportionalCalibrator(),
        subsystem_map=topology(),
    )
    engine.run(corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46)))

    registered = {template.template_id for template in atlas_library().for_domain(Domain.ATLAS)}
    spawned = {hypothesis.template_id for hypothesis in engine.store.hypotheses()}

    assert spawned <= registered
    assert spawned & {"sensor_or_device_fault", "process_disturbance"}


# ------------------------------------------------------------------------------------------------
# The boundary and the invariants the engine must not lose
# ------------------------------------------------------------------------------------------------


def test_an_in_band_candidate_never_becomes_evidence() -> None:
    """4A's boundary, still holding here: a candidate that never left its range is a non-event."""
    observation = Observation(
        id="obs_r00000c00",
        entity_ids=[ENTITY],
        feature="FT01",
        value=100.0,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
    )
    inside = Deviation(
        observation_id=observation.id,
        expected=band("FT01", 90.0, 110.0),
        magnitude=9.0,
        timestamp=EPOCH,
    )
    dataset = Dataset(name="one", domain=Domain.ATLAS, observations=[observation])

    engine = vertical(scripted(inside))

    assert engine.run(dataset) == []
    assert engine.store.evidence() == []


def test_a_carried_forward_reading_never_raises_a_deviation_through_the_vertical() -> None:
    """5A's stale-cell invariant, checked where it is easiest to lose: after the whole chain.

    The corpus below has a hole — ``PT01`` is not sampled at one instant — while its neighbours
    surge around it. The carried value legitimately informs the reconstruction of the rest of the
    plant; what it must never do is produce a deviation of its own, because there is no measurement
    at that instant for one to point back to.
    """
    hole = 43
    engine = vertical(fitted_on_clean_plant())
    engine.run(
        corpus(
            60,
            surge={"FT01": 40.0, "FT01Z": 20.0},
            surge_rows=range(40, 46),
            omit=frozenset({(hole, "PT01")}),
        )
    )

    stale_instant = EPOCH + hole * STEP
    for deviation in engine.store.deviations():
        observation = engine.store.get_observation(deviation.observation_id)
        assert observation is not None
        assert observation.timestamp == deviation.timestamp
        assert observation.feature == deviation.expected.feature
        assert not (deviation.timestamp == stale_instant and deviation.expected.feature == "PT01")


def test_the_engine_refuses_a_deviation_that_does_not_describe_a_fresh_measurement() -> None:
    """The guard behind the invariant above, rather than a hope that every model upholds it."""
    observation = Observation(
        id="obs_r00000c00",
        entity_ids=[ENTITY],
        feature="PT01",
        value=999.0,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
    )
    mislabelled = Deviation(
        observation_id=observation.id,
        expected=band("FT01", 0.0, 1.0),
        magnitude=9.0,
        timestamp=EPOCH,
    )
    dataset = Dataset(name="one", domain=Domain.ATLAS, observations=[observation])

    with pytest.raises(ValueError, match="fresh measurement"):
        vertical(scripted(mislabelled)).run(dataset)


def test_a_deviation_for_an_observation_the_corpus_does_not_hold_raises() -> None:
    orphan = Deviation(
        observation_id="obs_missing",
        expected=band("FT01", 0.0, 1.0),
        magnitude=9.0,
        timestamp=EPOCH,
    )
    dataset = Dataset(name="empty", domain=Domain.ATLAS, observations=[])

    with pytest.raises(ValueError, match="unknown observation"):
        vertical(scripted(orphan)).run(dataset)


def test_a_calibrator_that_does_not_return_probabilities_raises() -> None:
    """§3.3 at the one place an uncalibrated number could enter reasoning as an evidence weight."""
    observation = Observation(
        id="obs_r00000c00",
        entity_ids=[ENTITY],
        feature="FT01",
        value=999.0,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
    )
    outside = Deviation(
        observation_id=observation.id,
        expected=band("FT01", 0.0, 1.0),
        magnitude=9.0,
        timestamp=EPOCH,
    )
    dataset = Dataset(name="one", domain=Domain.ATLAS, observations=[observation])

    with pytest.raises(ValueError, match="outside"):
        vertical(scripted(outside), calibrator=OutOfRangeCalibrator()).run(dataset)


def test_a_calibrator_that_answers_a_different_number_of_questions_raises() -> None:
    observation = Observation(
        id="obs_r00000c00",
        entity_ids=[ENTITY],
        feature="FT01",
        value=999.0,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
    )
    outside = Deviation(
        observation_id=observation.id,
        expected=band("FT01", 0.0, 1.0),
        magnitude=9.0,
        timestamp=EPOCH,
    )
    second = Deviation(
        observation_id=observation.id,
        expected=band("FT01", 0.0, 1.0),
        magnitude=7.0,
        timestamp=EPOCH,
    )
    dataset = Dataset(name="one", domain=Domain.ATLAS, observations=[observation])

    with pytest.raises(ValueError, match="probabilities"):
        vertical(scripted(outside, second), calibrator=WrongShapeCalibrator()).run(dataset)


def test_running_a_second_time_reuses_the_observations_already_stored() -> None:
    """The store holds one copy of a measurement however many times it is explained.

    An observation is a fact about the plant, not about a run, and re-adding one would be rejected
    outright by the store — so this is what lets a caller accumulate several runs into one store
    and still walk the drill-down path afterwards.
    """
    engine = vertical(fitted_on_clean_plant())
    disturbed = corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))

    engine.run(disturbed)
    observations = len(engine.store.observations())
    deviations = len(engine.store.deviations())
    engine.run(disturbed)

    assert observations > 0
    assert len(engine.store.observations()) == observations
    assert len(engine.store.deviations()) == 2 * deviations


def test_a_non_positive_grouping_window_raises() -> None:
    with pytest.raises(ValueError, match="positive duration"):
        AtlasConfig(grouping_window=timedelta(0))


def test_the_config_carries_the_reasoning_settings_through() -> None:
    config = AtlasConfig(
        grouping_window=timedelta(seconds=30),
        reasoning=ReasoningConfig(correlation_window=timedelta(minutes=5)),
    )

    assert config.reasoning.correlation_window == timedelta(minutes=5)
    assert config.grouping_window == timedelta(seconds=30)


# ------------------------------------------------------------------------------------------------
# The honesty guards
# ------------------------------------------------------------------------------------------------


def blank_report() -> EvaluationReport:
    """Return a minimal report to annotate."""
    return EvaluationReport(
        detector_name="atlas-vertical",
        dataset_name="fixture",
        domain=Domain.ATLAS,
        seed=11,
        source_note="fixture corpus",
        alert_threshold=0.0,
        match_tolerance_seconds=0.0,
        calibration_bins=10,
        n_observations=1,
        n_detections=1,
        n_alerts=1,
        n_attack_intervals=1,
        normal_hours=1.0,
        window_recall=1.0,
        false_positives=0,
        false_positive_rate=0.0,
        precision=1.0,
        recall_sample=1.0,
        f1=1.0,
        latency=LatencySummary(count=0),
        expected_calibration_error=0.0,
        brier_score=0.0,
    )


def test_the_report_carries_both_honesty_guards() -> None:
    """PART 5C §2: neither caveat is commentary, and a report without them is not shippable.

    The first stops a large grouping reduction being read as a detection win; the second stops a
    hypothesis confidence being read as a calibrated probability.
    """
    annotated = annotate_with_caveats(blank_report())

    assert COARSE_MAP_CAVEAT in annotated.source_note
    assert UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT in annotated.source_note
    assert "§3.3" in UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT
    for caveat in ATLAS_VERTICAL_CAVEATS:
        assert caveat in annotated.source_note


def test_annotating_keeps_the_reports_own_provenance() -> None:
    annotated = annotate_with_caveats(blank_report())

    assert annotated.source_note.startswith("fixture corpus")
    assert annotated.window_recall == 1.0


def test_annotating_twice_changes_nothing() -> None:
    once = annotate_with_caveats(blank_report())

    assert annotate_with_caveats(once).source_note == once.source_note


# ------------------------------------------------------------------------------------------------
# The worked end-to-end run on real HAI data
# ------------------------------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HAI_MANIFEST = DATA_DIR / "hai" / "manifest.json"
HAI_TOPOLOGY = DATA_DIR / "hai" / "topology.toml"

#: Duplicated from `scripts/calibrate_corpora.py` rather than imported, so these tests do not
#: depend on anything under ``scripts/``. HAI's attacks all fall in the first half of its test
#: file, so the default fractions leave a test slice with nothing to be right about.
HAI_POLICY = CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30)
HAI_SEED = 11


def hai_present() -> bool:
    """Return whether the git-ignored HAI corpus and its topology are both on disk."""
    if not (HAI_MANIFEST.is_file() and HAI_TOPOLOGY.is_file()):
        return False
    manifest = json.loads(HAI_MANIFEST.read_text(encoding="utf-8"))
    return bool((DATA_DIR / manifest["path"]).is_file())


needs_hai = pytest.mark.skipif(
    not hai_present(),
    reason=(
        f"HAI corpus not present; run scripts/fetch_datasets.py --all (see {DATA_DIR}/README.md)"
    ),
)


@cache
def hai_vertical() -> tuple[AtlasEngine, Dataset, list[Narrative]]:
    """Run the whole vertical once on HAI's test slice and cache the result.

    The same three-way split every Atlas measurement uses: the model is fitted on the attack-free
    prefix, the calibrator on the middle slice, and the vertical runs on the test slice, so neither
    has seen the data the narratives come from.
    """
    manifest = json.loads(HAI_MANIFEST.read_text(encoding="utf-8"))
    fields = {
        key: value
        for key, value in manifest.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    loaded = LabelledCsvAdapter.model_validate(
        {**fields, "path": str(DATA_DIR / manifest["path"])}
    ).load()
    train, calib, test = train_calib_test_split(loaded, HAI_POLICY)

    fitted = MahalanobisModel().fit(train.observations)
    scores, labels = scores_and_labels_from(fitted, calib)
    engine = AtlasEngine(
        fitted=fitted,
        calibrator=IsotonicCalibrator(seed=HAI_SEED).fit(scores, labels),
        subsystem_map=load_topology(
            HAI_TOPOLOGY,
            {observation.feature for observation in loaded.observations},
            corpus="hai",
        ),
    )
    return engine, test, engine.run(test)


@needs_hai
@pytest.mark.slow
def test_the_whole_vertical_runs_on_hai_and_explains_a_real_subsystem_event() -> None:
    """The worked example: one narrative from real industrial telemetry, inspected in full."""
    engine, _, narratives = hai_vertical()
    assert narratives

    narrative = narratives[0]
    events = [resolved_evidence(engine.store, item) for item in narrative.evidence_ids]
    hypotheses = [resolved_hypothesis(engine.store, item) for item in narrative.hypothesis_ids]

    assert all(is_subsystem_event(event) for event in events)
    assert all(event.summary.startswith(("p1-", "p2-", "p3-", "p4-")) for event in events)
    assert len({hypothesis.template_id for hypothesis in hypotheses}) > 1
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in {h.template_id for h in hypotheses}
    assert all(0.0 <= hypothesis.confidence <= 1.0 for hypothesis in hypotheses)
    assert narrative.overall_confidence is None


@needs_hai
@pytest.mark.slow
def test_grouping_leaves_an_operator_materially_fewer_things_to_investigate_on_hai() -> None:
    """The counting claim, on the corpus it was written for — and only the counting claim."""
    engine, _, _ = hai_vertical()
    stored = engine.store.evidence(Domain.ATLAS)
    events = [item for item in stored if is_subsystem_event(item)]
    per_signal = [item for item in stored if not is_subsystem_event(item)]

    assert per_signal
    assert len(events) * 2 < len(per_signal)


@needs_hai
@pytest.mark.slow
def test_grouping_on_hai_discards_no_evidence_at_all() -> None:
    """The constraint the counting win must not be bought with: coverage is untouched."""
    engine, _, _ = hai_vertical()
    stored = engine.store.evidence(Domain.ATLAS)
    events = [item for item in stored if is_subsystem_event(item)]
    per_signal = [item for item in stored if not is_subsystem_event(item)]

    covered = [member for event in events for member in member_evidence_ids(event)]

    assert sorted(covered) == sorted(item.id for item in per_signal)


@needs_hai
@pytest.mark.slow
def test_grouping_on_hai_keeps_every_attack_window_it_had_covered() -> None:
    """Recall at the grouped level, measured rather than assumed unchanged (§9.7).

    A subsystem event covers an attack window when any of its members fell inside it, which is the
    span the event stands for. Asserting equality with the per-signal coverage is what would catch
    grouping quietly dropping an incident.
    """
    engine, test, _ = hai_vertical()
    stored = engine.store.evidence(Domain.ATLAS)
    per_signal = {item.id: item for item in stored if not is_subsystem_event(item)}

    caught_before = {
        index
        for index, interval in enumerate(test.attack_intervals)
        for item in per_signal.values()
        if interval.contains(item.timestamp)
    }
    caught_after = {
        index
        for index, interval in enumerate(test.attack_intervals)
        for event in stored
        if is_subsystem_event(event)
        and any(
            interval.contains(per_signal[member].timestamp) for member in member_evidence_ids(event)
        )
    }

    assert caught_after == caught_before


# ------------------------------------------------------------------------------------------------
# PART P3: command evidence alongside the sensor evidence
# ------------------------------------------------------------------------------------------------
#
# The vertical's fifth seam. Command evidence arrives already promoted — it comes through the same
# boundary, from a different measurement — so the engine's job is to store its whole traceability
# chain and to put it in front of the same templates, in one interleaved stream.


def command_bundle(weight: float = 1.0, *, at: datetime = EPOCH) -> CommandEvidence:
    """Build the command path's output directly: one behaviour departure, one graph change."""
    observation = Observation(
        entity_ids=["ent_10.0.0.9"],
        feature="write_command_share",
        value=0.9,
        timestamp=at,
        domain=Domain.ATLAS,
        context={"device_ip": "10.0.0.9", "frames": "/captures/plant.pcap:0-59"},
    )
    expected = ExpectedRange(
        feature="write_command_share",
        entity_id="ent_10.0.0.9",
        low=0.0,
        high=0.2,
        mean=0.1,
        stddev=0.05,
        learned_from_window=(at - timedelta(hours=1), at),
    )
    deviation = Deviation(
        observation_id=observation.id, expected=expected, magnitude=16.0, timestamp=at
    )
    finding = Observation(
        entity_ids=["ent_10.0.0.9", "ent_10.0.0.20"],
        feature=UNKNOWN_COMMAND_RELATIONSHIP,
        value=5.0,
        timestamp=at,
        domain=Domain.ATLAS,
        context={
            "issuer_ip": "10.0.0.9",
            "target_ip": "10.0.0.20",
            "function_codes": "6",
            "frames": "/captures/plant.pcap:0-4",
        },
    )
    return CommandEvidence(
        departures=(
            CommandDeparture(
                observation=observation,
                deviation=deviation,
                evidence=evidence_from_deviation(
                    deviation, observation, weight, summary="10.0.0.9 wrote far more than usual"
                ),
            ),
        ),
        changes=(
            GraphChange(
                finding=finding,
                evidence=evidence_from_relationship_change(
                    finding,
                    weight,
                    summary=(
                        f"{graph_finding_marker(UNKNOWN_COMMAND_RELATIONSHIP)} "
                        "10.0.0.9 commanded 10.0.0.20 for the first time"
                    ),
                ),
            ),
        ),
    )


def test_the_vertical_reasons_over_command_evidence_alongside_the_readings() -> None:
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=ProportionalCalibrator(),
        subsystem_map=topology(),
    )

    bundle = command_bundle(at=EPOCH + 125 * STEP)
    narratives = engine.run(
        corpus(60, start=EPOCH + 120 * STEP, surge={"FT01": 40.0}, surge_rows=range(20, 30)),
        commands=bundle,
    )

    told = {evidence_id for narrative in narratives for evidence_id in narrative.evidence_ids}
    assert {item.id for item in bundle.evidence()} <= told

    # The structural change did its work: it is attached to the malicious explanation and argues
    # against the benign one, which is the whole reason the capture was read.
    malicious = next(
        hypothesis
        for hypothesis in engine.store.hypotheses(Domain.ATLAS)
        if hypothesis.template_id == UNAUTHORISED_CONTROL_TEMPLATE_ID
    )
    upset = next(
        hypothesis
        for hypothesis in engine.store.hypotheses(Domain.ATLAS)
        if hypothesis.template_id == PROCESS_DISTURBANCE_TEMPLATE_ID
    )
    structural = bundle.changes[0].evidence.id
    assert structural in malicious.supporting
    assert structural in upset.contradictory
    assert malicious.confidence > upset.confidence
    maintenance = next(
        hypothesis
        for hypothesis in engine.store.hypotheses(Domain.ATLAS)
        if hypothesis.template_id == ENGINEERING_MAINTENANCE_TEMPLATE_ID
    )
    assert structural in maintenance.contradictory
    assert malicious.confidence > maintenance.confidence


def test_command_evidence_keeps_its_whole_traceability_chain_in_the_store() -> None:
    """Evidence stored without what it came from leaves a source_id pointing at nothing."""
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=ProportionalCalibrator(),
        subsystem_map=topology(),
    )
    bundle = command_bundle(at=EPOCH + 125 * STEP)

    engine.run(corpus(30, start=EPOCH + 120 * STEP), commands=bundle)

    departure = bundle.departures[0]
    assert engine.store.get_evidence(departure.evidence.id) is not None
    assert engine.store.get_deviation(departure.deviation.id) is not None
    assert engine.store.get_observation(departure.observation.id) is not None
    change = bundle.changes[0]
    assert engine.store.get_evidence(change.evidence.id) is not None
    # The finding is stored as the ordinary Observation it is, so the evidence's source_id opens.
    assert engine.store.get_observation(change.finding.id) is not None


def test_command_evidence_is_never_grouped_into_a_subsystem_event() -> None:
    """5B's map partitions a plant's signals; a device on a network is not one of them."""
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=ProportionalCalibrator(),
        subsystem_map=topology(),
    )
    bundle = command_bundle(at=EPOCH + 125 * STEP)

    engine.run(
        corpus(60, start=EPOCH + 120 * STEP, surge={"FT01": 40.0}, surge_rows=range(20, 30)),
        commands=bundle,
    )

    events = [item for item in engine.store.evidence(Domain.ATLAS) if is_subsystem_event(item)]
    members = {member for event in events for member in member_evidence_ids(event)}
    assert bundle.departures[0].evidence.id not in members
    assert bundle.changes[0].evidence.id not in members


def test_the_vertical_runs_unchanged_when_no_capture_was_read() -> None:
    """Command evidence is optional, and its absence must not change a sensor-only run."""

    def run(commands: CommandEvidence | None) -> int:
        engine = AtlasEngine(
            fitted=MahalanobisModel().fit(corpus(120).observations),
            calibrator=ProportionalCalibrator(),
            subsystem_map=topology(),
        )
        engine.run(corpus(30, start=EPOCH + 120 * STEP), commands=commands)
        return len(engine.store.evidence(Domain.ATLAS))

    assert run(None) == run(CommandEvidence())


def two_bursts(start: datetime) -> Dataset:
    """A corpus surging at the start and again ten minutes later, with calm in between."""
    surging = corpus(70, start=start, surge={"FT01": 40.0}, surge_rows=range(0, 70))
    calm = corpus(70, start=start)
    loud = set(range(0, 3)) | set(range(60, 63))
    observations = [
        (surging if index // len(ALL_SIGNALS) in loud else calm).observations[index]
        for index in range(len(calm.observations))
    ]
    return Dataset(name="two-bursts", domain=Domain.ATLAS, observations=observations)


def test_a_structural_change_is_weighed_with_the_readings_it_happened_among() -> None:
    """Aimed at a miss the mutation script found: the engine's two evidence streams must interleave.

    Concatenating two already-ordered lists is cheaper than sorting them and looks harmless, and
    nothing caught it — the run completes, every fact is stored, and a single accumulating
    hypothesis's confidence is order-independent anyway. What it breaks is *which* hypothesis
    accumulates. `ReasoningEngine` starts a fresh one when evidence arrives outside the correlation
    window of the last, so a structural change appended after a long run of readings is weighed as
    though it happened at the end, and the story it belonged to no longer holds it.

    The fixture makes that observable: two surges ten minutes apart, and a structural change
    stamped with the first. Interleaved, the change and the first surge's event land on one
    hypothesis; appended, the change arrives after the second surge and starts a third of its own.
    """
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=ProportionalCalibrator(),
        subsystem_map=topology(),
        config=AtlasConfig(reasoning=ReasoningConfig(correlation_window=timedelta(minutes=2))),
    )
    live_start = EPOCH + 120 * STEP
    bundle = command_bundle(at=live_start)

    engine.run(two_bursts(live_start), commands=bundle)

    structural = bundle.changes[0].evidence.id
    holder = next(
        hypothesis
        for hypothesis in engine.store.hypotheses(Domain.ATLAS)
        if structural in hypothesis.supporting
    )
    early = [
        item
        for item in engine.store.evidence(Domain.ATLAS)
        if is_subsystem_event(item) and item.timestamp < live_start + timedelta(minutes=2)
    ]
    assert early, "the fixture must produce a subsystem event alongside the structural change"
    assert any(item.id in holder.supporting for item in early)


def test_a_command_bundle_recorded_twice_is_stored_once() -> None:
    """Two runs against one store must not double-store a bundle, and must not abort on it either.

    `AtlasEngine` takes a store so several runs can accumulate in it, and `EvidenceStore` refuses a
    duplicate id. The sensor path never meets that refusal because `_promote` mints fresh evidence
    every run — but a `CommandEvidence` bundle is built once by the caller and keeps its identity,
    so scoring a long capture in overlapping slices would otherwise abort partway through with half
    its evidence already written.
    """
    store = InMemoryEvidenceStore()
    fitted = MahalanobisModel().fit(corpus(120).observations)
    bundle = command_bundle(at=EPOCH + 125 * STEP)

    for _ in range(2):
        AtlasEngine(
            fitted=fitted,
            calibrator=ProportionalCalibrator(),
            subsystem_map=topology(),
            store=store,
        ).run(corpus(30, start=EPOCH + 120 * STEP), commands=bundle)

    stored = store.observations(Domain.ATLAS)
    for identifier in (bundle.departures[0].observation.id, bundle.changes[0].finding.id):
        assert len([item for item in stored if item.id == identifier]) == 1
    assert (
        len([item for item in store.deviations() if item.id == bundle.departures[0].deviation.id])
        == 1
    )
    for item in bundle.evidence():
        assert store.get_evidence(item.id) is not None
