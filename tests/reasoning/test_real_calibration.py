"""The headline integration test: calibration must beat the uncalibrated baseline on real data.

Constitution §3.3 is not satisfied by owning a calibrator — it is satisfied by a calibrated
confidence that empirically means what it says. So this is measured on real industrial telemetry,
through the PART 2 harness, against the same uncalibrated `ModelDetector` PART 3 shipped, on the
same test slice and the same alert set.

The corpora are git-ignored while their manifests are committed, so every case skips itself when
its payload is absent and a fresh clone stays green. The numbers these tests assert on are the ones
``scripts/calibrate_corpora.py`` writes to the experiment log.

Split fractions are per corpus and are duplicated from that script rather than imported, so the
tests do not depend on anything under ``scripts/``. HAI needs its own fractions: its attacks all
fall in the first half of its test file, so the default 0.4/0.3 leaves a test slice with nothing to
be right about, and `train_calib_test_split` refuses it.
"""

import json
from functools import cache
from pathlib import Path

import numpy
import pytest

from phos.eval import EvalConfig, EvaluationReport, LabelledCsvAdapter, evaluate
from phos.models import GaussianBaseline, ModelDetector
from phos.reasoning import (
    CalibratedModelDetector,
    CalibrationSplitPolicy,
    IsotonicCalibrator,
    PlattCalibrator,
    evidence_from_deviation,
    is_out_of_band,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

ALERT_THRESHOLD = 3.0
SEED = 11

POLICIES = {
    "batadal": CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3),
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}


def available() -> list[str]:
    """Return the names of corpora that have both a manifest and its CSV on disk."""
    present: list[str] = []
    for name in sorted(POLICIES):
        manifest_path = DATA_DIR / name / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (DATA_DIR / manifest["path"]).is_file():
            present.append(name)
    return present


CORPORA = available()

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not CORPORA,
        reason=(
            "no real corpus present; run scripts/fetch_datasets.py --all "
            f"(see {DATA_DIR}/README.md)"
        ),
    ),
]


@cache
def measured(name: str) -> tuple[EvaluationReport, EvaluationReport, EvaluationReport]:
    """Return ``(uncalibrated, isotonic, platt)`` reports for one corpus.

    Cached because fitting and scoring a 180,000-observation corpus three times is the expensive
    part of this module, and every test below reads the same three reports.
    """
    manifest = json.loads((DATA_DIR / name / "manifest.json").read_text(encoding="utf-8"))
    fields = {
        key: value
        for key, value in manifest.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    corpus = LabelledCsvAdapter.model_validate(
        {**fields, "path": str(DATA_DIR / manifest["path"])}
    ).load()

    train, calib, test = train_calib_test_split(corpus, POLICIES[name])
    fitted = GaussianBaseline().fit(train.observations)
    scores, labels = scores_and_labels_from(fitted, calib)
    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)

    return (
        evaluate(ModelDetector(fitted=fitted), test, config),
        evaluate(
            CalibratedModelDetector(
                fitted=fitted, calibrator=IsotonicCalibrator(seed=SEED).fit(scores, labels)
            ),
            test,
            config,
        ),
        evaluate(
            CalibratedModelDetector(
                fitted=fitted, calibrator=PlattCalibrator(seed=SEED).fit(scores, labels)
            ),
            test,
            config,
        ),
    )


# ------------------------------------------------------------------------------------------------
# The headline
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", CORPORA)
def test_calibration_beats_the_uncalibrated_baseline(name: str) -> None:
    """ECE on the test slice must be strictly lower than the uncalibrated detector's.

    This is the whole point of PART 4A. The calibrator saw only the calibration slice, and this
    number comes only from the test slice, so the improvement cannot be an artefact of fitting and
    measuring on the same data.
    """
    uncalibrated, isotonic, _ = measured(name)

    assert isotonic.expected_calibration_error < uncalibrated.expected_calibration_error, (
        f"{name}: isotonic calibration did not improve on the uncalibrated baseline "
        f"({isotonic.expected_calibration_error:.4f} vs "
        f"{uncalibrated.expected_calibration_error:.4f})"
    )


@pytest.mark.parametrize("name", CORPORA)
def test_the_comparison_is_between_two_readings_of_the_same_alert_set(name: str) -> None:
    """Calibration must change the confidence and nothing else.

    If the alert sets differed, a lower ECE could come from alerting differently rather than from
    claiming more honestly, and the comparison above would be meaningless.
    """
    uncalibrated, isotonic, platt = measured(name)

    for calibrated in (isotonic, platt):
        assert calibrated.n_alerts == uncalibrated.n_alerts
        assert calibrated.n_detections == uncalibrated.n_detections
        assert calibrated.window_recall == uncalibrated.window_recall
        assert calibrated.false_positives == uncalibrated.false_positives


@pytest.mark.parametrize("name", CORPORA)
def test_calibrated_confidences_are_probabilities(name: str) -> None:
    _, isotonic, platt = measured(name)

    for report in (isotonic, platt):
        assert sum(row.count for row in report.reliability) == report.n_alerts
        for row in report.reliability:
            assert 0.0 <= row.mean_confidence <= 1.0
            assert 0.0 <= row.empirical_rate <= 1.0


def test_isotonic_beats_platt_on_batadal() -> None:
    """On BATADAL, only the non-parametric calibrator survives the score distribution.

    Nine of BATADAL's forty-three features are perfectly constant across the training window, so
    their z-scores are infinite and `clamp_magnitude` pins them at ``MAX_MAGNITUDE`` — 1e6. The
    resulting score distribution has a median of 1.4, a 99th percentile of 3.1, and a maximum of
    1e6. Platt's logit is *linear in the raw score*, so those few extreme points dominate both its
    parameters and it collapses towards predicting the overall base rate for everything else.
    Isotonic uses only the rank ordering of the scores, so the clamp costs it nothing.

    This is why the calibrator is chosen by measurement rather than by reputation, and why the
    script reports both even though one loses.
    """
    if "batadal" not in CORPORA:
        pytest.skip("BATADAL is not present")
    _, isotonic, platt = measured("batadal")

    assert isotonic.expected_calibration_error <= platt.expected_calibration_error


# ------------------------------------------------------------------------------------------------
# Calibrated evidence, end to end
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", CORPORA)
def test_evidence_is_produced_from_real_out_of_band_deviations(name: str) -> None:
    """The two halves of this PART meet here: a real detection becomes calibrated `Evidence`.

    This is what PART 4B will consume. Every piece of evidence built here is out of band by
    construction — `evidence_from_deviation` refuses anything else — and carries a calibrated
    probability as its weight, so §3.3 holds on the path that reaches reasoning.
    """
    manifest = json.loads((DATA_DIR / name / "manifest.json").read_text(encoding="utf-8"))
    fields = {
        key: value
        for key, value in manifest.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    corpus = LabelledCsvAdapter.model_validate(
        {**fields, "path": str(DATA_DIR / manifest["path"])}
    ).load()
    train, calib, test = train_calib_test_split(corpus, POLICIES[name])
    fitted = GaussianBaseline().fit(train.observations)
    calibrator = IsotonicCalibrator(seed=SEED).fit(*scores_and_labels_from(fitted, calib))

    by_id = {observation.id: observation for observation in test.observations}
    deviations = fitted.score(test.observations)
    assert deviations, "the model emitted no candidates on real data"

    sample = deviations[:5000]
    out_of_band = [
        deviation
        for deviation in sample
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    ]
    in_band = len(sample) - len(out_of_band)

    # Calibrated in one batched call, exactly as `CalibratedModelDetector` does it: `calibrate`
    # takes an array of scores, not one score at a time.
    weights = calibrator.calibrate(
        numpy.asarray([deviation.magnitude for deviation in out_of_band], dtype=float)
    )
    evidence = [
        evidence_from_deviation(
            deviation,
            by_id[deviation.observation_id],
            float(weight),
            summary=f"{by_id[deviation.observation_id].feature} outside learned range",
        )
        for deviation, weight in zip(out_of_band, weights, strict=True)
    ]

    assert evidence, "no out-of-band deviation was found on real data"
    assert in_band > 0, (
        "every candidate was out of band, so this corpus cannot demonstrate the boundary — "
        "check that emit_k still sits below band_k"
    )
    assert all(0.0 <= item.weight <= 1.0 for item in evidence)
    assert all(item.source_id.startswith("dev_") for item in evidence)
