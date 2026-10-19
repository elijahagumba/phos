"""Origin facts name Tier.ORIGIN signals once, at the W5 weight."""

from phos.atlas.origin_evidence import ORIGIN_WEIGHT, _exclude, loud_member_names, origin_signals
from phos.atlas.root_cause import RootCause, Tier
from phos.reasoning import calibrated_probabilities


def test_loud_members_keep_out_of_band_signals_not_already_named() -> None:
    """A score of 1 is in band. A named signal is not given a second fact."""
    scored = (
        ("chlorine_residual_mgpl", 36.0),
        ("distribution_pressure_bar", 1.0),
        ("raw_turbidity_ntu", 1.01),
        ("chlorine_residual_mgpl", 40.0),
    )
    assert loud_member_names(scored, frozenset({"raw_turbidity_ntu"})) == (
        "chlorine_residual_mgpl",
    )


def test_origin_signals_keep_origins_once_in_rank_order() -> None:
    """Inherited and in-band candidates drop out, and a repeated origin is named once."""
    ranked = (
        RootCause(2, "chlorine_residual_mgpl", Tier.ORIGIN, 4.0, 1),
        RootCause(3, "distribution_pressure_bar", Tier.INHERITED, 3.0, 0),
        RootCause(2, "chlorine_residual_mgpl", Tier.ORIGIN, 4.0, 1),
        RootCause(7, "raw_turbidity_ntu", Tier.ORIGIN, 2.0, 2),
        RootCause(1, "clearwell_level_m", Tier.IN_BAND, 0.2, 0),
    )
    assert origin_signals(ranked) == ("chlorine_residual_mgpl", "raw_turbidity_ntu")


def test_origin_weight_is_the_w5_half() -> None:
    """Coefficient 0 and intercept 0 map every score to one half. The weight is not tuned."""
    assert calibrated_probabilities(ORIGIN_WEIGHT, [0.0, 3.0, 40.0]) == [0.5, 0.5, 0.5]


def test_exclude_puts_the_reading_outside_the_band() -> None:
    """The stored range is a departure, so the evidence boundary will accept the fact."""
    low, high, _centre = _exclude(4.8, 3.0, 0.2)
    assert low <= high
    assert not low <= 4.8 <= high
