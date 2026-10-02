"""Structural co-occurrence of a process event with the command path."""

from datetime import UTC, datetime, timedelta

from phos.atlas import (
    CommandEvidence,
    CommandGrounding,
    attachable_graph_changes,
    command_act_entities,
    graph_finding_is_attachable,
    ground_event,
    promote_graph_findings,
)
from phos.atlas.command_evidence import CommandDeparture, GraphChange
from phos.atlas.packet import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.eval import LabelledInterval
from phos.ontology import (
    Deviation,
    Domain,
    Evidence,
    EvidenceKind,
    ExpectedRange,
    Observation,
)
from phos.reasoning import FittedPlattCalibrator

EPOCH = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
DEVICE = "ent_10.0.0.9"
TARGET = "ent_10.0.0.20"
POLLER = "ent_10.0.0.30"
OTHER_PLC = "ent_10.0.0.40"
CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)


class _Window:
    """A span with the `contains` the grounding function asks for."""

    def __init__(self, start: datetime, end: datetime) -> None:
        self.start = start
        self.end = end

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp <= self.end


def process_event(at: datetime = EPOCH) -> Evidence:
    """A broad subsystem event, the process-side fact being grounded."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="subsystem-event:ev_000000000001,ev_000000000002,ev_000000000003",
        entity_ids=["P1_FT01", "P1_LIT01", "P1_PIT01"],
        timestamp=at,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="P1: 3 signals departed together",
    )


def graph_finding(
    feature: str,
    *,
    minutes: float = 0.0,
    issuer: str = DEVICE,
    target: str = TARGET,
) -> Observation:
    """A graph finding of the shape `compare_to_graph` emits."""
    when = EPOCH + timedelta(minutes=minutes)
    return Observation(
        entity_ids=[issuer, target],
        feature=feature,
        value=5.0,
        timestamp=when,
        domain=Domain.ATLAS,
        context={
            "issuer_ip": issuer.removeprefix("ent_"),
            "target_ip": target.removeprefix("ent_"),
            "function_codes": "6",
            "function_code": "6",
            "function_name": "write_register",
            "learned_command_count": "121",
            "frames": "/captures/plant.pcap:0-4",
        },
    )


def promoted(
    feature: str,
    *,
    minutes: float = 0.0,
    issuer: str = DEVICE,
    target: str = TARGET,
) -> GraphChange:
    """Promote one graph finding so the bundle carries real boundary evidence."""
    return promote_graph_findings(
        [graph_finding(feature, minutes=minutes, issuer=issuer, target=target)], CERTAIN
    )[0]


def behaviour_departure(*, minutes: float = 0.0) -> CommandDeparture:
    """A command-behaviour deviation on a known device, not a graph finding."""
    when = EPOCH + timedelta(minutes=minutes)
    reading = Observation(
        entity_ids=[DEVICE],
        feature="command_count",
        value=6.0,
        timestamp=when,
        domain=Domain.ATLAS,
        context={"frames": "/captures/plant.pcap:0-59"},
    )
    expected = ExpectedRange(
        feature=reading.feature,
        entity_id=DEVICE,
        low=50.0,
        high=70.0,
        mean=60.0,
        stddev=2.0,
        learned_from_window=(EPOCH - timedelta(hours=1), EPOCH),
    )
    deviation = Deviation(
        observation_id=reading.id,
        expected=expected,
        magnitude=27.0,
        timestamp=when,
    )
    evidence = Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=deviation.id,
        entity_ids=[DEVICE],
        timestamp=when,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="write rate departed",
    )
    return CommandDeparture(observation=reading, deviation=deviation, evidence=evidence)


def same_hour() -> _Window:
    return _Window(EPOCH, EPOCH + timedelta(hours=1))


def test_no_command_evidence_is_uncommanded() -> None:
    assert (
        ground_event(process_event(), CommandEvidence(), same_hour())
        is CommandGrounding.UNCOMMANDED
    )


def test_an_unknown_master_is_unauthorised() -> None:
    bundle = CommandEvidence(changes=(promoted(UNKNOWN_COMMAND_RELATIONSHIP),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.UNAUTHORISED


def test_an_unexpected_function_on_a_known_link_is_commanded() -> None:
    bundle = CommandEvidence(changes=(promoted(UNEXPECTED_COMMAND_FUNCTION),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.COMMANDED


def test_a_command_behaviour_departure_is_commanded() -> None:
    bundle = CommandEvidence(departures=(behaviour_departure(),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.COMMANDED


def test_a_silent_known_link_is_not_commanded() -> None:
    """Silence is the opposite of activity; it is not an injection and not a write."""
    bundle = CommandEvidence(changes=(promoted(SILENT_COMMAND_RELATIONSHIP),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.UNCOMMANDED


def test_an_unknown_master_wins_over_known_link_activity() -> None:
    bundle = CommandEvidence(
        departures=(behaviour_departure(),),
        changes=(promoted(UNKNOWN_COMMAND_RELATIONSHIP), promoted(UNEXPECTED_COMMAND_FUNCTION)),
    )
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.UNAUTHORISED


def test_command_evidence_outside_the_window_does_not_ground_the_event() -> None:
    bundle = CommandEvidence(changes=(promoted(UNKNOWN_COMMAND_RELATIONSHIP, minutes=120.0),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.UNCOMMANDED


def test_a_labelled_interval_is_an_acceptable_window() -> None:
    """The eval interval type already has `contains`; grounding must accept it."""
    window = LabelledInterval(start=EPOCH, end=EPOCH + timedelta(minutes=10), label="attack")
    bundle = CommandEvidence(changes=(promoted(UNKNOWN_COMMAND_RELATIONSHIP),))
    assert ground_event(process_event(), bundle, window) is CommandGrounding.UNAUTHORISED


def test_ground_event_is_a_co_occurrence_table_not_a_confidence() -> None:
    """The three labels are an enum, not a probability. Reachability does not add a fourth score."""
    assert set(CommandGrounding) == {
        CommandGrounding.UNAUTHORISED,
        CommandGrounding.COMMANDED,
        CommandGrounding.UNCOMMANDED,
    }
    bundle = CommandEvidence(changes=(promoted(UNKNOWN_COMMAND_RELATIONSHIP),))
    assert ground_event(process_event(), bundle, same_hour()) is CommandGrounding.UNAUTHORISED


def test_a_silent_unrelated_poller_does_not_belong_to_a_rogue_write() -> None:
    """Primary session-3 attachment test: no shared entity, no path to the window's issuer."""
    rogue = promoted(UNKNOWN_COMMAND_RELATIONSHIP)
    silence = promoted(SILENT_COMMAND_RELATIONSHIP, issuer=POLLER, target=OTHER_PLC)
    window = same_hour()
    act = command_act_entities((rogue.evidence, silence.evidence), window)

    assert set(act) == {DEVICE, TARGET}
    assert graph_finding_is_attachable(rogue.evidence, act) is True
    assert graph_finding_is_attachable(silence.evidence, act) is False
    attached = attachable_graph_changes((rogue, silence), window)
    assert [change.evidence.id for change in attached] == [rogue.evidence.id]


def test_silence_on_a_chatty_link_that_shares_an_entity_still_attaches() -> None:
    """Power SCADA silence is real (ADR 0037). Sharing the issuer keeps it in the story."""
    write = promoted(UNEXPECTED_COMMAND_FUNCTION)
    silence = promoted(SILENT_COMMAND_RELATIONSHIP, issuer=DEVICE, target=TARGET)
    window = same_hour()
    act = command_act_entities((write.evidence, silence.evidence), window)

    assert DEVICE in act
    assert graph_finding_is_attachable(silence.evidence, act) is True
    attached = attachable_graph_changes((write, silence), window)
    assert {change.evidence.id for change in attached} == {write.evidence.id, silence.evidence.id}


def test_an_unknown_master_finding_attaches_even_when_it_is_the_only_act() -> None:
    rogue = promoted(UNKNOWN_COMMAND_RELATIONSHIP)
    window = same_hour()
    act = command_act_entities((rogue.evidence,), window)
    assert graph_finding_is_attachable(rogue.evidence, act) is True
    assert attachable_graph_changes((rogue,), window) == (rogue,)


def test_silence_alone_is_not_a_command_act_to_attach_to() -> None:
    """A learned link going quiet, with no unknown master or unexpected function, is not an act."""
    silence = promoted(SILENT_COMMAND_RELATIONSHIP)
    window = same_hour()
    act = command_act_entities((silence.evidence,), window)
    assert act == frozenset()
    assert graph_finding_is_attachable(silence.evidence, act) is False
    assert attachable_graph_changes((silence,), window) == ()
