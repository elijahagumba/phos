"""Score Atlas and Sentiel on the dataset library and append PART 2 reports to the experiment log.

Every report's ``source_note`` carries `SYNTHETIC_LIBRARY_CAVEATS`. Nothing here is quoted as
public-corpus attack recall. Distillation perturbation recall is a different ruler.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from phos.atlas import JointMomentDetector, MahalanobisFittedModel, MahalanobisModel
from phos.eval import (
    Dataset,
    Detector,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    append_to_experiment_log,
    evaluate,
)
from phos.library.caveats import SYNTHETIC_LIBRARY_CAVEATS
from phos.library.it import load_it_library
from phos.library.ot import LIBRARY_DIRNAME, ot_packs, ot_trains
from phos.models import GaussianBaseline, ModelDetector
from phos.ontology import Domain
from phos.sentiel import (
    AggregatedDetector,
    AggregationPolicy,
    evaluate_entity_aware,
    precision_policy,
    static_range_model,
)
from phos.synth.attacks.generate import TELEMETRY_FILE
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN

__all__ = [
    "ATLAS_DWELL_SAMPLES",
    "evaluate_it_library",
    "evaluate_ot_library",
    "library_root",
    "write_run_summary",
]

logger = logging.getLogger(__name__)

SEED: Final = 11
ATLAS_DWELL_SAMPLES: Final = 4
"""Four consecutive 30-second moments: two minutes of persistence before a page."""
_SENTIEL_ALERT_THRESHOLD: Final = 1.25
"""Score bar used on the library only. Not a CERT operating point."""


def library_root(repo: Path) -> Path:
    """Return ``<repo>/dataset library``."""
    return repo / LIBRARY_DIRNAME


def _stamp(report: EvaluationReport, extra: str) -> EvaluationReport:
    """Append the library caveats and a short protocol tag to ``source_note``."""
    note = " ".join((*SYNTHETIC_LIBRARY_CAVEATS, extra, report.source_note)).strip()
    return report.model_copy(update={"source_note": note})


def _load_telemetry(path: Path, name: str) -> Dataset:
    """Load a generated telemetry CSV through the ordinary labelled-CSV adapter."""
    adapter = LabelledCsvAdapter(
        name=name,
        path=path / TELEMETRY_FILE,
        timestamp_column=TIMESTAMP_COLUMN,
        label_column=LABEL_COLUMN,
        source_note=" ".join(SYNTHETIC_LIBRARY_CAVEATS),
        domain=Domain.ATLAS,
    )
    return adapter.load()


def evaluate_ot_library(
    root: Path,
    *,
    dwell_samples: int = ATLAS_DWELL_SAMPLES,
    log: bool = True,
    pack_limit: int | None = None,
) -> list[EvaluationReport]:
    """Fit per plant on the attack-free train corpus; score every generated attack pack."""
    generated = root / "OT" / "generated"
    trains = {config.plant_id: config for config in ot_trains()}
    fitted_by_plant: dict[str, MahalanobisFittedModel] = {}
    gaussian_by_plant: dict[str, ModelDetector] = {}
    reports: list[EvaluationReport] = []

    for plant_id, config in trains.items():
        train_dir = generated / config.name
        if not (train_dir / TELEMETRY_FILE).is_file():
            logger.warning("OT train %s missing; skip plant %s", train_dir, plant_id)
            continue
        train = _load_telemetry(train_dir, config.name)
        mahalanobis = MahalanobisModel(
            name="atlas-mahalanobis-joint-gated",
            adaptive_joint_quantile=0.995,
        ).fit(train.observations)
        if not isinstance(mahalanobis, MahalanobisFittedModel):
            raise TypeError(f"expected MahalanobisFittedModel, got {type(mahalanobis).__name__}")
        fitted_by_plant[plant_id] = mahalanobis
        gaussian_by_plant[plant_id] = ModelDetector(
            fitted=GaussianBaseline().fit(train.observations)
        )
        logger.info("%s: learned joint_k=%.4g from %s", plant_id, mahalanobis.joint_k, config.name)

    packs = list(ot_packs())
    if pack_limit is not None:
        packs = packs[:pack_limit]
    for pack in packs:
        fitted = fitted_by_plant.get(pack.plant_id)
        if fitted is None:
            continue
        pack_dir = generated / pack.name
        if not (pack_dir / TELEMETRY_FILE).is_file():
            logger.warning("OT pack %s missing; skip", pack.name)
            continue
        test = _load_telemetry(pack_dir, pack.name)
        detectors: list[Detector] = [
            gaussian_by_plant[pack.plant_id],
            JointMomentDetector(fitted=fitted),
            JointMomentDetector(fitted=fitted, dwell_samples=dwell_samples),
        ]
        extra = (
            f"library-ot plant={pack.plant_id} windows={len(test.attack_intervals)} "
            f"dwell_default=1 dwell_opt={dwell_samples}"
        )
        for detector in detectors:
            scored = evaluate(detector, test, EvalConfig(alert_threshold=0.0, seed=SEED))
            report = _stamp(scored, extra)
            reports.append(report)
            if log:
                append_to_experiment_log(report)
            logger.info(
                "%s %s recall=%.2f fp/hr=%.2f n_alerts=%d",
                report.dataset_name,
                report.detector_name,
                report.window_recall,
                report.false_positive_rate,
                report.n_alerts,
            )
    return reports


def evaluate_it_library(root: Path, *, log: bool = True) -> list[EvaluationReport]:
    """Fit a per-key Gaussian on the IT train half; score the test half under three policies."""
    train, test, labels = load_it_library(root)
    fitted = static_range_model(GaussianBaseline(min_samples=8).fit(train.observations))
    policies: tuple[AggregationPolicy, ...] = (
        AggregationPolicy(),
        precision_policy(),
        precision_policy(chronic_volume_halflife_days=4.0),
    )
    config = EvalConfig(alert_threshold=_SENTIEL_ALERT_THRESHOLD, seed=SEED)
    reports: list[EvaluationReport] = []
    calendar_days = 15.0
    for policy in policies:
        detector = AggregatedDetector(fitted=fitted, policy=policy)
        extra = (
            f"library-it n_labels={len(labels)} threshold={_SENTIEL_ALERT_THRESHOLD} "
            f"policy={detector.name}"
        )
        report = _stamp(evaluate_entity_aware(detector, test, labels, config), extra)
        reports.append(report)
        if log:
            append_to_experiment_log(report)
        logger.info(
            "%s recall=%.2f precision=%.3f alerts/day=%.1f fps=%d",
            report.detector_name,
            report.window_recall,
            report.precision,
            report.n_alerts / calendar_days,
            report.false_positives,
        )
    return reports


def write_run_summary(path: Path, reports: Sequence[EvaluationReport]) -> None:
    """Write a compact JSON summary beside the experiment log (not a substitute for it)."""
    rows = [
        {
            "detector": report.detector_name,
            "dataset": report.dataset_name,
            "window_recall": report.window_recall,
            "false_positives": report.false_positives,
            "false_positive_rate": report.false_positive_rate,
            "precision": report.precision,
            "n_alerts": report.n_alerts,
            "n_attack_intervals": report.n_attack_intervals,
            "normal_hours": report.normal_hours,
        }
        for report in reports
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
