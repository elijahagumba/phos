"""Tests for entity-aware evaluation — the reason this PART exists.

The headline assertion is `test_a_detection_about_the_wrong_user_is_a_false_positive`. Everything
else in Sentiel could be right and, without that property, every number the programme ever reports
would be inflated by the ratio of innocent users to guilty ones.
"""

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import phos.eval.metrics
import phos.sentiel.evaluation as sentiel_evaluation
from phos.eval import Dataset, Detection, EvalConfig, EvaluationReport, LabelledInterval
from phos.ontology import Domain, Observation
from phos.sentiel import (
    SENTIEL_CAVEATS,
    EntityLabelledInterval,
    base_rate,
    entity_aware_detections,
    evaluate_entity_aware,
    sentiel_source_note,
    user_entity_id,
)

DAY_4 = datetime(2010, 1, 4, tzinfo=UTC)
DAY_5 = datetime(2010, 1, 5, tzinfo=UTC)
USERS = ("ALICE001", "MALLORY9")

LABELS = [
    EntityLabelledInterval(
        user_id="MALLORY9",
        start=DAY_4,
        end=DAY_4 + timedelta(hours=23, minutes=59),
        scenario="1",
    )
]


def _dataset(name: str = "sentiel-fixture") -> Dataset:
    """Four user-windows: two users over two days, one feature each."""
    return Dataset(
        name=name,
        domain=Domain.SENTIEL,
        observations=[
            Observation(
                id=f"obs_{user}_{day:%Y%m%d}",
                entity_ids=[user_entity_id(user)],
                feature="logon_count",
                value=1.0,
                timestamp=day,
                domain=Domain.SENTIEL,
                context={"user_id": user},
            )
            for day in (DAY_4, DAY_5)
            for user in USERS
        ],
        source_note="fixture",
    )


def _detection(user: str, day: datetime, score: float = 5.0, confidence: float = 0.9) -> Detection:
    return Detection(
        timestamp=day,
        score=score,
        confidence=confidence,
        entity_ids=[user_entity_id(user)],
        feature="logon_count",
    )


class _StubDetector:
    """Emits a fixed detection list. Exists so a test states the alert set exactly."""

    def __init__(self, detections: list[Detection], name: str = "stub") -> None:
        self._detections = detections
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def run(self, dataset: Dataset) -> list[Detection]:
        return list(self._detections)


# ------------------------------------------------------------------------------------------------
# The headline property
# ------------------------------------------------------------------------------------------------


def test_a_detection_about_the_right_user_in_window_is_a_hit() -> None:
    hits, misses = entity_aware_detections([_detection("MALLORY9", DAY_4)], LABELS)
    assert len(hits) == 1
    assert misses == []


def test_a_detection_about_the_wrong_user_is_a_false_positive() -> None:
    """Inside Mallory's window, but it names Alice. It accuses an innocent person."""
    hits, misses = entity_aware_detections([_detection("ALICE001", DAY_4)], LABELS)
    assert hits == []
    assert len(misses) == 1


def test_the_right_user_outside_their_window_is_a_false_positive() -> None:
    hits, misses = entity_aware_detections([_detection("MALLORY9", DAY_5)], LABELS)
    assert hits == []
    assert len(misses) == 1


def test_the_split_is_scored_the_same_way_end_to_end() -> None:
    """The same two detections, through the whole evaluation: one hit, one false alarm."""
    detector = _StubDetector([_detection("MALLORY9", DAY_4), _detection("ALICE001", DAY_4)])

    report = evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())

    assert report.window_recall == 1.0
    assert report.false_positives == 1
    assert report.precision == 0.5
    assert report.n_alerts == 2
    assert report.n_attack_intervals == 1


def test_a_time_only_matcher_would_have_scored_both_as_hits() -> None:
    """The bug this module exists to prevent, demonstrated rather than asserted."""
    alerts = [_detection("MALLORY9", DAY_4), _detection("ALICE001", DAY_4)]
    time_only = Dataset(
        name="time-only",
        domain=Domain.SENTIEL,
        observations=[],
        attack_intervals=[LABELS[0].as_labelled_interval()],
    )

    assert phos.eval.metrics.false_positives(alerts, time_only) == 0  # time-only: both "right"
    assert len(entity_aware_detections(alerts, LABELS)[1]) == 1  # entity-aware: one is wrong


def test_a_detection_naming_no_entity_is_refused() -> None:
    anonymous = Detection(timestamp=DAY_4, score=5.0, confidence=0.9)
    with pytest.raises(ValueError, match="must name the entity"):
        entity_aware_detections([anonymous], LABELS)


def test_a_dataset_carrying_time_only_intervals_is_refused() -> None:
    """Passing time-only truth here would reintroduce exactly the error above."""
    polluted = _dataset().model_copy(
        update={"attack_intervals": [LABELS[0].as_labelled_interval()]}
    )
    with pytest.raises(ValueError, match="time-only attack interval"):
        evaluate_entity_aware(_StubDetector([]), polluted, LABELS, EvalConfig())


# ------------------------------------------------------------------------------------------------
# Report shape and metric sanity
# ------------------------------------------------------------------------------------------------


def test_missing_the_window_entirely_scores_zero_recall() -> None:
    report = evaluate_entity_aware(
        _StubDetector([_detection("ALICE001", DAY_5)]), _dataset(), LABELS, EvalConfig()
    )
    assert report.window_recall == 0.0
    assert report.false_positives == 1
    assert report.precision == 0.0


def test_no_alerts_at_all_is_not_perfect_precision() -> None:
    report = evaluate_entity_aware(_StubDetector([]), _dataset(), LABELS, EvalConfig())
    assert report.n_alerts == 0
    assert report.precision == 0.0
    assert report.window_recall == 0.0
    assert report.false_positive_rate == 0.0


def test_every_reported_metric_is_in_range() -> None:
    detector = _StubDetector(
        [_detection("MALLORY9", DAY_4), _detection("ALICE001", DAY_4, score=2.0, confidence=0.3)]
    )
    report = evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())

    assert 0.0 <= report.window_recall <= 1.0
    assert 0.0 <= report.precision <= 1.0
    assert 0.0 <= report.recall_sample <= 1.0
    assert 0.0 <= report.f1 <= 1.0
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert 0.0 <= report.brier_score <= 1.0
    assert report.false_positive_rate >= 0.0
    assert sum(row.count for row in report.reliability) == report.n_alerts
    assert report.latency.count <= report.n_attack_intervals


def test_the_report_round_trips_and_is_a_part_2_report() -> None:
    """Sentiel runs land in the shared experiment log with no new report type to reconcile."""
    report = evaluate_entity_aware(
        _StubDetector([_detection("MALLORY9", DAY_4)]), _dataset(), LABELS, EvalConfig()
    )
    assert isinstance(report, EvaluationReport)
    assert EvaluationReport.model_validate_json(report.model_dump_json()) == report


def test_the_threshold_sweep_is_entity_aware_too() -> None:
    detector = _StubDetector(
        [_detection("MALLORY9", DAY_4, score=9.0), _detection("ALICE001", DAY_4, score=1.0)]
    )
    report = evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())

    assert report.operating_points
    highest = report.operating_points[-1]
    assert highest.precision == 1.0  # the low-scoring wrong-user alert has been thresholded away
    assert highest.recall == 1.0


def test_the_denominator_is_normal_user_hours_not_wall_clock() -> None:
    """Normal time is summed per user, and the difference from wall clock is not a rounding error.

    Alice is unlabelled, so her whole 24-hour span is normal. Mallory's label covers all but the
    last minute of hers, so she contributes one minute. Entity-aware normal time is therefore
    24h 1m.

    A time-only reading of the same corpus would subtract Mallory's window from the corpus's single
    24-hour span and call **one minute** normal — a denominator 1440x smaller, which would inflate
    every false-positive rate Sentiel ever reported by the same factor.
    """
    report = evaluate_entity_aware(_StubDetector([]), _dataset(), LABELS, EvalConfig())

    assert report.normal_hours == pytest.approx(24.0 + 1.0 / 60.0)

    time_only = _dataset().model_copy(
        update={"attack_intervals": [LABELS[0].as_labelled_interval()]}
    )
    assert time_only.normal_duration().total_seconds() / 3600.0 == pytest.approx(1.0 / 60.0)


def test_evaluation_is_deterministic() -> None:
    detector = _StubDetector([_detection("MALLORY9", DAY_4), _detection("ALICE001", DAY_5)])
    first = evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())
    second = evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())
    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


def test_latency_is_measured_from_the_start_of_the_window() -> None:
    late = _detection("MALLORY9", DAY_4 + timedelta(hours=6))
    report = evaluate_entity_aware(_StubDetector([late]), _dataset(), LABELS, EvalConfig())
    assert report.latency.count == 1
    assert report.latency.min_seconds == 6 * 3600.0


# ------------------------------------------------------------------------------------------------
# PART 2 is reused, not reimplemented, and not modified
# ------------------------------------------------------------------------------------------------

_PART_2_FUNCTIONS = (
    "window_recall",
    "false_positives",
    "detection_latency",
    "recall_sample",
    "reliability_table",
    "expected_calibration_error",
    "brier_score",
    "sweep_thresholds",
)


@pytest.mark.parametrize("name", _PART_2_FUNCTIONS)
def test_the_metric_functions_are_part_2s_own_objects(name: str) -> None:
    """Imported and called, not copied — a change in PART 2 changes Sentiel's numbers too."""
    assert getattr(sentiel_evaluation, name) is getattr(phos.eval, name)


@pytest.mark.parametrize("name", _PART_2_FUNCTIONS)
def test_evaluation_actually_calls_each_part_2_function(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original: Callable[..., object] = getattr(sentiel_evaluation, name)
    calls: list[int] = []

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(sentiel_evaluation, name, spy)
    detector = _StubDetector([_detection("MALLORY9", DAY_4), _detection("ALICE001", DAY_5)])
    evaluate_entity_aware(detector, _dataset(), LABELS, EvalConfig())

    assert calls, f"entity-aware evaluation never called PART 2's {name}"


def test_part_2s_labelled_interval_was_not_taught_about_entities() -> None:
    """The entity-scoped type lives on the Sentiel side; PART 2's stayed as it was."""
    assert "user_id" not in LabelledInterval.model_fields


def test_the_part_2_package_is_unmodified_in_git() -> None:
    """The strongest available statement of "does not modify the PART 2 package"."""
    repo = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "--", "src/phos/eval"],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env dependent
        pytest.skip(f"git unavailable: {error}")
    if completed.returncode != 0:  # pragma: no cover - env dependent
        pytest.skip(f"not a git checkout: {completed.stderr.strip()}")
    assert completed.stdout.strip() == "", (
        "PART 6·D must not modify the PART 2 harness, but git reports changes under "
        f"src/phos/eval:\n{completed.stdout}"
    )


# ------------------------------------------------------------------------------------------------
# The caveats and the base rate
# ------------------------------------------------------------------------------------------------


def test_the_source_note_carries_every_mandatory_caveat() -> None:
    note = sentiel_source_note("CERT r3.1", base_rate="1 malicious of 4 user-windows")

    assert note.startswith("CERT r3.1")
    assert "1 malicious of 4 user-windows" in note
    for caveat in SENTIEL_CAVEATS:
        assert caveat in note


def test_the_caveats_name_the_three_things_that_must_travel() -> None:
    joined = " ".join(SENTIEL_CAVEATS)
    assert "SYNTHETIC" in joined
    assert "STARTER" in joined
    assert "ENTITY-SCOPED" in joined


def test_a_report_built_from_the_note_carries_the_caveats() -> None:
    dataset = _dataset().model_copy(update={"source_note": sentiel_source_note("CERT r3.1")})
    report = evaluate_entity_aware(_StubDetector([]), dataset, LABELS, EvalConfig())
    for caveat in SENTIEL_CAVEATS:
        assert caveat in report.source_note


def test_base_rate_counts_malicious_and_benign_user_windows() -> None:
    assert base_rate(_dataset(), LABELS) == {
        "malicious_user_windows": 1,
        "benign_user_windows": 3,
    }
