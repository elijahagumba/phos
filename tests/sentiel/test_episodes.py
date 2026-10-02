"""Episode boundaries must come from a declared rule, and the rule must not be tunable in secret."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.sentiel.episodes import (
    EPISODE_GAP_INHERITS_CORRELATION_WINDOW,
    EXTENSION_FLOOR_QUANTILES,
    GAP_SWEEP_DAYS,
    Episode,
    EpisodeDay,
    EpisodePolicy,
    assemble_episodes,
    episode_sensitivity,
    floor_at_quantile,
)

ENTITY = "ent_ALICE001"


def _day(index: int) -> datetime:
    return datetime(2010, 7, 1, tzinfo=UTC) + timedelta(days=index)


def _candidates(
    *rows: tuple[int, float],
) -> list[tuple[str, datetime, float, tuple[str, ...], str]]:
    return [(ENTITY, _day(index), score, ("ACCESS",), "logon_count") for index, score in rows]


class TestTheGapIsInherited:
    def test_it_equals_the_reasoning_correlation_window_sentiel_already_declares(self) -> None:
        """Two answers to "how far apart may related facts be?" would be one answer too many."""
        from phos.sentiel.engine import SentielConfig

        declared = SentielConfig().reasoning.correlation_window
        assert EPISODE_GAP_INHERITS_CORRELATION_WINDOW == declared
        assert EPISODE_GAP_INHERITS_CORRELATION_WINDOW == timedelta(days=7)

    def test_the_default_policy_uses_it(self) -> None:
        assert EpisodePolicy(anchor_threshold=1.0).gap == EPISODE_GAP_INHERITS_CORRELATION_WINDOW


class TestTheBoundaryRule:
    def test_days_within_the_gap_join_one_episode(self) -> None:
        episodes = assemble_episodes(
            _candidates((0, 10.0), (3, 2.0), (6, 2.0)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert len(episodes) == 1
        assert episodes[0].n_days == 3
        assert episodes[0].span == timedelta(days=6)

    def test_a_gap_wider_than_the_rule_splits_them(self) -> None:
        episodes = assemble_episodes(
            _candidates((0, 10.0), (20, 10.0)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert [episode.n_days for episode in episodes] == [1, 1]

    def test_days_below_the_extension_floor_never_join(self) -> None:
        episodes = assemble_episodes(
            _candidates((0, 10.0), (1, 0.5)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert episodes[0].n_days == 1

    def test_a_run_that_never_anchors_is_dropped_rather_than_reported(self) -> None:
        """An episode nothing in which was unusual enough to alert on is not a finding."""
        episodes = assemble_episodes(
            _candidates((0, 2.0), (1, 2.0), (2, 2.0)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert episodes == []

    def test_a_floor_above_the_anchor_is_refused(self) -> None:
        """A day could otherwise anchor an episode it is not allowed to join."""
        with pytest.raises(ValidationError, match="exceeds anchor_threshold"):
            EpisodePolicy(anchor_threshold=1.0, extension_floor=2.0)

    def test_a_zero_gap_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="positive duration"):
            EpisodePolicy(anchor_threshold=1.0, gap=timedelta(0))


class TestWhatAnEpisodeReports:
    def test_carried_days_are_the_ones_a_budget_would_never_have_shown(self) -> None:
        episodes = assemble_episodes(
            _candidates((0, 10.0), (1, 2.0), (2, 2.0)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert episodes[0].n_anchor_days == 1
        assert episodes[0].n_carried_days == 2

    @pytest.mark.parametrize(
        ("scores", "expected"),
        [
            ((1.0, 10.0), "rising"),
            ((10.0, 1.0), "falling"),
            ((10.0,), "single"),
            ((5.0, 9.0, 5.0), "flat"),
        ],
    )
    def test_trajectory(self, scores: tuple[float, ...], expected: str) -> None:
        episodes = assemble_episodes(
            _candidates(*[(index, score) for index, score in enumerate(scores)]),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=0.5),
        )
        assert episodes[0].trajectory == expected

    def test_a_gap_day_inside_an_episode_is_not_covered(self) -> None:
        """Claiming a day nothing fired on would inflate every recall built from episodes."""
        episodes = assemble_episodes(
            _candidates((0, 10.0), (3, 10.0)),
            EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
        )
        assert episodes[0].covers(_day(0))
        assert episodes[0].covers(_day(3))
        assert not episodes[0].covers(_day(1))

    def test_unordered_days_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="strictly ascending"):
            Episode(
                entity_id=ENTITY,
                days=(
                    EpisodeDay(day=_day(3), score=9.0, anchor=True),
                    EpisodeDay(day=_day(1), score=9.0, anchor=True),
                ),
                anchor_threshold=5.0,
                extension_floor=1.0,
            )

    def test_an_unanchored_episode_cannot_be_constructed(self) -> None:
        with pytest.raises(ValidationError, match="no anchor day"):
            Episode(
                entity_id=ENTITY,
                days=(EpisodeDay(day=_day(0), score=1.0, anchor=False),),
                anchor_threshold=5.0,
                extension_floor=0.5,
            )


class TestEntitiesAreNeverMixed:
    def test_two_entities_never_share_an_episode(self) -> None:
        """An episode is about somebody, on ADR 0023's rule for a hypothesis."""
        rows = [
            (ENTITY, _day(0), 10.0, ("ACCESS",), "logon_count"),
            ("ent_BOB00002", _day(0), 10.0, ("ACCESS",), "logon_count"),
        ]
        episodes = assemble_episodes(rows, EpisodePolicy(anchor_threshold=5.0))
        assert {episode.entity_id for episode in episodes} == {ENTITY, "ent_BOB00002"}
        assert all(episode.n_days == 1 for episode in episodes)


class TestSensitivityIsReportedWhole:
    def test_the_grid_covers_every_declared_pair(self) -> None:
        """A rule that only works at one setting is a rule fitted to the answer."""
        rows = _candidates(*[(index, float(index % 7)) for index in range(40)])
        table = episode_sensitivity(rows, anchor_threshold=5.0)
        assert len(table) == len(GAP_SWEEP_DAYS) * len(EXTENSION_FLOOR_QUANTILES)
        assert {row.gap_days for row in table} == set(GAP_SWEEP_DAYS)
        assert {row.quantile for row in table} == set(EXTENSION_FLOOR_QUANTILES)

    def test_a_wider_gap_never_produces_more_episodes(self) -> None:
        """Merging can only join runs, never split them — a monotonicity the rule must keep."""
        rows = _candidates(*[(index * 2, 9.0) for index in range(10)])
        table = episode_sensitivity(rows, anchor_threshold=5.0, quantiles=(0.0,))
        counts = [row.n_episodes for row in sorted(table, key=lambda row: row.gap_days)]
        assert counts == sorted(counts, reverse=True)


class TestTheFloorIsReadOffTheScores:
    def test_a_quantile_consults_no_label(self) -> None:
        assert floor_at_quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0
        assert floor_at_quantile([], 0.9) == 0.0

    def test_an_out_of_range_quantile_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            floor_at_quantile([1.0], 1.5)
