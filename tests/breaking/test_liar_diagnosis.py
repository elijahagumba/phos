"""S2 of the learning engine (ADR 0119): why a liar run failed, by a declared precedence.

Unit tests drive `classify` with hand-built runs, one per clause. The integration test generates
development seed 4242 for one plant and is ``slow``. No held-out seed is generated or read.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from phos.atlas.consistency import THRESHOLD
from phos.breaking.liar import LiarRun
from phos.breaking.liar_diagnosis import (
    LIAR_PRECEDENCE,
    LiarDiagnosis,
    classify,
    refuse_held_out,
    write_report,
)
from phos.eval.liar_declaration import LEADING_TEMPLATE_ID, LIAR_HELD_OUT_SEEDS

FAILED = LiarRun(
    plant_id="water-treatment",
    seed=4242,
    subtlety=0.4,
    attack_id="wt-liar-s4242",
    scored=True,
    passes=False,
    leader_with_inlet="normal_operation",
    leads_without_inlet=False,
    leader_without_inlet=None,
    opponent_alert=(False, False, False),
)
ABOVE = THRESHOLD + 0.5


def test_an_unscored_run_is_not_a_verdict_on_the_detector() -> None:
    assert classify(replace(FAILED, scored=False), 0.1, False, 0) == "unscored"


def test_a_passing_run_passes_whatever_its_quantities() -> None:
    assert classify(replace(FAILED, passes=True), 0.1, False, 0) == "passed"


def test_subthreshold_comes_before_calibrator_availability() -> None:
    assert classify(FAILED, THRESHOLD, False, 0) == "inlet_subthreshold"


def test_crossed_without_a_calibrator_is_unavailable() -> None:
    assert classify(FAILED, ABOVE, False, 0) == "inlet_unavailable"


def test_crossed_and_calibrated_but_not_promoted() -> None:
    assert classify(FAILED, ABOVE, True, 0) == "inlet_not_promoted"


def test_a_tie_is_insufficient_observations() -> None:
    assert classify(replace(FAILED, leader_with_inlet=None), ABOVE, True, 2) == (
        "insufficient_observations"
    )


def test_another_leader_is_misinterpreted() -> None:
    assert classify(FAILED, ABOVE, True, 2) == "misinterpreted"


def test_the_right_leader_that_still_fails_is_not_forced_into_a_clause() -> None:
    run = replace(FAILED, leader_with_inlet=LEADING_TEMPLATE_ID)
    assert classify(run, ABOVE, True, 2) == "not_separable"


def test_an_unmodelled_target_skips_the_subthreshold_clause() -> None:
    assert classify(FAILED, None, False, 0) == "inlet_unavailable"


def test_the_precedence_names_every_clause_classify_can_return() -> None:
    for mechanism in (
        "unscored",
        "passed",
        "inlet_subthreshold",
        "inlet_unavailable",
        "inlet_not_promoted",
        "insufficient_observations",
        "misinterpreted",
        "not_separable",
    ):
        assert mechanism in LIAR_PRECEDENCE


@pytest.mark.parametrize("seed", LIAR_HELD_OUT_SEEDS)
def test_every_held_out_seed_is_refused(seed: int) -> None:
    with pytest.raises(ValueError, match="held out"):
        refuse_held_out(seed)


def test_a_development_seed_is_allowed() -> None:
    refuse_held_out(4242)


def test_the_report_keeps_every_run_and_its_quantities(tmp_path: Path) -> None:
    diagnosis = LiarDiagnosis(FAILED, "misinterpreted", "LIT-101", 1.7, THRESHOLD, True, 2, "dec_1")
    path = tmp_path / "report.json"
    write_report([diagnosis], path, 4242)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["seed"] == 4242
    assert payload["runs"][0]["mechanism"] == "misinterpreted"
    assert payload["runs"][0]["peak_loop"] == 1.7
    assert payload["runs"][0]["decision_id"] == "dec_1"


@pytest.mark.slow
def test_one_development_corpus_is_diagnosed_and_recorded(tmp_path: Path) -> None:
    from phos.breaking.corpus import load_attack_corpus, load_normal_corpus
    from phos.breaking.liar import fit_inlet, inlet_calibrator, liar_corpus_config
    from phos.breaking.liar_diagnosis import diagnose_corpus, learning_records
    from phos.eval.learning_records import LearningLedger
    from phos.library.ot import SEEDS, SUBTLETIES, ot_trains
    from phos.synth.attacks.generate import generate_attack_dataset
    from phos.synth.generate import generate_dataset

    plant = "power-generation"
    train = next(config for config in ot_trains() if config.plant_id == plant)
    normal = load_normal_corpus(generate_dataset(train, tmp_path, with_capture=False)[0])
    inlet = fit_inlet(normal)
    development = [
        load_attack_corpus(
            generate_attack_dataset(liar_corpus_config(plant, s), tmp_path, with_capture=False)[0]
        )
        for s in SEEDS
    ]
    calibrator = inlet_calibrator(inlet, development, seed=7)
    corpus = load_attack_corpus(
        generate_attack_dataset(liar_corpus_config(plant, 4242), tmp_path, with_capture=False)[0]
    )
    ledger = LearningLedger(tmp_path / "ledger.jsonl")
    diagnoses = diagnose_corpus(corpus, normal, inlet, calibrator, ledger=ledger)
    assert [d.run.subtlety for d in diagnoses] == list(SUBTLETIES)
    assert [d.run.subtlety for d in diagnoses if d.mechanism == "passed"] == [0.0, 0.2]
    assert len(ledger.decisions()) == len(ledger.outcomes()) == len(diagnoses)
    records = learning_records(diagnoses, LearningLedger(tmp_path / "ledger.jsonl"))
    assert all(record.eligible for record in records)
    assert {record.channel for record in records} == {"success", "explanation"}


RECORDED = Path(__file__).resolve().parents[2] / "eval_runs" / "learning"


def test_the_recorded_seed_4242_ledger_verifies_and_matches_adr_0119() -> None:
    from collections import Counter

    from phos.eval.learning_records import LearningLedger

    ledger = LearningLedger(RECORDED / "liar-dev-s4242.ledger.jsonl")
    assert len(ledger.decisions()) == len(ledger.outcomes()) == 18
    assert {d.source_role for d in ledger.decisions()} == {"development"}
    report = json.loads((RECORDED / "liar-dev-s4242.diagnosis.json").read_text(encoding="utf-8"))
    counts = Counter(run["mechanism"] for run in report["runs"])
    assert counts == {
        "passed": 4,
        "inlet_subthreshold": 10,
        "inlet_not_promoted": 2,
        "inlet_unavailable": 1,
        "insufficient_observations": 1,
    }
    ids = {run["decision_id"] for run in report["runs"]}
    assert ids == {d.id for d in ledger.decisions()}
