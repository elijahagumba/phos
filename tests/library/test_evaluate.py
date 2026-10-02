"""The library evaluator is a measurement façade, not a public-corpus runner.

These tests pin the wiring and the honesty tags. They do not generate a library or quote a
detection rate. ``ATLAS_DWELL_SAMPLES = 4`` is a library-only default; public Atlas rows freeze
``dwell_samples=1``.
"""

from pathlib import Path

import pytest

from phos.eval import EvaluationReport, LatencySummary
from phos.library.caveats import SYNTHETIC_LIBRARY_CAVEATS
from phos.library.evaluate import (
    ATLAS_DWELL_SAMPLES,
    _stamp,
    evaluate_it_library,
    evaluate_ot_library,
    library_root,
    write_run_summary,
)
from phos.ontology import Domain


def _report(*, source_note: str = "raw") -> EvaluationReport:
    return EvaluationReport(
        detector_name="dummy",
        dataset_name="dummy-pack",
        domain=Domain.ATLAS,
        seed=11,
        source_note=source_note,
        alert_threshold=0.0,
        match_tolerance_seconds=0.0,
        calibration_bins=10,
        n_observations=0,
        n_detections=0,
        n_alerts=0,
        n_attack_intervals=0,
        normal_hours=1.0,
        window_recall=0.0,
        false_positives=0,
        false_positive_rate=0.0,
        precision=0.0,
        recall_sample=0.0,
        f1=0.0,
        latency=LatencySummary(count=0),
        expected_calibration_error=0.0,
        brier_score=0.0,
    )


def test_library_dwell_is_not_the_public_atlas_default() -> None:
    """Public Atlas rows freeze dwell_samples=1. The library's 4 is a different experiment."""
    assert ATLAS_DWELL_SAMPLES == 4


def test_library_root_is_the_repo_dataset_library_directory() -> None:
    repo = Path("/tmp/phos-fake-root")
    assert library_root(repo) == repo / "dataset library"


def test_stamp_prepends_the_synthetic_library_caveats() -> None:
    stamped = _stamp(_report(), "library-ot plant=water-treatment")
    for caveat in SYNTHETIC_LIBRARY_CAVEATS:
        assert caveat in stamped.source_note
    assert "library-ot plant=water-treatment" in stamped.source_note
    assert "raw" in stamped.source_note
    assert "CERT" not in stamped.detector_name


def test_evaluate_ot_library_skips_when_payloads_are_missing(tmp_path: Path) -> None:
    reports = evaluate_ot_library(tmp_path, log=False)
    assert reports == []


def test_evaluate_it_library_refuses_a_missing_payload(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="IT library payload missing"):
        evaluate_it_library(tmp_path, log=False)


def test_write_run_summary_is_json_beside_the_log_not_a_substitute(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    write_run_summary(path, [_report()])
    text = path.read_text(encoding="utf-8")
    assert '"detector": "dummy"' in text
    assert '"dataset": "dummy-pack"' in text
    assert "CERT" not in text
