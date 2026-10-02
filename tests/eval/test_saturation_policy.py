"""Session C2: saturated FP load is a refuse, not a rewritten metric.

The mechanism is opt-in. `evaluate` never fires it, so public distillation 18.72 and
Data4Cyber Track A names stay ``MEASURED``. Applying `DEFAULT_SYNTH_SATURATION` to a
loud row refuses the *claim* and leaves every number unchanged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from phos.atlas import ATLAS_VERTICAL_CAVEATS, SATURATED_FP_LOAD_CAVEAT
from phos.eval.datasets import SyntheticAnomaly, SyntheticICSAdapter
from phos.eval.detectors import ThresholdDetector
from phos.eval.harness import EvalConfig, evaluate
from phos.eval.metrics import OperatingPoint, ReliabilityBin
from phos.eval.report import (
    DEFAULT_SYNTH_SATURATION,
    ClaimStatus,
    EvaluationReport,
    LatencySummary,
    SaturationPolicy,
    apply_saturation_policy,
)
from phos.ontology import Domain

T0 = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def _report(**overrides: object) -> EvaluationReport:
    fields: dict[str, object] = {
        "detector_name": "threshold-detector",
        "dataset_name": "fixture",
        "domain": Domain.ATLAS,
        "created_at": T0,
        "seed": 7,
        "source_note": "hand-built",
        "alert_threshold": 2.0,
        "match_tolerance_seconds": 30.0,
        "calibration_bins": 10,
        "n_observations": 100,
        "n_detections": 100,
        "n_alerts": 5,
        "n_attack_intervals": 3,
        "normal_hours": 0.88,
        "window_recall": 2 / 3,
        "false_positives": 2,
        "false_positive_rate": 2.26,
        "precision": 0.6,
        "recall_sample": 0.3,
        "f1": 0.4,
        "latency": LatencySummary.from_latencies([timedelta(seconds=60)]),
        "operating_points": [OperatingPoint(threshold=0.0, recall=1.0, fp_rate=3.0, precision=0.2)],
        "expected_calibration_error": 0.05,
        "brier_score": 0.125,
        "reliability": [
            ReliabilityBin(lower=0.9, upper=1.0, count=5, mean_confidence=0.92, empirical_rate=0.8)
        ],
    }
    fields.update(overrides)
    return EvaluationReport.model_validate(fields)


def test_historical_json_without_claim_status_loads_as_measured() -> None:
    """Old log.jsonl rows had no field. They must keep validating as MEASURED."""
    payload = json.loads(_report().model_dump_json())
    del payload["claim_status"]
    del payload["saturation_policy"]
    del payload["refusal_reason"]
    restored = EvaluationReport.model_validate(payload)
    assert restored.claim_status is ClaimStatus.MEASURED
    assert restored.saturation_policy is None
    assert restored.refusal_reason is None


def test_evaluate_does_not_refuse_when_the_corpus_is_loud() -> None:
    """Public re-runs stay MEASURED unless a caller applies a policy."""
    dataset = SyntheticICSAdapter(
        n_points=240,
        anomaly_intervals=(
            SyntheticAnomaly(
                start_index=100, end_index=119, magnitude=50.0, attack_type="setpoint_tamper"
            ),
        ),
        seed=11,
        noise_stddev=1.0,
    ).load()
    report = evaluate(ThresholdDetector(), dataset, EvalConfig())
    assert report.claim_status is ClaimStatus.MEASURED
    assert report.saturation_policy is None
    assert report.refusal_reason is None


def test_saturation_policy_refuses_when_fp_per_hour_exceeds_the_declared_line() -> None:
    loud = _report(false_positive_rate=18.72)
    refused = apply_saturation_policy(loud, DEFAULT_SYNTH_SATURATION)
    assert refused.claim_status is ClaimStatus.REFUSED
    assert refused.saturation_policy == DEFAULT_SYNTH_SATURATION
    assert refused.refusal_reason is not None
    assert "18.7200" in refused.refusal_reason
    assert refused.false_positive_rate == 18.72
    assert refused.window_recall == loud.window_recall
    assert refused.precision == loud.precision
    assert loud.claim_status is ClaimStatus.MEASURED


def test_saturation_policy_does_not_fire_at_the_declared_line() -> None:
    on_the_line = _report(false_positive_rate=1.0)
    kept = apply_saturation_policy(on_the_line, DEFAULT_SYNTH_SATURATION)
    assert kept.claim_status is ClaimStatus.MEASURED
    assert kept.refusal_reason is None
    assert kept.false_positive_rate == 1.0


def test_omitting_a_policy_leaves_a_loud_row_measured() -> None:
    """This is the public-distillation path: omit the policy, keep the log name comparable."""
    loud = _report(false_positive_rate=18.72)
    assert apply_saturation_policy(loud, None).claim_status is ClaimStatus.MEASURED
    empty = SaturationPolicy(max_fp_per_hour=None)
    assert apply_saturation_policy(loud, empty).claim_status is ClaimStatus.MEASURED


def test_default_synth_saturation_is_the_breaking_harness_line() -> None:
    assert DEFAULT_SYNTH_SATURATION.max_fp_per_hour == 1.0


def test_atlas_vertical_carries_the_saturated_fp_load_caveat() -> None:
    assert SATURATED_FP_LOAD_CAVEAT in ATLAS_VERTICAL_CAVEATS
    assert "REFUSED" in SATURATED_FP_LOAD_CAVEAT
    assert "18.72" in SATURATED_FP_LOAD_CAVEAT


def test_applying_saturation_does_not_change_latency_or_counts() -> None:
    original = _report(false_positive_rate=2.26)
    refused = apply_saturation_policy(original, SaturationPolicy(max_fp_per_hour=1.0))
    assert refused.claim_status is ClaimStatus.REFUSED
    assert refused.n_alerts == original.n_alerts
    assert refused.false_positives == original.false_positives
    assert refused.latency == original.latency
    assert refused.operating_points == original.operating_points
