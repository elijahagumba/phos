"""Path findings must be judged by the directory and never by the entity's own history."""

from datetime import UTC, datetime

import pytest

from phos.ontology import Domain, Entity, EntityType
from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.graph import DeclaredGraph
from phos.sentiel.interaction import DeclaredCounterpartyDirectory
from phos.sentiel.paths import (
    DISTANT_HOPS,
    PATH_FEATURES,
    DayDeviceIndex,
    InteractionVerdict,
    device_index_for_day,
    path_findings,
    summarise_verdicts,
)
from phos.sentiel.traces import EntityDayTrace

DAY = datetime(2010, 7, 5, tzinfo=UTC)


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
                    _entity(
                        "A",
                        email="a@dtaa.com",
                        role="Salesman",
                        business_unit="1",
                        functional_unit="F1",
                        department="D1",
                        team="T1",
                    ),
                    _entity(
                        "MATE",
                        email="mate@dtaa.com",
                        role="Salesman",
                        business_unit="1",
                        functional_unit="F1",
                        department="D1",
                        team="T1",
                    ),
                    _entity(
                        "FAR",
                        email="far@dtaa.com",
                        role="ITAdmin",
                        business_unit="1",
                        functional_unit="F2",
                        department="D2",
                        team="T2",
                    ),
                )
            }
        )
    )


def _trace(
    user_id: str, *, recipients: tuple[str, ...] = (), pcs: tuple[str, ...] = ()
) -> EntityDayTrace:
    return EntityDayTrace(
        user_id=user_id, day=DAY, recipients=recipients, pcs=pcs, emails=len(recipients)
    )


class TestTheDirectoryDoesTheJudging:
    def test_a_teammate_is_not_distant_and_another_department_is(self) -> None:
        graph = _graph()
        findings = path_findings(
            _trace("A", recipients=("mate@dtaa.com", "far@dtaa.com")),
            graph,
            DayDeviceIndex(),
        )
        assert findings.internal_recipients == 2
        assert findings.distant_internal_recipients == 1
        assert findings.max_hops >= DISTANT_HOPS

    def test_an_external_address_is_undeclared_not_distant(self) -> None:
        """An absence of a record is a different claim from a record of distance."""
        findings = path_findings(
            _trace("A", recipients=("stranger@elsewhere.com",)), _graph(), DayDeviceIndex()
        )
        assert findings.undeclared_recipients == 1
        assert findings.distant_internal_recipients == 0
        assert findings.internal_recipients == 0

    def test_undeclared_recipients_are_excluded_from_the_novel_count(self) -> None:
        """external_email_count already measures them; counting twice inflates one behaviour."""
        findings = path_findings(
            _trace("A", recipients=("stranger@elsewhere.com",)), _graph(), DayDeviceIndex()
        )
        assert findings.novel_beyond_counts == 0

    def test_mean_hops_is_zero_when_no_colleague_was_mailed(self) -> None:
        findings = path_findings(_trace("A"), _graph(), DayDeviceIndex())
        assert findings.mean_hops == 0.0

    def test_the_feature_names_match_what_values_returns(self) -> None:
        findings = path_findings(_trace("A"), _graph(), DayDeviceIndex())
        assert set(findings.values()) == set(PATH_FEATURES)


class TestSharedDevicesAreOneDaysFact:
    def test_a_machine_shared_with_a_distant_colleague_is_counted(self) -> None:
        index = device_index_for_day([_trace("A", pcs=("PC-1",)), _trace("FAR", pcs=("PC-1",))])
        findings = path_findings(_trace("A", pcs=("PC-1",)), _graph(), index)
        assert findings.shared_device_distant == 1

    def test_a_machine_shared_with_a_teammate_is_not(self) -> None:
        index = device_index_for_day([_trace("A", pcs=("PC-1",)), _trace("MATE", pcs=("PC-1",))])
        findings = path_findings(_trace("A", pcs=("PC-1",)), _graph(), index)
        assert findings.shared_device_distant == 0

    def test_pooling_days_is_refused_because_it_would_invent_co_presence(self) -> None:
        other = _trace("FAR", pcs=("PC-1",)).model_copy(
            update={"day": datetime(2010, 7, 6, tzinfo=UTC)}
        )
        with pytest.raises(ValueError, match="ONE day"):
            device_index_for_day([_trace("A", pcs=("PC-1",)), other])


class TestTheInteractionPolicyRefusesOnCert:
    def test_with_no_declared_policy_every_verdict_is_insufficient(self) -> None:
        """A missing directory is insufficient evidence, never an alert — and now it is wired."""
        findings = path_findings(
            _trace("A", recipients=("mate@dtaa.com", "far@dtaa.com")), _graph(), DayDeviceIndex()
        )
        assert findings.interaction_verdicts == {InteractionVerdict.INSUFFICIENT.value: 2}

    def test_a_declared_policy_produces_real_verdicts(self) -> None:
        """The module works when a corpus does ship a policy; CERT simply does not."""
        policy = DeclaredCounterpartyDirectory(allowed={"Salesman": frozenset({"Salesman"})})
        findings = path_findings(
            _trace("A", recipients=("mate@dtaa.com", "far@dtaa.com")),
            _graph(),
            DayDeviceIndex(),
            policy,
        )
        assert findings.interaction_verdicts == {
            InteractionVerdict.EXPECTED.value: 1,
            InteractionVerdict.UNEXPECTED.value: 1,
        }

    def test_verdicts_pool_across_a_run(self) -> None:
        findings = [
            path_findings(_trace("A", recipients=("mate@dtaa.com",)), _graph(), DayDeviceIndex())
            for _ in range(3)
        ]
        assert summarise_verdicts(findings) == {InteractionVerdict.INSUFFICIENT.value: 3}
