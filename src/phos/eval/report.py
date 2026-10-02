"""The evaluation report and the append-only experiment log.

A report is the durable answer to "how good was this detector, on what, under which settings".
It carries the metrics *and* everything needed to re-create them — corpus name, seed, threshold,
tolerance, and the git commit of the code that produced it — because a number nobody can
reproduce is not a measurement (Constitution §3.7).

The experiment log is one JSON object per line, appended and never rewritten. Over a year of
building engines it is the record of whether they actually got better.
"""

import logging
import statistics
import subprocess
from collections.abc import Sequence
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.metrics import OperatingPoint, ReliabilityBin
from phos.ontology import Domain, UtcDatetime, utc_now

__all__ = [
    "DEFAULT_LOG_PATH",
    "DEFAULT_SYNTH_SATURATION",
    "ClaimStatus",
    "EvaluationReport",
    "LatencySummary",
    "SaturationPolicy",
    "append_to_experiment_log",
    "apply_saturation_policy",
    "current_git_commit",
]

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("eval_runs/log.jsonl")
_GIT_TIMEOUT_SECONDS = 10


class ClaimStatus(StrEnum):
    """Whether a logged row may be quoted as a detection claim.

    ``MEASURED`` is the default and the only status historical ``log.jsonl`` rows had
    (they had no field). ``REFUSED`` means the metrics were computed but a declared
    saturation policy forbids quoting them as detection. Opt-in via
    `apply_saturation_policy`; `evaluate` never sets this on its own, so public
    distillation 18.72 and Data4Cyber Track A names stay ``MEASURED`` unless a
    caller applies a policy.
    """

    MEASURED = "MEASURED"
    REFUSED = "REFUSED"


class SaturationPolicy(BaseModel):
    """Declared FP load above which a detection claim is refused.

    Attributes:
        max_fp_per_hour: If set, a report whose ``false_positive_rate`` exceeds this
            is ``REFUSED``. ``None`` means the policy does not fire (C2 default for
            public re-runs).
    """

    model_config = ConfigDict(frozen=True)

    max_fp_per_hour: float | None = None


DEFAULT_SYNTH_SATURATION = SaturationPolicy(max_fp_per_hour=1.0)
"""The breaking-harness saturation line (1.0 FP/hour), as an opt-in eval policy."""


class LatencySummary(BaseModel):
    """Distribution of detection latencies across the windows a detector caught.

    Reported as a summary rather than a mean alone because latency is usually skewed: a detector
    that catches most incidents instantly and one late is a different product from one that is
    uniformly slow, and a mean hides which you have.

    Attributes:
        count: Number of windows that were detected at all. Windows that were missed contribute
            no latency, so this is *not* the number of attack windows in the corpus.
        min_seconds: Fastest detection, or ``None`` when nothing was detected.
        median_seconds: Median detection delay, or ``None``.
        mean_seconds: Mean detection delay, or ``None``.
        max_seconds: Slowest detection, or ``None``.
    """

    model_config = ConfigDict(frozen=True)

    count: int = Field(ge=0)
    min_seconds: float | None = None
    median_seconds: float | None = None
    mean_seconds: float | None = None
    max_seconds: float | None = None

    @classmethod
    def from_latencies(cls, latencies: Sequence[timedelta]) -> Self:
        """Summarise per-window latencies. An empty list yields all-``None`` statistics."""
        if not latencies:
            return cls(count=0)
        seconds = [latency.total_seconds() for latency in latencies]
        return cls(
            count=len(seconds),
            min_seconds=min(seconds),
            median_seconds=statistics.median(seconds),
            mean_seconds=statistics.fmean(seconds),
            max_seconds=max(seconds),
        )


class EvaluationReport(BaseModel):
    """Everything one run of the harness measured, plus what is needed to reproduce it.

    Attributes:
        detector_name: Which detector was scored.
        dataset_name: Which corpus it was scored on.
        domain: The corpus's domain.
        created_at: Wall-clock time of the run. This is provenance, not a result: it is the one
            field that differs between two otherwise identical runs.
        git_commit: Commit of the code that produced the numbers, when it could be determined.
        seed: The run's random seed.
        source_note: The corpus's provenance string, copied so the report stands alone.
        alert_threshold: Score at or above which a detection was treated as an alert.
        match_tolerance_seconds: Slack applied to attack-window bounds.
        calibration_bins: Bin count used for the reliability table.
        n_observations: Observations in the corpus.
        n_detections: Scored detections the detector emitted.
        n_alerts: Detections that met `alert_threshold`.
        n_attack_intervals: Ground-truth attack windows.
        n_unscored_intervals: Ground-truth windows that are neither attack nor normal (ADR 0082).
            Zero for every corpus that declares none, and for log lines written before the field.
        n_unscored_alerts: Alerts set aside because they fell in unscored time: neither true nor
            false positives, and absent from precision and the reliability table. With the true
            and false positives it adds up to `n_alerts`.
        normal_hours: Hours of normal operation — the false-positive-rate denominator. Excludes
            attack and unscored time.
        window_recall: Fraction of attack windows caught.
        false_positives: Alerts landing in no attack window and no unscored window.
        false_positive_rate: False positives per hour of normal operation. May be infinite when
            the corpus contains no normal time.
        precision: Fraction of alerts that were right.
        recall_sample: Fraction of attack-labelled observations flagged.
        f1: Harmonic mean of `precision` and `recall_sample`.
        latency: Detection-latency summary.
        operating_points: Recall / FP-rate / precision across a sweep of thresholds.
        expected_calibration_error: Population-weighted calibration gap.
        brier_score: Mean squared error of confidence against outcome.
        reliability: The reliability table behind the calibration numbers.
        claim_status: ``MEASURED`` (default) or ``REFUSED``. Historical log lines had no
            field and load as ``MEASURED``. Session C2: opt-in via `apply_saturation_policy`.
        saturation_policy: The declared FP-load policy, if a caller applied one.
        refusal_reason: Why a claim is ``REFUSED``, else ``None``. Metrics are never rewritten.

    Note:
        ``false_positive_rate`` can be infinite, so this model serialises non-finite floats as
        the JSON constants ``Infinity``/``NaN``. Python's ``json`` module reads them back; a
        strict RFC-8259 parser will not. Honesty about an undefined rate is worth that.
    """

    model_config = ConfigDict(frozen=True, ser_json_inf_nan="constants")

    detector_name: str
    dataset_name: str
    domain: Domain
    created_at: UtcDatetime = Field(default_factory=utc_now)
    git_commit: str | None = None
    seed: int
    source_note: str = ""

    alert_threshold: float
    match_tolerance_seconds: float
    calibration_bins: int = Field(ge=1)

    n_observations: int = Field(ge=0)
    n_detections: int = Field(ge=0)
    n_alerts: int = Field(ge=0)
    n_attack_intervals: int = Field(ge=0)
    n_unscored_intervals: int = Field(default=0, ge=0)
    n_unscored_alerts: int = Field(default=0, ge=0)
    normal_hours: float = Field(ge=0.0)

    window_recall: float = Field(ge=0.0, le=1.0)
    false_positives: int = Field(ge=0)
    false_positive_rate: float = Field(ge=0.0)
    precision: float = Field(ge=0.0, le=1.0)
    recall_sample: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    latency: LatencySummary
    operating_points: list[OperatingPoint] = Field(default_factory=list)

    expected_calibration_error: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0)
    reliability: list[ReliabilityBin] = Field(default_factory=list)

    claim_status: ClaimStatus = ClaimStatus.MEASURED
    saturation_policy: SaturationPolicy | None = None
    refusal_reason: str | None = None


def apply_saturation_policy(
    report: EvaluationReport, policy: SaturationPolicy | None = None
) -> EvaluationReport:
    """Return ``report`` with ``claim_status`` set from a declared saturation policy.

    Metrics are never rewritten. ``policy is None`` and a policy with
    ``max_fp_per_hour is None`` both leave the claim ``MEASURED``. Public
    distillation and Data4Cyber callers must omit a firing policy so those log
    names stay comparable.
    """
    active = policy if policy is not None else report.saturation_policy
    if active is None or active.max_fp_per_hour is None:
        return report.model_copy(
            update={
                "claim_status": ClaimStatus.MEASURED,
                "saturation_policy": active,
                "refusal_reason": None,
            }
        )
    if report.false_positive_rate > active.max_fp_per_hour:
        return report.model_copy(
            update={
                "claim_status": ClaimStatus.REFUSED,
                "saturation_policy": active,
                "refusal_reason": (
                    f"false_positive_rate {report.false_positive_rate:.4f} "
                    f"> max_fp_per_hour {active.max_fp_per_hour}"
                ),
            }
        )
    return report.model_copy(
        update={
            "claim_status": ClaimStatus.MEASURED,
            "saturation_policy": active,
            "refusal_reason": None,
        }
    )


def current_git_commit(cwd: Path | None = None) -> str | None:
    """Return the current git commit sha, or ``None`` if it cannot be determined.

    Tolerates every way this can fail — git not installed, not a repository, a repository with
    no commits yet — because provenance is worth recording but never worth failing a run over.
    """
    try:
        # Fixed argv, no shell, no interpolated input.
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.debug("could not determine git commit: %s", error)
        return None
    if completed.returncode != 0:
        logger.debug("git rev-parse failed: %s", completed.stderr.strip())
        return None
    return completed.stdout.strip() or None


def append_to_experiment_log(report: EvaluationReport, path: Path | str = DEFAULT_LOG_PATH) -> None:
    """Append one report to the experiment log as a single JSON line.

    Stamps the git commit if the report does not already carry one, so every logged number can
    be traced to the code that produced it. Creates the log's parent directory if needed.

    Args:
        report: The report to record.
        path: Log file. Defaults to `DEFAULT_LOG_PATH`.
    """
    stamped = report
    if stamped.git_commit is None:
        stamped = report.model_copy(update={"git_commit": current_git_commit()})

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(stamped.model_dump_json() + "\n")
    logger.info(
        "logged evaluation of %s on %s to %s", report.detector_name, report.dataset_name, path
    )
