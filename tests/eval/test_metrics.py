"""Tests for the pure metric functions.

Every expected value in this module is computed by hand in the comments, not by re-implementing
the metric. A metric that only agrees with itself proves nothing.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval.datasets import Dataset, LabelledInterval
from phos.eval.detectors import Detection
from phos.eval.metrics import (
    OperatingPoint,
    ReliabilityBin,
    brier_score,
    detection_latency,
    expected_calibration_error,
    f1,
    false_positive_rate,
    false_positives,
    false_positives_per_day,
    precision,
    precision_at_budget,
    recall_sample,
    reliability_table,
    threshold_sweep,
    unscored_alerts,
    window_recall,
)
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def make_observations(end_seconds: int, step: int = 60) -> list[Observation]:
    return [
        Observation(
            id=f"obs_{second:012d}",
            entity_ids=["ent_000000000001"],
            feature="flow_rate",
            value=1.0,
            timestamp=at(second),
            domain=Domain.ATLAS,
        )
        for second in range(0, end_seconds + 1, step)
    ]


def make_interval(start: int, end: int) -> LabelledInterval:
    return LabelledInterval(start=at(start), end=at(end), label="attack", attack_type=None)


def detect(second: int, score: float = 1.0, confidence: float = 0.5) -> Detection:
    return Detection(timestamp=at(second), score=score, confidence=confidence)


# --------------------------------------------------------------------------------------------
# Fixture A — the hand-worked example used across the alerting metrics.
#
#   Corpus span            0 .. 3600 s   (61 observations at 60 s cadence) = 3600 s
#   Attack intervals       I1 [600, 900]  (300 s)
#                          I2 [1800, 1860] (60 s)
#                          I3 [3000, 3060] (60 s)      total attack = 420 s
#   normal_duration        3600 - 420 = 3180 s = 0.883333... h
#
#   Detections             300  -> outside every interval           FALSE POSITIVE
#                          660  -> inside I1                        true positive
#                          840  -> inside I1                        true positive
#                          1860 -> inside I2 (on its end bound)     true positive
#                          2040 -> outside every interval           FALSE POSITIVE
#
#   window_recall          I1 hit, I2 hit, I3 missed                = 2/3
#   false_positives        {300, 2040}                              = 2
#   false_positive_rate    2 / 0.883333... h                        = 2.2641509...
#   detection_latency      I1: 660-600 = 60 s; I2: 1860-1800 = 60 s = [60 s, 60 s]
#   precision              3 true positives / 5 alerts              = 0.6
#   recall_sample          attack-labelled observations are
#                          {600,660,720,780,840,900, 1800,1860, 3000,3060} = 10;
#                          alerts land on {660, 840, 1860}          = 3/10 = 0.3
#   f1(0.6, 0.3)           2*0.6*0.3 / 0.9                          = 0.4
# --------------------------------------------------------------------------------------------

INTERVALS_A = [make_interval(600, 900), make_interval(1800, 1860), make_interval(3000, 3060)]
DETECTIONS_A = [detect(300), detect(660), detect(840), detect(1860), detect(2040)]


@pytest.fixture
def dataset_a() -> Dataset:
    return Dataset(
        name="fixture-a",
        domain=Domain.ATLAS,
        observations=make_observations(3600),
        attack_intervals=INTERVALS_A,
        source_note="hand-worked example",
    )


def test_fixture_a_normal_duration_is_what_the_hand_working_assumes(dataset_a: Dataset) -> None:
    assert dataset_a.duration() == timedelta(seconds=3600)
    assert dataset_a.normal_duration() == timedelta(seconds=3180)


# --------------------------------------------------------------------------------------------
# window_recall
# --------------------------------------------------------------------------------------------


def test_window_recall_matches_the_hand_computed_value() -> None:
    assert window_recall(DETECTIONS_A, INTERVALS_A) == pytest.approx(2 / 3)


def test_window_recall_counts_an_interval_once_however_many_alerts_land_in_it() -> None:
    # Both alerts sit inside I1, so recall must be 1/1 rather than 2/1.
    assert window_recall([detect(660), detect(840)], [make_interval(600, 900)]) == 1.0


def test_window_recall_is_zero_when_nothing_is_detected() -> None:
    assert window_recall([], INTERVALS_A) == 0.0


def test_window_recall_credits_an_alert_just_outside_an_interval_within_tolerance() -> None:
    # 590 s is 10 s before I1 starts; a 30 s tolerance forgives the label's boundary.
    alerts = [detect(590)]
    assert window_recall(alerts, [make_interval(600, 900)]) == 0.0
    assert window_recall(alerts, [make_interval(600, 900)], timedelta(seconds=30)) == 1.0


def test_window_recall_of_a_corpus_with_no_attacks_is_zero_not_one() -> None:
    # Vacuous "perfect recall" would let a do-nothing detector look flawless.
    assert window_recall(DETECTIONS_A, []) == 0.0


# --------------------------------------------------------------------------------------------
# false_positives / false_positive_rate
# --------------------------------------------------------------------------------------------


def test_false_positives_matches_the_hand_computed_count(dataset_a: Dataset) -> None:
    assert false_positives(DETECTIONS_A, dataset_a) == 2


def test_false_positive_rate_is_per_hour_of_normal_operation(dataset_a: Dataset) -> None:
    # 2 false positives / (3180 s / 3600 s per hour) = 2.264150943...
    assert false_positive_rate(DETECTIONS_A, dataset_a) == pytest.approx(2 / (3180 / 3600))


def test_false_positive_rate_uses_normal_time_not_total_time(dataset_a: Dataset) -> None:
    # The distinction is the whole point of the metric: dividing by total time would understate.
    assert false_positive_rate(DETECTIONS_A, dataset_a) > 2 / (3600 / 3600)


def test_tolerance_stops_an_alert_being_a_false_positive_and_a_hit_at_once() -> None:
    dataset = Dataset(
        name="edge",
        domain=Domain.ATLAS,
        observations=make_observations(3600),
        attack_intervals=[make_interval(600, 900)],
        source_note="",
    )
    alerts = [detect(590)]
    assert false_positives(alerts, dataset) == 1
    assert false_positives(alerts, dataset, timedelta(seconds=30)) == 0


def test_false_positive_rate_of_an_all_attack_corpus_is_zero_without_false_positives() -> None:
    dataset = Dataset(
        name="all-attack",
        domain=Domain.ATLAS,
        observations=make_observations(600),
        attack_intervals=[make_interval(0, 600)],
        source_note="",
    )
    assert dataset.normal_duration() == timedelta(0)
    assert false_positive_rate([detect(300)], dataset) == 0.0


def test_false_positive_rate_of_an_all_attack_corpus_is_infinite_with_false_positives() -> None:
    # No normal time to amortise a false alarm over: the rate is undefined-large, and saying so
    # is more honest than dividing by a fudge factor.
    dataset = Dataset(
        name="all-attack",
        domain=Domain.ATLAS,
        observations=make_observations(600),
        attack_intervals=[make_interval(0, 600)],
        source_note="",
    )
    assert false_positive_rate([detect(900)], dataset) == math.inf


# --------------------------------------------------------------------------------------------
# detection_latency
# --------------------------------------------------------------------------------------------


def test_detection_latency_matches_the_hand_computed_values() -> None:
    assert detection_latency(DETECTIONS_A, INTERVALS_A) == [
        timedelta(seconds=60),
        timedelta(seconds=60),
    ]


def test_detection_latency_reports_the_first_alert_in_an_interval() -> None:
    latencies = detection_latency([detect(840), detect(660)], [make_interval(600, 900)])
    assert latencies == [timedelta(seconds=60)]


def test_detection_latency_skips_undetected_intervals() -> None:
    assert detection_latency([], INTERVALS_A) == []


def test_detection_latency_ignores_alerts_that_only_matched_on_tolerance() -> None:
    # An alert before the interval starts has no meaningful latency, so it contributes none.
    assert detection_latency([detect(590)], [make_interval(600, 900)]) == []


def test_detection_latency_is_zero_when_the_alert_lands_on_the_interval_start() -> None:
    assert detection_latency([detect(600)], [make_interval(600, 900)]) == [timedelta(0)]


# --------------------------------------------------------------------------------------------
# precision / recall_sample / f1
# --------------------------------------------------------------------------------------------


def test_precision_matches_the_hand_computed_value(dataset_a: Dataset) -> None:
    assert precision(DETECTIONS_A, dataset_a) == pytest.approx(0.6)


def test_precision_without_alerts_is_zero(dataset_a: Dataset) -> None:
    assert precision([], dataset_a) == 0.0


def test_recall_sample_matches_the_hand_computed_value(dataset_a: Dataset) -> None:
    assert recall_sample(DETECTIONS_A, dataset_a) == pytest.approx(0.3)


def test_recall_sample_differs_from_window_recall(dataset_a: Dataset) -> None:
    # Window recall says "2 of 3 incidents caught"; sample recall says "3 of 10 attack samples
    # flagged". Reporting only the second is how detectors get talked out of adoption.
    assert recall_sample(DETECTIONS_A, dataset_a) != window_recall(DETECTIONS_A, INTERVALS_A)


def test_recall_sample_honours_tolerance(dataset_a: Dataset) -> None:
    # An alert 10 s before the 600 s sample catches it once tolerance covers the gap.
    assert recall_sample([detect(590)], dataset_a) == 0.0
    assert recall_sample([detect(590)], dataset_a, timedelta(seconds=30)) == pytest.approx(0.1)


def test_recall_sample_of_a_corpus_with_no_attack_samples_is_zero() -> None:
    dataset = Dataset(
        name="clean",
        domain=Domain.ATLAS,
        observations=make_observations(600),
        attack_intervals=[],
        source_note="",
    )
    assert recall_sample([detect(300)], dataset) == 0.0


@pytest.mark.parametrize(
    ("precision_value", "recall_value", "expected"),
    [
        (0.6, 0.3, 0.4),
        (1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, 0.5, 0.5),
    ],
)
def test_f1_is_the_harmonic_mean(
    precision_value: float, recall_value: float, expected: float
) -> None:
    assert f1(precision_value, recall_value) == pytest.approx(expected)


# --------------------------------------------------------------------------------------------
# threshold_sweep
# --------------------------------------------------------------------------------------------

SCORED_A = [
    detect(300, score=1.0),
    detect(660, score=5.0),
    detect(840, score=2.0),
    detect(1860, score=4.0),
    detect(2040, score=3.0),
]


def test_threshold_sweep_matches_the_hand_computed_operating_points(dataset_a: Dataset) -> None:
    # t=0.0  -> all 5 alerts:            recall 2/3, 2 FP, precision 3/5
    # t=3.0  -> {660:5, 1860:4, 2040:3}: recall 2/3, 1 FP (2040), precision 2/3
    # t=4.5  -> {660:5}:                 recall 1/3, 0 FP, precision 1.0
    # t=6.0  -> {}:                      recall 0,   0 FP, precision 0.0
    points = threshold_sweep(SCORED_A, dataset_a, [0.0, 3.0, 4.5, 6.0])
    assert [p.threshold for p in points] == [0.0, 3.0, 4.5, 6.0]
    assert [p.recall for p in points] == pytest.approx([2 / 3, 2 / 3, 1 / 3, 0.0])
    assert [p.precision for p in points] == pytest.approx([0.6, 2 / 3, 1.0, 0.0])
    hours = 3180 / 3600
    assert [p.fp_rate for p in points] == pytest.approx([2 / hours, 1 / hours, 0.0, 0.0])


def test_threshold_sweep_recall_and_fp_rate_never_rise_with_the_threshold(
    dataset_a: Dataset,
) -> None:
    points = threshold_sweep(SCORED_A, dataset_a, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    recalls = [p.recall for p in points]
    fp_rates = [p.fp_rate for p in points]
    assert recalls == sorted(recalls, reverse=True)
    assert fp_rates == sorted(fp_rates, reverse=True)


def test_threshold_sweep_is_empty_for_no_thresholds(dataset_a: Dataset) -> None:
    assert threshold_sweep(SCORED_A, dataset_a, []) == []


def test_operating_point_round_trips_through_json() -> None:
    point = OperatingPoint(threshold=1.0, recall=0.5, fp_rate=2.0, precision=0.25)
    assert OperatingPoint.model_validate_json(point.model_dump_json()) == point


# --------------------------------------------------------------------------------------------
# Calibration
#
# Corpus spans 0..1200 s with a single attack interval [0, 600]: an alert at or before 600 s is
# a true attack, anything later is not.
#
#   Ten alerts at confidence 0.9, nine of them at attack times  -> bin [0.9, 1.0]: empirical 0.9
#   Ten alerts at confidence 0.2, two  of them at attack times  -> bin [0.2, 0.3]: empirical 0.2
#
# Both bins are exactly right, so ECE = 0.
#   Brier = (9*(0.9-1)^2 + 1*(0.9-0)^2 + 2*(0.2-1)^2 + 8*(0.2-0)^2) / 20
#         = (0.09      + 0.81       + 1.28        + 0.32       ) / 20 = 2.50/20 = 0.125
# --------------------------------------------------------------------------------------------


@pytest.fixture
def calibration_dataset() -> Dataset:
    return Dataset(
        name="calibration",
        domain=Domain.ATLAS,
        observations=make_observations(1200),
        attack_intervals=[make_interval(0, 600)],
        source_note="",
    )


CALIBRATED = (
    [detect(second, confidence=0.9) for second in (0, 60, 120, 180, 240, 300, 360, 420, 480)]
    + [detect(720, confidence=0.9)]
    + [detect(second, confidence=0.2) for second in (540, 600)]
    + [detect(second, confidence=0.2) for second in (780, 840, 900, 960, 1020, 1080, 1140, 1200)]
)


def test_reliability_table_covers_the_unit_interval_in_equal_bins(
    calibration_dataset: Dataset,
) -> None:
    table = reliability_table(CALIBRATED, calibration_dataset, 10)
    assert len(table) == 10
    assert [round(b.lower, 10) for b in table] == [round(i / 10, 10) for i in range(10)]
    assert [round(b.upper, 10) for b in table] == [round((i + 1) / 10, 10) for i in range(10)]


def test_reliability_table_matches_the_hand_computed_bins(calibration_dataset: Dataset) -> None:
    table = reliability_table(CALIBRATED, calibration_dataset, 10)
    low_bin = table[2]
    high_bin = table[9]

    assert low_bin.count == 10
    assert low_bin.mean_confidence == pytest.approx(0.2)
    assert low_bin.empirical_rate == pytest.approx(0.2)

    assert high_bin.count == 10
    assert high_bin.mean_confidence == pytest.approx(0.9)
    assert high_bin.empirical_rate == pytest.approx(0.9)


def test_reliability_table_reports_empty_bins_with_a_zero_count(
    calibration_dataset: Dataset,
) -> None:
    table = reliability_table(CALIBRATED, calibration_dataset, 10)
    assert [b.count for b in table] == [0, 0, 10, 0, 0, 0, 0, 0, 0, 10]


def test_reliability_table_puts_full_confidence_in_the_last_bin(
    calibration_dataset: Dataset,
) -> None:
    table = reliability_table([detect(0, confidence=1.0)], calibration_dataset, 10)
    assert table[9].count == 1


def test_reliability_table_rejects_a_non_positive_bin_count(
    calibration_dataset: Dataset,
) -> None:
    with pytest.raises(ValueError, match="at least one bin"):
        reliability_table(CALIBRATED, calibration_dataset, 0)


def test_expected_calibration_error_of_a_perfectly_calibrated_set_is_zero(
    calibration_dataset: Dataset,
) -> None:
    assert expected_calibration_error(CALIBRATED, calibration_dataset, 10) == pytest.approx(0.0)


def test_expected_calibration_error_matches_the_hand_computed_value(
    calibration_dataset: Dataset,
) -> None:
    # Five alerts at 0.9 confidence, none of them real: |0.9 - 0.0| weighted 1.0 -> ECE 0.9.
    overconfident = [detect(second, confidence=0.9) for second in (660, 720, 780, 840, 900)]
    assert expected_calibration_error(overconfident, calibration_dataset, 10) == pytest.approx(0.9)


def test_expected_calibration_error_weights_bins_by_population(
    calibration_dataset: Dataset,
) -> None:
    # One wildly overconfident alert among nine perfect ones must not dominate:
    #   bin [0.9,1.0]: 9 alerts, all attacks, mean conf 0.9 -> |0.9-1.0| = 0.1, weight 9/10
    #   bin [0.0,0.1]: 1 alert, an attack,    mean conf 0.0 -> |0.0-1.0| = 1.0, weight 1/10
    #   ECE = 0.9*0.1 + 0.1*1.0 = 0.19
    detections = [
        detect(second, confidence=0.9) for second in (0, 60, 120, 180, 240, 300, 360, 420, 480)
    ] + [detect(540, confidence=0.0)]
    assert expected_calibration_error(detections, calibration_dataset, 10) == pytest.approx(0.19)


def test_expected_calibration_error_of_no_detections_is_zero(
    calibration_dataset: Dataset,
) -> None:
    assert expected_calibration_error([], calibration_dataset, 10) == 0.0


def test_brier_score_matches_the_hand_computed_value(calibration_dataset: Dataset) -> None:
    assert brier_score(CALIBRATED, calibration_dataset) == pytest.approx(0.125)


def test_brier_score_of_a_confidently_wrong_set(calibration_dataset: Dataset) -> None:
    # Confidence 0.9 on five non-attacks: (0.9 - 0)^2 = 0.81 every time.
    wrong = [detect(second, confidence=0.9) for second in (660, 720, 780, 840, 900)]
    assert brier_score(wrong, calibration_dataset) == pytest.approx(0.81)


def test_brier_score_of_a_perfect_set_is_zero(calibration_dataset: Dataset) -> None:
    perfect = [detect(0, confidence=1.0), detect(1200, confidence=0.0)]
    assert brier_score(perfect, calibration_dataset) == pytest.approx(0.0)


def test_brier_score_of_no_detections_is_zero(calibration_dataset: Dataset) -> None:
    assert brier_score([], calibration_dataset) == 0.0


def test_reliability_bin_round_trips_through_json() -> None:
    reliability_bin = ReliabilityBin(
        lower=0.0, upper=0.1, count=3, mean_confidence=0.05, empirical_rate=0.33
    )
    assert ReliabilityBin.model_validate_json(reliability_bin.model_dump_json()) == reliability_bin


def test_reliability_bin_rejects_rates_outside_the_unit_interval() -> None:
    with pytest.raises(ValidationError):
        ReliabilityBin(lower=0.0, upper=0.1, count=1, mean_confidence=0.05, empirical_rate=1.5)


def test_false_positives_per_day_is_twenty_four_times_the_hourly_rate() -> None:
    """Distillation 18.72 FP/hour * 24 = 449.28 FP/day. That is why 2-3/day stays refused."""
    assert false_positives_per_day(18.72) == pytest.approx(449.28)


def test_precision_at_budget_matches_cert_six_b_hand_count() -> None:
    """5 true positives in 48 alerts is 5/48. Empty ranking at a positive budget is 0."""
    ranked = (True,) * 5 + (False,) * 43
    assert precision_at_budget(ranked, 48) == pytest.approx(5 / 48)
    assert precision_at_budget((), 48) == 0.0
    with pytest.raises(ValueError, match="positive"):
        precision_at_budget(ranked, 0)


# --------------------------------------------------------------------------------------------
# Unscored intervals (ADR 0082)
# --------------------------------------------------------------------------------------------


def phased_dataset() -> Dataset:
    return Dataset(
        name="phased",
        domain=Domain.ATLAS,
        observations=make_observations(3600),
        attack_intervals=[make_interval(600, 900)],
        unscored_intervals=[
            LabelledInterval(start=at(1200), end=at(1800), label="unscored"),
        ],
    )


def test_unscored_time_leaves_the_denominator_and_its_alerts_leave_every_count() -> None:
    dataset = phased_dataset()
    alerts = [detect(700, confidence=0.5), detect(1500, confidence=0.9), detect(2400)]

    # Normal time: 3600 - 300 (attack) - 600 (unscored) = 2700 s = 0.75 h.
    assert dataset.normal_duration() == timedelta(seconds=2700)
    # 700 is a hit, 1500 is unscored and dropped, 2400 is the only false positive.
    assert false_positives(alerts, dataset) == 1
    # One hit + one false positive + one set aside = the three alerts.
    assert unscored_alerts(alerts, dataset) == 1
    assert false_positive_rate(alerts, dataset) == pytest.approx(1 / 0.75)
    # Precision over the two scored alerts: 1 hit of 2.
    assert precision(alerts, dataset) == pytest.approx(0.5)
    # Brier over the two scored alerts: ((0.5 - 1)^2 + (0.5 - 0)^2) / 2 = 0.25. Counting the
    # unscored 0.9 alert as a miss would give (0.25 + 0.81 + 0.25) / 3.
    assert brier_score(alerts, dataset) == pytest.approx(0.25)
    assert sum(row.count for row in reliability_table(alerts, dataset)) == 2
    # Unscored time is not a recall target.
    assert window_recall(alerts, dataset.attack_intervals) == 1.0


def test_a_true_positive_by_tolerance_is_not_lost_to_an_adjacent_unscored_window() -> None:
    dataset = Dataset(
        name="phased",
        domain=Domain.ATLAS,
        observations=make_observations(3600),
        attack_intervals=[make_interval(600, 900)],
        unscored_intervals=[LabelledInterval(start=at(901), end=at(1100), label="unscored")],
    )
    alerts = [detect(950)]
    tolerance = timedelta(seconds=60)
    # 950 is inside the unscored window but within tolerance of the attack: it is a hit.
    assert precision(alerts, dataset, tolerance) == 1.0
    assert false_positives(alerts, dataset, tolerance) == 0


def test_an_alert_only_in_unscored_time_gives_no_precision_rather_than_a_perfect_one() -> None:
    assert precision([detect(1500)], phased_dataset()) == 0.0
    assert brier_score([detect(1500)], phased_dataset()) == 0.0
