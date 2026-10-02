"""Weak-signal accumulation must be described, never scored — and its ceiling must be visible."""

from datetime import UTC, datetime, timedelta

from phos.ontology import Domain, Entity, EntityType
from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.episodes import Episode, EpisodePolicy, assemble_episodes
from phos.sentiel.graph import DeclaredGraph, DeclaredRelation
from phos.sentiel.templates import BehaviourFamily
from phos.sentiel.weak_signals import linked_episodes, weak_signal_profile

START = datetime(2010, 7, 1, tzinfo=UTC)
ACCESS = BehaviourFamily.ACCESS.value
DATA = BehaviourFamily.DATA_HANDLING.value
REL = BehaviourFamily.RELATIONSHIP.value


def _day(index: int) -> datetime:
    return START + timedelta(days=index)


def _episode(
    entity: str, *rows: tuple[int, float, tuple[str, ...]], anchor: float = 5.0
) -> Episode:
    episodes = assemble_episodes(
        [
            (f"ent_{entity}", _day(index), score, families, "logon_count")
            for index, score, families in rows
        ],
        EpisodePolicy(anchor_threshold=anchor, extension_floor=1.0),
    )
    return episodes[0]


class TestWhatAccumulationAdded:
    def test_a_family_only_sub_threshold_days_spoke_for_is_named(self) -> None:
        """The sharpest available statement that the capability worked."""
        episode = _episode(
            "A",
            (0, 9.0, (ACCESS,)),
            (1, 2.0, (DATA,)),
            (2, 2.0, (REL,)),
        )
        profile = weak_signal_profile(episode)
        assert profile.carried_only_families == (DATA, REL)
        assert profile.breadth_gain == 2
        assert profile.accumulated

    def test_an_episode_that_is_just_its_loudest_day_gains_nothing(self) -> None:
        episode = _episode("A", (0, 9.0, (ACCESS, DATA)), (1, 2.0, (ACCESS,)))
        profile = weak_signal_profile(episode)
        assert profile.carried_only_families == ()
        assert profile.breadth_gain == 0
        assert not profile.accumulated

    def test_carried_and_anchor_scores_are_kept_apart(self) -> None:
        episode = _episode("A", (0, 9.0, (ACCESS,)), (1, 2.0, (DATA,)), (2, 3.0, (DATA,)))
        profile = weak_signal_profile(episode)
        assert profile.anchor_score == 9.0
        assert profile.carried_score == 5.0
        assert profile.n_anchor_days == 1
        assert profile.n_carried_days == 2

    def test_the_ceiling_denominator_travels_with_the_breadth(self) -> None:
        """An episode touching three of four families is near the maximum, not modestly broad."""
        episode = _episode("A", (0, 9.0, (ACCESS,)))
        profile = weak_signal_profile(episode)
        assert profile.n_families_available == len(BehaviourFamily)


def _entity(user_id: str, **attributes: str) -> Entity:
    return Entity(
        id=f"ent_{user_id}",
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name=user_id,
        attributes={"employee_name": user_id, **attributes},
    )


def _graph() -> DeclaredGraph:
    return DeclaredGraph.from_catalogue(
        EntityCatalogue(
            entities={
                entity.name: entity
                for entity in (
                    _entity("A", business_unit="1", department="D1", team="T1"),
                    _entity("MATE", business_unit="1", department="D1", team="T1"),
                    _entity("FAR", business_unit="1", department="D2", team="T2"),
                )
            }
        )
    )


class TestAccumulationAcrossTheDeclaredGraph:
    def test_overlapping_episodes_on_declared_teammates_are_linked(self) -> None:
        episodes = [
            _episode("A", (0, 9.0, (ACCESS,)), (2, 9.0, (ACCESS,))),
            _episode("MATE", (1, 9.0, (ACCESS,))),
        ]
        links = linked_episodes(episodes, _graph())
        assert len(links) == 1
        assert links[0].relation is DeclaredRelation.SAME_TEAM
        assert links[0].overlap_days >= 1

    def test_a_pair_with_no_close_declared_relation_is_not_linked(self) -> None:
        """On r3.1 the wider containers hold everybody, so linking on them would say nothing."""
        episodes = [
            _episode("A", (0, 9.0, (ACCESS,))),
            _episode("FAR", (0, 9.0, (ACCESS,))),
        ]
        assert linked_episodes(episodes, _graph()) == []

    def test_episodes_that_do_not_overlap_in_time_are_not_linked(self) -> None:
        episodes = [
            _episode("A", (0, 9.0, (ACCESS,))),
            _episode("MATE", (30, 9.0, (ACCESS,))),
        ]
        assert linked_episodes(episodes, _graph()) == []
