"""Whether a process event co-occurs with a valid command, an unknown master, or neither.

Templates decide which *explanation* a fact argues for. This module answers a narrower question
an operator actually asks, and which the cycle contract measures as ranking: given a telemetry
event, was there command-path activity in the same window, and if so was it from a device the
plant already knew as a commander?

The answer is a co-occurrence table, not a probability. Three declared outcomes:

- ``UNAUTHORISED`` — a master that has never commanded this target wrote in the window
  (``unknown_command_relationship``). That is not how a plant's engineering station works, and
  it is the finding that lets `unauthorised_control_activity` outrank `engineering_maintenance`.
- ``COMMANDED`` — command-path activity from a *known* relationship (a behaviour departure, or a
  function-code change on a learned link) and no unknown master.
- ``UNCOMMANDED`` — no command evidence in the window, or only a learned link going silent. A
  process event with nothing on the wire is still a process event.

Ranking of competing explanations remains the template library's job. This function exists so a
test (and later a UI) can ask the structural question without re-deriving it from hypothesis
order, and so an unknown-master write can be named as unauthorised independently of priors.

**Reachability is a separate question**, asked when a graph finding is considered for a window's
*story*. A finding may attach only if it shares an entity with in-window command activity
(unknown master or unexpected function), or is the unknown-master finding itself. That is
declared from the finding's ``entity_ids`` — identities the command graph already recorded —
not inferred from co-movement. ``ground_event`` does not become a fourth score when that rule
runs.
"""

import logging
from collections.abc import Iterable, Sequence, Set
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from phos.atlas.command_evidence import CommandEvidence, GraphChange, graph_finding_feature_of
from phos.atlas.packet import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.ontology import Evidence

__all__ = [
    "CommandGrounding",
    "attachable_graph_changes",
    "command_act_entities",
    "command_act_entities_near",
    "graph_finding_is_attachable",
    "ground_event",
]

logger = logging.getLogger(__name__)

_COMMAND_ACT_FEATURES: frozenset[str] = frozenset(
    {UNKNOWN_COMMAND_RELATIONSHIP, UNEXPECTED_COMMAND_FUNCTION}
)


@runtime_checkable
class TimestampWindow(Protocol):
    """Anything that can say whether an instant falls inside a span.

    `phos.eval.LabelledInterval` and the synth `TimeWindow` both satisfy this; the protocol keeps
    this module from depending on either.
    """

    def contains(self, timestamp: datetime) -> bool:
        """Return whether ``timestamp`` falls inside the window."""
        ...


class CommandGrounding(StrEnum):
    """How a process event sits relative to the command path in the same window."""

    UNAUTHORISED = "unauthorised"
    COMMANDED = "commanded"
    UNCOMMANDED = "uncommanded"


class _HorizonWindow:
    """A closed interval of ``horizon`` either side of an instant.

    Used when the caller has a correlation window rather than an attack interval. Not a fitted
    knob: it is whatever duration the reasoning engine already uses to decide one story.
    """

    def __init__(self, at: datetime, horizon: timedelta) -> None:
        self._at = at
        self._horizon = horizon

    def contains(self, timestamp: datetime) -> bool:
        """Return whether ``timestamp`` is within ``horizon`` of the anchor instant."""
        return abs(timestamp - self._at) <= self._horizon


def command_act_entities(
    facts: Iterable[Evidence], window: TimestampWindow | None = None
) -> frozenset[str]:
    """Return entities named by in-scope unknown-master or unexpected-function findings.

    Args:
        facts: Graph-finding evidence (and anything else; unmarked facts contribute nothing).
        window: If given, only findings inside this span count as the window's command act.

    Returns:
        The entity ids on those findings. Empty when the window has no command act.

    Notes:
        This is not inferred from co-movement. The identities are the ones the command graph
        already recorded on the finding.
    """
    entities: set[str] = set()
    for fact in facts:
        if window is not None and not window.contains(fact.timestamp):
            continue
        feature = graph_finding_feature_of(fact)
        if feature in _COMMAND_ACT_FEATURES:
            entities.update(fact.entity_ids)
    return frozenset(entities)


def command_act_entities_near(
    facts: Iterable[Evidence], at: datetime, horizon: timedelta
) -> frozenset[str]:
    """Return command-act entities among ``facts`` within ``horizon`` of ``at``.

    Args:
        facts: Evidence already in the working set.
        at: The instant the candidate finding occurred.
        horizon: How far apart two facts may be and still count as one window's act. Pass the
            reasoning engine's correlation window; do not fit a second duration on D2.

    Returns:
        The same set `command_act_entities` would return for a horizon window around ``at``.
    """
    return command_act_entities(facts, window=_HorizonWindow(at, horizon))


def graph_finding_is_attachable(fact: Evidence, act_entities: Set[str]) -> bool:
    """Return whether ``fact`` may enter a window's story given ``act_entities``.

    Args:
        fact: A candidate piece of evidence. Non-graph facts always attach; this function is
            safe to call on every ingested fact.
        act_entities: Entities named by in-window unknown-master or unexpected-function
            findings, from `command_act_entities`.

    Returns:
        True for unmarked evidence, for the unknown-master finding itself, and for unexpected
        function (those *are* the command act). A silent learned link attaches only when it
        shares an entity with that act. A silent link with no command act in scope does not
        attach.

    Notes:
        Sharing an entity is not plant physics. It is the smallest declared relation the
        finding already carries. It is not grouping.py and not co-movement.
    """
    feature = graph_finding_feature_of(fact)
    if feature is None:
        return True
    if feature in _COMMAND_ACT_FEATURES:
        return True
    if feature == SILENT_COMMAND_RELATIONSHIP:
        return bool(act_entities & set(fact.entity_ids))
    return True


def attachable_graph_changes(
    changes: Sequence[GraphChange], window: TimestampWindow
) -> tuple[GraphChange, ...]:
    """Return in-window graph findings that belong to this window's command act.

    Args:
        changes: Promoted graph findings for a capture (or a test bundle).
        window: The incident span, typically an attack window.

    Returns:
        The subset that may enter the window's story, in the input order. Unknown-master and
        unexpected-function findings always belong when they sit in the window. Silence
        belongs only when it shares an entity with that act.
    """
    in_window = tuple(change for change in changes if window.contains(change.evidence.timestamp))
    act = command_act_entities((change.evidence for change in in_window), window)
    return tuple(
        change for change in in_window if graph_finding_is_attachable(change.evidence, act)
    )


def _unknown_master(changes: tuple[GraphChange, ...], window: TimestampWindow) -> bool:
    """Return whether any in-window finding is a device that has never commanded this target."""
    for change in changes:
        if not window.contains(change.evidence.timestamp):
            continue
        feature = change.finding.feature
        if feature == UNKNOWN_COMMAND_RELATIONSHIP:
            return True
        if graph_finding_feature_of(change.evidence) == UNKNOWN_COMMAND_RELATIONSHIP:
            return True
    return False


def _known_command_activity(bundle: CommandEvidence, window: TimestampWindow) -> bool:
    """Return whether the window shows commanding on a relationship the plant already knew.

    A behaviour departure is a device writing (or polling) unlike its own past — activity, not
    identity. An unexpected function code on a learned link is the same device using a new
    code. A silent link is the opposite of activity and is excluded.
    """
    if any(window.contains(departure.evidence.timestamp) for departure in bundle.departures):
        return True
    for change in bundle.changes:
        if not window.contains(change.evidence.timestamp):
            continue
        feature = change.finding.feature or graph_finding_feature_of(change.evidence)
        if feature == UNEXPECTED_COMMAND_FUNCTION:
            return True
        if feature == SILENT_COMMAND_RELATIONSHIP:
            continue
    return False


def ground_event(
    event: Evidence,
    command_evidence: CommandEvidence,
    window: TimestampWindow,
) -> CommandGrounding:
    """Return how ``event`` co-occurs with command-path evidence inside ``window``.

    Args:
        event: The process-side fact being grounded. The window is the incident span; the event
            names which telemetry fact is in view. An event sitting outside the window is still
            grounded against that window's command evidence.
        command_evidence: The command-behaviour departures and graph findings already promoted
            through the evidence boundary.
        window: The span to look for command-path activity in, typically an attack window.

    Returns:
        One of `CommandGrounding`. Unknown-master writes win over known-link activity: a rogue
        issuer on the wire is unauthorised even if a learned station also moved.

    Notes:
        This is not a detection score and not a calibrated confidence. A later UI may display the
        label; it must not display it as a probability. Reachability — which graph findings enter
        the window's *story* — is `attachable_graph_changes` / `graph_finding_is_attachable`, not
        a fourth value of this enum.
    """
    if not window.contains(event.timestamp):
        logger.debug(
            "grounding event %s at %s against a window that does not contain it",
            event.id,
            event.timestamp,
        )
    if _unknown_master(command_evidence.changes, window):
        return CommandGrounding.UNAUTHORISED
    if _known_command_activity(command_evidence, window):
        return CommandGrounding.COMMANDED
    return CommandGrounding.UNCOMMANDED
