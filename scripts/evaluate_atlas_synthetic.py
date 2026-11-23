#!/usr/bin/env python3
"""Score Atlas against synthetic corpora D1+D2 produce, SYNTHETIC-DERIVED only.

This is D3: the missing third PART of the synthetic data engine. D1 builds the plants,
D2 builds the graded attack library, D3 runs Atlas against the result and maps where it
goes blind. Nothing here is a detection claim for any real environment.

Usage::

    python scripts/evaluate_atlas_synthetic.py
    python scripts/evaluate_atlas_synthetic.py --dataset synth-attack-water-treatment-graded
    python scripts/evaluate_atlas_synthetic.py --no-log   # print tables, write nothing

Every report carries SYNTHETIC-DERIVED and the four standing caveats. Nothing is appended to
eval_runs/log.jsonl. Nothing is compared against a frozen public row.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas import (  # noqa: E402
    ATLAS_VERTICAL_CAVEATS,
    AtlasEngine,
    CrossSubsystemSynchronyModel,
    MahalanobisModel,
    annotate_with_caveats,
    is_subsystem_event,
    load_topology,
    member_evidence_ids,
)
from phos.eval import (  # noqa: E402
    Dataset,
    Detection,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    LabelledInterval,
    evaluate,
)
from phos.models import ModelDetector, uncalibrated_confidence  # noqa: E402
from phos.ontology import Domain, Evidence  # noqa: E402
from phos.reasoning import (  # noqa: E402
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

#: Where D2 writes generated attack corpora.
SYNTH_ROOT: Final = REPO_ROOT / "data" / "synth"

#: Matches scripts/evaluate_atlas_vertical.py so the 5A context row is comparable.
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11
DEFAULT_THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)

#: The four standing caveats every synthetic result must travel with.
SYNTHETIC_CAVEATS: Final[tuple[str, ...]] = (
    "MODEL_NOT_REALITY_CAVEAT: this is a model of a plant, not reality. Good scores here mean "
    "Atlas handles our model of a plant, not evidence of handling a real one.",
    "ATTACKS_ARE_OURS_CAVEAT: these are attacks we designed. A detection rate measured here is "
    "an upper bound on this library, never a lower bound on reality.",
    "SYNTHETIC_TOPOLOGY_CAVEAT: the topology is declared by us, not derived from plant "
    "documentation.",
    "INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT: input-hostile survival is not detection.",
)

logger = logging.getLogger("phos.atlas.synthetic")


class SyntheticResult(BaseModel):
    """One synthetic corpus's measured recall / FP, with the caveats attached."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    corpus: str
    reports: tuple[EvaluationReport, ...]
    n_per_signal: int
    n_events: int
    n_narratives: int
    windows_before: int
    windows_after: int
    n_windows: int


class PrecomputedDetector(BaseModel):
    """Adapts an already-computed alert set to the PART 2 Detector protocol.

    A measurement adapter, not a detector: the vertical produced these alerts already, and this
    exists only so the same harness scores them as it scores everything else.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    detections: tuple[Detection, ...]

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return the precomputed detections, ignoring ``dataset``."""
        logger.debug(
            "%s replaying %d detection(s) for %s", self.name, len(self.detections), dataset.name
        )
        return list(self.detections)


def adapter_for(path: Path, name: str) -> LabelledCsvAdapter:
    """Build a LabelledCsvAdapter pointing at a synthetic corpus's telemetry.csv."""
    return LabelledCsvAdapter(
        path=path,
        timestamp_column="timestamp",
        label_column="label",
        name=name,
        domain=Domain.ATLAS,
        source_note=f"synthetic corpus: {path.name}",
        entity_id="ent_synthetic0001",
    )


def discover(
    names: Sequence[str] | None = None,
    root: Path = SYNTH_ROOT,
) -> list[tuple[str, Path, dict[str, Any]]]:
    """Return ``(dataset_name, corpus_dir, manifest)`` for every synthetic corpus present.

    A corpus needs telemetry.csv and topology.toml. Without a declared topology there is no
    declared map to group by, and inventing one would be the circularity ADR 0010 exists to
    prevent. Searches recursively under ``root`` so both normal corpora (written directly
    under ``data/synth/``) and attack corpora (written under ``data/synth/attacks/``) are found.
    """
    found: list[tuple[str, Path, dict[str, Any]]] = []
    if not root.is_dir():
        return found
    for manifest_path in sorted(root.rglob("manifest.json")):
        corpus_dir = manifest_path.parent
        name = corpus_dir.name
        if names and name not in names:
            continue
        telemetry_path = corpus_dir / "telemetry.csv"
        topology_path = corpus_dir / "topology.toml"
        if not telemetry_path.is_file():
            logger.warning("%s: no telemetry.csv, skipping", name)
            continue
        if not topology_path.is_file():
            logger.warning("%s: no topology.toml, so there is no declared map to group by", name)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Skip input-hostile corpora: they test software survival, not detection, and their
        # CSVs are deliberately malformed. Only detection corpora are scored here.
        if manifest.get("flavour") == "INPUT_HOSTILE":
            logger.debug("%s: input-hostile corpus, skipping (not a detection corpus)", name)
            continue
        found.append((name, corpus_dir, manifest))
    return found


def detections_from(
    events: Sequence[Evidence],
    magnitudes: Mapping[str, float],
    signals: Mapping[str, Sequence[str]],
) -> tuple[Detection, ...]:
    """Turn evidence into harness detections, scored by the raw magnitude behind them."""
    return tuple(
        Detection(
            timestamp=event.timestamp,
            score=magnitudes[event.id],
            confidence=event.weight,
            entity_ids=list(event.entity_ids),
            feature=", ".join(signals[event.id]),
        )
        for event in events
    )


def windows_covered(
    evidence: Sequence[Evidence],
    members: Mapping[str, Evidence],
    intervals: Sequence[LabelledInterval],
) -> set[int]:
    """Return the indices of the attack windows a set of evidence overlaps.

    Overlap rather than the alert's own timestamp, because a subsystem event stands for the span
    from its earliest member to its latest and is stamped at the earliest — so an event that began
    in normal time and continued into an attack has plainly caught that attack.
    """
    covered: set[int] = set()
    for item in evidence:
        stamps = (
            [members[member].timestamp for member in member_evidence_ids(item)]
            if is_subsystem_event(item)
            else [item.timestamp]
        )
        for index, interval in enumerate(intervals):
            if any(interval.contains(stamp) for stamp in stamps):
                covered.add(index)
    return covered


def split_evidence(engine: AtlasEngine) -> tuple[list[Evidence], list[Evidence]]:
    """Return ``(per-signal evidence, subsystem events)`` from a completed run, in stored order."""
    stored = engine.store.evidence(Domain.ATLAS)
    return (
        [item for item in stored if not is_subsystem_event(item)],
        [item for item in stored if is_subsystem_event(item)],
    )


def magnitudes_of(
    engine: AtlasEngine, per_signal: Sequence[Evidence], events: Sequence[Evidence]
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Return each piece of evidence's raw magnitude and the signals it concerns.

    Both are recovered by walking the traceability path rather than being carried alongside it,
    so the numbers in this report and the drill-down an operator would perform read the same
    objects.
    """
    magnitude: dict[str, float] = {}
    signals: dict[str, list[str]] = {}
    for item in per_signal:
        deviation = engine.store.get_deviation(item.source_id)
        if deviation is None:
            raise RuntimeError(f"evidence {item.id} has no deviation in the store")
        magnitude[item.id] = deviation.magnitude
        signals[item.id] = [deviation.expected.feature]
    for event in events:
        members = member_evidence_ids(event)
        magnitude[event.id] = max(magnitude[member] for member in members)
        signals[event.id] = list(event.entity_ids)
    return magnitude, signals


def synthetic_caveats_note() -> str:
    """Return the standing caveats joined as a source_note fragment."""
    return " | ".join(SYNTHETIC_CAVEATS)


def run_corpus(name: str, corpus_dir: Path, manifest: Mapping[str, Any]) -> SyntheticResult | None:
    """Fit, calibrate and run the vertical on one synthetic corpus; return its measured result.

    When the calib slice carries no attack points, an isotonic calibrator cannot be fitted
    (it needs both positive and negative labels). In that case we fall back to the 5A context
    row only — ModelDetector without calibration — which still measures false-positive rate
    honestly. The vertical rows (before/after) require calibrated weights and are skipped.
    """
    telemetry = corpus_dir / "telemetry.csv"
    loaded = adapter_for(telemetry, name).load()

    if not loaded.attack_intervals:
        logger.info("%s: no labelled attack windows; measuring false positives only", name)

    policy = DEFAULT_THREE_WAY
    try:
        train, calib, test = train_calib_test_split(loaded, policy)
    except DegenerateSplitError as error:
        logger.warning("%s: %s", name, error)
        return None

    fitted = MahalanobisModel().fit(train.observations)

    # Try to fit a calibrator; fall back to raw model if the calib slice has no attacks.
    calibrator = None
    try:
        scores, labels = scores_and_labels_from(fitted, calib)
        calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)
    except ValueError as error:
        logger.warning(
            "%s: no calibrator fitted (%s); reporting 5A context only", name, error
        )

    topology_corpus = str(manifest.get("plant_id", name))
    topology = load_topology(
        corpus_dir / "topology.toml",
        {observation.feature for observation in loaded.observations},
        corpus=topology_corpus,
    )

    # 5A context row: raw model, no calibration, always available.
    reports: list[EvaluationReport] = [
        _named(
            evaluate(
                ModelDetector(fitted=fitted),
                test,
                EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
            ),
            f"{name}[5A context]",
        ),
    ]

    if calibrator is not None:
        engine = AtlasEngine(fitted=fitted, calibrator=calibrator, subsystem_map=topology)
        narratives = engine.run(test)

        per_signal, events = split_evidence(engine)
        magnitude, signals = magnitudes_of(engine, per_signal, events)
        members = {item.id: item for item in per_signal}

        config = EvalConfig(alert_threshold=0.0, seed=SEED)
        reports.extend(
            [
                _named(
                    evaluate(
                        PrecomputedDetector(
                            name=f"{engine.name}/per-signal-evidence",
                            detections=detections_from(per_signal, magnitude, signals),
                        ),
                        test,
                        config,
                    ),
                    f"{name}[before]",
                ),
                _named(
                    evaluate(
                        PrecomputedDetector(
                            name=f"{engine.name}/subsystem-events",
                            detections=detections_from(events, magnitude, signals),
                        ),
                        test,
                        config,
                    ),
                    f"{name}[after]",
                ),
            ]
        )
        _n_per_signal = len(per_signal)
        _n_events = len(events)
        _n_narratives = len(narratives)
        _windows_before = len(windows_covered(per_signal, members, test.attack_intervals))
        _windows_after = len(windows_covered(events, members, test.attack_intervals))
    else:
        _n_per_signal = 0
        _n_events = 0
        _n_narratives = 0
        _windows_before = 0
        _windows_after = 0

    # Cross-subsystem synchrony: a separate model variant that judges subsystem pairs,
    # not individual signals. No calibrator needed — it emits raw z-score magnitudes.
    # Fit on train, score on test. Runs whether or not calibration succeeded.
    try:
        sync_fitted = CrossSubsystemSynchronyModel(
            subsystem_map=topology,
            persistence_windows=3,
        ).fit(train.observations)
        sync_deviations = sync_fitted.score(test.observations)
        if sync_deviations:
            sync_detections = tuple(
                Detection(
                    timestamp=d.timestamp,
                    score=d.magnitude,
                    confidence=uncalibrated_confidence(d.magnitude, 3.0),
                    entity_ids=[d.expected.entity_id],
                    feature=d.expected.feature,
                )
                for d in sync_deviations
            )
            reports.append(
                _named(
                    evaluate(
                        PrecomputedDetector(
                            name=f"{sync_fitted.name}/subsystem-synchrony",
                            detections=sync_detections,
                        ),
                        test,
                        EvalConfig(alert_threshold=3.0, seed=SEED),
                    ),
                    f"{name}[synchrony]",
                )
            )
    except ValueError as error:
        logger.warning("%s: synchrony model could not fit (%s)", name, error)

    # Annotate every report with the Atlas vertical caveats AND the synthetic caveats.
    annotated = []
    for report in reports:
        report = annotate_with_caveats(report)
        note = report.source_note or ""
        if synthetic_caveats_note() not in note:
            note = f"{note} | {synthetic_caveats_note()}" if note else synthetic_caveats_note()
        report = report.model_copy(update={"source_note": note})
        annotated.append(report)

    return SyntheticResult(
        corpus=name,
        reports=tuple(annotated),
        n_per_signal=_n_per_signal,
        n_events=_n_events,
        n_narratives=_n_narratives,
        windows_before=_windows_before,
        windows_after=_windows_after,
        n_windows=len(test.attack_intervals),
    )


def _named(report: EvaluationReport, label: str) -> EvaluationReport:
    """Stamp which corpus and which counting unit a report describes."""
    return report.model_copy(update={"dataset_name": label})


def write_report(path: Path, report: EvaluationReport) -> None:
    """Append one SYNTHETIC-DERIVED report to the synthetic experiment log.

    Deliberately NOT eval_runs/log.jsonl: synthetic results must never share the public log
    with frozen rows (ADR 0454, Decision 3).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = report.model_dump_json() + "\n"
    path.write_text(line, encoding="utf-8")
    logger.info("%s: wrote %s", path.parent.name, path.name)


def render(results: Sequence[SyntheticResult]) -> str:
    """Render every report as a markdown table."""
    header = (
        "| Corpus | Counted as | Alerts | Recall | FPs | FP/normal-hr | Precision | ECE |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        f"| `{report.dataset_name}` | `{report.detector_name}` | {report.n_alerts:,} "
        f"| {report.window_recall:.2f} | {report.false_positives:,} "
        f"| {report.false_positive_rate:.2f} | {report.precision:.4f} "
        f"| {report.expected_calibration_error:.4f} |"
        for result in results
        for report in result.reports
    ]
    return "\n".join([header, *rows])


def summarise(results: Sequence[SyntheticResult]) -> str:
    """State the before/after per corpus as a counting change, with the recall check beside it."""
    lines: list[str] = []
    for result in results:
        before, after = result.reports[1], result.reports[2]
        factor = result.n_per_signal / result.n_events if result.n_events else float("inf")
        lines.append(
            f"{result.corpus}: {result.n_per_signal:,} per-signal alerts -> "
            f"{result.n_events:,} subsystem events ({factor:.1f}x fewer things to investigate), "
            f"{result.n_narratives:,} narrative(s)"
        )
        lines.append(
            f"  counting only: FP/normal-hr {before.false_positive_rate:.2f} -> "
            f"{after.false_positive_rate:.2f}. The detector did not change."
        )
        lines.append(
            f"  attack windows covered: {result.windows_before}/{result.n_windows} before "
            f"grouping, {result.windows_after}/{result.n_windows} after (overlap-aware); "
            f"harness window recall {before.window_recall:.2f} -> {after.window_recall:.2f}"
        )
    return "\n".join(lines) or "nothing to compare"


def caveats() -> str:
    """Render the caveats that must be read with every number above."""
    return "\n".join(
        [
            "Read every number above with these:",
            *(f"  - {c}" for c in ATLAS_VERTICAL_CAVEATS),
            "",
            "Synthetic standing caveats:",
            *(f"  - {c}" for c in SYNTHETIC_CAVEATS),
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument("--no-log", action="store_true", help="print tables, write nothing")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error(
            "no synthetic corpus found; run scripts/generate_attacks.py first, or check "
            "data/synth/attacks/"
        )
        return 2

    results: list[SyntheticResult] = []
    for name, corpus_dir, manifest in corpora:
        result = run_corpus(name, corpus_dir, manifest)
        if result is None:
            continue
        results.append(result)
        if not arguments.no_log:
            for report in result.reports:
                write_report(REPO_ROOT / "eval_runs" / "synth" / f"{name}.jsonl", report)

    if not results:
        logger.error("no corpus yielded a usable split")
        return 1

    print("\n" + render(results))
    print("\n" + summarise(results))
    print("\n" + caveats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
