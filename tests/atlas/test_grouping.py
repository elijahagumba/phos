"""Collapsing per-signal evidence into one event per physical unit.

Everything here runs on hand-built fixtures — a two-subsystem map over five signals — so every
expected answer can be computed by hand. The HAI map is checked in `test_hai_topology.py`; what is
under test here is the collapse itself.

Three properties carry the weight, and each has its own group of tests below:

- **The count changes and the coverage does not.** Grouping is a counting fix. A test asserts that
  every input piece of evidence lands in exactly one event and that none is discarded, separately
  from any claim about how many events came out.
- **Membership comes only from the map.** Never from name similarity, never from co-movement. A
  signal the map does not hold raises rather than being guessed at.
- **Traceability survives.** One test walks the whole drill-down path — event to member evidence to
  deviation to observation — through an `EvidenceStore`, because a grouped event an operator cannot
  expand is a summary rather than a finding.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas import (
    Subsystem,
    SubsystemMap,
    TopologyError,
    group_evidence,
    is_subsystem_event,
    member_evidence_ids,
)
from phos.ontology import (
    Deviation,
    Domain,
    Evidence,
    EvidenceKind,
    ExpectedRange,
    InMemoryEvidenceStore,
    Observation,
)
from phos.reasoning import evidence_from_deviation

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
ENTITY = "ent_plant00001"
WINDOW = timedelta(minutes=1)

#: Two units over five signals. `FT01`/`FT01Z` are a transmitter and its feedback channel, the
#: pairing HAI's own naming uses, so "one device" and "more than one device" are both expressible.
SUBSYSTEMS = (
    Subsystem(
        subsystem_id="pump-a",
        label="Pump A",
        signals=frozenset({"FT01", "FT01Z", "PT01"}),
        source="test fixture",
    ),
    Subsystem(
        subsystem_id="tank-b",
        label="Tank B",
        signals=frozenset({"LT01", "LT01Z"}),
        source="test fixture",
    ),
)
CORPUS_SIGNALS = frozenset({"FT01", "FT01Z", "PT01", "LT01", "LT01Z"})


def topology() -> SubsystemMap:
    """Return the two-unit fixture map."""
    return SubsystemMap(SUBSYSTEMS, CORPUS_SIGNALS)


def fact(
    signal: str,
    at: datetime,
    weight: float = 0.5,
    magnitude: float = 5.0,
    domain: Domain = Domain.ATLAS,
) -> tuple[Observation, Deviation, Evidence]:
    """Build one out-of-band measurement and the calibrated evidence promoted from it.

    Goes through `evidence_from_deviation` rather than constructing `Evidence` directly, so a
    fixture can never be a shape the evidence boundary would have refused.
    """
    observation = Observation(
        entity_ids=[ENTITY], feature=signal, value=99.0, timestamp=at, domain=domain
    )
    deviation = Deviation(
        observation_id=observation.id,
        expected=ExpectedRange(
            feature=signal,
            entity_id=ENTITY,
            low=0.0,
            high=1.0,
            mean=0.5,
            stddev=0.1,
            learned_from_window=(EPOCH, EPOCH),
        ),
        magnitude=magnitude,
        timestamp=at,
    )
    evidence = evidence_from_deviation(
        deviation, observation, weight, summary=f"{signal} left its expected range"
    )
    return observation, deviation, evidence


def bundle(
    *specs: tuple[str, datetime, float],
) -> tuple[list[Observation], dict[str, Deviation], list[Evidence]]:
    """Build several facts at once, returning them in the shapes `group_evidence` wants."""
    built = [fact(signal, at, weight) for signal, at, weight in specs]
    return (
        [observation for observation, _, _ in built],
        {deviation.id: deviation for _, deviation, _ in built},
        [evidence for _, _, evidence in built],
    )


# ------------------------------------------------------------------------------------------------
# The collapse
# ------------------------------------------------------------------------------------------------


def test_evidence_on_one_unit_in_one_window_becomes_one_event() -> None:
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4),
        ("FT01Z", EPOCH + timedelta(seconds=10), 0.6),
        ("PT01", EPOCH + timedelta(seconds=20), 0.5),
    )

    events = group_evidence(evidence, topology(), WINDOW, deviations)

    assert len(events) == 1
    assert events[0].kind is EvidenceKind.DEVIATION


def test_the_event_names_its_subsystem_and_lists_its_member_signals() -> None:
    _, deviations, evidence = bundle(("PT01", EPOCH, 0.4), ("FT01", EPOCH, 0.6))

    event = group_evidence(evidence, topology(), WINDOW, deviations)[0]

    assert "pump-a" in event.summary
    assert "Pump A" in event.summary
    assert event.entity_ids == ["FT01", "PT01"]


def test_the_event_takes_the_strongest_members_calibrated_weight() -> None:
    """A unit is at least as suspicious as its most suspicious signal, never an average of them."""
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.1), ("FT01Z", EPOCH, 0.9), ("PT01", EPOCH, 0.2)
    )

    event = group_evidence(evidence, topology(), WINDOW, deviations)[0]

    assert event.weight == pytest.approx(0.9)
    assert "FT01Z" in event.summary


def test_the_strongest_member_is_broken_by_signal_name_not_by_identity() -> None:
    """Two members of equal weight must not let a random uuid decide what the summary says."""
    _, deviations, evidence = bundle(("PT01", EPOCH, 0.7), ("FT01", EPOCH, 0.7))

    summaries = {
        group_evidence(evidence, topology(), WINDOW, deviations)[0].summary,
        group_evidence(list(reversed(evidence)), topology(), WINDOW, deviations)[0].summary,
    }

    assert len(summaries) == 1


def test_the_event_is_stamped_at_its_earliest_member() -> None:
    late = EPOCH + timedelta(seconds=30)
    _, deviations, evidence = bundle(("FT01", late, 0.4), ("PT01", EPOCH, 0.6))

    event = group_evidence(evidence, topology(), WINDOW, deviations)[0]

    assert event.timestamp == EPOCH


def test_the_event_carries_its_members_domain() -> None:
    observation, deviation, evidence = fact("FT01", EPOCH, domain=Domain.SENTIEL)

    event = group_evidence([evidence], topology(), WINDOW, {deviation.id: deviation})[0]

    assert event.domain is Domain.SENTIEL
    assert observation.domain is Domain.SENTIEL


def test_an_empty_input_yields_no_events() -> None:
    assert group_evidence([], topology(), WINDOW, {}) == []


# ------------------------------------------------------------------------------------------------
# What keeps apart
# ------------------------------------------------------------------------------------------------


def test_evidence_on_different_units_stays_apart() -> None:
    _, deviations, evidence = bundle(("FT01", EPOCH, 0.4), ("LT01", EPOCH, 0.6))

    events = group_evidence(evidence, topology(), WINDOW, deviations)

    assert [event.entity_ids for event in events] == [["FT01"], ["LT01"]]


def test_evidence_in_different_windows_stays_apart() -> None:
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4), ("PT01", EPOCH + timedelta(minutes=5), 0.6)
    )

    events = group_evidence(evidence, topology(), WINDOW, deviations)

    assert len(events) == 2
    assert [event.timestamp for event in events] == [EPOCH, EPOCH + timedelta(minutes=5)]


def test_evidence_from_two_engines_never_shares_a_group() -> None:
    """Domain is part of the key. Correlating across engines is PART 7's job, not grouping's."""
    _, atlas_deviations, atlas_evidence = bundle(("FT01", EPOCH, 0.4))
    _, sentiel_deviation, sentiel_evidence = fact("PT01", EPOCH, domain=Domain.SENTIEL)

    events = group_evidence(
        [*atlas_evidence, sentiel_evidence],
        topology(),
        WINDOW,
        {**atlas_deviations, sentiel_deviation.id: sentiel_deviation},
    )

    assert len(events) == 2
    assert {event.domain for event in events} == {Domain.ATLAS, Domain.SENTIEL}


def test_the_window_grid_is_absolute_so_two_batches_group_the_same_way() -> None:
    """Buckets are anchored to a fixed epoch, not to whichever evidence happened to arrive first.

    Without that, the same measurement would land in a different event depending on what else was
    in the batch, and two runs over overlapping slices of one corpus would disagree.
    """
    early = EPOCH - timedelta(minutes=10)
    _, together_deviations, together_evidence = bundle(
        ("LT01", early, 0.3), ("FT01", EPOCH, 0.4), ("PT01", EPOCH + timedelta(seconds=20), 0.5)
    )
    together = group_evidence(together_evidence, topology(), WINDOW, together_deviations)
    apart = group_evidence(together_evidence[1:], topology(), WINDOW, together_deviations)

    assert [event.entity_ids for event in together] == [["LT01"], ["FT01", "PT01"]]
    assert [event.entity_ids for event in apart] == [["FT01", "PT01"]]


def test_events_come_out_in_time_then_subsystem_order() -> None:
    _, deviations, evidence = bundle(
        ("LT01", EPOCH + timedelta(minutes=5), 0.3), ("PT01", EPOCH, 0.4), ("LT01Z", EPOCH, 0.5)
    )

    events = group_evidence(evidence, topology(), WINDOW, deviations)

    assert [event.entity_ids for event in events] == [["PT01"], ["LT01Z"], ["LT01"]]


# ------------------------------------------------------------------------------------------------
# Counting, not detecting
# ------------------------------------------------------------------------------------------------


def test_grouping_changes_the_count_without_changing_the_coverage() -> None:
    """The whole claim of this module, asserted as two separate things.

    Fewer things to investigate is the win. Not one measurement dropped out of consideration is
    the constraint. A collapse that quietly lost evidence would satisfy the first and betray the
    second, so they are asserted apart rather than as one number.
    """
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4),
        ("FT01Z", EPOCH, 0.5),
        ("PT01", EPOCH, 0.6),
        ("LT01", EPOCH, 0.7),
        ("LT01Z", EPOCH, 0.8),
    )

    events = group_evidence(evidence, topology(), WINDOW, deviations)

    assert len(events) < len(evidence)
    covered = [member for event in events for member in member_evidence_ids(event)]
    assert sorted(covered) == sorted(item.id for item in evidence)


def test_every_piece_of_evidence_lands_in_exactly_one_group() -> None:
    """Membership is a partition, so no fact can be counted twice or dropped."""
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4),
        ("PT01", EPOCH + timedelta(minutes=2), 0.5),
        ("LT01", EPOCH, 0.6),
        ("LT01Z", EPOCH + timedelta(minutes=2), 0.7),
    )

    events = group_evidence(evidence, topology(), WINDOW, deviations)
    covered = [member for event in events for member in member_evidence_ids(event)]

    assert len(covered) == len(set(covered)) == len(evidence)


def test_grouping_is_deterministic_and_leaves_its_input_alone() -> None:
    _, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4), ("PT01", EPOCH, 0.6), ("LT01", EPOCH, 0.5)
    )
    before = list(evidence)

    first = group_evidence(evidence, topology(), WINDOW, deviations)
    second = group_evidence(evidence, topology(), WINDOW, deviations)

    assert evidence == before
    assert [(e.entity_ids, e.timestamp, e.weight, e.summary) for e in first] == [
        (e.entity_ids, e.timestamp, e.weight, e.summary) for e in second
    ]


# ------------------------------------------------------------------------------------------------
# Traceability
# ------------------------------------------------------------------------------------------------


def test_the_drill_down_path_walks_event_to_signal_to_observation() -> None:
    """Constitution §3.2 through the collapse: the whole path, walked, not asserted in the abstract.

    An operator looking at one subsystem event must be able to reach every measurement behind it.
    This walks exactly that route through the store — event, member evidence, deviation,
    observation — and checks that what comes back is the set of signals the event claims.
    """
    observations, deviations, evidence = bundle(
        ("FT01", EPOCH, 0.4), ("FT01Z", EPOCH, 0.5), ("PT01", EPOCH, 0.6)
    )
    event = group_evidence(evidence, topology(), WINDOW, deviations)[0]

    store = InMemoryEvidenceStore()
    for observation in observations:
        store.add_observation(observation)
    for deviation in deviations.values():
        store.add_deviation(deviation)
    for item in [*evidence, event]:
        store.add_evidence(item)

    reached: list[str] = []
    for member_id in member_evidence_ids(event):
        member = store.get_evidence(member_id)
        assert member is not None
        raised_by = store.get_deviation(member.source_id)
        assert raised_by is not None
        measured = store.get_observation(raised_by.observation_id)
        assert measured is not None
        reached.append(measured.feature)

    assert sorted(reached) == event.entity_ids


def test_a_subsystem_event_is_recognisable_and_a_per_signal_one_is_not() -> None:
    _, deviations, evidence = bundle(("FT01", EPOCH, 0.4))
    event = group_evidence(evidence, topology(), WINDOW, deviations)[0]

    assert is_subsystem_event(event)
    assert not is_subsystem_event(evidence[0])


def test_asking_a_per_signal_evidence_for_its_members_raises() -> None:
    _, _, evidence = bundle(("FT01", EPOCH, 0.4))

    with pytest.raises(ValueError, match="not a subsystem event"):
        member_evidence_ids(evidence[0])


# ------------------------------------------------------------------------------------------------
# Refusals
# ------------------------------------------------------------------------------------------------


def test_a_signal_outside_the_map_raises_rather_than_being_guessed_at() -> None:
    observation, deviation, evidence = fact("UNMAPPED", EPOCH)
    assert observation.feature == "UNMAPPED"

    with pytest.raises(TopologyError, match="UNMAPPED"):
        group_evidence([evidence], topology(), WINDOW, {deviation.id: deviation})


def test_evidence_whose_deviation_is_missing_raises() -> None:
    """Without the deviation there is no signal, and without the signal there is no subsystem."""
    _, _, evidence = bundle(("FT01", EPOCH, 0.4))

    with pytest.raises(ValueError, match="cannot be resolved"):
        group_evidence(evidence, topology(), WINDOW, {})


def test_a_non_positive_window_raises() -> None:
    with pytest.raises(ValueError, match="positive duration"):
        group_evidence([], topology(), timedelta(0), {})
