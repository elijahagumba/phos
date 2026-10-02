"""Walk a narrative back to raw observations (Sessions D2 and Ω1).

Constitution §3.2: every user-visible conclusion reconstructs from stored `Evidence`. This
module is the executable audit, not a second score.
"""

from __future__ import annotations

from collections.abc import Iterator

from phos.atlas.command_evidence import command_behaviour_feature_of, graph_finding_feature_of
from phos.atlas.grouping import is_subsystem_event, member_evidence_ids
from phos.atlas.work_orders import work_order_feature_of
from phos.ontology import Evidence, EvidenceKind, EvidenceStore, Narrative, Observation

__all__ = [
    "observations_under",
    "walk_evidence_to_observation",
]


def observations_under(narrative: Narrative, store: EvidenceStore) -> list[Observation]:
    """Return every measurement a narrative cites, in evidence-id order.

    Raises:
        ValueError: If any cited id is missing or does not reconstruct to an observation.
    """
    found: list[Observation] = []
    for evidence_id in narrative.evidence_ids:
        evidence = store.get_evidence(evidence_id)
        if evidence is None:
            raise ValueError(f"narrative {narrative.id} cites missing evidence {evidence_id}")
        found.extend(walk_evidence_to_observation(evidence, store))
    return found


def walk_evidence_to_observation(evidence: Evidence, store: EvidenceStore) -> list[Observation]:
    """Expand one stored fact to the observation(s) underneath it."""
    return list(_walk(evidence, store))


def _walk(evidence: Evidence, store: EvidenceStore) -> Iterator[Observation]:
    if is_subsystem_event(evidence):
        for member_id in member_evidence_ids(evidence):
            member = store.get_evidence(member_id)
            if member is None:
                raise ValueError(f"subsystem event {evidence.id} cites missing member {member_id}")
            yield from _walk(member, store)
        return

    if evidence.kind is EvidenceKind.DEVIATION:
        deviation = store.get_deviation(evidence.source_id)
        if deviation is None:
            raise ValueError(
                f"evidence {evidence.id} source {evidence.source_id} is not a stored deviation"
            )
        observation = store.get_observation(deviation.observation_id)
        if observation is None:
            raise ValueError(
                f"deviation {deviation.id} observation {deviation.observation_id} is not stored"
            )
        yield observation
        return

    observation = store.get_observation(evidence.source_id)
    if observation is None:
        raise ValueError(
            f"evidence {evidence.id} source {evidence.source_id} is not a stored observation"
        )
    _ = (
        graph_finding_feature_of(evidence),
        command_behaviour_feature_of(evidence),
        work_order_feature_of(evidence),
    )
    yield observation
