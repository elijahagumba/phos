"""Session S4: CERT recall vs ticket budget is a curve; 6B @ 48 stays the ruler."""

from phos.sentiel import CERT_R31_BUDGET_CURVE, CERT_R31_HEADLINE_ALERTS


def test_the_48_alert_point_is_still_six_b() -> None:
    assert CERT_R31_HEADLINE_ALERTS == 48
    headline = next(point for point in CERT_R31_BUDGET_CURVE if point.headline)
    assert headline.alerts == 48
    assert headline.precision == 0.104
    assert headline.recall == 0.5
    assert headline.kind == "identity_6b"


def test_precision_policy_at_the_same_budget_is_a_loss_and_not_headlined() -> None:
    policy = next(point for point in CERT_R31_BUDGET_CURVE if point.kind == "precision_policy")
    assert policy.alerts == 48
    assert policy.precision == 0.083
    assert policy.recall == 0.5
    assert policy.headline is False
    assert policy.precision < 0.104
