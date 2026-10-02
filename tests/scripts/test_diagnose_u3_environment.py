"""Structural helpers for the U3 diagnostic — no 120 h fit, no detection claim."""

from scripts.diagnose_u3_environment import (
    Story,
    more_confident_with_less,
    more_uncertain,
    overlap_on_seed,
    story_from_work_orders,
)


def _story(
    *,
    findings: int = 0,
    evidence: int = 0,
    unique: str | None = None,
    insufficient: bool = False,
    competing: tuple[str, ...] = (),
) -> Story:
    return Story(
        n_graph_findings=findings,
        n_live_features=0,
        n_evidence=evidence,
        competing=competing,
        tied_leaders=(),
        unique_leader=unique,
        insufficient_leads=insufficient,
    )


class TestUncertaintyDirection:
    def test_a_vanished_leader_is_more_uncertain(self) -> None:
        present = _story(findings=2, evidence=2, unique="unauthorised_control_activity")
        removed = _story()
        assert more_uncertain(present, removed)
        assert not more_confident_with_less(present, removed)

    def test_raising_insufficient_evidence_is_more_uncertain(self) -> None:
        present = _story(findings=1, evidence=1, unique="engineering_maintenance")
        removed = _story(
            unique="insufficient_evidence",
            insufficient=True,
            competing=("insufficient_evidence",),
        )
        assert more_uncertain(present, removed)
        assert not more_confident_with_less(present, removed)

    def test_ordinary_silence_staying_silent_is_not_a_break(self) -> None:
        quiet = _story()
        assert not more_uncertain(quiet, quiet)
        assert not more_confident_with_less(quiet, quiet)

    def test_a_leader_that_appears_only_after_removal_is_a_break(self) -> None:
        present = _story()
        removed = _story(unique="unauthorised_control_activity", evidence=1)
        assert more_confident_with_less(present, removed)


class TestOverlapSearchIsAPropertyOfTheSeed:
    def test_seed_eleven_is_the_no_overlap_control(self) -> None:
        assert overlap_on_seed(11) is False

    def test_seed_seven_finds_a_window_without_moving_the_calendar(self) -> None:
        assert overlap_on_seed(7) is True


class TestEmptyInlet:
    def test_withholding_work_orders_promotes_nothing(self) -> None:
        story = story_from_work_orders(())
        assert story.n_evidence == 0
