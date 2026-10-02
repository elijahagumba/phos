"""Aimed at the P3 seams where several fields have to agree, and a wrong answer still looks right.

P1 and P2 both learned the same lesson: the defects worth writing tests for are not the ones that
raise. They are the ones that produce a different number, or attach a correct-looking value to the
wrong thing, and leave every surface an engineer would glance at intact. P3 adds three seams with
exactly that property.

- **A calibrated weight is attached to a finding by position.** Both promoters sort their input and
  then calibrate a parallel list of scores. If the sort and the calibration ever disagree, every
  piece of evidence carries a probability computed from *a different measurement* — the weights are
  all in range, the count is right, the ordering is right, and every number is wrong.
- **Traceability is a string that either resolves or does not.** A ``source_id`` naming an object
  the store does not hold is a dead link an operator only discovers by clicking it, so the tests
  here resolve every one rather than checking it is non-empty.
- **A timestamp decides which story a fact belongs to.** Command evidence stamped a window late
  still sorts, still stores and still reasons; it just lands in the wrong incident.

The mutation script ``scripts/mutate_command_integration.py`` injects deliberate defects at each of
these seams and checks this module turns red. A green suite nobody has tried to fool is not
evidence.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas import (
    UNKNOWN_COMMAND_RELATIONSHIP,
    AtlasEngine,
    CommandEvidence,
    MahalanobisModel,
    Subsystem,
    SubsystemMap,
    is_subsystem_event,
    member_evidence_ids,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.eval import Dataset
from phos.models import GaussianBaseline
from phos.ontology import Domain, EvidenceKind, Observation
from phos.reasoning import FittedPlattCalibrator

EPOCH = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=1)
DEVICE = "ent_10.0.0.9"
TARGET = "ent_10.0.0.20"

#: Monotone and spread across the values used below, so two findings never share a weight by
#: accident — which is what makes a mispairing visible rather than merely possible.
DISCRIMINATING = FittedPlattCalibrator(coefficient=1.0, intercept=-5.0)

#: Maps everything to exactly 0.5, for the store-integrity tests where a weight is not the
#: subject and a varying one would only be noise.
FLAT = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)


def finding(value: float, *, index: int) -> Observation:
    """Build a graph finding at window ``index`` measuring ``value``."""
    return Observation(
        entity_ids=[DEVICE, TARGET],
        feature=UNKNOWN_COMMAND_RELATIONSHIP,
        value=value,
        timestamp=EPOCH + WINDOW * index,
        domain=Domain.ATLAS,
        context={
            "issuer_ip": "10.0.0.9",
            "target_ip": "10.0.0.20",
            "function_codes": "6",
            "frames": f"/captures/plant.pcap:{index}-{index + 4}",
        },
    )


def behaviour(value: float, *, index: int, feature: str = "command_count") -> Observation:
    """Build a command-behaviour observation at window ``index``."""
    return Observation(
        entity_ids=[DEVICE],
        feature=feature,
        value=value,
        timestamp=EPOCH + WINDOW * index,
        domain=Domain.ATLAS,
        context={"device_ip": "10.0.0.9", "frames": f"/captures/plant.pcap:{index}-{index}"},
    )


def sigmoid_of(value: float) -> float:
    """What `DISCRIMINATING` maps ``value`` to, computed independently of the calibrator."""
    import math

    return 1.0 / (1.0 + math.exp(-(value - 5.0)))


# ------------------------------------------------------------------------------------------------
# A weight belongs to its own measurement
# ------------------------------------------------------------------------------------------------


def test_each_graph_finding_keeps_the_weight_computed_from_its_own_value() -> None:
    """Input order deliberately disagrees with time order, so a positional slip mispairs every one.

    Without this test a promoter that calibrated the *unsorted* scores and returned the *sorted*
    findings would pass everything else in the suite: the right number of pieces of evidence, every
    weight a probability, the output in time order, each ``source_id`` resolving. Only the pairing
    would be wrong, and only silently.
    """
    findings = [finding(9.0, index=2), finding(1.0, index=0), finding(5.0, index=1)]

    changes = promote_graph_findings(findings, DISCRIMINATING)

    for change in changes:
        assert change.evidence.weight == pytest.approx(sigmoid_of(change.finding.value))
    assert [change.finding.value for change in changes] == [1.0, 5.0, 9.0]


def test_each_command_departure_keeps_the_weight_computed_from_its_own_magnitude() -> None:
    training = [behaviour(60.0 + (index % 2), index=index) for index in range(20)]
    fitted = GaussianBaseline(name="commands").fit(training)
    # Two departures whose magnitudes the calibrator can actually tell apart — 4.0 and 9.0 learned
    # spreads — handed over in the reverse of their time order. A saturating pair would map to the
    # same weight and hide exactly the mispairing this test is aimed at.
    live = [behaviour(65.0, index=22), behaviour(62.5, index=21)]

    departures = promote_command_behaviour(live, fitted, DISCRIMINATING)

    for departure in departures:
        assert departure.evidence.weight == pytest.approx(sigmoid_of(departure.deviation.magnitude))
    assert len({departure.evidence.weight for departure in departures}) == 2


def test_a_weight_is_never_carried_across_from_a_neighbour() -> None:
    """One large finding beside small ones: a shifted pairing lands the big weight elsewhere."""
    findings = [finding(1.0, index=0), finding(1.0, index=1), finding(20.0, index=2)]

    changes = promote_graph_findings(findings, DISCRIMINATING)

    heaviest = max(changes, key=lambda change: change.evidence.weight)
    assert heaviest.finding.value == 20.0


# ------------------------------------------------------------------------------------------------
# Every traceability link resolves
# ------------------------------------------------------------------------------------------------


def topology() -> SubsystemMap:
    """A one-unit fixture map over the three signals the corpus below carries."""
    signals = frozenset({"FT01", "FT01Z", "PT01"})
    return SubsystemMap(
        [Subsystem(subsystem_id="pump-a", label="Pump A", signals=signals, source="test fixture")],
        signals,
    )


def corpus(n_rows: int, *, start: datetime = EPOCH, surge: float = 0.0) -> Dataset:
    """A small correlated three-signal corpus, optionally with a surge on one signal."""
    import math

    observations: list[Observation] = []
    for row in range(n_rows):
        cycle = 100.0 + 5.0 * math.sin(row / 6.0)
        wobble = ((row * 37) % 11 - 5) * 0.01
        for column, (signal, gain, offset) in enumerate(
            (("FT01", 1.0, 0.0), ("FT01Z", 0.5, 3.0), ("PT01", -0.2, 40.0))
        ):
            value = gain * cycle + offset + wobble + (surge if signal == "FT01" else 0.0)
            observations.append(
                Observation(
                    id=f"obs_r{row:05d}c{column:02d}",
                    entity_ids=["ent_plant00001"],
                    feature=signal,
                    value=value,
                    timestamp=start + row * timedelta(seconds=10),
                    domain=Domain.ATLAS,
                )
            )
    return Dataset(name="fixture", domain=Domain.ATLAS, observations=observations)


def command_bundle(at: datetime) -> CommandEvidence:
    """Build a bundle with one behaviour departure and one structural change."""
    training = [behaviour(60.0 + (index % 2), index=index) for index in range(20)]
    fitted = GaussianBaseline(name="commands").fit(training)
    stamp_index = int((at - EPOCH) / WINDOW)
    return CommandEvidence(
        departures=tuple(
            promote_command_behaviour([behaviour(5.0, index=stamp_index)], fitted, DISCRIMINATING)
        ),
        changes=tuple(promote_graph_findings([finding(9.0, index=stamp_index)], DISCRIMINATING)),
    )


def test_every_source_id_the_vertical_emits_resolves_inside_its_own_store() -> None:
    """No dead links. A ``source_id`` is only worth anything if the object it names is there.

    Walked exhaustively rather than sampled: a subsystem event's members, each member's deviation,
    each deviation's observation, and — for command evidence — the finding or the deviation behind
    it. An unresolvable link is a traceability failure (Constitution §3.2) and this is the only
    place that would notice one.
    """
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=FLAT,
        subsystem_map=topology(),
    )
    at = EPOCH + timedelta(seconds=1250)
    engine.run(
        corpus(60, start=EPOCH + timedelta(seconds=1200), surge=40.0), commands=command_bundle(at)
    )

    store = engine.store
    for item in store.evidence(Domain.ATLAS):
        if is_subsystem_event(item):
            for member_id in member_evidence_ids(item):
                assert store.get_evidence(member_id) is not None
            continue
        if item.kind is EvidenceKind.RELATIONSHIP_CHANGE:
            assert store.get_observation(item.source_id) is not None
            continue
        deviation = store.get_deviation(item.source_id)
        assert deviation is not None, f"{item.id} names {item.source_id}, which is not in the store"
        assert store.get_observation(deviation.observation_id) is not None


def test_a_hypothesis_never_rests_on_evidence_the_store_cannot_produce() -> None:
    engine = AtlasEngine(
        fitted=MahalanobisModel().fit(corpus(120).observations),
        calibrator=FLAT,
        subsystem_map=topology(),
    )
    at = EPOCH + timedelta(seconds=1250)
    engine.run(
        corpus(60, start=EPOCH + timedelta(seconds=1200), surge=40.0), commands=command_bundle(at)
    )

    for hypothesis in engine.store.hypotheses(Domain.ATLAS):
        for evidence_id in (*hypothesis.supporting, *hypothesis.contradictory):
            assert engine.store.get_evidence(evidence_id) is not None


# ------------------------------------------------------------------------------------------------
# A timestamp decides which story a fact belongs to
# ------------------------------------------------------------------------------------------------


def test_command_evidence_is_stamped_at_its_measurement_and_not_at_its_promotion() -> None:
    """A fact stamped anywhere else still stores and still reasons; it lands in the wrong story."""
    source = finding(9.0, index=3)

    change = promote_graph_findings([source], DISCRIMINATING)[0]

    assert change.evidence.timestamp == source.timestamp
    assert change.evidence.timestamp == EPOCH + WINDOW * 3


def test_the_two_streams_are_interleaved_by_time_and_not_by_stream() -> None:
    """A structural change must be weighed when it happened, not after every reading in the run."""
    bundle = CommandEvidence(
        departures=tuple(
            promote_command_behaviour(
                [behaviour(5.0, index=9)],
                GaussianBaseline(name="commands").fit(
                    [behaviour(60.0 + (i % 2), index=i) for i in range(20)]
                ),
                DISCRIMINATING,
            )
        ),
        changes=tuple(promote_graph_findings([finding(9.0, index=1)], DISCRIMINATING)),
    )

    stream = bundle.evidence()

    assert [item.kind for item in stream] == [
        EvidenceKind.RELATIONSHIP_CHANGE,
        EvidenceKind.DEVIATION,
    ]
    assert [item.timestamp for item in stream] == sorted(item.timestamp for item in stream)


# ------------------------------------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------------------------------------


def test_two_runs_over_one_input_agree_on_everything_but_the_minted_ids() -> None:
    findings = [finding(9.0, index=2), finding(1.0, index=0)]

    def summary(changes: Sequence[object]) -> list[tuple[float, float, str]]:
        return [
            (change.finding.value, change.evidence.weight, change.evidence.summary)  # type: ignore[attr-defined]
            for change in changes
        ]

    assert summary(promote_graph_findings(findings, DISCRIMINATING)) == summary(
        promote_graph_findings(list(reversed(findings)), DISCRIMINATING)
    )
