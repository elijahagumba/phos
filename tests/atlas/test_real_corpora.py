"""The headline integration test: does joint modelling actually fix HAI's false-positive rate.

PART 5A exists because of one number. PART 3's per-signal Gaussian, one independent baseline per
signal, posts roughly 8,390 false positives per normal hour on HAI's seventy-nine-signal corpus,
and that is operationally useless. The claim under test is that modelling the plant as a *related
system* — flagging only what breaks its learned correlations — collapses that number without
giving up recall.

Everything here is apples-to-apples on purpose. The same corpus, the same three-way split, the
same alert threshold and seed, the same harness. The only thing that differs between the baseline
and the contender is the model, so the difference in the numbers is attributable to the modelling
and to nothing else. The split fractions are duplicated from ``scripts/evaluate_atlas.py`` rather
than imported, so these tests do not depend on anything under ``scripts/``.

**Two results, and the second one is not the one PART 5A expected.** `MahalanobisModel` delivers
the claim in full. `PcaResidualModel` — the model 5A nominated as primary — does not: on HAI it
makes the false-positive rate *worse*. That is a measured fact about a real corpus rather than a
defect, its mechanism is understood and pinned by a test below, and it is recorded here rather
than tuned away (Constitution §3.5).
"""

import json
from functools import cache
from pathlib import Path

import pytest

from phos.atlas import MahalanobisModel, PcaResidualModel
from phos.eval import (
    Dataset,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    evaluate,
)
from phos.models import BehaviouralModel, FittedModel, GaussianBaseline, ModelDetector
from phos.reasoning import (
    CalibratedModelDetector,
    CalibrationSplitPolicy,
    IsotonicCalibrator,
    evidence_from_deviation,
    is_out_of_band,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

ALERT_THRESHOLD = 3.0
SEED = 11

#: HAI needs its own fractions: its attacks all fall in the first half of its test file, so the
#: default 0.4/0.3 leaves a test slice with nothing to be right about. Duplicated from
#: `scripts/calibrate_corpora.py`, which is where PART 4A's 8,390 figure comes from.
POLICIES = {
    "batadal": CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3),
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}

#: The reduction in false-positives-per-normal-hour that counts as "materially lower". Set well
#: below the 13x measured on HAI so this asserts the claim rather than the decimal place, and well
#: above 1.0 so a marginal change could not satisfy it.
MATERIAL_REDUCTION = 4.0


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
def sliced(name: str) -> tuple[Dataset, Dataset, Dataset]:
    """Return the ``(train, calib, test)`` slices of one corpus.

    Cached because loading and splitting a several-hundred-thousand-observation corpus is the
    expensive part of this module and every test below wants the same three slices.
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
    return train_calib_test_split(corpus, POLICIES[name])


@cache
def fitted_on_train(name: str, model: BehaviouralModel) -> FittedModel:
    """Return ``model`` fitted on the training slice of ``name``. Cached; models are frozen."""
    train, _, _ = sliced(name)
    return model.fit(train.observations)


@cache
def measured(name: str, model: BehaviouralModel) -> EvaluationReport:
    """Score ``model`` on the test slice of ``name`` through the PART 2 harness."""
    _, _, test = sliced(name)
    return evaluate(
        ModelDetector(fitted=fitted_on_train(name, model)),
        test,
        EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
    )


def out_of_band_rate(fitted: FittedModel, corpus: Dataset) -> float:
    """Return the share of a corpus's readings that fell outside the range judging them."""
    by_id = {observation.id: observation for observation in corpus.observations}
    outside = sum(
        1
        for deviation in fitted.score(corpus.observations)
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    )
    return outside / len(corpus.observations)


# ------------------------------------------------------------------------------------------------
# The headline
# ------------------------------------------------------------------------------------------------


@pytest.mark.skipif("hai" not in CORPORA, reason="HAI is the corpus this claim is about")
def test_joint_modelling_collapses_hai_false_positives_at_no_cost_to_recall() -> None:
    """The measured proof that treating the plant as one machine beats treating it as seventy-nine.

    Same corpus, same split, same threshold, same harness; only the model differs. The reduction
    must not be bought with recall, which is why both halves are asserted together — a detector
    that alerts less by detecting less has improved nothing.
    """
    baseline = measured("hai", GaussianBaseline())
    joint = measured("hai", MahalanobisModel())

    assert joint.window_recall >= baseline.window_recall, (
        f"joint modelling gave up recall ({joint.window_recall:.2f} vs "
        f"{baseline.window_recall:.2f}); a quieter detector that catches less is not an improvement"
    )
    assert joint.false_positive_rate * MATERIAL_REDUCTION < baseline.false_positive_rate, (
        f"joint modelling did not materially reduce false positives per normal hour: "
        f"{baseline.false_positive_rate:.2f} -> {joint.false_positive_rate:.2f}"
    )


@pytest.mark.skipif("hai" not in CORPORA, reason="HAI is the corpus this claim is about")
def test_the_per_signal_baseline_is_still_as_bad_as_part_three_reported() -> None:
    """Guards the other end of the comparison: the baseline must be the one PART 3 measured.

    Without this, a change that quietly degraded `GaussianBaseline` would make the headline test
    pass for entirely the wrong reason.
    """
    baseline = measured("hai", GaussianBaseline())

    assert baseline.false_positive_rate > 1000.0
    assert baseline.window_recall == 1.0


@pytest.mark.parametrize("name", CORPORA)
def test_joint_modelling_never_costs_recall_on_this_split(name: str) -> None:
    baseline = measured(name, GaussianBaseline())
    joint = measured(name, MahalanobisModel())

    assert joint.window_recall >= baseline.window_recall


# ------------------------------------------------------------------------------------------------
# The result PART 5A did not expect, and the mechanism behind it
# ------------------------------------------------------------------------------------------------


@pytest.mark.skipif("hai" not in CORPORA, reason="HAI is the corpus this claim is about")
def test_the_pca_residual_band_is_the_one_that_does_not_survive_capture_drift() -> None:
    """Why the primary model loses on HAI, stated as a measurement rather than an excuse.

    A PCA residual band is built from the variance the retained components *failed* to explain —
    5% of it at the default. That is a far tighter band than a marginal standard deviation, and it
    is tight in the one direction that matters here: HAI's training and test data are different
    capture periods, and between them the plant's correlation structure drifts. The drift is small
    in absolute terms and enormous relative to a band sized by the noise floor.

    The test measures the inflation itself. Both models are near their expected in-sample rate; the
    question is what happens to each when the capture changes underneath them.
    """
    train, _, _ = sliced("hai")
    _, _, test = sliced("hai")

    pca = fitted_on_train("hai", PcaResidualModel())
    gaussian = fitted_on_train("hai", GaussianBaseline())

    pca_inflation = out_of_band_rate(pca, test) / out_of_band_rate(pca, train)
    gaussian_inflation = out_of_band_rate(gaussian, test) / out_of_band_rate(gaussian, train)

    assert pca_inflation > gaussian_inflation, (
        "the finding this test pins has reversed: the PCA residual band now tolerates HAI's "
        f"capture drift at least as well as a marginal band ({pca_inflation:.1f}x vs "
        f"{gaussian_inflation:.1f}x). Re-measure and revisit ADR 0009"
    )


@pytest.mark.skipif("hai" not in CORPORA, reason="HAI is the corpus this claim is about")
def test_the_pca_residual_band_is_correct_in_sample() -> None:
    """The inflation above is drift, not a broken fit.

    On the data it learned from, a three-sigma band should leave a small single-digit percentage
    of readings outside it. If that were wrong too, the model would simply be defective and the
    drift explanation would be a story.
    """
    train, _, _ = sliced("hai")

    assert out_of_band_rate(fitted_on_train("hai", PcaResidualModel()), train) < 0.03


# ------------------------------------------------------------------------------------------------
# Pipeline integration: the joint models are ordinary citizens of PARTs 2 and 4
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", CORPORA)
def test_an_atlas_deviation_becomes_evidence_through_the_existing_boundary(name: str) -> None:
    """4A's out-of-band filter accepts a joint deviation with no special case written for it."""
    _, _, test = sliced(name)
    fitted = fitted_on_train(name, MahalanobisModel())
    by_id = {observation.id: observation for observation in test.observations}

    promoted = 0
    for deviation in fitted.score(test.observations):
        observation = by_id[deviation.observation_id]
        if not is_out_of_band(deviation, observation):
            continue
        evidence = evidence_from_deviation(
            deviation, observation, 0.7, summary=f"{deviation.expected.feature} left its band"
        )
        assert evidence.source_id == deviation.id
        assert evidence.entity_ids == observation.entity_ids
        promoted += 1
        if promoted == 25:
            break

    assert promoted > 0, f"{name}: no joint deviation was out-of-band, so nothing could be evidence"


@pytest.mark.parametrize("name", CORPORA)
def test_a_calibrated_atlas_detector_reports_real_probabilities(name: str) -> None:
    """Constitution §3.3 end to end: a joint model behind a calibrator fitted on a held-out slice.

    The calibrator never saw the test slice, and every number here comes only from it.
    """
    _, calib, test = sliced(name)
    fitted = fitted_on_train(name, MahalanobisModel())
    scores, labels = scores_and_labels_from(fitted, calib)
    calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)

    detector = CalibratedModelDetector(fitted=fitted, calibrator=calibrator)
    detections = detector.run(test)

    assert detections != []
    assert all(0.0 <= detection.confidence <= 1.0 for detection in detections)
    assert detector.name == f"model:{fitted.name}+isotonic"


@pytest.mark.parametrize("name", CORPORA)
def test_calibrating_a_joint_model_beats_leaving_it_uncalibrated(name: str) -> None:
    _, calib, test = sliced(name)
    fitted = fitted_on_train(name, MahalanobisModel())
    scores, labels = scores_and_labels_from(fitted, calib)
    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)

    calibrated = evaluate(
        CalibratedModelDetector(
            fitted=fitted, calibrator=IsotonicCalibrator(seed=SEED).fit(scores, labels)
        ),
        test,
        config,
    )

    uncalibrated = measured(name, MahalanobisModel())

    assert calibrated.expected_calibration_error < uncalibrated.expected_calibration_error


@pytest.mark.parametrize("name", CORPORA)
def test_calibration_leaves_the_alert_set_untouched(name: str) -> None:
    """`score` stays the raw magnitude, so before and after are two readings of one alert set."""
    _, calib, test = sliced(name)
    fitted = fitted_on_train(name, MahalanobisModel())
    scores, labels = scores_and_labels_from(fitted, calib)
    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)

    uncalibrated = measured(name, MahalanobisModel())
    calibrated = evaluate(
        CalibratedModelDetector(
            fitted=fitted, calibrator=IsotonicCalibrator(seed=SEED).fit(scores, labels)
        ),
        test,
        config,
    )

    assert calibrated.n_alerts == uncalibrated.n_alerts
    assert calibrated.window_recall == uncalibrated.window_recall
    assert calibrated.false_positive_rate == uncalibrated.false_positive_rate


# ------------------------------------------------------------------------------------------------
# Explainability holds on real telemetry, not only on fixtures
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", CORPORA)
def test_every_deviation_on_real_telemetry_names_a_signal_and_a_measurement(name: str) -> None:
    _, _, test = sliced(name)
    fitted = fitted_on_train(name, MahalanobisModel())
    by_id = {observation.id: observation for observation in test.observations}
    features = {observation.feature for observation in test.observations}

    deviations = fitted.score(test.observations)

    assert deviations != []
    for deviation in deviations[:500]:
        assert deviation.expected.feature in features
        observation = by_id[deviation.observation_id]
        assert observation.feature == deviation.expected.feature
        assert deviation.timestamp == observation.timestamp
        assert deviation.expected.low <= deviation.expected.high
