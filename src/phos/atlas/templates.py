"""The industrial explanations Atlas may draw on, and the base rates their priors come from.

Five curated explanations, written by hand, and no mechanism for inventing a sixth (Constitution
§3.6). 4B's `HypothesisTemplate` supplies the form: a label, a prior, and a declarative statement of
which evidence argues for the explanation and which argues against it. What this module adds is the
domain knowledge — what actually goes wrong in a plant, and how often.

**The priors are derived from base rates, and the derivation is executable.** Two anchors and one
rule produce every number, so none of them is a round figure chosen by feel:

- *The ordering* comes from what causes unexpected behaviour in a running plant. Instrument and
  equipment faults are the modal cause — a plant with hundreds of transmitters, each with a
  service life measured in years, sees faults continuously, which is why alarm-management practice
  treats nuisance alarms from failing instrumentation as its dominant load. Human intervention and
  genuine process upsets are common but episodic. A cyber attack with a visible process effect is
  rarer than all of them by orders of magnitude: the publicly confirmed set numbers in the tens
  across two decades, against a population of industrial plants in the hundreds of thousands.
- *The floor* is `phos.reasoning.ReasoningConfig.pruning_threshold`. Below it the engine marks a
  hypothesis implausible, which is a judgement made before looking, so the rarest explanation
  starts exactly at that threshold and no lower.
- *The step* is one piece of fully-trusted evidence. `prior_at_rank` multiplies the odds by
  ``exp(EVIDENCE_STRENGTH)`` per rank, so the gap between two explanations is readable as "how many
  observations does it take to close it": one to lift an attack to where maintenance began, two to
  where an equipment fault began.

The unconditional attack base rate is far below this floor, and using it directly would produce an
explanation no evidence could ever raise. The priors here are therefore **conditional** — the
population is "a unit on which a calibrated, out-of-band departure has already been raised", not
"a plant-hour" — and the compression that conditioning implies is not something the available data
measures. That is the second honesty guard in `phos.atlas.engine` restated at its source: these
priors order competing explanations, and the confidences built on them are not calibrated
probabilities and must not be surfaced under Constitution §3.3.

**The matchers see breadth, because grouping put breadth inside a single fact.** A subsystem event
lists the signals that departed together on one unit, so "how much of this unit moved" is a
property of one piece of evidence rather than of a set, and `SubsystemBreadthPattern` reads it. The
boundary between *one device* and *more than one* is HAI's own instrumentation convention — a
device appears as at most a command channel and its feedback, as in ``P1_FCV01D``/``P1_FCV01Z`` —
so it is a fact about the corpus rather than a tuned threshold.

**Persistence is not a pattern, and does not need to be.** A unit that keeps departing produces a
subsystem event in each successive window, and each one is another piece of evidence on the same
hypothesis; the reasoning engine's accumulation *is* the persistence measure. A single blip moves
an explanation a little and a sustained fault moves it a lot, without any template having to
describe a span.

**Two limits HAI imposed, and what PART P3 does to them.** 5C recorded both, and said each would
stand until Atlas could produce evidence about the environment's *structure*. The packet adapter
produces exactly that, so both move — one is lifted, one is halved, and neither disappears.

- `engineering_maintenance` had no matcher worth the name, because a process-telemetry corpus
  carries no maintenance window, work order or engineering-workstation context. It now has its
  first real one: `phos.atlas.packet.graph` reports a command relationship that has never been
  seen, one that has gone silent, and an unfamiliar function code on a known link, and a planned
  change is precisely the mundane explanation for a structure that no longer matches what was
  learned.
- `unauthorised_control_activity` weighed evidence *identically* to `process_disturbance` and was
  told apart only by its prior. A structural change now separates them, and the asymmetry is a
  claim about physics rather than a tuning choice: a real process upset moves readings, and it does
  not make a workstation begin commanding a PLC. So the same fact supports the malicious
  explanation and contradicts the benign upset.

**What remains impossible, and what an unknown master does not.** An *untyped* structural change —
a relationship change that does not declare which of P3's three findings it is — still supports
`engineering_maintenance` and `unauthorised_control_activity` equally, because a commissioning
engineer and an intruder can leave behind the same new link; only the priors separate them. A
*marked unknown master* is a more specific fact: a device that has never commanded this target
began to, which is not how a plant's engineering station works. That finding supports the
malicious explanation and contradicts maintenance. A function-code change or a silence on a
*known* link still supports both, which is ADR 0014's remaining limit.

**A command-behaviour departure now routes, and still does not discriminate (ADR 0071).** ADR 0014
recorded that it bore on no explanation at all, because "which command feature departed is not
expressible in the pattern language: `Evidence` names a kind and some entities, never a feature."
ADR 0070's typed facet is that missing field, so `CommandBehaviourPattern` reads it and the fact
reaches the two explanations that involve somebody operating a device — supporting both
`engineering_maintenance` and `unauthorised_control_activity`, separating neither. What it adds is
the one thing a sensor departure cannot say: *this was control activity, not a reading.* What it
deliberately does not do is bear on `process_disturbance` or `sensor_or_device_fault`, because a
closed loop answers a real upset by commanding differently — the structural asymmetry is about who
commands whom, which an upset cannot change, and not about how much an existing commander commands,
which it changes routinely. The command **graph** therefore remains the only command signal an OT
template can *discriminate* on; behaviour is the only one it can now *weigh*.
"""

import logging
import math
from collections.abc import Mapping
from typing import Final, Self

from pydantic import Field, field_validator, model_validator

from phos.atlas.command_evidence import command_behaviour_feature_of, graph_finding_feature_of
from phos.atlas.grouping import is_subsystem_event
from phos.atlas.packet import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.atlas.work_orders import work_order_feature_of
from phos.ontology import Domain, Entity, EntityId, Evidence, EvidenceKind
from phos.reasoning import (
    EVIDENCE_STRENGTH,
    EvidencePattern,
    HypothesisTemplate,
    ReasoningConfig,
    TemplateLibrary,
    insufficient_evidence_template,
)

__all__ = [
    "ENGINEERING_MAINTENANCE_TEMPLATE_ID",
    "LOWEST_BASE_RATE_PRIOR",
    "ONE_DEVICE_MAX_SIGNALS",
    "PROCESS_DISTURBANCE_TEMPLATE_ID",
    "RANK_ODDS_FACTOR",
    "SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID",
    "UNAUTHORISED_CONTROL_TEMPLATE_ID",
    "CommandBehaviourPattern",
    "GraphFindingPattern",
    "SubsystemBreadthPattern",
    "UntypedStructurePattern",
    "WorkOrderPattern",
    "atlas_library",
    "atlas_templates",
    "prior_at_rank",
]

logger = logging.getLogger(__name__)

SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID: Final = "sensor_or_device_fault"
ENGINEERING_MAINTENANCE_TEMPLATE_ID: Final = "engineering_maintenance"
PROCESS_DISTURBANCE_TEMPLATE_ID: Final = "process_disturbance"
UNAUTHORISED_CONTROL_TEMPLATE_ID: Final = "unauthorised_control_activity"

LOWEST_BASE_RATE_PRIOR: Final = ReasoningConfig().pruning_threshold
"""Prior of the rarest explanation, and the anchor the whole ladder is built up from.

Taken from the reasoning engine's pruning threshold rather than chosen: a hypothesis starting below
it is born marked implausible, which is a verdict reached before any evidence. This is the lowest
prior an explanation can carry while still being genuinely under consideration.
"""

RANK_ODDS_FACTOR: Final = math.exp(EVIDENCE_STRENGTH)
"""Odds multiplier for one rank of the base-rate ordering.

Equal to what one fully-trusted piece of evidence multiplies a hypothesis's odds by, so a rank gap
is readable as a number of observations rather than as a preference.
"""

ONE_DEVICE_MAX_SIGNALS: Final = 2
"""Most signals one physical device contributes, and therefore where "localised" stops.

HAI 21.03 instruments a device as at most a command channel and its feedback — ``P1_FCV01D`` with
``P1_FCV01Z``, ``P1_PP01AD`` with ``P1_PP01AR`` — so up to two signals departing together on a unit
is consistent with one device failing, and three or more is not. A fact about the corpus's
instrumentation, taken from ``data/hai/topology.toml``, rather than a threshold tuned on results.
"""

_FLOOR_ODDS: Final = LOWEST_BASE_RATE_PRIOR / (1.0 - LOWEST_BASE_RATE_PRIOR)


def prior_at_rank(rank: int) -> float:
    """Return the prior of an explanation ``rank`` steps above the rarest one.

    Args:
        rank: How many ranks of base rate this explanation sits above the floor. ``0`` is the
            rarest explanation on offer, and each step multiplies the odds by `RANK_ODDS_FACTOR`.

    Returns:
        A probability strictly inside ``(0, 1)``, suitable as a `HypothesisTemplate` prior.

    Raises:
        ValueError: If ``rank`` is negative, which would place an explanation below the floor and
            so have the engine pre-judge it as implausible.
    """
    if rank < 0:
        raise ValueError(
            f"rank must be non-negative, got {rank}: a prior below {LOWEST_BASE_RATE_PRIOR} is one "
            "the reasoning engine marks pruned before any evidence arrives"
        )
    odds = _FLOOR_ODDS * RANK_ODDS_FACTOR**rank
    return odds / (1.0 + odds)


class SubsystemBreadthPattern(EvidencePattern):
    """An `EvidencePattern` that also constrains how much of a unit departed.

    4B's pattern language deliberately expresses only what is true of one fact, and leaves
    properties of a *set* to the engine. Breadth would normally be a set property — but grouping
    has already collapsed a unit's departures into one piece of evidence whose ``entity_ids`` list
    the signals involved, so how broad the departure was is now readable from the fact itself.

    The band is closed and finite on both dimensions the base class constrains, so `overlaps` stays
    exact and `HypothesisTemplate` can still refuse, at construction, to call one fact both
    supporting and contradictory.

    **Breadth is only defined for a grouped event, and P3 made saying so necessary.** Until the
    packet adapter, every `EvidenceKind.DEVIATION` the Atlas engine reasoned over was a subsystem
    event, so "how many entities does this fact name" and "how much of a unit departed" were the
    same question, and the guard below was implicit and free. P3 introduces per-device
    command-behaviour evidence — an ordinary `DEVIATION` naming one device, deliberately
    indistinguishable in kind — and for that fact the two questions come apart: it names one entity
    because a device is one device, not because one instrument on a pump failed. Read as breadth it
    would match ``_LOCALISED`` and therefore argue *against* `unauthorised_control_activity`, which
    is the exact inversion reading the command stream exists to prevent. ``subsystem_events_only``
    turns the implicit invariant into a checked one, the way
    `phos.atlas.engine._require_fresh_measurement` does for carried-forward cells.

    Attributes:
        min_signals: Fewest departing signals that match. At least one.
        max_signals: Most that match; ``None`` for no upper bound.
        subsystem_events_only: Whether this pattern reads only collapsed subsystem events, tested
            with `phos.atlas.grouping.is_subsystem_event` — a declared marker rather than a guess
            about how identifiers happen to be spelled. ``True`` by default, because a band over
            ``entity_ids`` is a claim about a physical unit.

    Invariants:
        ``min_signals <= max_signals`` when an upper bound is given.
    """

    min_signals: int = Field(default=1, ge=1)
    max_signals: int | None = Field(default=None, ge=1)
    subsystem_events_only: bool = True

    @model_validator(mode="after")
    def _check_band(self) -> Self:
        if self.max_signals is not None and self.max_signals < self.min_signals:
            raise ValueError(
                f"min_signals ({self.min_signals}) must not exceed max_signals "
                f"({self.max_signals}); an inverted band matches nothing"
            )
        return self

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether ``evidence`` satisfies the inherited constraints *and* the breadth band.

        Args:
            evidence: The fact to test. Its ``entity_ids`` are read as the signals that departed,
                which is what `phos.atlas.grouping` puts there.
            entities: Entity lookup, used only by the inherited constraints.

        Returns:
            ``True`` if the evidence matches on every dimension, the scope guard included.
        """
        if not super().matches(evidence, entities):
            return False
        if is_subsystem_event(evidence) is not self.subsystem_events_only:
            return False
        breadth = len(evidence.entity_ids)
        return self.min_signals <= breadth and (
            self.max_signals is None or breadth <= self.max_signals
        )

    def overlaps(self, other: EvidencePattern) -> bool:
        """Return whether some piece of evidence could satisfy both patterns.

        Exact when ``other`` also carries a band. A plain `EvidencePattern` constrains no breadth,
        so it is treated as unbounded — which is what it means. The reverse call
        (``plain.overlaps(banded)``) runs the base implementation and cannot see the band, so it
        answers conservatively; conservative only ever makes `HypothesisTemplate` refuse a template
        it could have allowed, never allow an ambiguous one.

        Two banded patterns scoped to different evidence — one to subsystem events, one to
        everything else — can never both match, because `phos.atlas.grouping.is_subsystem_event`
        reads a single declared marker and no fact both carries it and lacks it.
        """
        if not super().overlaps(other):
            return False
        if (
            isinstance(other, SubsystemBreadthPattern)
            and other.subsystem_events_only is not self.subsystem_events_only
        ):
            return False
        low, high = _band(other)
        return _reaches(self.min_signals, high) and _reaches(low, self.max_signals)


def _band(pattern: EvidencePattern) -> tuple[int, int | None]:
    """Return a pattern's breadth band.

    A plain `EvidencePattern` constrains no breadth at all, so it is read as unbounded — which is
    what it means, not a default standing in for a missing answer.
    """
    if isinstance(pattern, SubsystemBreadthPattern):
        return pattern.min_signals, pattern.max_signals
    return 1, None


def _reaches(low: int, high: int | None) -> bool:
    """Return whether ``low`` is at or below ``high``, where ``None`` means no upper bound."""
    return high is None or low <= high


_LOCALISED: Final = SubsystemBreadthPattern(
    kinds=(EvidenceKind.DEVIATION,), max_signals=ONE_DEVICE_MAX_SIGNALS
)
"""At most one device's worth of a unit departed."""

_BROAD: Final = SubsystemBreadthPattern(
    kinds=(EvidenceKind.DEVIATION,), min_signals=ONE_DEVICE_MAX_SIGNALS + 1
)
"""More of a unit departed than any one device accounts for."""


class CommandBehaviourPattern(EvidencePattern):
    """An `EvidencePattern` that reads a device's declared command-behaviour departure.

    ADR 0014 refused this matcher on two grounds. The first — "`Evidence` names a kind and some
    entities, never a feature", so "no pattern in 4B's language can ask whether it was a write
    share, a polling rhythm or a register span" — stopped being true when ADR 0070 typed the
    facet. The second still binds: a matcher supporting *every* explanation equally would change
    no ordering and cost code. This one supports two of the four and is silent on the other two,
    which is an ordering change and a claim each half of which is argued below (ADR 0071).

    **What it claims.** A declared command-behaviour departure says one thing: *this device's
    commanding changed*. That is control activity, not a reading — which is the whole reason P2
    measured the command stream separately from the plant's sensors. Both explanations that
    involve somebody operating a device are therefore supported by it: a commissioning engineer
    alters how a device commands, and so does an attacker. The two are **not** separated by this
    fact, and the tie is deliberate. It is the same tie ADR 0014 Decision 4 recorded for a
    function-code change on a known link — "a commissioning engineer and an intruder leave behind
    the *same* new relationship" — reached here for the same reason and left unresolved, because
    resolving it would be a claim about intent that no command feature carries.

    **What it refuses to claim.** `process_disturbance` and `sensor_or_device_fault` get no
    relation at all, and the refusal is the load-bearing half. Calling a command departure
    evidence *against* a real upset would be false: a closed loop answers a disturbance by acting,
    so an upset genuinely does move `write_command_share`, `register_write_value_mean` and
    `command_interval_mean_ms`. ADR 0014's structural asymmetry does not transfer here — it is
    about *who commands whom*, which an upset cannot change, not about *how much* an existing
    commander commands, which an upset changes routinely. Calling it evidence *for* an upset would
    be a claim about closed-loop controller dynamics that nothing in Atlas has measured.

    **No `features` field, unlike `GraphFindingPattern`.** That class enumerates features because
    P3 needed an unknown master told apart from a known-link change, a separation ADR 0027 argues
    from plant practice. Nothing here needs a sub-selection, and choosing one would mean deciding
    that a write-side departure is more suspicious than a rhythm-side one — a tuning choice with
    nothing to tune against, since ADR 0040 and the TU Wien assessment both record that the corpus
    which could justify it does not exist. Any declared command-behaviour feature matches, which is
    exactly the strength of the claim being made.

    **The subsystem-event guard is checked, not assumed.** `_LOCALISED` *contradicts*
    `unauthorised_control_activity` and is scoped to the same `EvidenceKind.DEVIATION` this
    pattern is, so the two must be provably disjoint or `HypothesisTemplate` would be right to
    refuse the template — and it would be refusing a real ambiguity, because matching `_LOCALISED`
    is the inversion ADR 0014 Decision 3 exists to prevent. Nothing promotes a grouped subsystem
    event carrying a command-behaviour facet, but "nothing does" is an invariant holding by
    accident, which is the gap Decision 3 closed with ``subsystem_events_only``. Reading
    `phos.atlas.grouping.is_subsystem_event` here makes the disjointness a fact about a declared
    marker: no evidence both carries it and lacks it, so `overlaps` can answer exactly.
    """

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether this fact declares a command-behaviour facet and is not a grouped event.

        Args:
            evidence: The fact to test. Resolved through `command_behaviour_feature_of`, which
                reads the typed facet and falls back to the summary marker only when no facet is
                present (ADR 0070) — so a reworded operator sentence cannot unmatch this pattern.
            entities: Entity lookup, used only by the inherited constraints.

        Returns:
            ``True`` if the evidence declares a command-behaviour feature and is not a collapsed
            subsystem event. Evidence declaring no facet — a hand-built fixture, a sensor
            departure, another facet — returns ``False``, because a matcher that read an
            undeclared deviation as command behaviour would put every sensor reading on both
            control explanations.
        """
        if not super().matches(evidence, entities):
            return False
        if is_subsystem_event(evidence):
            return False
        return command_behaviour_feature_of(evidence) is not None

    def overlaps(self, other: EvidencePattern) -> bool:
        """Return whether some piece of evidence could satisfy both patterns.

        Exactly disjoint from any pattern scoped to grouped subsystem events, because `matches`
        reads the same declared marker `SubsystemBreadthPattern` does and no fact both carries it
        and lacks it. That is what lets this pattern support `unauthorised_control_activity` while
        `_LOCALISED` contradicts it.

        Against everything else the base implementation answers: exact for the three
        relationship-change patterns, which constrain a kind this one does not share, and
        deliberately not a blanket refusal for a band declared with ``subsystem_events_only=False``,
        where a fact genuinely could satisfy both.
        """
        if isinstance(other, SubsystemBreadthPattern) and other.subsystem_events_only:
            return False
        return super().overlaps(other)


_COMMAND_BEHAVIOUR: Final = CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,))
"""A device's commanding departed from its learned band — control activity, not a reading."""


class WorkOrderPattern(EvidencePattern):
    """A sanctioned change-window / work-order fact (Session E3).

    Disjoint from command-graph structure so a work order can support maintenance and
    contradict unauthorised control without overlapping `_STRUCTURE_CHANGED`.
    """

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether this fact declares the work-order facet (ADR 0070)."""
        if not super().matches(evidence, entities):
            return False
        return work_order_feature_of(evidence) is not None

    def overlaps(self, other: EvidencePattern) -> bool:
        """Work orders are disjoint from graph findings and untyped structure."""
        rivals = (GraphFindingPattern, UntypedStructurePattern, CommandStructurePattern)
        if isinstance(other, rivals):
            return False
        if isinstance(other, WorkOrderPattern):
            return super().overlaps(other)
        return super().overlaps(other)


class CommandStructurePattern(EvidencePattern):
    """A relationship change that is not a work-order stamp.

    Command-graph structure still supports both maintenance and an attacker on a known
    link. A work order is a different fact and must not ride this pattern onto the
    attack explanation (Session E3).
    """

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether this is command structure, not a sanctioned work order."""
        if not super().matches(evidence, entities):
            return False
        return work_order_feature_of(evidence) is None

    def overlaps(self, other: EvidencePattern) -> bool:
        """Command structure and a work order are disjoint by construction."""
        if isinstance(other, WorkOrderPattern):
            return False
        return super().overlaps(other)


_STRUCTURE_CHANGED: Final = CommandStructurePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))
"""The environment's own structure changed — the shape of evidence a planned change would leave."""

_WORK_ORDER: Final = WorkOrderPattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))
"""A declared work order / change window. Supports maintenance; contradicts unauthorised control."""


class GraphFindingPattern(EvidencePattern):
    """An `EvidencePattern` that reads which command-graph finding the fact declares.

    P3's three structural changes are one `EvidenceKind`, so a template that treated them as
    identical could not say an unknown master is an attacker while a new function on a known
    engineering station is maintenance.

    **The finding type is read from the typed facet** — `phos.ontology.FacetKind.GRAPH_FINDING`
    plus the feature — through `graph_finding_feature_of`. It used to be recovered by parsing a
    declared prefix off the human-readable summary, which made this matcher, and therefore a
    reasoning outcome, depend on the wording of a sentence written for an operator (ADR 0070).
    The stamp is still written and still resolves evidence that carries no facet.

    Attributes:
        features: Which graph-finding feature names match. Empty matches any declared finding.
    """

    features: tuple[str, ...] = ()

    @field_validator("features")
    @classmethod
    def _normalise_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether this fact declares a graph finding in ``features``."""
        if not super().matches(evidence, entities):
            return False
        feature = graph_finding_feature_of(evidence)
        if feature is None:
            return False
        return not self.features or feature in self.features

    def overlaps(self, other: EvidencePattern) -> bool:
        """Declared findings never overlap untyped structure; two overlap on shared features."""
        if isinstance(other, UntypedStructurePattern):
            return False
        if isinstance(other, WorkOrderPattern):
            return False
        if not super().overlaps(other):
            return False
        if isinstance(other, GraphFindingPattern):
            if not self.features or not other.features:
                return True
            return bool(set(self.features) & set(other.features))
        return True


class UntypedStructurePattern(EvidencePattern):
    """A relationship change that does not declare which graph finding it is.

    Test fixtures and any promoter that has declared no facet still have to support the P3 claim
    that *some* structural change argues for a planned change. A declared unknown master is not
    this: it is a more specific fact, matched by `GraphFindingPattern`.
    """

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether this is a relationship change declaring neither facet."""
        if not super().matches(evidence, entities):
            return False
        return (
            graph_finding_feature_of(evidence) is None and work_order_feature_of(evidence) is None
        )

    def overlaps(self, other: EvidencePattern) -> bool:
        """Untyped structure and a declared graph finding are disjoint by construction."""
        if isinstance(other, GraphFindingPattern):
            return False
        if isinstance(other, WorkOrderPattern):
            return False
        return super().overlaps(other)


_UNKNOWN_MASTER: Final = GraphFindingPattern(
    kinds=(EvidenceKind.RELATIONSHIP_CHANGE,), features=(UNKNOWN_COMMAND_RELATIONSHIP,)
)
"""A device that has never commanded this target began to. Not how plant engineers work."""

_KNOWN_LINK_CHANGE: Final = GraphFindingPattern(
    kinds=(EvidenceKind.RELATIONSHIP_CHANGE,),
    features=(SILENT_COMMAND_RELATIONSHIP, UNEXPECTED_COMMAND_FUNCTION),
)
"""A known command relationship changed its function mix or went silent."""

_UNTYPED_STRUCTURE: Final = UntypedStructurePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))
"""A structural change whose finding type was not declared — the P3 fixture shape."""


def atlas_templates() -> tuple[HypothesisTemplate, ...]:
    """Return the five OT explanations Atlas reasons with, in registration order.

    Five and no more (PART 5C §11). Each carries a prior from `prior_at_rank` at the base-rate rank
    argued for in this module's docstring, and a matcher that claims only what industrial process
    telemetry can actually support.

    Returns:
        ``(sensor or device fault, engineering maintenance, process disturbance, unauthorised
        control activity, insufficient evidence)``.
    """
    return (
        HypothesisTemplate(
            template_id=SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
            label="A sensor or device on this unit has failed",
            domain=Domain.ATLAS,
            # Rank 2: the modal cause of unexpected behaviour in a running plant.
            prior=prior_at_rank(2),
            supported_by=(_LOCALISED,),
            contradicted_by=(_BROAD,),
        ),
        HypothesisTemplate(
            template_id=ENGINEERING_MAINTENANCE_TEMPLATE_ID,
            label="A planned engineering or maintenance change",
            domain=Domain.ATLAS,
            # Rank 1: common, but episodic rather than continuous.
            prior=prior_at_rank(1),
            # A planned change is argued for by a change in the environment's structure — but
            # not by every kind of it. An untyped relationship change (the P3 fixture shape)
            # and a function-code change or silence on a *known* link are exactly what a
            # commissioning engineer leaves behind. A device that has never commanded this
            # target beginning to write is not: that finding contradicts this explanation.
            # A deviation is deliberately *not* listed as contradictory: maintenance genuinely
            # produces deviations, of any breadth, so calling one evidence against it would be
            # wrong rather than merely weak.
            # `_COMMAND_BEHAVIOUR` is ADR 0071's addition and argues for this explanation for the
            # plainest reason available: altering how a device commands is what the work is.
            supported_by=(_UNTYPED_STRUCTURE, _KNOWN_LINK_CHANGE, _WORK_ORDER, _COMMAND_BEHAVIOUR),
            contradicted_by=(_UNKNOWN_MASTER,),
        ),
        HypothesisTemplate(
            template_id=PROCESS_DISTURBANCE_TEMPLATE_ID,
            label="A real process upset on this unit",
            domain=Domain.ATLAS,
            # Rank 1: a plant is continuously rejecting disturbances, but only large ones break the
            # learned structure.
            prior=prior_at_rank(1),
            supported_by=(_BROAD,),
            # A real upset moves readings; it does not make a workstation start commanding a PLC,
            # silence a link that always polled, or put an unfamiliar function code on the wire.
            # A change in the command structure is therefore evidence *against* this explanation.
            contradicted_by=(_LOCALISED, _STRUCTURE_CHANGED),
        ),
        HypothesisTemplate(
            template_id=UNAUTHORISED_CONTROL_TEMPLATE_ID,
            label="Unauthorised control activity on this unit",
            domain=Domain.ATLAS,
            # Rank 0: rarer than every other explanation by orders of magnitude.
            prior=prior_at_rank(0),
            # On process telemetry alone this matcher is identical to the process-upset one and
            # only the prior separates them: nothing in a plant's readings tells an operator's
            # legitimate action from an attacker's. `_STRUCTURE_CHANGED` is P3's contribution and
            # the one asymmetry — a departure in *who commands whom* is control activity by
            # definition, and a process upset does not produce one. An unknown master is that
            # fact at its strongest; a known-link change still supports this explanation too,
            # and is the remaining case that cannot be told from maintenance by evidence alone.
            # `_COMMAND_BEHAVIOUR` (ADR 0071) joins that remaining case rather than narrowing it:
            # an attacker operating a device changes how it commands, and so does an engineer, so
            # the fact supports both and separates neither. It is disjoint from `_LOCALISED` by
            # the subsystem-event marker, which is what keeps the role single-valued.
            supported_by=(_BROAD, _STRUCTURE_CHANGED, _COMMAND_BEHAVIOUR),
            contradicted_by=(_LOCALISED, _WORK_ORDER),
        ),
        insufficient_evidence_template(Domain.ATLAS),
    )


def atlas_library() -> TemplateLibrary:
    """Return a `TemplateLibrary` holding exactly `atlas_templates` for `Domain.ATLAS`."""
    return TemplateLibrary(templates=atlas_templates())
