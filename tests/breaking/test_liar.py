"""The T1 liar runner: its corpora, its competing set and its refusals (ADR 0114).

Nothing here touches a held-out seed. The integration test uses library seed 71001, a
development seed, and is ``slow``.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest

from phos.breaking.liar import (
    Inlet,
    _leader,
    fit_inlet,
    inlet_calibrator,
    liar_corpus_config,
    run_liar_corpus,
)
from phos.eval.liar_declaration import DEVELOPMENT_SEEDS, LIAR_HELD_OUT_SEEDS, LIAR_PLANTS
from phos.library.ot import SEEDS, SUBTLETIES, liar_recipe
from phos.ontology import Domain, Hypothesis, HypothesisStatus
from phos.synth.attacks.spec import AttackType


@pytest.mark.parametrize("plant_id", LIAR_PLANTS)
def test_each_liar_plant_has_exactly_one_liar_recipe(plant_id: str) -> None:
    assert liar_recipe(plant_id).attack_type is AttackType.LIAR


def test_a_plant_without_a_liar_is_refused() -> None:
    with pytest.raises(ValueError, match="liar recipe"):
        liar_recipe("no-such-plant")


@pytest.mark.parametrize("plant_id", LIAR_PLANTS)
def test_a_corpus_holds_the_liar_once_at_every_subtlety_without_overlap(plant_id: str) -> None:
    config = liar_corpus_config(plant_id, LIAR_HELD_OUT_SEEDS[0])
    assert [plan.type for plan in config.attacks] == [AttackType.LIAR] * len(SUBTLETIES)
    assert tuple(plan.subtlety for plan in config.attacks) == SUBTLETIES
    ends = [plan.start_hours + plan.duration_hours for plan in config.attacks]
    starts = [plan.start_hours for plan in config.attacks]
    assert all(end < start for end, start in zip(ends, starts[1:], strict=False))
    assert config.duration_hours > ends[-1]
    assert config.seed == LIAR_HELD_OUT_SEEDS[0]


def test_the_calibration_seeds_are_development_seeds_not_held_out() -> None:
    assert set(SEEDS) <= DEVELOPMENT_SEEDS
    assert not set(SEEDS) & set(LIAR_HELD_OUT_SEEDS)


def _hypothesis(template_id: str, confidence: float) -> Hypothesis:
    return Hypothesis(
        label=template_id,
        template_id=template_id,
        domain=Domain.ATLAS,
        prior=0.1,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
    )


def test_the_leader_is_unique_and_contentful() -> None:
    assert _leader([]) is None
    assert _leader([_hypothesis("insufficient_evidence", 0.9)]) is None
    lead = [_hypothesis("sensor_or_device_fault", 0.6), _hypothesis("process_disturbance", 0.3)]
    assert _leader(lead) == "sensor_or_device_fault"
    tie = [_hypothesis("sensor_or_device_fault", 0.5), _hypothesis("process_disturbance", 0.5)]
    assert _leader(tie) is None


@pytest.mark.slow
def test_one_development_corpus_runs_end_to_end(tmp_path: Path) -> None:
    from phos.breaking.corpus import load_attack_corpus, load_normal_corpus
    from phos.library.ot import ot_trains
    from phos.synth.attacks.generate import generate_attack_dataset
    from phos.synth.generate import generate_dataset

    plant = "batch-reactor"
    train = next(config for config in ot_trains() if config.plant_id == plant)
    normal = load_normal_corpus(generate_dataset(train, tmp_path, with_capture=False)[0])
    config = liar_corpus_config(plant, SEEDS[0])
    corpus = load_attack_corpus(generate_attack_dataset(config, tmp_path, with_capture=False)[0])
    inlet = fit_inlet(normal)
    assert isinstance(inlet, Inlet)
    assert inlet.model.windows.lags == (0, 1, 2)  # ADR 0112 at the library's 30 s
    calibrator = inlet_calibrator(inlet, [corpus], seed=7)
    runs = run_liar_corpus(corpus, normal, inlet, calibrator)
    assert [run.subtlety for run in runs] == list(SUBTLETIES)
    assert all(len(run.opponent_alert) == 3 for run in runs)
    assert all(numpy.isfinite(run.subtlety) for run in runs)
