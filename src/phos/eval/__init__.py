"""The PHOS evaluation harness: the measurement spine.

Import everything public from here — ``from phos.eval import evaluate, EvalConfig`` — rather than
from the submodules, so internal layout can change without breaking callers.

Constitution §3.5 says nothing is trusted until it is measured. This package is where measuring
happens, and it is deliberately built before the things it measures. Its shape:

- A corpus reaches the harness only as a :class:`Dataset`, produced by a :class:`DatasetAdapter`.
  The harness never learns which corpus it is scoring, so a metric means the same thing on
  synthetic data and on a real ICS capture.
- A detector reaches the harness only as a :class:`Detector` — a name and ``run(dataset)``. That
  contract is the smallest thing that can be scored, so PART 3's behavioural models and the
  Atlas and Sentiel engines can conform to it later without the harness changing.
- :func:`evaluate` is pure and deterministic. Writing results to the experiment log is a
  separate, explicit step.

The only detector shipped here is :class:`ThresholdDetector`, a throwaway fixture that exists so
the harness's own tests are end-to-end. It is not a PHOS detection model.
"""

from phos.eval.datasets import (
    Dataset,
    DatasetAdapter,
    LabelledCsvAdapter,
    LabelledInterval,
    SyntheticAnomaly,
    SyntheticICSAdapter,
    default_attack_when,
)
from phos.eval.detectors import Detection, Detector, ThresholdDetector
from phos.eval.harness import EvalConfig, evaluate, sweep_thresholds
from phos.eval.joint_table import PUBLIC_JOINT_VS_UNIVARIATE, THREE_W_OFFSHORE_WELLS
from phos.eval.metrics import (
    EtaPrResult,
    OperatingPoint,
    ReliabilityBin,
    brier_score,
    detection_latency,
    etapr,
    expected_calibration_error,
    f1,
    false_positive_rate,
    false_positives,
    precision,
    recall_sample,
    recall_within_budget,
    reliability_table,
    threshold_sweep,
    unscored_alerts,
    window_recall,
)
from phos.eval.report import (
    DEFAULT_LOG_PATH,
    DEFAULT_SYNTH_SATURATION,
    ClaimStatus,
    EvaluationReport,
    LatencySummary,
    SaturationPolicy,
    append_to_experiment_log,
    apply_saturation_policy,
    current_git_commit,
)
from phos.eval.three_w import (
    FAULT_RECALL_NOT_ATTACK_CAVEAT,
    is_attack_class,
    is_fault_class,
    is_normal_class,
    prepare_attack_track,
)

__all__ = [
    "DEFAULT_LOG_PATH",
    "DEFAULT_SYNTH_SATURATION",
    "FAULT_RECALL_NOT_ATTACK_CAVEAT",
    "PUBLIC_JOINT_VS_UNIVARIATE",
    "THREE_W_OFFSHORE_WELLS",
    "ClaimStatus",
    "Dataset",
    "DatasetAdapter",
    "Detection",
    "Detector",
    "EtaPrResult",
    "EvalConfig",
    "EvaluationReport",
    "LabelledCsvAdapter",
    "LabelledInterval",
    "LatencySummary",
    "OperatingPoint",
    "ReliabilityBin",
    "SaturationPolicy",
    "SyntheticAnomaly",
    "SyntheticICSAdapter",
    "ThresholdDetector",
    "append_to_experiment_log",
    "apply_saturation_policy",
    "brier_score",
    "current_git_commit",
    "default_attack_when",
    "detection_latency",
    "etapr",
    "evaluate",
    "expected_calibration_error",
    "f1",
    "false_positive_rate",
    "false_positives",
    "is_attack_class",
    "is_fault_class",
    "is_normal_class",
    "precision",
    "prepare_attack_track",
    "recall_sample",
    "recall_within_budget",
    "reliability_table",
    "sweep_thresholds",
    "threshold_sweep",
    "unscored_alerts",
    "window_recall",
]
