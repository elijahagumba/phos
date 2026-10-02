"""Tests for the detection record, the detector protocol and the threshold test stub."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection, Detector, ThresholdDetector
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def make_dataset(values: list[float], feature: str = "flow_rate") -> Dataset:
    return Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=[
            Observation(
                id=f"obs_{feature}_{index:06d}",
                entity_ids=["ent_000000000001"],
                feature=feature,
                value=value,
                timestamp=at(index),
                domain=Domain.ATLAS,
            )
            for index, value in enumerate(values)
        ],
        attack_intervals=[],
        source_note="hand-built fixture",
    )


# --------------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------------


def test_detection_defaults_to_no_entities_and_no_feature() -> None:
    detection = Detection(timestamp=T0, score=1.0, confidence=0.5)
    assert detection.entity_ids == []
    assert detection.feature is None


def test_detection_rejects_confidence_outside_the_unit_interval() -> None:
    with pytest.raises(ValidationError):
        Detection(timestamp=T0, score=1.0, confidence=1.5)
    with pytest.raises(ValidationError):
        Detection(timestamp=T0, score=1.0, confidence=-0.1)


def test_detection_is_frozen() -> None:
    detection = Detection(timestamp=T0, score=1.0, confidence=0.5)
    with pytest.raises(ValidationError):
        detection.score = 2.0  # type: ignore[misc]


def test_detection_round_trips_through_json() -> None:
    detection = Detection(
        timestamp=T0, score=3.5, confidence=0.75, entity_ids=["ent_1"], feature="flow_rate"
    )
    assert Detection.model_validate_json(detection.model_dump_json()) == detection


# --------------------------------------------------------------------------------------------
# ThresholdDetector
# --------------------------------------------------------------------------------------------


def test_threshold_detector_satisfies_the_detector_protocol() -> None:
    assert isinstance(ThresholdDetector(), Detector)


def test_threshold_detector_has_a_name_for_the_report() -> None:
    assert ThresholdDetector().name
    assert ThresholdDetector(name="custom").name == "custom"


def test_threshold_detector_scores_every_observation_at_the_default_threshold() -> None:
    dataset = make_dataset([10.0, 12.0, 14.0])
    assert len(ThresholdDetector().run(dataset)) == 3


def test_threshold_detector_computes_hand_checkable_zscores() -> None:
    # mean = 12, population stddev = sqrt(8/3) = 1.632993...
    dataset = make_dataset([10.0, 12.0, 14.0])
    scores = [d.score for d in ThresholdDetector().run(dataset)]
    expected = 2.0 / math.sqrt(8.0 / 3.0)
    assert scores == pytest.approx([expected, 0.0, expected])


def test_threshold_detector_scores_a_constant_feature_as_perfectly_normal() -> None:
    dataset = make_dataset([5.0, 5.0, 5.0])
    assert [d.score for d in ThresholdDetector().run(dataset)] == [0.0, 0.0, 0.0]


def test_threshold_detector_absolute_mode_scores_the_raw_value() -> None:
    dataset = make_dataset([10.0, 12.0, 14.0])
    detections = ThresholdDetector(use_zscore=False).run(dataset)
    assert [d.score for d in detections] == [10.0, 12.0, 14.0]


def test_threshold_detector_emits_only_scores_at_or_above_its_threshold() -> None:
    dataset = make_dataset([10.0, 12.0, 14.0])
    detections = ThresholdDetector(use_zscore=False, threshold=12.0).run(dataset)
    assert [d.score for d in detections] == [12.0, 14.0]


def test_threshold_detector_scores_each_feature_against_its_own_statistics() -> None:
    # A wide-ranging feature must not swamp a quiet one: both extremes score identically.
    quiet = make_dataset([1.0, 2.0, 3.0], feature="quiet")
    loud = make_dataset([100.0, 200.0, 300.0], feature="loud")
    combined = Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=sorted(quiet.observations + loud.observations, key=lambda o: o.timestamp),
        attack_intervals=[],
        source_note="two features",
    )
    detections = ThresholdDetector().run(combined)
    by_feature: dict[str, list[float]] = {"quiet": [], "loud": []}
    for detection in detections:
        assert detection.feature is not None
        by_feature[detection.feature].append(detection.score)
    assert by_feature["quiet"] == pytest.approx(by_feature["loud"])


def test_threshold_detector_confidence_is_bounded_and_monotone_in_score() -> None:
    dataset = make_dataset([10.0, 11.0, 30.0])
    detections = ThresholdDetector().run(dataset)
    for detection in detections:
        assert 0.0 <= detection.confidence <= 1.0
    ordered = sorted(detections, key=lambda d: d.score)
    confidences = [d.confidence for d in ordered]
    assert confidences == sorted(confidences)


def test_threshold_detector_carries_entities_and_feature_onto_the_detection() -> None:
    detection = ThresholdDetector().run(make_dataset([10.0, 20.0]))[0]
    assert detection.entity_ids == ["ent_000000000001"]
    assert detection.feature == "flow_rate"


def test_threshold_detector_returns_detections_in_time_order() -> None:
    dataset = make_dataset([10.0, 30.0, 11.0, 29.0])
    stamps = [d.timestamp for d in ThresholdDetector().run(dataset)]
    assert stamps == sorted(stamps)


def test_threshold_detector_handles_an_empty_dataset() -> None:
    empty = Dataset(
        name="empty",
        domain=Domain.ATLAS,
        observations=[],
        attack_intervals=[],
        source_note="",
    )
    assert ThresholdDetector().run(empty) == []


def test_threshold_detector_is_deterministic() -> None:
    dataset = make_dataset([10.0, 12.0, 14.0, 90.0])
    assert ThresholdDetector().run(dataset) == ThresholdDetector().run(dataset)


def test_threshold_detector_clamps_confidence_for_negative_absolute_scores() -> None:
    dataset = make_dataset([-50.0, -10.0])
    detections = ThresholdDetector(use_zscore=False, threshold=-100.0).run(dataset)
    assert [d.confidence for d in detections] == [0.0, 0.0]
