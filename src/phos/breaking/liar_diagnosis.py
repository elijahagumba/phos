"""Why a liar run failed: a declared precedence over what the consistency inlet saw.

Stage S2 of `docs/learning-engine.md` (ADR 0119). ADR 0114 explained in prose why water treatment
never passes T1 on development seed 4242: the falsified level's loop score never crosses the
inlet's threshold. This module turns that kind of explanation into a verdict a machine can check,
for every liar run, with the quantities behind it.

**Development seeds only.** `diagnose_development_seed` refuses any seed in
`phos.eval.liar_declaration.LIAR_HELD_OUT_SEEDS`. Every figure it returns is synthetic (R4) and is
diagnosis, not a result.

**It re-runs, it does not re-score.** The pass verdict is `run_liar_corpus`'s, unchanged. The
quantities are recomputed from the same fitted parts, and the recomputed leader must equal the
runner's, or the module raises rather than report a diagnosis of something else.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal

import numpy

from phos.atlas import AtlasEngine
from phos.atlas.consistency import THRESHOLD, feature_components
from phos.breaking.corpus import AttackCorpus, NormalCorpus
from phos.breaking.harness import (
    BreakingConfig,
    _covers,
    _fold_boundary,
    _fold_calibrator,
    _model_for,
    _slice,
)
from phos.breaking.liar import (
    Inlet,
    LiarRun,
    _competing,
    _leader,
    _matrix,
    _names,
    _promote,
    _Unit,
    run_liar_corpus,
)
from phos.eval import Dataset
from phos.eval.learning_records import (
    DecisionRecord,
    LearningLedger,
    LearningRecord,
    OutcomeRecord,
    arena_eligibility,
    sha256_text,
    window_sha256,
)
from phos.eval.liar_declaration import LEADING_TEMPLATE_ID, LIAR_HELD_OUT_SEEDS
from phos.ontology import EvidenceStore, Hypothesis
from phos.ontology.ids import utc_now
from phos.reasoning import FittedCalibrator
from phos.synth.attacks.spec import AttackGroundTruth, AttackType

__all__ = [
    "LIAR_PRECEDENCE",
    "T1_ASSEMBLY",
    "LiarDiagnosis",
    "LiarMechanism",
    "classify",
    "diagnose_corpus",
    "learning_records",
    "refuse_held_out",
    "write_report",
]

#: The name a decision record carries for the T1 assembly: not a result name, never logged.
T1_ASSEMBLY: Final = "atlas-t1-assembly (ADR 0114: joint model and consistency inlet)"

LiarMechanism = Literal[
    "unscored",
    "passed",
    "inlet_subthreshold",
    "inlet_unavailable",
    "inlet_not_promoted",
    "insufficient_observations",
    "misinterpreted",
    "not_separable",
]

LIAR_PRECEDENCE: Final = """\
A liar run is read in this order, and the first clause that fits decides it:

1. not scored                          -> unscored. The attack straddled the fold boundary; no
                                          verdict on the detector.
2. ADR 0094's predicate passes         -> passed.
3. peak loop score <= THRESHOLD        -> inlet_subthreshold. On the falsified signal, inside the
                                          window, the reading never departed from what the rest of
                                          the plant implies by enough to open an event. Checked
                                          before calibrator availability because it is upstream:
                                          with no crossing on development corpora there are no
                                          positives to calibrate on.
4. the plant has no inlet calibrator   -> inlet_unavailable. It crossed, but no citation could
                                          exist.
5. no promoted fact inside the window  -> inlet_not_promoted. It crossed, but the range score
                                          dominated or the event's onset fell elsewhere.
6. no unique contentful leader         -> insufficient_observations. A tie, or nothing contentful.
7. the leader is another template      -> misinterpreted.
8. otherwise                           -> not_separable. Stated, never forced into a clause.

Clauses 3 and 5 point at the detector's relation; 4 at its calibration data; 6 and 7 at the
reasoning that weighs the evidence. Those are different repairs.
"""


@dataclass(frozen=True)
class LiarDiagnosis:
    """One liar run, its verdict, and the quantities the precedence read.

    Attributes:
        run: The runner's own result, unchanged.
        mechanism: The first clause of `LIAR_PRECEDENCE` that fits.
        target: The falsified signal, or ``None`` if the inlet does not model it.
        peak_loop: The largest loop score on ``target`` inside the window, or ``None``.
        threshold: The inlet's threshold, `phos.atlas.consistency.THRESHOLD`.
        inlet_available: Whether the plant had an inlet calibrator.
        facts_in_window: Promoted consistency facts inside the window, on any signal.
        decision_id: The ledger decision recorded for it, or ``None`` when none was recorded.
    """

    run: LiarRun
    mechanism: LiarMechanism
    target: str | None
    peak_loop: float | None
    threshold: float
    inlet_available: bool
    facts_in_window: int
    decision_id: str | None = None


def classify(
    run: LiarRun,
    peak_loop: float | None,
    inlet_available: bool,
    facts_in_window: int,
) -> LiarMechanism:
    """Apply `LIAR_PRECEDENCE` to one run's quantities. Pure."""
    if not run.scored:
        return "unscored"
    if run.passes:
        return "passed"
    if peak_loop is not None and peak_loop <= THRESHOLD:
        return "inlet_subthreshold"
    if not inlet_available:
        return "inlet_unavailable"
    if facts_in_window == 0:
        return "inlet_not_promoted"
    if run.leader_with_inlet is None:
        return "insufficient_observations"
    if run.leader_with_inlet != LEADING_TEMPLATE_ID:
        return "misinterpreted"
    return "not_separable"


def refuse_held_out(seed: int) -> None:
    """Raise if ``seed`` is a T1 held-out seed.

    Raises:
        ValueError: If it is.
    """
    if seed in LIAR_HELD_OUT_SEEDS:
        raise ValueError(
            f"seed {seed} is held out for T1 (ADR 0094); diagnosis is development-only"
        )


@dataclass(frozen=True)
class _Fold:
    test: Dataset
    store: EvidenceStore


def _folds(
    corpus: AttackCorpus,
    normal: NormalCorpus,
    inlet: Inlet,
    calibrator: FittedCalibrator | None,
    settings: BreakingConfig,
) -> list[_Fold]:
    """The with-inlet stores, rebuilt exactly as `run_liar_corpus` builds them."""
    dataset = corpus.dataset
    boundary = _fold_boundary(dataset, dataset.attack_intervals)
    if boundary is None:
        raise ValueError(f"{corpus.name} cannot be split into two folds")
    first = dataset.observations[0].timestamp
    last = dataset.observations[-1].timestamp + timedelta(seconds=1)
    early = _slice(dataset, first, boundary, "early")
    late = _slice(dataset, boundary, last, "late")
    fitted = _model_for(normal.plant_id, settings).fit(normal.dataset.observations)
    folds: list[_Fold] = []
    for calibration_slice, test_slice in ((late, early), (early, late)):
        sensor = _fold_calibrator(fitted, calibration_slice, settings)
        engine = AtlasEngine(fitted, sensor, corpus.subsystem_map(), config=settings.atlas)
        facts = None if calibrator is None else _promote(inlet, test_slice, calibrator)
        engine.run(test_slice, consistency=facts)
        folds.append(_Fold(test_slice, engine.store))
    return folds


def _peak_loop(
    inlet: Inlet, test: Dataset, truth: AttackGroundTruth
) -> tuple[str | None, float | None]:
    features, _entity_of = _names(inlet.space)
    targets = [name for name in truth.target_signals if name in features]
    if not targets:
        return None, None
    matrix = _matrix(test, inlet.space)
    loop, _range = feature_components(inlet.model, matrix.values)
    window = truth.interval()
    rows = [i for i, stamp in enumerate(matrix.timestamps) if window.contains(stamp)]
    if not rows:
        return targets[0], None
    peaks = {name: float(numpy.max(loop[rows, features.index(name)])) for name in targets}
    target = max(peaks, key=lambda name: peaks[name])
    return target, peaks[target]


def _facts_in_window(inlet: Inlet, test: Dataset, truth: AttackGroundTruth) -> int:
    window = truth.interval()
    return sum(
        1
        for fact in _promote(inlet, test, _Unit()).facts
        if window.contains(fact.evidence.timestamp)
    )


def diagnose_corpus(
    corpus: AttackCorpus,
    normal: NormalCorpus,
    inlet: Inlet,
    calibrator: FittedCalibrator | None,
    config: BreakingConfig | None = None,
    ledger: LearningLedger | None = None,
    commit: str | None = None,
) -> list[LiarDiagnosis]:
    """Run, diagnose and optionally record every liar in one development corpus.

    Args:
        corpus: A liar corpus on a development seed.
        normal: The plant's attack-free corpus.
        inlet: `phos.breaking.liar.fit_inlet` of ``normal``.
        calibrator: The inlet calibrator from development corpora, or ``None``.
        config: Harness settings.
        ledger: If given, one decision and one outcome per scored run are appended to it.
        commit: The git commit to stamp on each decision.

    Raises:
        ValueError: If the corpus is on a held-out seed, or the recomputed leader of any run
            disagrees with `run_liar_corpus`'s.
    """
    refuse_held_out(corpus.manifest.spec.seed)
    settings = BreakingConfig() if config is None else config
    runs = run_liar_corpus(corpus, normal, inlet, calibrator, settings)
    folds = _folds(corpus, normal, inlet, calibrator, settings)
    liars = [truth for truth in corpus.manifest.attacks if truth.type is AttackType.LIAR]
    fit_hash = window_sha256(*_rows(normal.dataset, inlet))
    config_hash = sha256_text(settings.model_dump_json() + f"|calibrated={calibrator is not None}")
    out: list[LiarDiagnosis] = []
    for run, truth in zip(runs, liars, strict=True):
        fold = next((f for f in folds if _covers(f.test, truth.interval())), None)
        if fold is None:
            available = calibrator is not None
            mechanism = classify(run, None, available, 0)
            out.append(LiarDiagnosis(run, mechanism, None, None, THRESHOLD, available, 0))
            continue
        competing = _competing(truth, fold.store)
        if _leader(competing) != run.leader_with_inlet:
            raise ValueError(f"{truth.attack_id}: recomputed leader disagrees with the runner")
        target, peak = _peak_loop(inlet, fold.test, truth)
        facts = _facts_in_window(inlet, fold.test, truth)
        mechanism = classify(run, peak, calibrator is not None, facts)
        decision_id = None
        if ledger is not None:
            decision_id = _record(
                ledger,
                corpus,
                fold,
                inlet,
                truth,
                competing,
                fit_hash,
                config_hash,
                commit,
                calibrator,
            )
        out.append(
            LiarDiagnosis(
                run, mechanism, target, peak, THRESHOLD, calibrator is not None, facts, decision_id
            )
        )
    return out


def learning_records(
    diagnoses: Sequence[LiarDiagnosis], ledger: LearningLedger
) -> list[LearningRecord]:
    """Join each recorded diagnosis to its current outcome. A passed run is channel E, success."""
    records: list[LearningRecord] = []
    for d in diagnoses:
        if d.decision_id is None:
            continue
        decision = ledger.decision(d.decision_id)
        outcomes = ledger.current_outcomes(d.decision_id)
        eligible, reason = arena_eligibility(decision, outcomes[-1] if outcomes else None)
        records.append(
            LearningRecord(
                decision_id=d.decision_id,
                outcome_ids=tuple(o.id for o in outcomes),
                channel="success" if d.run.passes else "explanation",
                mechanism=d.mechanism,
                quantities={
                    "plant": d.run.plant_id,
                    "subtlety": d.run.subtlety,
                    "target": d.target,
                    "peak_loop": d.peak_loop,
                    "threshold": d.threshold,
                    "inlet_available": d.inlet_available,
                    "facts_in_window": d.facts_in_window,
                    "leader_with_inlet": d.run.leader_with_inlet,
                },
                eligible=eligible,
                reason=reason,
            )
        )
    return records


def _rows(dataset: Dataset, inlet: Inlet) -> tuple[Sequence[datetime], list[list[float]]]:
    matrix = _matrix(dataset, inlet.space)
    return matrix.timestamps, matrix.values.tolist()


def _record(
    ledger: LearningLedger,
    corpus: AttackCorpus,
    fold: _Fold,
    inlet: Inlet,
    truth: AttackGroundTruth,
    competing: Sequence[Hypothesis],
    fit_hash: str,
    config_hash: str,
    commit: str | None,
    calibrator: FittedCalibrator | None,
) -> str:
    """Record one decision (Atlas's explanation of this window) and its synthetic-truth outcome.

    Returns the decision's id.

    The explanation channel raises no queue alerts, so ``alerts`` is empty. The window is the
    attack's; the input hash covers the whole fold the engine scored.
    """
    cited = {item for h in competing for item in (*h.supporting, *h.contradictory)}
    window = truth.interval()
    decision = DecisionRecord(
        detector=T1_ASSEMBLY,
        commit=commit,
        config_sha256=config_hash,
        fit=f"lib-ot attack-free train corpus for {corpus.manifest.plant_id}",
        fit_sha256=fit_hash,
        source=corpus.name,
        source_role="development",
        window_start=window.start,
        window_end=window.end,
        input_sha256=window_sha256(*_rows(fold.test, inlet)),
        budget_per_shift=8,
        hypotheses=tuple(competing),
        evidence=tuple(e for e in fold.store.evidence() if e.id in cited),
        calibrator=None if calibrator is None else calibrator.name,
    )
    ledger.append_decision(decision)
    ledger.append_outcome(
        OutcomeRecord(
            decision_id=decision.id,
            entities=truth.target_signals,
            kind="attack",
            status="confirmed",
            source="synthetic_truth",
            source_ref=f"{corpus.name}/truth.csv#{truth.attack_id}",
            occurred_at=window.start,
            known_at=utc_now(),
        )
    )
    return decision.id


def write_report(diagnoses: Sequence[LiarDiagnosis], path: Path, seed: int) -> None:
    """Write the diagnoses as JSON, one object per run, sorted by plant and subtlety."""
    rows = [
        {
            "plant": d.run.plant_id,
            "seed": d.run.seed,
            "subtlety": d.run.subtlety,
            "attack_id": d.run.attack_id,
            "passes": d.run.passes,
            "leader_with_inlet": d.run.leader_with_inlet,
            "mechanism": d.mechanism,
            "target": d.target,
            "peak_loop": None if d.peak_loop is None else round(d.peak_loop, 6),
            "threshold": d.threshold,
            "inlet_available": d.inlet_available,
            "facts_in_window": d.facts_in_window,
            "decision_id": d.decision_id,
        }
        for d in sorted(diagnoses, key=lambda d: (d.run.plant_id, d.run.subtlety))
    ]
    payload = {"seed": seed, "precedence": LIAR_PRECEDENCE, "runs": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
