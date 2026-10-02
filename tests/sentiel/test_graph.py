"""The declared graph must contain what the directory says and nothing the behaviour implies."""

import inspect
from pathlib import Path

from phos.ontology import Domain, Entity, EntityType
from phos.sentiel.entities import ABSENT_FROM_DIRECTORY, DIRECTORY_RECORD_ATTRIBUTE, EntityCatalogue
from phos.sentiel.graph import (
    ORG_LEVELS,
    RELATION_HOPS,
    DeclaredGraph,
    DeclaredRelation,
)


def _entity(user_id: str, **attributes: str) -> Entity:
    return Entity(
        id=f"ent_{user_id}",
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name=user_id,
        attributes={"employee_name": user_id, **attributes},
    )


def _catalogue(*entities: Entity) -> EntityCatalogue:
    return EntityCatalogue(entities={entity.name: entity for entity in entities})


class TestNothingBehaviouralCanReachIt:
    def test_no_method_accepts_an_observation_an_event_or_a_trace(self) -> None:
        """Declared-not-inferred is a property of the type, on `PeerGroups`' pattern."""
        forbidden = {"Observation", "EnterpriseEvent", "EntityDayTrace", "ScoredWindow"}
        for name, member in inspect.getmembers(DeclaredGraph, callable):
            if name.startswith("__"):
                continue
            annotations = inspect.get_annotations(member, eval_str=False)
            for annotation in annotations.values():
                assert not (forbidden & set(str(annotation).replace("|", " ").split())), (
                    f"DeclaredGraph.{name} accepts {annotation!r}; behaviour must not be able to "
                    "move anybody in the declared graph"
                )


class TestWhatTheDirectoryDeclares:
    def test_accounts_map_addresses_to_their_owners(self) -> None:
        graph = DeclaredGraph.from_catalogue(
            _catalogue(_entity("A", email="A.One@dtaa.com", role="Salesman"))
        )
        assert graph.owner_of("a.one@dtaa.com") == "A"
        assert graph.owner_of("stranger@elsewhere.com") is None

    def test_a_supervisor_is_resolved_from_the_name_column(self) -> None:
        graph = DeclaredGraph.from_catalogue(
            _catalogue(
                _entity("BOSS", role="Director"),
                _entity("A", role="Salesman", supervisor="BOSS"),
            )
        )
        assert graph.supervisor_of == {"A": "BOSS"}
        assert graph.relation_between("A", "BOSS") is DeclaredRelation.SUPERVISOR
        assert graph.relation_between("BOSS", "A") is DeclaredRelation.DIRECT_REPORT

    def test_an_ambiguous_supervisor_name_is_left_unresolved_rather_than_guessed(self) -> None:
        """Guessing which colleague someone reports to fabricates the edge this module refuses."""
        twin_one = _entity("X1", role="Director")
        twin_two = _entity("X2", role="Director")
        catalogue = EntityCatalogue(
            entities={
                "X1": twin_one.model_copy(update={"attributes": {"employee_name": "Same Name"}}),
                "X2": twin_two.model_copy(update={"attributes": {"employee_name": "Same Name"}}),
                "A": _entity("A", role="Salesman", supervisor="Same Name"),
            }
        )
        graph = DeclaredGraph.from_catalogue(catalogue)
        assert "A" not in graph.supervisor_of
        assert graph.summary.unresolved_supervisors == 1

    def test_entities_absent_from_the_directory_declare_nothing(self) -> None:
        catalogue = EntityCatalogue(
            entities={
                "GHOST": Entity(
                    id="ent_GHOST",
                    type=EntityType.USER,
                    domain=Domain.SENTIEL,
                    name="GHOST",
                    attributes={DIRECTORY_RECORD_ATTRIBUTE: ABSENT_FROM_DIRECTORY},
                )
            }
        )
        graph = DeclaredGraph.from_catalogue(catalogue)
        assert not graph.knows("GHOST")
        assert graph.summary.users == 0


class TestRelationsAreNarrowestFirst:
    def test_a_shared_team_beats_a_shared_department(self) -> None:
        graph = DeclaredGraph.from_catalogue(
            _catalogue(
                _entity("A", business_unit="1", department="D", team="T"),
                _entity("B", business_unit="1", department="D", team="T"),
            )
        )
        assert graph.relation_between("A", "B") is DeclaredRelation.SAME_TEAM

    def test_a_reporting_line_beats_a_shared_container(self) -> None:
        """A supervisor is one declared edge; a shared container is two or more."""
        graph = DeclaredGraph.from_catalogue(
            _catalogue(
                _entity("BOSS", business_unit="1", department="D"),
                _entity("A", business_unit="1", department="D", supervisor="BOSS"),
            )
        )
        assert graph.relation_between("A", "BOSS") is DeclaredRelation.SUPERVISOR
        assert graph.hops_between("A", "BOSS") == 1

    def test_an_unknown_counterparty_is_undeclared_not_unrelated(self) -> None:
        """An absence of a record is a different claim from a record of distance."""
        graph = DeclaredGraph.from_catalogue(_catalogue(_entity("A", role="Salesman")))
        assert graph.relation_between("A", "NOBODY") is DeclaredRelation.UNDECLARED

    def test_hops_rise_with_containment_depth(self) -> None:
        assert RELATION_HOPS[DeclaredRelation.SAME_TEAM] == 2
        assert RELATION_HOPS[DeclaredRelation.SAME_DEPARTMENT] == 4
        assert RELATION_HOPS[DeclaredRelation.SAME_FUNCTIONAL_UNIT] == 6
        assert RELATION_HOPS[DeclaredRelation.SAME_BUSINESS_UNIT] == 8


class TestVacuousLevelsAreMeasured:
    def test_a_level_holding_one_value_separates_nobody(self) -> None:
        """On r3.1 this is business_unit, and a finding built on it would say nothing."""
        graph = DeclaredGraph.from_catalogue(
            _catalogue(
                _entity("A", business_unit="1", department="D1"),
                _entity("B", business_unit="1", department="D2"),
            )
        )
        # A level everybody shares and a level nobody declares both separate nobody.
        assert "business_unit" in graph.summary.vacuous_levels
        assert "department" not in graph.summary.vacuous_levels
        assert not graph.separates("business_unit")
        assert graph.separates("department")


class TestTheRealDirectory:
    """Read the shipped r3.1 directory when it is on disk; skip cleanly when it is not."""

    def test_r31_declares_an_org_chart_and_no_device_ownership(self) -> None:
        directory = Path("data/cert-insider-threat/r3.1/LDAP")
        if not directory.is_dir():
            import pytest

            pytest.skip("CERT r3.1 is not on disk")
        graph = DeclaredGraph.from_catalogue(EntityCatalogue.from_ldap_directory(directory))
        assert graph.summary.users == 1000
        assert graph.summary.accounts == 1000
        # Every employee sits in one business unit, so the outermost level separates nobody.
        assert graph.summary.level_sizes["business_unit"] == 1
        assert "business_unit" in graph.summary.vacuous_levels
        assert graph.summary.level_sizes["department"] > 1
        assert set(graph.levels) == set(ORG_LEVELS)
