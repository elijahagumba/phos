"""Compression must be counted in items read AND days contained, or it is a conjuring trick."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.sentiel.compression import (
    COMPRESSION_CAVEATS,
    EPISODE_DETECTOR_PREFIX,
    QueuedDay,
    build_episode_queue,
    compare_at_budget,
    episode_detector_name,
    rank_episodes,
)
from phos.sentiel.episodes import Episode, EpisodePolicy, assemble_episodes
from phos.sentiel.labels import EntityLabelledInterval

START = datetime(2010, 7, 1, tzinfo=UTC)
INSIDER = "MALLORY9"


def _day(index: int) -> datetime:
    return START + timedelta(days=index)


def _labels() -> list[EntityLabelledInterval]:
    return [
        EntityLabelledInterval(
            user_id=INSIDER, start=_day(0), end=_day(9), scenario="1", release="3.1"
        )
    ]


def _episodes(entity: str, *rows: tuple[int, float], anchor: float = 5.0) -> list[Episode]:
    return assemble_episodes(
        [
            (f"ent_{entity}", _day(index), score, ("ACCESS",), "logon_count")
            for index, score in rows
        ],
        EpisodePolicy(anchor_threshold=anchor, extension_floor=1.0),
    )


class TestTruthUsesTheOntologysOwnRule:
    def test_an_episode_is_true_when_any_member_day_is_malicious(self) -> None:
        alerts = build_episode_queue(_episodes(INSIDER, (0, 9.0), (1, 2.0)), _labels())
        assert alerts[0].is_true_positive
        assert len(alerts[0].malicious_days) == 2
        assert alerts[0].insider == INSIDER

    def test_an_episode_about_an_innocent_user_is_never_true(self) -> None:
        alerts = build_episode_queue(_episodes("NORMAL01", (0, 9.0)), _labels())
        assert not alerts[0].is_true_positive
        assert alerts[0].insider is None

    def test_a_gap_day_is_not_counted_as_covered(self) -> None:
        """Claiming a day nothing fired on would inflate every recall built from episodes."""
        alerts = build_episode_queue(_episodes(INSIDER, (0, 9.0), (4, 9.0)), _labels())
        assert alerts[0].n_days == 2
        assert len(alerts[0].malicious_days) == 2


class TestTheComparison:
    def test_episodes_can_show_more_malicious_days_than_the_same_number_of_entity_days(
        self,
    ) -> None:
        episodes = _episodes(INSIDER, (0, 9.0), (1, 2.0), (2, 2.0), (3, 2.0))
        alerts = build_episode_queue(episodes, _labels())
        days = [
            QueuedDay(user_id=INSIDER, day=_day(index), score=score, malicious=True)
            for index, score in ((0, 9.0), (1, 2.0), (2, 2.0), (3, 2.0))
        ] + [
            QueuedDay(user_id=f"N{index}", day=_day(0), score=8.0, malicious=False)
            for index in range(10)
        ]
        comparison = compare_at_budget(days, alerts, 1, n_malicious_days=4, n_insiders=1)
        assert comparison.baseline_malicious_days == 1
        assert comparison.episode_malicious_days == 4
        assert comparison.coverage_multiple == 4.0
        assert comparison.episode_entity_days == 4
        assert comparison.days_read_per_item == 4.0
        assert "4 of 4 malicious entity-days" in comparison.verdict()

    def test_a_verdict_says_so_plainly_when_grouping_bought_nothing(self) -> None:
        episodes = _episodes(INSIDER, (0, 9.0))
        alerts = build_episode_queue(episodes, _labels())
        days = [QueuedDay(user_id=INSIDER, day=_day(0), score=9.0, malicious=True)]
        comparison = compare_at_budget(days, alerts, 1, n_malicious_days=1, n_insiders=1)
        assert "exactly as much" in comparison.verdict()

    def test_compression_ratio_is_days_per_episode(self) -> None:
        episodes = _episodes(INSIDER, (0, 9.0), (1, 2.0))
        alerts = build_episode_queue(episodes, _labels())
        days = [
            QueuedDay(user_id=INSIDER, day=_day(index), score=score, malicious=True)
            for index, score in ((0, 9.0), (1, 2.0))
        ]
        comparison = compare_at_budget(days, alerts, 1, n_malicious_days=2, n_insiders=1)
        assert comparison.compression_ratio == 2.0

    def test_a_zero_budget_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive analyst volume"):
            compare_at_budget([], [], 0, 0, 0)


class TestAnArbitraryCutIsReported:
    def test_a_tie_spanning_the_boundary_is_flagged(self) -> None:
        """Precision at such a cut is a property of the sort order, not of the system."""
        episodes = [
            episode for entity in ("A", "B", "C") for episode in _episodes(entity, (0, 9.0))
        ]
        alerts = build_episode_queue(episodes, _labels())
        comparison = compare_at_budget([], alerts, 2, n_malicious_days=0, n_insiders=1)
        assert comparison.cut_is_arbitrary
        assert comparison.tie_span_at_cut == 3


class TestRankingIsTotalAndReproducible:
    def test_ties_break_deterministically(self) -> None:
        episodes = [episode for entity in ("B", "A") for episode in _episodes(entity, (0, 9.0))]
        alerts = build_episode_queue(episodes, _labels())
        assert [alert.user_id for alert in rank_episodes(alerts, "peak")] == ["A", "B"]

    @pytest.mark.parametrize("ranking", ["peak", "total", "days", "breadth"])
    def test_every_declared_key_ranks_something(self, ranking: str) -> None:
        episodes = _episodes(INSIDER, (0, 9.0), (1, 2.0))
        alerts = build_episode_queue(episodes, _labels())
        assert rank_episodes(alerts, ranking)  # type: ignore[arg-type]


class TestNamesAndCaveats:
    def test_a_queue_name_can_never_be_mistaken_for_the_frozen_row(self) -> None:
        assert episode_detector_name("peak").startswith(EPISODE_DETECTOR_PREFIX)
        assert "aggregate:gaussian" not in episode_detector_name("peak")

    def test_the_unit_caveat_travels(self) -> None:
        assert any("LARGER UNIT OF READING" in caveat for caveat in COMPRESSION_CAVEATS)
