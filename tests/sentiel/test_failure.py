"""Tests for `phos.sentiel.failure` — Usefulness Phase U2's classification of why Sentiel fails.

The module's whole claim rests on one piece of arithmetic — that a sum of squashed terms is bounded
by its term count — so that bound is tested directly, at its edges, and against the real squashing
function rather than a restatement of it.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from phos.models.detector import uncalibrated_confidence
from phos.sentiel.episode_null import (
    coherence_permutation_null,
    coherence_share,
    episode_permutation_null,
)
from phos.sentiel.failure import (
    DayCeiling,
    VisibilityVerdict,
    baseline_shifts,
    classify_insider,
    contribution_curve,
    day_ceiling,
    features_required,
    labelled_event_profile,
    score_ceiling,
)

DAY = datetime(2010, 7, 2, tzinfo=UTC)
THRESHOLD = 13.700640148454447
"""PART 6B's operating point. Passed in, never owned by the module under test."""


# ------------------------------------------------------------------------------------------------
# The ceiling is the finding, so it is tested against the real squashing function
# ------------------------------------------------------------------------------------------------


SATURATION_RATIO = 37.4299
"""``magnitude / scale`` at which the squashed term reaches exactly 1.0 in IEEE754.

Measured by bisection, not asserted. Below it the mathematical strict bound survives in floating
point; above it the term saturates and the ceiling becomes attainable rather than a supremum. At
`AggregationPolicy`'s scale of 3 this needs a magnitude of 112.29, against a largest magnitude of
18.768 anywhere in the CERT r3.1 run.
"""


@pytest.mark.parametrize("magnitude", [0.1, 1.0, 3.0, 10.0, 18.768, 100.0])
@pytest.mark.parametrize("scale", [3.0])
def test_one_feature_never_contributes_a_whole_point_at_any_observed_magnitude(
    magnitude: float, scale: float
) -> None:
    """The bound the whole U2 finding rests on, over the range the corpus actually reaches."""
    assert magnitude / scale < SATURATION_RATIO
    assert uncalibrated_confidence(magnitude, scale) < 1.0


@pytest.mark.parametrize("scale", [1.0, 3.0, 10.0])
def test_the_term_does_saturate_to_one_in_floating_point_and_the_module_says_so(
    scale: float,
) -> None:
    """The honest limit of the claim, pinned so a future reader cannot mistake it for exactness.

    A first draft of this module asserted a strict ``<`` bound. This test failed it. The bound is
    mathematically strict and numerically not, and the module now states the ``<=`` version.
    """
    assert uncalibrated_confidence(SATURATION_RATIO * scale * 1.01, scale) == 1.0
    assert uncalibrated_confidence(SATURATION_RATIO * scale * 0.99, scale) < 1.0


def test_the_saturation_ratio_is_where_bisection_puts_it() -> None:
    """The constant above is measured, so it is re-measured here rather than trusted."""
    low, high = 0.0, 200.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if uncalibrated_confidence(mid, 1.0) >= 1.0:
            high = mid
        else:
            low = mid
    assert high == pytest.approx(SATURATION_RATIO, abs=1e-3)


@pytest.mark.parametrize("n", [0, 1, 13, 14, 34])
def test_score_ceiling_is_the_speaking_feature_count(n: int) -> None:
    assert score_ceiling(n) == float(n)


def test_score_ceiling_refuses_a_negative_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        score_ceiling(-1)


def test_features_required_at_the_frozen_operating_point() -> None:
    """The number that makes the finding legible: 14 of 34 features must speak to alert at all."""
    assert features_required(THRESHOLD) == 14


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [(0.5, 1), (1.0, 1), (13.0, 13), (13.999, 14), (14.0, 14)],
)
def test_features_required_is_the_ceiling_of_the_threshold(threshold: float, expected: int) -> None:
    """``ceil``, because a term can reach exactly 1.0 in floating point.

    An earlier draft used ``floor(threshold) + 1``, which is right for every non-integer threshold
    — including PART 6B's — and one too many at an integer one.
    """
    assert features_required(threshold) == expected


def test_features_required_refuses_a_negative_threshold() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        features_required(-1.0)


# ------------------------------------------------------------------------------------------------
# The precedence rule
# ------------------------------------------------------------------------------------------------


def test_a_day_with_no_speaking_feature_is_evidence_absent() -> None:
    result = day_ceiling(DAY, 0.0, {}, THRESHOLD)
    assert result.verdict is VisibilityVerdict.EVIDENCE_ABSENT
    assert result.strongest_feature is None


def test_too_few_features_is_structurally_unalertable_however_large_they_are() -> None:
    """The counterfactual, as a test: infinite magnitude on every speaking feature still misses."""
    magnitudes = {f"f{i}": 1e9 for i in range(13)}
    result = day_ceiling(DAY, 12.99, magnitudes, THRESHOLD)
    assert result.verdict is VisibilityVerdict.STRUCTURALLY_UNALERTABLE
    assert result.ceiling == 13.0
    assert result.ceiling < THRESHOLD


def test_fourteen_features_lifts_the_ceiling_over_the_threshold() -> None:
    """One more speaking feature changes the verdict, which is what makes 14 the reported number."""
    magnitudes = {f"f{i}": 0.5 for i in range(14)}
    result = day_ceiling(DAY, 2.0, magnitudes, THRESHOLD)
    assert result.verdict is VisibilityVerdict.REACHABLE_BUT_SUBTHRESHOLD
    assert result.ceiling > THRESHOLD


def test_a_day_over_the_threshold_alerted() -> None:
    magnitudes = {f"f{i}": 9.0 for i in range(20)}
    result = day_ceiling(DAY, 18.5, magnitudes, THRESHOLD)
    assert result.verdict is VisibilityVerdict.ALERTED


def test_the_strongest_feature_is_reported_even_when_the_day_cannot_be_heard() -> None:
    """A day that cannot alert still says something, and the record keeps what it said."""
    result = day_ceiling(DAY, 3.0, {"quiet": 1.0, "loud": 6.33}, THRESHOLD)
    assert result.verdict is VisibilityVerdict.STRUCTURALLY_UNALERTABLE
    assert result.strongest_feature == "loud"
    assert result.strongest_magnitude == pytest.approx(6.33)


def test_the_strongest_feature_breaks_ties_by_name_so_the_record_is_deterministic() -> None:
    result = day_ceiling(DAY, 1.0, {"b": 2.0, "a": 2.0}, THRESHOLD)
    assert result.strongest_feature == "b"


# ------------------------------------------------------------------------------------------------
# The insider record
# ------------------------------------------------------------------------------------------------


def _days(n: int, speaking: int, score: float) -> list[tuple[datetime, float, dict[str, float]]]:
    return [
        (DAY + timedelta(days=i), score, {f"f{j}": 2.0 for j in range(speaking)}) for i in range(n)
    ]


def test_an_insider_whose_days_cannot_reach_the_ceiling_is_counted_as_such() -> None:
    record = classify_insider(
        "CCH0959",
        "2",
        _days(5, speaking=11, score=4.5),
        THRESHOLD,
        best_rank=957,
        n_scored_days=210_814,
        ordinary_scores=[4.6, 4.7],
    )
    assert record.counts[VisibilityVerdict.STRUCTURALLY_UNALERTABLE.value] == 5
    assert record.counts[VisibilityVerdict.ALERTED.value] == 0


def test_malicious_days_below_a_persons_own_ordinary_days_do_not_separate() -> None:
    """The comparison that needs no threshold at all."""
    record = classify_insider(
        "CCH0959",
        "2",
        _days(3, speaking=11, score=4.500),
        THRESHOLD,
        ordinary_scores=[4.586, 4.586],
    )
    assert record.separates_from_own_ordinary is False


def test_separation_is_none_when_there_are_no_ordinary_days_to_compare_against() -> None:
    """A refusal, not a False: an entity present only while malicious cannot answer."""
    record = classify_insider("X", "1", _days(2, speaking=20, score=15.0), THRESHOLD)
    assert record.separates_from_own_ordinary is None


def test_an_insider_with_no_malicious_days_reports_no_medians() -> None:
    record = classify_insider("X", "1", [], THRESHOLD)
    assert record.n_malicious_days == 0
    assert record.malicious_median is None


# ------------------------------------------------------------------------------------------------
# The permutation null
# ------------------------------------------------------------------------------------------------


def _series(scores: list[float]) -> list[tuple[datetime, float]]:
    return [(DAY + timedelta(days=i), s) for i, s in enumerate(scores)]


def test_the_null_is_reproducible_from_its_seed() -> None:
    by_entity = {
        f"u{i}": _series([random.Random(i).random() * 20 for _ in range(60)]) for i in range(20)
    }
    first = episode_permutation_null(
        by_entity, "n_episodes", 4.24, 13.70, timedelta(days=7), iterations=25, seed=11
    )
    second = episode_permutation_null(
        by_entity, "n_episodes", 4.24, 13.70, timedelta(days=7), iterations=25, seed=11
    )
    assert first.mean == second.mean
    assert first.low == second.low


def test_the_null_rejects_an_unknown_statistic() -> None:
    with pytest.raises(ValueError, match="unknown statistic"):
        episode_permutation_null({}, "not_a_statistic", 1.0, 2.0, timedelta(days=7), iterations=1)


def test_a_genuinely_clustered_entity_falls_outside_the_null() -> None:
    """The null must be able to say 'no', or its 'yes' means nothing.

    One entity with every elevated day contiguous, and long quiet stretches either side, produces
    one episode; reshuffling scatters those days and produces several.
    """
    high = [20.0] * 10
    low = [0.1] * 50
    by_entity = {"clustered": _series([*low[:25], *high, *low[25:]])}
    null = episode_permutation_null(
        by_entity, "n_episodes", 4.24, 13.70, timedelta(days=7), iterations=200, seed=11
    )
    assert null.observed == 1.0
    assert null.mean > null.observed


def test_the_null_records_its_seed_and_iteration_count() -> None:
    by_entity = {"u": _series([5.0] * 30)}
    null = episode_permutation_null(
        by_entity, "n_days", 4.24, 13.70, timedelta(days=7), iterations=7, seed=3
    )
    assert (null.n_iterations, null.seed) == (7, 3)


# ------------------------------------------------------------------------------------------------
# The coverage null — the one that reads a published claim back against chance
# ------------------------------------------------------------------------------------------------


def test_coverage_refuses_without_the_ground_truth_it_needs() -> None:
    """A missing argument must raise, not quietly count zero.

    Silently returning 0 would read as "the queue covered no malicious days", which is a
    measurement, not a missing input.
    """
    with pytest.raises(ValueError, match="needs both"):
        episode_permutation_null(
            {"u": _series([20.0] * 12)},
            "malicious_days",
            4.24,
            13.70,
            timedelta(days=7),
            iterations=1,
        )


def test_coverage_counts_only_malicious_days_inside_reportable_episodes() -> None:
    """A malicious day the queue never shows is not covered, however malicious it is."""
    by_entity = {"shown": _series([20.0] * 12), "quiet": _series([0.1] * 12)}
    null = episode_permutation_null(
        by_entity,
        "malicious_days",
        4.24,
        13.70,
        timedelta(days=7),
        iterations=1,
        malicious=frozenset({("shown", DAY), ("shown", DAY + timedelta(days=1)), ("quiet", DAY)}),
        budget=48,
    )
    assert null.observed == 2.0


def test_coverage_respects_the_operator_budget_by_peak_rank() -> None:
    """The budget is the whole point: an episode an operator never reaches covers nothing.

    Two reportable episodes, one strictly louder. At a budget of one, only the louder is read, so
    only the malicious day inside it counts.
    """
    by_entity = {"loud": _series([30.0] * 12), "soft": _series([14.0] * 12)}
    malicious = frozenset({("loud", DAY), ("soft", DAY)})
    wide = episode_permutation_null(
        by_entity,
        "malicious_days",
        4.24,
        13.70,
        timedelta(days=7),
        iterations=1,
        malicious=malicious,
        budget=48,
    )
    narrow = episode_permutation_null(
        by_entity,
        "malicious_days",
        4.24,
        13.70,
        timedelta(days=7),
        iterations=1,
        malicious=malicious,
        budget=1,
    )
    assert (wide.observed, narrow.observed) == (2.0, 1.0)


def test_coverage_can_say_no_when_the_malicious_days_are_genuinely_clustered() -> None:
    """The null must be able to reject, or an 'inside the null' verdict means nothing.

    Every malicious day placed on this entity's loudest days. Reshuffling moves the loud scores
    away from them, so the permuted coverage is reliably lower than the observed.
    """
    scores = [*([0.1] * 40), *([20.0] * 10)]
    by_entity = {"u": _series(scores)}
    malicious = frozenset({("u", DAY + timedelta(days=i)) for i in range(40, 50)})
    null = episode_permutation_null(
        by_entity,
        "malicious_days",
        4.24,
        13.70,
        timedelta(days=7),
        iterations=200,
        seed=11,
        malicious=malicious,
        budget=48,
    )
    assert null.observed == 10.0
    assert null.mean < null.observed
    assert null.p_at_least_observed < 0.5


# ------------------------------------------------------------------------------------------------
# Coherence
# ------------------------------------------------------------------------------------------------


def _triples(rows: list[tuple[float, str]]) -> list[tuple[datetime, float, str | None]]:
    return [(DAY + timedelta(days=i), s, f) for i, (s, f) in enumerate(rows)]


def test_the_coherence_null_observes_the_same_statistic_the_report_prints() -> None:
    """The null's observed value must equal a direct mean over multi-day episodes.

    The runner gates on exactly this equality, because a null whose observed value disagreed with
    the reported one would be a null about a different statistic.
    """
    rows = _triples([(20.0, "a")] * 6 + [(20.0, "b")] * 6)
    null = coherence_permutation_null(
        {"u": rows}, 4.24, 13.70, timedelta(days=7), iterations=1, seed=11
    )
    assert null.observed == coherence_share([f or "" for _d, _s, f in rows])


def test_the_coherence_null_is_reproducible_from_its_seed() -> None:
    by_entity = {
        f"u{i}": _triples([(random.Random(i).random() * 20, f"f{j % 5}") for j in range(60)])
        for i in range(10)
    }
    first = coherence_permutation_null(
        by_entity, 4.24, 13.70, timedelta(days=7), iterations=20, seed=11
    )
    second = coherence_permutation_null(
        by_entity, 4.24, 13.70, timedelta(days=7), iterations=20, seed=11
    )
    assert (first.mean, first.low, first.high) == (second.mean, second.low, second.high)


def test_the_coherence_null_can_say_no_when_the_leading_feature_tracks_time() -> None:
    """The null must be able to reject, or 'indistinguishable from chance' means nothing.

    Reshuffling carries the leading feature along with the score, so a *single* episode's feature
    mix is the same however its days are ordered. What the null can therefore detect is feature
    identity clustering **across** episodes: here two blocks of elevated days, separated by more
    than the seven-day gap, each internally driven by one feature. Observed, that is two perfectly
    coherent episodes. Reshuffled, the elevated days scatter, chain through the gap into one
    episode, and its two features disagree half the time.
    """
    rows = (
        [(20.0, "p")] * 10  # block one, one feature throughout
        + [(0.1, "x")] * 15  # a quiet stretch longer than the gap
        + [(20.0, "q")] * 10  # block two, a different feature throughout
    )
    null = coherence_permutation_null(
        {"u": _triples(rows)}, 4.24, 13.70, timedelta(days=7), iterations=200, seed=11
    )
    assert null.observed == 1.0
    assert null.mean < null.observed
    assert null.p_at_least_observed < 0.5


def test_the_coherence_null_reads_a_missing_leading_feature_as_the_empty_string() -> None:
    """A day with no leading feature must not crash the null, and must agree with the runner."""
    rows: list[tuple[datetime, float, str | None]] = [
        (DAY + timedelta(days=i), 20.0, None) for i in range(6)
    ]
    null = coherence_permutation_null(
        {"u": rows}, 4.24, 13.70, timedelta(days=7), iterations=1, seed=11
    )
    assert null.observed == 1.0


def test_a_single_day_episode_cannot_disagree_with_itself() -> None:
    assert coherence_share(["a"]) is None
    assert coherence_share([]) is None


def test_a_wholly_agreeing_episode_shares_everything() -> None:
    assert coherence_share(["a", "a", "a"]) == 1.0


def test_an_episode_driven_by_a_different_feature_every_day_shares_the_minimum() -> None:
    assert coherence_share(["a", "b", "c", "d"]) == 0.25


def test_the_share_is_the_modal_feature_not_the_first() -> None:
    assert coherence_share(["a", "b", "b", "b"]) == 0.75


def test_day_ceiling_round_trips_through_its_model() -> None:
    """The record is serialised into the report's JSON, so it must survive the trip."""
    result = day_ceiling(DAY, 9.155, {"new_counterparties": 6.333}, THRESHOLD)
    assert DayCeiling.model_validate(result.model_dump()) == result


# ------------------------------------------------------------------------------------------------
# Baseline shifts — the Q2 mechanism
# ------------------------------------------------------------------------------------------------


def test_an_onset_from_a_near_zero_baseline_reports_a_large_ratio() -> None:
    """Scenario 1's shape: a person who never did a thing starts doing it."""
    pre = [{"removable_device_connects": 0.0}] * 9 + [{"removable_device_connects": 1.0}]
    mal = [{"removable_device_connects": 1.0}] * 8
    (shift,) = baseline_shifts(pre, mal, ["removable_device_connects"])
    assert shift.pre_mean == pytest.approx(0.1)
    assert shift.ratio == pytest.approx(10.0)
    assert shift.shift_z is not None
    assert shift.shift_z > 2.0


def test_an_escalation_from_an_established_baseline_reports_a_small_shift() -> None:
    """Scenario 2's shape: a person who already did the thing does more of it."""
    pre = [{"removable_device_connects": v} for v in (1.0, 2.0, 3.0, 2.0, 4.0, 1.0)]
    mal = [{"removable_device_connects": v} for v in (3.0, 4.0, 3.0)]
    (shift,) = baseline_shifts(pre, mal, ["removable_device_connects"])
    assert shift.ratio is not None
    assert shift.ratio < 2.0
    assert shift.shift_z is not None
    assert shift.shift_z < 1.5


def test_a_feature_with_no_pre_attack_spread_reports_none_rather_than_zero() -> None:
    """A z-score over a constant baseline is undefined, and undefined is not zero."""
    pre = [{"f": 2.0}] * 5
    (shift,) = baseline_shifts(pre, [{"f": 9.0}], ["f"])
    assert shift.pre_stddev == 0.0
    assert shift.shift_z is None
    assert shift.ratio == pytest.approx(4.5)


def test_a_feature_with_a_zero_pre_attack_mean_reports_no_ratio() -> None:
    pre = [{"f": 0.0}, {"f": 0.0}, {"f": 1.0}, {"f": -1.0}]
    (shift,) = baseline_shifts(pre, [{"f": 3.0}], ["f"])
    assert shift.pre_mean == 0.0
    assert shift.ratio is None
    assert shift.shift_z is not None


def test_an_absent_feature_reads_as_zero_because_that_is_what_emission_means() -> None:
    (shift,) = baseline_shifts([{}, {}], [{"f": 1.0}], ["f"])
    assert shift.pre_mean == 0.0
    assert shift.malicious_mean == 1.0


def test_shifts_come_back_in_emission_order_not_sorted_by_the_quantity_reported() -> None:
    pre = [{"a": 1.0, "b": 1.0}]
    mal = [{"a": 9.0, "b": 2.0}]
    shifts = baseline_shifts(pre, mal, ["b", "a"])
    assert [s.feature for s in shifts] == ["b", "a"]


def test_no_shift_is_reported_when_either_side_is_empty() -> None:
    assert baseline_shifts([], [{"f": 1.0}], ["f"]) == ()
    assert baseline_shifts([{"f": 1.0}], [], ["f"]) == ()


# ------------------------------------------------------------------------------------------------
# The ground-truth profile — how "does the corpus contain the evidence" is checked
# ------------------------------------------------------------------------------------------------


def _row(kind: str, day: int, target: str | None) -> tuple[str, datetime, str | None]:
    return (kind, datetime(2010, 8, day, tzinfo=UTC), target)


def test_the_profile_counts_kinds_days_and_span() -> None:
    rows = [
        _row("http", 2, "indeed.com"),
        _row("http", 2, "monster.com"),
        _row("device", 5, None),
        _row("email", 9, "rival@example.com"),
    ]
    profile = labelled_event_profile("CCH0959", rows)
    assert profile.n_events == 4
    assert profile.kinds == {"http": 2, "device": 1, "email": 1}
    assert profile.active_days == 3
    assert profile.span_days == 8
    assert profile.distinct_targets == 3


def test_events_naming_no_target_do_not_inflate_the_target_count() -> None:
    """A workstation the person logs into daily is not somewhere data can go."""
    profile = labelled_event_profile("X", [_row("logon", 1, None), _row("device", 1, None)])
    assert profile.n_events == 2
    assert profile.distinct_targets == 0
    assert profile.top_targets == ()


def test_the_most_named_target_leads_and_the_list_is_capped() -> None:
    rows = [_row("http", 1, "jobs.example") for _ in range(5)]
    rows += [_row("http", 2, f"other{i}.example") for i in range(4)]
    profile = labelled_event_profile("X", rows, top=2)
    assert profile.top_targets[0] == ("jobs.example", 5)
    assert len(profile.top_targets) == 2


def test_an_insider_with_no_labelled_events_is_a_fact_not_an_error() -> None:
    profile = labelled_event_profile("X", [])
    assert (profile.n_events, profile.active_days, profile.span_days) == (0, 0, 0)


def test_a_single_event_spans_one_day() -> None:
    assert labelled_event_profile("X", [_row("http", 4, "a")]).span_days == 1


# ------------------------------------------------------------------------------------------------
# The saturation curve, as data rather than as a claim
# ------------------------------------------------------------------------------------------------


def test_the_curve_is_monotone_and_flattens() -> None:
    points = contribution_curve((1.0, 3.0, 6.0, 10.0, 18.768), 3.0)
    values = [c for _m, c in points]
    assert values == sorted(values)
    early = values[1] - values[0]
    late = values[-1] - values[-2]
    assert late < early


def test_the_curve_reports_the_magnitudes_it_was_given() -> None:
    points = contribution_curve((2.0, 5.0), 3.0)
    assert [m for m, _c in points] == [2.0, 5.0]


def test_depth_buys_almost_nothing_past_the_out_of_band_cut() -> None:
    """The claim the aggregation finding rests on, as a test rather than as prose."""
    (_, at_cut), (_, deep) = contribution_curve((3.0, 6.333), 3.0)
    assert at_cut == pytest.approx(0.6321, abs=1e-4)
    assert deep == pytest.approx(0.8789, abs=1e-4)
    assert deep / at_cut < 1.4
