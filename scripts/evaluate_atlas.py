#!/usr/bin/env python3
"""Measure what modelling the plant as a *related system* is worth, and log the answer.

This is the reproducible proof behind PART 5A. On each integrated ICS corpus it fits PART 3's
per-signal `GaussianBaseline` and Atlas's two joint models on **exactly the same data, with exactly
the same harness config**, and scores all three on the same test slice. Every report is appended to
``eval_runs/log.jsonl`` stamped with the git commit and seed (Constitution §3.7).

The comparison is deliberately run under all three protocols already on the experiment log, because
"the PART 3 baseline" names three different numbers and the claim should hold against whichever one
a reader has in mind:

* **designed** — fit on the corpus's own attack-free training file, score its labelled test file.
  How the corpus authors intend it to be used.
* **prefix** — carve an attack-free prefix out of the labelled file alone
  (``scripts/evaluate_corpora.py``). Same protocol PART 3 used on synthetic data.
* **three-way** — the train/calib/test split PART 4A introduced
  (``scripts/calibrate_corpora.py``). This is the protocol behind the 8,390 false-positives-per-
  normal-hour figure that PART 5A exists to attack, and the only one that can also report a
  *calibrated* Atlas detector, since a calibrator needs a held-out labelled slice of its own.

Nothing here lets a model score data it was fitted on, and no calibrator is fitted on the slice its
calibration error is reported from.

Usage::

    python scripts/evaluate_atlas.py
    python scripts/evaluate_atlas.py hai
    python scripts/evaluate_atlas.py --no-log      # print the tables, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas import (  # noqa: E402
    JointMomentDetector,
    LinearDynamicsModel,
    MahalanobisFittedModel,
    MahalanobisModel,
    PcaResidualModel,
    PhaseConditionalModel,
    ShrinkageTarget,
)
from phos.eval import (  # noqa: E402
    Dataset,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    append_to_experiment_log,
    evaluate,
)
from phos.eval.batch_distillation import OPERATING_POINT_FEATURE, RECIPE_STEP_FEATURE  # noqa: E402
from phos.models import (  # noqa: E402
    BehaviouralModel,
    GaussianBaseline,
    ModelDetector,
    SplitPolicy,
)
from phos.reasoning import (  # noqa: E402
    CalibratedModelDetector,
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    prefix_split,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR: Final = REPO_ROOT / "data"
logger = logging.getLogger("phos.atlas.evaluate")

#: Matches `scripts/evaluate_corpora.py` and `scripts/calibrate_corpora.py` exactly. The whole
#: point of this script is that the only thing that changed is the model.
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11
PREFIX_POLICY: Final = SplitPolicy(train_fraction=0.5)
DEFAULT_THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)

#: Copied from `scripts/calibrate_corpora.py`, for the same reason it exists there: HAI's attacks
#: all fall in the first half of its test file, so the default fractions leave a test slice with no
#: attacks in it and every metric computed on it is meaningless.
THREE_WAY_POLICIES: Final[dict[str, CalibrationSplitPolicy]] = {
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}

#: Data4Cyber S0/S1 are two independent ~30-minute recordings. A prefix carved from S1 is not
#: an attack-free learn stretch, and a three-way split of S1 is not the designed protocol.
#: ADR 0046: designed is the only protocol that may be logged for this corpus.
DESIGNED_PROTOCOL_ONLY: Final[frozenset[str]] = frozenset({"data4cyber"})


def contenders() -> list[BehaviouralModel]:
    """Return the models to compare, baseline first so every table reads as before/after."""
    return [GaussianBaseline(), PcaResidualModel(), MahalanobisModel()]


def var_contenders() -> list[BehaviouralModel]:
    """Return the VAR residual only, so a HAI three-way run cannot re-log frozen Mahalanobis.

    Named experiment ``atlas-var1`` (ADR 0054). Public snapshot rows stay
    ``model:atlas-mahalanobis``. Threshold and seed stay 3.0 / 11.
    """
    return [LinearDynamicsModel()]


def correlation_contenders() -> list[BehaviouralModel]:
    """Return correlation-target Mahalanobis only (ADR 0052). Not the public default."""
    return [
        MahalanobisModel(
            name="atlas-mahalanobis-correlation",
            shrinkage_target=ShrinkageTarget.CORRELATION,
        )
    ]


def is_singular_covariance_refuse(error: BaseException) -> bool:
    """Return whether ``error`` is the joint-model invert refusal, not a bug to retune around.

    ADR 0052: do not raise default shrinkage on a public holdout. A singular correlation-target
    fit on HAI is a refused detector name, not a licence to edit ``_shrink``.
    """
    text = str(error)
    return "singular" in text and "shrinkage" in text


def gated_contenders() -> list[BehaviouralModel]:
    """Return the joint-gated Mahalanobis model, named so its row is not the baseline.

    The default `MahalanobisModel()` is ungated, which is the number ADR 0025 logged. This
    contender learns a joint-distance envelope from attack-free training (the 0.995 quantile of
    ``D_M``) and only then attributes per-signal residuals. See ADR 0026.
    """
    return [
        MahalanobisModel(
            name="atlas-mahalanobis-joint-gated",
            adaptive_joint_quantile=0.995,
        )
    ]


_ROUTING_REGISTERS: Final = frozenset({RECIPE_STEP_FEATURE, OPERATING_POINT_FEATURE})


def _adapter(config: dict[str, Any]) -> LabelledCsvAdapter:
    """Build an adapter from a manifest block, resolving its path against ``data/``."""
    fields = {
        key: value
        for key, value in config.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    return LabelledCsvAdapter.model_validate({**fields, "path": str(DATA_DIR / config["path"])})


def discover(names: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(dataset_name, manifest)`` for every integrated corpus present on disk.

    A manifest whose CSV is absent is skipped rather than failing: manifests are committed and the
    data they describe is not, so a fresh clone legitimately has one without the other.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for manifest_path in sorted(DATA_DIR.glob("*/manifest.json")):
        name = manifest_path.parent.name
        if names and name not in names:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not (DATA_DIR / manifest["path"]).is_file():
            logger.warning("%s: manifest present but %s is not", name, manifest["path"])
            continue
        found.append((name, manifest))
    return found


def _config() -> EvalConfig:
    return EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)


def selected_contenders(*, gated: bool, phase_feature: str | None = None) -> list[BehaviouralModel]:
    """Return the baseline comparison, plus optional gated and phase-conditional rows.

    Pooled Gaussian / PCA / Mahalanobis stay the public comparison. A declared
    ``phase_feature`` adds `PhaseConditionalModel` with settling disabled so the first
    measurement is the per-phase covariance, not the batch-reactor settling allowance.
    """
    models = contenders()
    if gated:
        models.extend(gated_contenders())
    if phase_feature:
        models.append(
            PhaseConditionalModel(
                phase_feature=phase_feature,
                inner=MahalanobisModel(),
                settling_window=timedelta(0),
            )
        )
    return models


def _routing_feature(manifest: dict[str, Any]) -> str | None:
    """Return the declared phase register on ``manifest``, or ``None``."""
    value = manifest.get("phase_feature")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stamp(report: EvaluationReport, test: Dataset, label: str) -> EvaluationReport:
    """Stamp the protocol onto the report's dataset name."""
    return report.model_copy(update={"dataset_name": f"{test.name.rsplit('-', 1)[0]}[{label}]"})


def _scored(
    model: BehaviouralModel,
    train: Dataset,
    test: Dataset,
    label: str,
    *,
    routing_feature: str | None = None,
) -> list[EvaluationReport]:
    """Fit on ``train``, score ``test``, and add a moment-level row if a joint gate was learned.

    When a routing register is present on the CSV, pooled models are fitted and scored
    without those columns so the frozen ungated comparison does not treat a recipe or
    operating-point register as a process signal. A `PhaseConditionalModel` keeps only
    its own ``phase_feature`` and drops the other register.
    """
    drop = set(_ROUTING_REGISTERS)
    if isinstance(model, PhaseConditionalModel):
        drop.discard(model.phase_feature)
    fit_train = train.without_features(drop)
    score_test = test.without_features(drop)
    fitted = model.fit(fit_train.observations)
    reports = [_stamp(evaluate(ModelDetector(fitted=fitted), score_test, _config()), test, label)]
    if isinstance(fitted, MahalanobisFittedModel) and fitted.joint_k > 0.0:
        moment = evaluate(
            JointMomentDetector(fitted=fitted),
            score_test,
            EvalConfig(alert_threshold=0.0, seed=SEED),
        )
        reports.append(_stamp(moment, test, label))
        logger.info(
            "%s: joint-gated Mahalanobis learned joint_k=%.4g; moment-level row emitted",
            test.name,
            fitted.joint_k,
        )
    return reports


def run_designed(
    name: str,
    manifest: dict[str, Any],
    models: Sequence[BehaviouralModel] | None = None,
) -> list[EvaluationReport]:
    """Fit on the corpus's own attack-free training file and score its labelled test file."""
    if "train" not in manifest or not (DATA_DIR / manifest["train"]["path"]).is_file():
        logger.info("%s: no attack-free training corpus on disk, skipping designed split", name)
        return []

    train = _adapter(manifest["train"]).load()
    test = _adapter(manifest).load()
    if train.attack_intervals:
        raise RuntimeError(
            f"{name}: the training corpus carries {len(train.attack_intervals)} attack "
            "interval(s); it must be attack-free or every model learns the attack as normal"
        )
    if train.unscored_intervals:
        raise RuntimeError(
            f"{name}: the training corpus carries {len(train.unscored_intervals)} unscored "
            "interval(s); unscored time is not verified normal and must not be fitted on"
        )
    logger.info(
        "%s designed: fit on %d obs, score %d obs, %d attack windows",
        name,
        len(train.observations),
        len(test.observations),
        len(test.attack_intervals),
    )
    reports: list[EvaluationReport] = []
    routing = _routing_feature(manifest)
    for model in models if models is not None else contenders():
        reports.extend(_scored(model, train, test, "designed", routing_feature=routing))
    return reports


def run_prefix(
    name: str,
    manifest: dict[str, Any],
    models: Sequence[BehaviouralModel] | None = None,
) -> list[EvaluationReport]:
    """Carve an attack-free prefix out of the labelled corpus and score the remainder."""
    if name in DESIGNED_PROTOCOL_ONLY:
        logger.info(
            "%s: prefix split is not an honest protocol on this corpus (ADR 0046); skipping",
            name,
        )
        return []
    corpus = _adapter(manifest).load()
    train, test = prefix_split(corpus, PREFIX_POLICY)

    if not train.observations or not test.attack_intervals:
        logger.warning("%s: prefix split left nothing usable, skipping", name)
        return []
    logger.info(
        "%s prefix: fit on %d obs, score %d obs, %d attack windows",
        name,
        len(train.observations),
        len(test.observations),
        len(test.attack_intervals),
    )
    reports: list[EvaluationReport] = []
    routing = _routing_feature(manifest)
    for model in models if models is not None else contenders():
        reports.extend(_scored(model, train, test, "prefix", routing_feature=routing))
    return reports


def run_three_way(
    name: str,
    manifest: dict[str, Any],
    models: Sequence[BehaviouralModel] | None = None,
) -> list[EvaluationReport]:
    """Score every model on PART 4A's three-way split, uncalibrated and calibrated.

    This is the protocol the 8,390 FP/normal-hour figure comes from, and the only one that can
    report a calibrated Atlas detector: the calibrator is fitted on the middle slice and every
    reported number, calibration error included, comes from the test slice alone.
    """
    if name in DESIGNED_PROTOCOL_ONLY:
        logger.info(
            "%s: three-way split is not an honest protocol on this corpus (ADR 0046); skipping",
            name,
        )
        return []
    corpus = _adapter(manifest).load()
    policy = THREE_WAY_POLICIES.get(name, DEFAULT_THREE_WAY)

    try:
        train, calib, test = train_calib_test_split(corpus, policy)
    except DegenerateSplitError as error:
        logger.warning("%s: %s", name, error)
        return []

    reports: list[EvaluationReport] = []
    for model in models if models is not None else contenders():
        drop = set(_ROUTING_REGISTERS)
        if isinstance(model, PhaseConditionalModel):
            drop.discard(model.phase_feature)
        fit_train = train.without_features(drop)
        score_calib = calib.without_features(drop)
        score_test = test.without_features(drop)
        try:
            fitted = model.fit(fit_train.observations)
        except ValueError as error:
            if is_singular_covariance_refuse(error):
                logger.error(
                    "%s/%s: REFUSED (singular covariance at frozen shrinkage; "
                    "do not retune _shrink): %s",
                    name,
                    model.name,
                    error,
                )
                continue
            raise
        reports.append(evaluate(ModelDetector(fitted=fitted), score_test, _config()))

        scores, labels = scores_and_labels_from(fitted, score_calib)
        try:
            calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)
        except ValueError as error:
            logger.warning("%s/%s: could not fit a calibrator: %s", name, model.name, error)
            continue
        detector = CalibratedModelDetector(fitted=fitted, calibrator=calibrator)
        reports.append(evaluate(detector, score_test, _config()))
    return reports


def render(reports: Sequence[EvaluationReport]) -> str:
    """Render the reports as a markdown table, in the shape PROGRESS.md uses."""
    header = (
        "| Corpus | Detector | Recall | FPs | FP/normal-hr | Precision | Latency | ECE | Brier |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for report in reports:
        latency = f"{report.latency.median_seconds:.0f} s" if report.latency.count else "n/a"
        rows.append(
            f"| `{report.dataset_name}` | `{report.detector_name}` "
            f"| {report.window_recall:.2f} | {report.false_positives} "
            f"| {report.false_positive_rate:.2f} | {report.precision:.4f} | {latency} "
            f"| {report.expected_calibration_error:.4f} | {report.brier_score:.4f} |"
        )
    return "\n".join([header, *rows])


def summarise(reports: Sequence[EvaluationReport]) -> str:
    """State the headline per corpus and protocol: what did joint modelling do to the alarms?

    Both halves of the claim are printed, always. A collapse in false positives bought by a
    collapse in recall is not a win, and a summary that reported only the first number would be
    an advertisement rather than a measurement.
    """
    groups: dict[str, list[EvaluationReport]] = {}
    for report in reports:
        groups.setdefault(report.dataset_name, []).append(report)

    lines: list[str] = []
    for corpus, group in groups.items():
        baseline = next((r for r in group if r.detector_name == "model:gaussian"), None)
        if baseline is None:
            continue
        for report in group:
            if report is baseline or "gaussian" in report.detector_name:
                continue
            before, after = baseline.false_positive_rate, report.false_positive_rate
            factor = f"{before / after:.1f}x fewer" if after > 0 else "eliminated"
            lines.append(
                f"{corpus}: {report.detector_name} — FP/normal-hr {before:.2f} -> {after:.2f} "
                f"({factor}), recall {baseline.window_recall:.2f} -> {report.window_recall:.2f}"
            )
    return "\n".join(lines) or "nothing to compare"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument("--no-log", action="store_true", help="do not append to the experiment log")
    parser.add_argument(
        "--protocol",
        choices=("designed", "prefix", "three-way", "all"),
        default="all",
        help="which split protocol(s) to run; default is all three",
    )
    parser.add_argument(
        "--gated",
        action="store_true",
        help=(
            "also score Mahalanobis with an adaptive joint-distance gate (ADR 0026), and emit a "
            "moment-level detection row for the gated fit"
        ),
    )
    parser.add_argument(
        "--var",
        action="store_true",
        help=(
            "score LinearDynamicsModel (atlas-var1) only; do not re-log frozen Gaussian / PCA / "
            "Mahalanobis. Incompatible with --gated and --correlation."
        ),
    )
    parser.add_argument(
        "--correlation",
        action="store_true",
        help=(
            "score MahalanobisModel with ShrinkageTarget.CORRELATION only "
            "(atlas-mahalanobis-correlation). Incompatible with --var and --gated."
        ),
    )
    arguments = parser.parse_args(argv)
    exclusive = [flag for flag in ("var", "gated", "correlation") if getattr(arguments, flag)]
    if len(exclusive) > 1:
        parser.error("--var, --gated, and --correlation cannot be combined")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error("no integrated corpus found; run scripts/fetch_datasets.py --all first")
        return 2

    def models_for(manifest: dict[str, Any]) -> list[BehaviouralModel]:
        if arguments.var:
            return var_contenders()
        if arguments.correlation:
            return correlation_contenders()
        return selected_contenders(gated=arguments.gated, phase_feature=_routing_feature(manifest))

    def designed(n: str, m: dict[str, Any]) -> list[EvaluationReport]:
        return run_designed(n, m, models_for(m))

    def prefix(n: str, m: dict[str, Any]) -> list[EvaluationReport]:
        return run_prefix(n, m, models_for(m))

    def three_way(n: str, m: dict[str, Any]) -> list[EvaluationReport]:
        return run_three_way(n, m, models_for(m))

    selected: tuple[Callable[[str, dict[str, Any]], list[EvaluationReport]], ...] = {
        "designed": (designed,),
        "prefix": (prefix,),
        "three-way": (three_way,),
        "all": (designed, prefix, three_way),
    }[arguments.protocol]
    reports: list[EvaluationReport] = []
    for name, manifest in corpora:
        for protocol in selected:
            for report in protocol(name, manifest):
                reports.append(report)
                if not arguments.no_log:
                    append_to_experiment_log(report)

    if not reports:
        logger.error(
            "no scored row: no usable split, or a named model refused at frozen shrinkage "
            "(do not retune _shrink)"
        )
        return 2

    print("\n" + render(reports))
    print("\n" + summarise(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
