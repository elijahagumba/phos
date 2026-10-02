"""The command path's plumbing: when it declines to run, and how a fold's span is carved out.

No packet capture is built here. Reading a ``.pcap`` is P1's job and is tested there. What needs
covering at this level is the decisions D3 makes *around* that: the three honest reasons there is
no command measurement to make, the promotion of an already-read path, and the restriction of a
bundle to one fold's span so the two folds do not both score the same evidence.
"""

from datetime import timedelta
from pathlib import Path

import numpy
import pytest
from tests.breaking.conftest import ground_truth
from tests.breaking.test_integration import (
    attack,
    run_start,
    toy_plant,
    write_corpus,
    write_normal,
)

from phos.atlas.command_evidence import CommandDeparture, CommandEvidence, GraphChange
from phos.breaking.commands import CommandPath
from phos.breaking.corpus import (
    AttackCorpus,
    NormalCorpus,
    load_attack_corpus,
    load_normal_corpus,
)
from phos.breaking.harness import (
    BreakingConfig,
    _command_calibrator,
    _command_path,
    _within,
)
from phos.eval import Dataset
from phos.models import GaussianBaseline
from phos.ontology import (
    Deviation,
    Domain,
    Evidence,
    EvidenceKind,
    ExpectedRange,
    Observation,
)
from phos.reasoning import PlattCalibrator
from phos.synth.attacks import AttackType

ENTITY = "ent_test0000000001"


def observation(offset_minutes: float, value: float = 1.0) -> Observation:
    """One command-behaviour reading, as `featurise_commands` would produce it."""
    return Observation(
        timestamp=run_start() + timedelta(minutes=offset_minutes),
        feature="write_rate",
        value=value,
        domain=Domain.ATLAS,
        entity_ids=[ENTITY],
    )


def evidence_at(offset_minutes: float) -> Evidence:
    """One piece of evidence stamped at a known instant."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        domain=Domain.ATLAS,
        timestamp=run_start() + timedelta(minutes=offset_minutes),
        summary="a device began writing",
        weight=0.5,
        entity_ids=[ENTITY],
        source_id="dev_test0000000001",
    )


def departure_at(offset_minutes: float) -> CommandDeparture:
    """A command-behaviour departure, assembled without running the packet path."""
    reading = observation(offset_minutes)
    return CommandDeparture(
        observation=reading,
        deviation=Deviation(
            observation_id=reading.id,
            expected=ExpectedRange(
                feature=reading.feature,
                entity_id=ENTITY,
                low=0.0,
                high=0.5,
                mean=0.25,
                stddev=0.1,
                learned_from_window=(run_start(), run_start() + timedelta(hours=1)),
            ),
            magnitude=3.0,
            timestamp=reading.timestamp,
        ),
        evidence=evidence_at(offset_minutes),
    )


def change_at(offset_minutes: float) -> GraphChange:
    """A structural graph finding, assembled the same way."""
    return GraphChange(
        finding=observation(offset_minutes, 1.0), evidence=evidence_at(offset_minutes)
    )


def span(start_minutes: float, end_minutes: float) -> Dataset:
    """A fold's test slice, described only by the span its observations cover."""
    return Dataset(
        name="fold",
        domain=Domain.ATLAS,
        observations=[observation(start_minutes), observation(end_minutes)],
    )


# --- restricting a bundle to one fold ------------------------------------


def test_a_bundle_is_cut_down_to_the_folds_own_span() -> None:
    """Both folds would otherwise score the same command evidence, double-counting it."""
    bundle = CommandEvidence(
        departures=(departure_at(10.0), departure_at(400.0)),
        changes=(change_at(20.0), change_at(500.0)),
    )
    early = _within(bundle, span(0.0, 100.0))
    late = _within(bundle, span(300.0, 600.0))
    assert len(early.departures) == 1
    assert len(early.changes) == 1
    assert len(late.departures) == 1
    assert len(late.changes) == 1
    assert len(early.evidence()) + len(late.evidence()) == len(bundle.evidence())


def test_a_fold_with_no_observations_gets_nothing() -> None:
    bundle = CommandEvidence(departures=(departure_at(10.0),), changes=(change_at(20.0),))
    empty = Dataset(name="fold", domain=Domain.ATLAS, observations=[])
    assert _within(bundle, empty).evidence() == ()


# --- the command calibrator ----------------------------------------------


def test_no_command_features_in_a_fold_means_no_calibrator() -> None:
    """Returning None rather than raising.

    A fold whose commands produced nothing has nothing to calibrate, and that is a result the caller
    reports rather than a failure of the run.
    """
    fitted = GaussianBaseline().fit([observation(index) for index in range(40)])
    assert _command_calibrator([], fitted, span(0.0, 100.0)) is None


def test_single_class_command_features_yield_no_calibrator() -> None:
    """A constant calibrator would post a perfect ECE while carrying no information."""
    features = [observation(index, value=1.0) for index in range(40)]
    fitted = GaussianBaseline().fit(features)
    unlabelled = Dataset(
        name="fold",
        domain=Domain.ATLAS,
        observations=features,
        attack_intervals=[],
    )
    assert _command_calibrator(features, fitted, unlabelled) is None


# --- promoting an already-read path --------------------------------------


def test_a_read_path_promotes_both_streams_with_the_calibrator_it_is_given() -> None:
    """`CommandPath` exists so a two-fold run reads each capture once and only re-weighs it."""
    features = [observation(index, value=float(index % 4)) for index in range(60)]
    fitted = GaussianBaseline().fit(features)
    calibrator = PlattCalibrator(seed=7).fit(
        numpy.asarray([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        numpy.asarray([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
    )
    path = CommandPath(live_features=tuple(features), graph_findings=(), fitted=fitted)
    bundle = path.promote(calibrator)
    assert isinstance(bundle, CommandEvidence)
    # Every promoted piece carries a weight the calibrator produced, in [0, 1].
    assert all(0.0 <= item.weight <= 1.0 for item in bundle.evidence())


# --- the three honest reasons there is nothing to measure ----------------


def test_the_pass_can_be_switched_off(tmp_path: Path) -> None:
    corpus, normal = _command_corpora(tmp_path)
    settings = BreakingConfig(measure_commands=False)
    assert _command_path(corpus, normal, settings) is None


def test_a_plant_with_no_command_attacks_has_nothing_to_measure(tmp_path: Path) -> None:
    """The batch reactor's case: no control network, so no command attack can exist on it."""
    plant = toy_plant()
    attacked = tmp_path / "synth-attack-toy-sensors-only"
    normal = tmp_path / "synth-toy-train"
    write_corpus(
        attacked,
        plant,
        attacks=(
            attack(
                "sensor-only",
                AttackType.BLATANT,
                subtlety=0.0,
                start_hours=3.0,
                targets=("pump_pct",),
            ),
        ),
    )
    write_normal(normal, plant)
    assert (
        _command_path(load_attack_corpus(attacked), load_normal_corpus(normal), BreakingConfig())
        is None
    )


def test_a_missing_capture_is_reported_rather_than_guessed(tmp_path: Path) -> None:
    """Command attacks are declared but no capture was shipped: measured as absent, not invented."""
    corpus, normal = _command_corpora(tmp_path)
    assert not (corpus.directory / "capture.pcap").exists()
    assert _command_path(corpus, normal, BreakingConfig()) is None


def _command_corpora(tmp_path: Path) -> tuple[AttackCorpus, NormalCorpus]:
    """A battery declaring command attacks, with no capture file beside it."""
    plant = toy_plant()
    attacked = tmp_path / "synth-attack-toy-commands"
    normal = tmp_path / "synth-toy-train"
    write_corpus(
        attacked,
        plant,
        attacks=(
            attack(
                "rogue",
                AttackType.ROGUE_COMMAND,
                subtlety=0.0,
                start_hours=3.0,
                targets=("pump_pct",),
                issuer="dev-1",
            ),
        ),
    )
    write_normal(normal, plant)
    return load_attack_corpus(attacked), load_normal_corpus(normal)


def test_a_command_attack_is_recognised_from_its_type() -> None:
    """Guards the routing: only these two types put anything on the wire."""
    assert AttackType.ROGUE_COMMAND.is_command_attack
    assert AttackType.MIMIC_COMMAND.is_command_attack
    assert not AttackType.BLATANT.is_command_attack
    assert not ground_truth("a", AttackType.LIAR).type.is_command_attack


@pytest.mark.parametrize("offset", [0.0, 50.0, 100.0])
def test_the_span_boundaries_are_inclusive(offset: float) -> None:
    """An event exactly on a fold's edge belongs to that fold rather than falling between them."""
    bundle = CommandEvidence(departures=(departure_at(offset),))
    assert len(_within(bundle, span(0.0, 100.0)).departures) == 1
