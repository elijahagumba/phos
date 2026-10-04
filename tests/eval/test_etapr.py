"""eTaPR against the reference package, and recall inside a shift budget.

The eTaPR numbers below were produced by eTaPR 22.6.1 ``evaluate_w_ranges`` (wheel
``eTaPR-22.6.1-py3-none-any.whl``) on these same ranges. They are not recomputed by a second
copy of this implementation.
"""

from datetime import timedelta

import pytest
from tests.eval.test_metrics import (
    DETECTIONS_A,
    INTERVALS_A,
    T0,
    detect,
    make_interval,
    make_observations,
)

from phos.eval.datasets import Dataset
from phos.eval.metrics import etapr, recall_within_budget
from phos.ontology import Domain

# Anomalies (0, 9) and (30, 34). Predictions (2, 8), (32, 40), (50, 52).
# theta_p 0.5, theta_r 0.1, delta 0.
_BASE_ANOMALIES = ((0, 9), (30, 34))
_BASE_PREDICTIONS = ((2, 8), (32, 40), (50, 52))


def test_etapr_matches_the_reference_on_the_hand_built_case() -> None:
    result = etapr(_BASE_ANOMALIES, _BASE_PREDICTIONS, theta_p=0.5, theta_r=0.1, delta=0.0)
    assert result.etar == pytest.approx(0.425)
    assert result.etar_detection == pytest.approx(0.5)
    assert result.etar_portion == pytest.approx(0.35)
    assert result.etap == pytest.approx(0.35860968734610654)
    assert result.etap_detection == pytest.approx(0.35860968734610654)
    assert result.etap_portion == pytest.approx(0.35860968734610654)
    assert result.f1 == pytest.approx(0.38899242718212823)


def test_etapr_matches_the_reference_when_the_ambiguous_tail_is_on() -> None:
    # Anomaly (0, 9), predictions (10, 12) in the tail and (0, 4) in the anomaly.
    anomalies = ((0, 9),)
    predictions = ((10, 12), (0, 4))
    without = etapr(anomalies, predictions, theta_p=0.5, theta_r=0.1, delta=0.0)
    with_tail = etapr(anomalies, predictions, theta_p=0.5, theta_r=0.1, delta=0.5)
    assert without.etar == pytest.approx(0.75)
    assert without.etap == pytest.approx(0.5635083268962916)
    assert without.f1 == pytest.approx(0.6435151365516812)
    assert with_tail.etar == pytest.approx(0.8725050751832899)
    assert with_tail.etar_detection == pytest.approx(1.0)
    assert with_tail.etar_portion == pytest.approx(0.7450101503665799)
    assert with_tail.etap == pytest.approx(0.9599956475496451)
    assert with_tail.etap_detection == pytest.approx(1.0)
    assert with_tail.etap_portion == pytest.approx(0.9199912950992903)
    assert with_tail.f1 == pytest.approx(0.9141617945904674)
    assert with_tail.etar != pytest.approx(without.etar)


def test_etapr_of_a_perfect_cover_is_one_and_a_total_miss_is_zero() -> None:
    perfect = etapr(_BASE_ANOMALIES, _BASE_ANOMALIES, theta_p=0.5, theta_r=0.1)
    missed = etapr(_BASE_ANOMALIES, ((100, 103),), theta_p=0.5, theta_r=0.1)
    assert perfect.etar == pytest.approx(1.0)
    assert perfect.etap == pytest.approx(1.0)
    assert perfect.f1 == pytest.approx(1.0)
    assert missed.etar == pytest.approx(0.0)
    assert missed.etap == pytest.approx(0.0)
    assert missed.f1 == pytest.approx(0.0)


def test_etapr_of_an_empty_side_is_zero_rather_than_the_reference_nan() -> None:
    # eTaPR 22.6.1 returns NaN or raises on an empty side. An empty trial is a zero.
    assert etapr((), _BASE_PREDICTIONS, theta_p=0.5, theta_r=0.1).f1 == 0.0
    assert etapr(_BASE_ANOMALIES, (), theta_p=0.5, theta_r=0.1).f1 == 0.0


def test_etapr_rejects_a_parameter_outside_the_unit_interval() -> None:
    with pytest.raises(ValueError, match="theta_p"):
        etapr(_BASE_ANOMALIES, _BASE_PREDICTIONS, theta_p=1.1, theta_r=0.1)
    with pytest.raises(ValueError, match="delta"):
        etapr(_BASE_ANOMALIES, _BASE_PREDICTIONS, theta_p=0.5, theta_r=0.1, delta=-0.1)


def test_etapr_rejects_an_inverted_range() -> None:
    with pytest.raises(ValueError, match="inverted"):
        etapr(((5, 1),), _BASE_PREDICTIONS, theta_p=0.5, theta_r=0.1)


def _fixture_a() -> Dataset:
    """The one-hour corpus used by the hand-worked alerting example."""
    return Dataset(
        name="fixture-a",
        domain=Domain.ATLAS,
        observations=make_observations(3600),
        attack_intervals=list(INTERVALS_A),
        source_note="hand-worked example",
    )


def test_shift_budget_on_fixture_a() -> None:
    """One hour of fixture A sits in one eight-hour shift.

    Equal scores keep the earliest alerts. Budget 1 keeps 300 s (no hit). Budget 2 keeps
    300 and 660, and 660 hits the first of three windows.
    """
    dataset = _fixture_a()
    assert recall_within_budget(DETECTIONS_A, dataset, 1) == 0.0
    assert recall_within_budget(DETECTIONS_A, dataset, 2) == pytest.approx(1 / 3)
    # Five alerts, all kept: the same 2/3 as window recall.
    assert recall_within_budget(DETECTIONS_A, dataset, 5) == pytest.approx(2 / 3)


def test_a_higher_score_is_kept_ahead_of_an_earlier_miss() -> None:
    # 1860 is inside I2. Score 10 with a budget of one keeps it and drops the earlier miss.
    alerts = [detect(300, score=1.0), detect(1860, score=10.0)]
    assert recall_within_budget(alerts, _fixture_a(), 1) == pytest.approx(1 / 3)


def test_each_shift_has_its_own_budget() -> None:
    # Two one-hour shifts. Shift 0 holds a loud miss at 50 s and a real hit at 100 s.
    # Budget 1 keeps the miss. Shift 1's only alert hits its attack.
    observations = make_observations(7200)
    dataset = Dataset(
        name="two-shifts",
        domain=observations[0].domain,
        observations=observations,
        attack_intervals=[make_interval(100, 120), make_interval(4000, 4060)],
        source_note="two shifts",
    )
    alerts = [detect(50, score=100.0), detect(100, score=1.0), detect(4000, score=1.0)]
    assert recall_within_budget(alerts, dataset, 1, shift=timedelta(hours=1)) == pytest.approx(0.5)
    # A budget of two in the first shift also keeps the hit.
    assert recall_within_budget(alerts, dataset, 2, shift=timedelta(hours=1)) == pytest.approx(1.0)


def test_an_alert_on_the_shift_boundary_belongs_to_the_later_shift() -> None:
    # Origin is T0. An alert at exactly eight hours is shift 1, so it does not compete
    # with an alert at T0 when the budget is one.
    boundary = T0 + timedelta(hours=8)
    early = detect(0, score=1.0)
    late = detect(0, score=50.0).model_copy(update={"timestamp": boundary})
    dataset = Dataset(
        name="boundary",
        domain=Domain.ATLAS,
        observations=make_observations(8 * 3600),
        attack_intervals=[make_interval(0, 60), make_interval(8 * 3600, 8 * 3600)],
        source_note="shift boundary",
    )
    assert recall_within_budget([early, late], dataset, 1) == pytest.approx(1.0)


def test_recall_within_budget_rejects_a_non_positive_budget() -> None:
    with pytest.raises(ValueError, match="positive alert budget"):
        recall_within_budget(DETECTIONS_A, _fixture_a(), 0)
    with pytest.raises(ValueError, match="positive duration"):
        recall_within_budget(DETECTIONS_A, _fixture_a(), 1, shift=timedelta(0))


def test_unscored_alert_still_spends_a_slot() -> None:
    # 1500 s is normal in fixture A (between I1 and I2). Give it the only slot.
    # The real hit at 660 is dropped even though 1500 is not an attack.
    alerts = [detect(1500, score=10.0), detect(660, score=1.0)]
    assert recall_within_budget(alerts, _fixture_a(), 1) == 0.0
