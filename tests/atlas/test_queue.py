"""Ranking the subsystem-event queue and cutting it to an operator's budget.

Everything here runs on hand-built alerts, so every expected answer is countable by hand. What the
vertical measures on HAI is checked in `test_real_corpora.py`; what is under test here is the
ranking and the cut.

Three properties carry the weight:

- **The cut's denominator is the budget.** An operator who can work ten alerts and is handed three
  did not earn credit for the seven they never saw, so precision divides by the budget rather than
  by what happened to be available. This is `phos.eval.metrics.precision_at_budget`'s rule, and
  the two must not drift apart.
- **A tie across the cut is refused, not reported.** When the last alert taken and the first alert
  dropped share a score, membership of the queue was decided by the tiebreak. `cut_is_arbitrary`
  says so and `honest_points` drops the point.
- **Truth is overlap-aware.** A subsystem event is stamped at its earliest member but stands for
  all of them, so an event that began in normal time and continued into an attack has caught it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.atlas.queue import (
    ARBITRARY_CUT_CAVEAT,
    QUEUE_DETECTOR_PREFIX,
    RANKING_KEYS,
    BudgetOutcome,
    QueuedAlert,
    outcome_at_budget,
    queue_curve,
    queue_detector_name,
    rank_queue,
    windows_overlapped,
)
from phos.eval.datasets import LabelledInterval

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def alert(
    name: str,
    *,
    magnitude: float = 1.0,
    weight: float = 0.01,
    breadth: int = 1,
    offset_seconds: int = 0,
    covers: tuple[int, ...] = (),
) -> QueuedAlert:
    """Build one queued alert. Defaults are deliberately dull so a test names what it varies."""
    return QueuedAlert(
        evidence_id=name,
        timestamp=BASE + timedelta(seconds=offset_seconds),
        magnitude=magnitude,
        weight=weight,
        breadth=breadth,
        covers_windows=covers,
    )


class TestRanking:
    """The order the operator reads the queue in."""

    def test_ranks_most_severe_first(self) -> None:
        queue = [alert("a", magnitude=1.0), alert("b", magnitude=9.0), alert("c", magnitude=5.0)]
        assert [item.evidence_id for item in rank_queue(queue, "magnitude")] == ["b", "c", "a"]

    def test_ties_break_on_timestamp_then_id_so_the_order_is_reproducible(self) -> None:
        queue = [
            alert("z", magnitude=4.0, offset_seconds=10),
            alert("a", magnitude=4.0, offset_seconds=10),
            alert("m", magnitude=4.0, offset_seconds=0),
        ]
        assert [item.evidence_id for item in rank_queue(queue, "magnitude")] == ["m", "a", "z"]

    def test_the_same_queue_shuffled_ranks_identically(self) -> None:
        queue = [alert(f"e{index}", magnitude=float(index % 3)) for index in range(12)]
        forward = rank_queue(queue, "magnitude")
        backward = rank_queue(list(reversed(queue)), "magnitude")
        assert [item.evidence_id for item in forward] == [item.evidence_id for item in backward]

    def test_duplicate_ids_are_refused_because_the_tiebreak_would_be_ambiguous(self) -> None:
        queue = [alert("same", magnitude=1.0), alert("same", magnitude=2.0)]
        with pytest.raises(ValueError, match="duplicate evidence ids"):
            rank_queue(queue, "magnitude")

    @pytest.mark.parametrize("ranking", RANKING_KEYS)
    def test_every_declared_key_ranks_something(self, ranking: str) -> None:
        queue = [
            alert("low", magnitude=1.0, weight=0.001, breadth=1),
            alert("high", magnitude=9.0, weight=0.030, breadth=4),
        ]
        ranked = rank_queue(queue, ranking)  # type: ignore[arg-type]
        assert ranked[0].evidence_id == "high"


class TestBudgetCut:
    """What an operator working the top N alerts would actually have got."""

    def test_precision_divides_by_the_budget_not_by_what_was_available(self) -> None:
        queue = rank_queue([alert("a", magnitude=5.0, covers=(0,))], "magnitude")
        outcome = outcome_at_budget(queue, 10, "magnitude", n_windows=1)
        assert outcome.n_queued == 1
        assert outcome.true_positives == 1
        assert outcome.precision == pytest.approx(1 / 10)

    def test_window_recall_is_the_union_of_the_windows_the_taken_alerts_cover(self) -> None:
        queue = rank_queue(
            [
                alert("a", magnitude=9.0, covers=(0,)),
                alert("b", magnitude=8.0, covers=(0, 1)),
                alert("c", magnitude=1.0, covers=(2,)),
            ],
            "magnitude",
        )
        outcome = outcome_at_budget(queue, 2, "magnitude", n_windows=3)
        assert outcome.window_recall == pytest.approx(2 / 3)

    def test_a_corpus_with_no_windows_reports_zero_recall_not_a_vacuous_one(self) -> None:
        queue = rank_queue([alert("a", magnitude=1.0)], "magnitude")
        assert outcome_at_budget(queue, 1, "magnitude", n_windows=0).window_recall == 0.0

    def test_a_budget_of_zero_is_not_an_operating_point(self) -> None:
        queue = rank_queue([alert("a")], "magnitude")
        with pytest.raises(ValueError, match="positive operator volume"):
            outcome_at_budget(queue, 0, "magnitude", n_windows=1)

    def test_a_clean_cut_is_not_arbitrary(self) -> None:
        queue = rank_queue(
            [alert("a", magnitude=9.0), alert("b", magnitude=5.0), alert("c", magnitude=1.0)],
            "magnitude",
        )
        outcome = outcome_at_budget(queue, 2, "magnitude", n_windows=1)
        assert outcome.cut_is_arbitrary is False
        assert outcome.tie_span_at_cut == 1
        assert outcome.caveat is None

    def test_a_tie_spanning_the_cut_is_declared_arbitrary(self) -> None:
        queue = rank_queue(
            [
                alert("a", magnitude=9.0),
                alert("b", magnitude=4.0, offset_seconds=1),
                alert("c", magnitude=4.0, offset_seconds=2),
            ],
            "magnitude",
        )
        outcome = outcome_at_budget(queue, 2, "magnitude", n_windows=1)
        assert outcome.cut_is_arbitrary is True
        assert outcome.tie_span_at_cut == 2
        assert outcome.caveat == ARBITRARY_CUT_CAVEAT

    def test_a_budget_past_the_end_of_the_queue_cut_nothing_so_is_not_arbitrary(self) -> None:
        queue = rank_queue([alert("a", magnitude=4.0), alert("b", magnitude=4.0)], "magnitude")
        outcome = outcome_at_budget(queue, 5, "magnitude", n_windows=1)
        assert outcome.cut_is_arbitrary is False
        assert outcome.n_queued == 2

    def test_an_outcome_cannot_claim_an_arbitrary_cut_without_a_tie(self) -> None:
        with pytest.raises(ValidationError, match="tie_span_at_cut"):
            BudgetOutcome(
                budget=1,
                ranking="magnitude",
                n_queued=1,
                n_available=1,
                true_positives=0,
                precision=0.0,
                window_recall=0.0,
                n_windows=1,
                n_true_available=0,
                cut_score=1.0,
                tie_span_at_cut=1,
                cut_is_arbitrary=True,
            )


class TestOverlapAwareTruth:
    """An event stamped in normal time that continued into an attack has caught that attack."""

    def test_a_later_member_inside_a_window_counts_even_when_the_stamp_is_outside(self) -> None:
        window = LabelledInterval(
            start=BASE + timedelta(seconds=100),
            end=BASE + timedelta(seconds=200),
            label="attack",
        )
        stamps = [BASE, BASE + timedelta(seconds=150)]
        assert windows_overlapped(stamps, [window]) == (0,)

    def test_an_event_wholly_in_normal_time_covers_nothing(self) -> None:
        window = LabelledInterval(
            start=BASE + timedelta(seconds=100),
            end=BASE + timedelta(seconds=200),
            label="attack",
        )
        assert windows_overlapped([BASE], [window]) == ()

    def test_tolerance_widens_both_bounds_exactly_as_the_metrics_module_does(self) -> None:
        window = LabelledInterval(
            start=BASE + timedelta(seconds=100),
            end=BASE + timedelta(seconds=200),
            label="attack",
        )
        just_before = BASE + timedelta(seconds=95)
        assert windows_overlapped([just_before], [window]) == ()
        assert windows_overlapped([just_before], [window], timedelta(seconds=10)) == (0,)

    def test_indices_are_ascending_and_without_repeats(self) -> None:
        windows = [
            LabelledInterval(start=BASE, end=BASE + timedelta(seconds=10), label="attack"),
            LabelledInterval(
                start=BASE + timedelta(seconds=20),
                end=BASE + timedelta(seconds=30),
                label="attack",
            ),
        ]
        stamps = [BASE + timedelta(seconds=25), BASE + timedelta(seconds=5), BASE]
        assert windows_overlapped(stamps, windows) == (0, 1)


class TestCurve:
    """The curve an operator's budget is read off."""

    def test_budgets_are_deduplicated_and_presented_ascending(self) -> None:
        queue = [alert(f"e{index}", magnitude=float(index)) for index in range(5)]
        curve = queue_curve(queue, [10, 1, 10, 3], "magnitude", n_windows=1)
        assert [point.budget for point in curve.points] == [1, 3, 10]

    def test_an_empty_budget_list_is_not_a_curve(self) -> None:
        with pytest.raises(ValueError, match="at least one budget"):
            queue_curve([alert("a")], [], "magnitude", n_windows=1)

    def test_a_constant_key_is_reported_as_having_ranked_nothing(self) -> None:
        queue = [alert(f"e{index}", breadth=1) for index in range(6)]
        curve = queue_curve(queue, [3], "breadth", n_windows=1)
        assert curve.distinct_scores == 1
        assert curve.ranks_at_all is False

    def test_honest_points_drop_the_cuts_the_tiebreak_decided(self) -> None:
        queue = [
            alert("a", magnitude=9.0),
            alert("b", magnitude=4.0, offset_seconds=1),
            alert("c", magnitude=4.0, offset_seconds=2),
        ]
        curve = queue_curve(queue, [1, 2, 3], "magnitude", n_windows=1)
        assert [point.budget for point in curve.points] == [1, 2, 3]
        assert [point.budget for point in curve.honest_points] == [1, 3]


class TestNamesCannotCollideWithTheFrozenVerticalRows:
    """53.26 grouped and 646.58 ungated are frozen public names. A queue row is not one of them."""

    @pytest.mark.parametrize("ranking", RANKING_KEYS)
    def test_every_queue_name_carries_the_queue_prefix(self, ranking: str) -> None:
        name = queue_detector_name(ranking)  # type: ignore[arg-type]
        assert name.startswith(QUEUE_DETECTOR_PREFIX)

    @pytest.mark.parametrize("ranking", RANKING_KEYS)
    def test_no_queue_name_is_a_vertical_name(self, ranking: str) -> None:
        name = queue_detector_name(ranking)  # type: ignore[arg-type]
        assert "atlas-vertical" not in name
        assert not name.startswith("model:")


class TestTheRandomBaseline:
    """A ranking that scores below chance has not failed to help; it has buried the incidents."""

    def test_a_cut_that_finds_less_than_chance_does_not_beat_random(self) -> None:
        # Ten alerts, two true, and both are at the back: the top two find nothing.
        queue = [alert(f"e{index}", magnitude=float(10 - index)) for index in range(8)]
        queue += [alert("t0", magnitude=1.0, covers=(0,)), alert("t1", magnitude=0.5, covers=(1,))]
        curve = queue_curve(queue, [2], "magnitude", n_windows=2)
        point = curve.points[0]
        assert point.true_positives == 0
        assert point.expected_true_positives == pytest.approx(2 * 2 / 10)
        assert point.beats_random is False

    def test_a_cut_that_finds_more_than_chance_beats_random(self) -> None:
        queue = [alert("t0", magnitude=9.0, covers=(0,)), alert("t1", magnitude=8.0, covers=(1,))]
        queue += [alert(f"e{index}", magnitude=float(index) / 10) for index in range(8)]
        point = queue_curve(queue, [2], "magnitude", n_windows=2).points[0]
        assert point.true_positives == 2
        assert point.beats_random is True

    def test_an_empty_queue_expects_nothing_rather_than_dividing_by_zero(self) -> None:
        point = outcome_at_budget([], 5, "magnitude", n_windows=1)
        assert point.expected_true_positives == 0.0
        assert point.beats_random is False


class TestTruthPositionInTheQueue:
    """Where the true alerts landed is the finding a curve of precisions can only imply."""

    def test_ranks_are_recorded_zero_indexed_and_ascending(self) -> None:
        queue = [
            alert("a", magnitude=9.0),
            alert("b", magnitude=8.0, covers=(0,)),
            alert("c", magnitude=7.0),
            alert("d", magnitude=6.0, covers=(1,)),
        ]
        curve = queue_curve(queue, [2], "magnitude", n_windows=2)
        assert curve.true_positive_ranks == (1, 3)
        assert curve.n_true_positives == 2

    def test_truth_in_the_back_half_is_declared_an_anti_ranking(self) -> None:
        queue = [alert(f"e{index}", magnitude=float(10 - index)) for index in range(8)]
        queue += [alert("t0", magnitude=1.0, covers=(0,)), alert("t1", magnitude=0.5, covers=(1,))]
        curve = queue_curve(queue, [2], "magnitude", n_windows=2)
        assert curve.sorts_truth_downwards is True

    def test_truth_at_the_front_is_not_an_anti_ranking(self) -> None:
        queue = [alert("t0", magnitude=9.0, covers=(0,)), alert("t1", magnitude=8.0, covers=(1,))]
        queue += [alert(f"e{index}", magnitude=float(index) / 10) for index in range(8)]
        curve = queue_curve(queue, [2], "magnitude", n_windows=2)
        assert curve.sorts_truth_downwards is False

    def test_a_queue_with_no_truth_is_not_an_anti_ranking_either(self) -> None:
        curve = queue_curve([alert("a"), alert("b")], [1], "magnitude", n_windows=1)
        assert curve.true_positive_ranks == ()
        assert curve.sorts_truth_downwards is False
