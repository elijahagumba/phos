"""Tests for the per-entity trailing history, against hand-computed answers.

The load-bearing property here is **causality**: a feature for window *t* may read only windows
strictly before *t*. Every test that could be satisfied by a leaky implementation is written so
that it cannot be — the fixture history and the current value are chosen to give visibly different
answers depending on whether the current window folded itself into its own baseline.
"""

import math

import pytest
from pydantic import ValidationError

from phos.sentiel.history import (
    NEUTRAL_VALUE,
    HistoryPolicy,
    TrailingHistory,
)

USER = "MALLORY9"
FEATURE = "file_access_count"
KIND = "counterparty"

# mean 5, population standard deviation exactly 2 — chosen so every expected z-score below is a
# whole number rather than a float with a comment attached to it.
EXACT = (2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0)


def _history(
    values: tuple[float, ...] = EXACT, policy: HistoryPolicy | None = None
) -> TrailingHistory:
    """Return a history that has already observed ``values`` for one user and one feature."""
    history = TrailingHistory(policy or HistoryPolicy())
    for value in values:
        history.observe(USER, {FEATURE: value}, {})
    return history


def _counterparty_history(
    *rounds: tuple[str, ...], policy: HistoryPolicy | None = None
) -> TrailingHistory:
    """Return a history that has already observed one set of counterparties per window."""
    history = TrailingHistory(policy or HistoryPolicy())
    for names in rounds:
        history.observe(USER, {}, {KIND: frozenset(names)})
    return history


# ------------------------------------------------------------------------------------------------
# Policy
# ------------------------------------------------------------------------------------------------


class TestHistoryPolicy:
    def test_the_defaults_are_the_documented_ones(self) -> None:
        policy = HistoryPolicy()
        assert policy.trailing_windows == 30
        assert policy.min_history_windows == 8
        assert policy.trend_windows == 7
        assert policy.deviation_cap == 10.0

    def test_it_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            HistoryPolicy().trailing_windows = 5  # type: ignore[misc]

    def test_a_min_history_longer_than_the_trailing_window_is_refused(self) -> None:
        """It would be a baseline that can never be reached, so it is rejected, not clamped."""
        with pytest.raises(ValidationError, match="min_history_windows"):
            HistoryPolicy(trailing_windows=4, min_history_windows=5, trend_windows=2)

    def test_a_trend_longer_than_the_trailing_window_can_supply_is_refused(self) -> None:
        """It would be a feature that is neutral forever — a dead signal, silently."""
        with pytest.raises(ValidationError, match="trend_windows"):
            HistoryPolicy(trailing_windows=4, min_history_windows=2, trend_windows=6)

    def test_a_trend_needs_at_least_two_points(self) -> None:
        with pytest.raises(ValidationError):
            HistoryPolicy(trend_windows=1)

    def test_a_non_positive_cap_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            HistoryPolicy(deviation_cap=0.0)


# ------------------------------------------------------------------------------------------------
# Causality — the load-bearing property
# ------------------------------------------------------------------------------------------------


class TestCausality:
    def test_reading_never_advances_the_history(self) -> None:
        """Two identical reads must agree; if a read folded its value in, the second would not."""
        history = _history()
        first = history.deviation(USER, FEATURE, 11.0)
        second = history.deviation(USER, FEATURE, 11.0)
        assert first == second == 3.0

    def test_the_current_value_is_absent_from_its_own_baseline(self) -> None:
        """The test that fails if the current window leaks into the baseline it is judged against.

        History is eight 10.0s, so the trailing mean is 10 and the trailing standard deviation is
        0 — a departure is the capped value. Had 100.0 been folded in first, the mean would be 20
        and the standard deviation 30, giving a finite z of about 2.67 instead.
        """
        history = _history((10.0,) * 8)
        assert history.deviation(USER, FEATURE, 100.0) == 10.0

    def test_observing_is_the_only_thing_that_advances_the_history(self) -> None:
        history = _history((10.0,) * 8)
        before = history.deviation(USER, FEATURE, 100.0)
        history.observe(USER, {FEATURE: 100.0}, {})
        after = history.deviation(USER, FEATURE, 100.0)
        assert before == 10.0
        assert after != before

    def test_one_users_history_is_untouched_by_another_users(self) -> None:
        history = _history()
        for value in (1000.0,) * 20:
            history.observe("SOMEONE_ELSE", {FEATURE: value}, {})
        assert history.deviation(USER, FEATURE, 11.0) == 3.0

    def test_one_features_history_is_untouched_by_another_features(self) -> None:
        history = _history()
        for value in (1000.0,) * 20:
            history.observe(USER, {"logon_count": value}, {})
        assert history.deviation(USER, FEATURE, 11.0) == 3.0


# ------------------------------------------------------------------------------------------------
# Baseline-relative deviation
# ------------------------------------------------------------------------------------------------


class TestDeviation:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(11.0, 3.0), (9.0, 2.0), (5.0, 0.0), (3.0, -1.0), (1.0, -2.0)],
    )
    def test_it_is_a_signed_z_score_against_the_users_own_trailing_history(
        self, value: float, expected: float
    ) -> None:
        """Mean 5, population standard deviation 2, so (value - 5) / 2 by hand."""
        assert _history().deviation(USER, FEATURE, value) == expected

    def test_it_is_signed_so_a_collapse_is_distinguishable_from_a_spike(self) -> None:
        history = _history()
        assert history.deviation(USER, FEATURE, 11.0) > 0.0
        assert history.deviation(USER, FEATURE, -1.0) < 0.0

    def test_it_is_capped_rather_than_allowed_to_run_away(self) -> None:
        assert _history().deviation(USER, FEATURE, 10_000.0) == 10.0
        assert _history().deviation(USER, FEATURE, -10_000.0) == -10.0

    def test_the_cap_is_configurable(self) -> None:
        policy = HistoryPolicy(deviation_cap=2.5)
        assert _history(policy=policy).deviation(USER, FEATURE, 10_000.0) == 2.5

    def test_a_shorter_history_than_min_history_windows_is_neutral(self) -> None:
        """Seven windows is one short of the default eight, so there is nothing to claim yet."""
        assert _history(EXACT[:7]).deviation(USER, FEATURE, 10_000.0) == NEUTRAL_VALUE

    def test_the_very_first_window_is_neutral(self) -> None:
        assert TrailingHistory().deviation(USER, FEATURE, 42.0) == NEUTRAL_VALUE

    def test_the_baseline_rolls_so_it_tracks_a_drifting_user(self) -> None:
        """Twelve old 0.0s fall out of a ten-window memory; only the recent 100.0s remain."""
        policy = HistoryPolicy(trailing_windows=10)
        history = _history((0.0,) * 12 + (100.0,) * 10, policy=policy)
        assert history.deviation(USER, FEATURE, 100.0) == 0.0

    def test_a_history_that_never_varied_reports_zero_for_the_same_value(self) -> None:
        assert _history((7.0,) * 8).deviation(USER, FEATURE, 7.0) == 0.0

    @pytest.mark.parametrize(("value", "expected"), [(7.5, 10.0), (6.5, -10.0)])
    def test_a_history_that_never_varied_reports_the_signed_cap_for_any_other_value(
        self, value: float, expected: float
    ) -> None:
        """The divide-by-zero policy: a documented capped value, never an infinity."""
        assert _history((7.0,) * 8).deviation(USER, FEATURE, value) == expected

    def test_no_deviation_is_ever_nan_or_infinite(self) -> None:
        histories = [_history(), _history((7.0,) * 8), _history(EXACT[:3]), TrailingHistory()]
        for history in histories:
            for value in (-1e12, -1.0, 0.0, 7.0, 1e12):
                assert math.isfinite(history.deviation(USER, FEATURE, value))


# ------------------------------------------------------------------------------------------------
# Temporal — first difference and trailing trend
# ------------------------------------------------------------------------------------------------


class TestDifference:
    def test_it_is_today_minus_the_prior_populated_window(self) -> None:
        """The last observed value is 9.0, so 11.0 today is a step of +2."""
        assert _history().difference(USER, FEATURE, 11.0) == 2.0

    def test_a_fall_is_negative(self) -> None:
        assert _history().difference(USER, FEATURE, 4.0) == -5.0

    def test_the_prior_window_is_the_prior_populated_one_not_the_prior_calendar_day(self) -> None:
        """History holds only the windows a user was active in, so gaps close rather than zero."""
        assert _history((3.0,)).difference(USER, FEATURE, 10.0) == 7.0

    def test_the_first_ever_window_is_neutral(self) -> None:
        assert TrailingHistory().difference(USER, FEATURE, 42.0) == NEUTRAL_VALUE


class TestTrend:
    def test_it_is_the_least_squares_slope_over_the_trailing_window_including_today(self) -> None:
        """Series [4, 4, 5, 5, 7, 9, 11] over x = 0..6: slope = 33 / 28 by hand."""
        assert _history().trend(USER, FEATURE, 11.0) == pytest.approx(33.0 / 28.0)

    def test_a_flat_user_has_no_trend(self) -> None:
        assert _history((5.0,) * 10).trend(USER, FEATURE, 5.0) == 0.0

    def test_a_sustained_climb_is_positive_and_a_decline_negative(self) -> None:
        climbing = _history((1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
        falling = _history((6.0, 5.0, 4.0, 3.0, 2.0, 1.0))
        assert climbing.trend(USER, FEATURE, 7.0) == pytest.approx(1.0)
        assert falling.trend(USER, FEATURE, 0.0) == pytest.approx(-1.0)

    def test_fewer_windows_than_the_trend_needs_is_neutral(self) -> None:
        """Five past windows plus today is six, one short of the default seven."""
        assert _history(EXACT[:5]).trend(USER, FEATURE, 100.0) == NEUTRAL_VALUE

    def test_the_trend_length_is_configurable(self) -> None:
        history = _history((1.0, 2.0), policy=HistoryPolicy(trend_windows=3))
        assert history.trend(USER, FEATURE, 3.0) == pytest.approx(1.0)

    def test_it_reads_only_as_far_back_as_the_trend_length_allows(self) -> None:
        """A distant spike outside the trend window cannot bend the slope."""
        assert _history((1000.0,) + (5.0,) * 6).trend(USER, FEATURE, 5.0) == 0.0

    def test_no_trend_is_ever_nan_or_infinite(self) -> None:
        history = _history((0.0, 1e12, 0.0, 1e12, 0.0, 1e12))
        assert math.isfinite(history.trend(USER, FEATURE, 1e12))


# ------------------------------------------------------------------------------------------------
# New counterparties
# ------------------------------------------------------------------------------------------------


class TestNewCounterparties:
    def test_it_counts_only_names_absent_from_the_users_trailing_history(self) -> None:
        history = _counterparty_history(*[("a", "b")] * 8)
        assert history.new_counterparties(USER, KIND, {"a", "b"}) == 0.0
        assert history.new_counterparties(USER, KIND, {"a", "c"}) == 1.0
        assert history.new_counterparties(USER, KIND, {"c", "d", "e"}) == 3.0

    def test_new_means_new_for_this_user_not_new_to_the_organisation(self) -> None:
        history = _counterparty_history(*[("a",)] * 8)
        for _ in range(8):
            history.observe("SOMEONE_ELSE", {}, {KIND: frozenset({"z"})})
        assert history.new_counterparties(USER, KIND, {"z"}) == 1.0

    def test_reading_does_not_make_a_counterparty_old(self) -> None:
        history = _counterparty_history(*[("a",)] * 8)
        assert history.new_counterparties(USER, KIND, {"q"}) == 1.0
        assert history.new_counterparties(USER, KIND, {"q"}) == 1.0

    def test_a_counterparty_that_falls_out_of_memory_is_new_again(self) -> None:
        """The rolling window is a memory, not a ledger; that is what bounds it."""
        policy = HistoryPolicy(trailing_windows=4, min_history_windows=2, trend_windows=2)
        history = _counterparty_history(("a",), *[("b",)] * 9, policy=policy)
        assert history.new_counterparties(USER, KIND, {"a"}) == 1.0

    def test_before_min_history_windows_it_is_neutral(self) -> None:
        """Everything is new to a user with no history; counting that would be noise, not signal."""
        history = _counterparty_history(*[("a",)] * 7)
        assert history.new_counterparties(USER, KIND, {"x", "y", "z"}) == NEUTRAL_VALUE

    def test_kinds_do_not_pool(self) -> None:
        history = _counterparty_history(*[("PC-1",)] * 8)
        assert history.new_counterparties(USER, KIND, {"PC-1"}) == 0.0
        assert history.new_counterparties(USER, "another_kind", {"PC-1"}) == NEUTRAL_VALUE

    def test_an_empty_day_counts_nothing(self) -> None:
        history = _counterparty_history(*[("a",)] * 8)
        assert history.new_counterparties(USER, KIND, frozenset()) == 0.0

    def test_a_window_with_no_counterparties_still_counts_as_history(self) -> None:
        """Otherwise a quiet user would never accumulate the history the cold start asks for."""
        history = _counterparty_history(*[()] * 8)
        assert history.new_counterparties(USER, KIND, {"a"}) == 1.0
