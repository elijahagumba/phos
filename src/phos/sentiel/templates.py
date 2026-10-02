"""The enterprise explanations Sentiel may draw on, and the base rates their priors come from.

Four curated explanations plus the residual, written by hand, and no mechanism for inventing a
fifth (Constitution §3.6). 4B's `HypothesisTemplate` supplies the form — a label, a prior, and a
declarative statement of which evidence argues for the explanation and which argues against it.
What this module adds is the domain knowledge: what actually accounts for a person behaving
unusually in an organisation, and how often.

**The discriminant is a behaviour family, and the families are mostly not 6C's to choose.** 4B's
pattern language expresses only what is true of one fact, and `Evidence` names a kind and some
entities but never a feature — so a template cannot ask "was it the file activity that departed?"
unless the fact itself says so. `phos.sentiel.engine` therefore groups a scored entity-window's
per-feature evidence into at most one **behaviour event** per family, and writes the family into
the event's ``source_id`` behind `BEHAVIOUR_EVENT_MARKER`, the same declared-marker idiom
`phos.atlas.grouping` uses for a subsystem event. `BehaviourFamilyPattern` reads it back.

Three of the four boundaries are already drawn by code this PART reuses rather than by this PART:

- `PEER` is exactly `phos.sentiel.PEER_RELATIVE_FEATURES`. It is the one *register* a template
  discriminates on, because "unlike their group" and "unlike their own past" are different claims
  about the same person and PART 6B built the second one specifically to separate them.
- `RELATIONSHIP` is exactly `phos.sentiel.RELATIONSHIP_FEATURES` — the featuriser's own declared
  family of first-order structural summaries. It is the enterprise counterpart of the structural
  change `phos.atlas.templates` matches on, and it is what a sanctioned change leaves behind.
- `ACCESS` and `DATA_HANDLING` divide what is left along the line `RELATIONSHIP_FEATURES`' own
  docstring draws: "a machine is somewhere a user acts *from*, a recipient or a host is somewhere
  data can go". Logons, machines and hours are where someone acts from; devices, files, mail and
  web are where data can go. A count and its self-relative, first-difference and trend companions
  are the same behaviour measured four ways, so they share a family.

**Grouping before reasoning is the same discipline PART 6B established, one layer up.** 6A measured
what happens when a wider feature set is allowed to multiply the alerts; letting it multiply the
*evidence* would reintroduce exactly that at the reasoning layer, and a hypothesis's confidence
would grow with the size of the feature set rather than with anything the person did. Because an
entity-window yields at most one event per family, 34 features produce no more evidence than 26 do.
What accumulation remains is accumulation over *time*, which is the persistence of a behaviour and
is a fact about the organisation rather than about the featuriser.

**The priors are derived from base rates, and the derivation is executable.** Two anchors and one
rule produce every number, so none of them is a round figure chosen by feel — and, critically, none
of them is a number that could be nudged to make r3.1's two known insiders score better (PART 6C
§9). A later PART that disagrees has to move a *rank*, which is a claim about how often something
happens, not a float.

- *The ordering* comes from what accounts for a person behaving unusually at work. A sanctioned
  change is the modal cause: people join teams, change projects, take on cover, adopt new tooling,
  and hit deadlines, continuously and in large numbers. A declared peer group failing to describe
  someone is just as ordinary, and for a related reason — corporate directories are stale, roles
  are hybrid, and PART 6B found r3.1's own ``role`` attribute yielding a 180-member "peer group",
  which is a department. Account compromise is rarer than both per entity-window, and a deliberate
  malicious insider is rarer still: insider-threat casework consistently reports far fewer
  confirmed malicious insiders than credential-based intrusions.
- *The floor* is `phos.reasoning.ReasoningConfig.pruning_threshold`, exactly as in Atlas: below it
  the engine marks a hypothesis implausible, which is a judgement made before looking.
- *The ceiling* is the residual's own prior. No offered explanation may start ahead of "we do not
  yet know", or the engine would lead with an explanation before any evidence arrived.
- *The step* is one piece of fully-trusted evidence, so a rank gap reads as "how many observations
  does it take to close it".

**Two explanations share the top rank, and that is a claim rather than a shortage of ranks.** In a
real directory, "this person's declared group no longer describes them" and "this person's work has
changed" are frequently the *same event*: the role changed and the directory did not. Nothing in
enterprise base rates separates them, so nothing here pretends to.

**No template declares a contradictory pattern, and that is a finding.** Atlas can say a process
upset does not make a workstation start commanding a PLC. Sentiel has no such asymmetry to spend:
a sanctioned role change genuinely moves access and data handling, an insider genuinely acquires
new counterparties and works odd hours (CERT's own scenario 1), and a compromised account genuinely
touches files. Every family of departure is consistent with every explanation on offer, so what
separates the explanations is which family *fires* and their base rates. Inventing a contradiction
would make the engine argue against an explanation the evidence does not argue against. What would
create a real one is evidence about *sanction* rather than about behaviour — an HR change record, a
project assignment, a change ticket — which is the enterprise counterpart of the maintenance work
order Atlas lacked until PART P3, and which no corpus PHOS reads carries.

**One honest limit, restated at its source.** These priors are conditional on "an entity-window on
which a calibrated, out-of-band departure has already been raised", not on an entity-day in
general, and the compression that conditioning implies is not something the available data
measures. The confidences built on them are not calibrated probabilities and must not be surfaced
under Constitution §3.3 — see `phos.sentiel.engine.SENTIEL_VERTICAL_CAVEATS`.
"""

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Final

from pydantic import field_validator

from phos.ontology import Domain, Entity, EntityId, Evidence, EvidenceId, EvidenceKind
from phos.reasoning import (
    EVIDENCE_STRENGTH,
    EvidencePattern,
    HypothesisTemplate,
    ReasoningConfig,
    TemplateLibrary,
    insufficient_evidence_template,
)
from phos.sentiel.featurise import (
    BASELINE_RELATIVE_SUFFIX,
    DIFFERENCE_SUFFIX,
    PEER_FEATURES,
    PEER_RELATIVE_FEATURES,
    RELATIONSHIP_FEATURES,
    STARTER_FEATURES,
    TREND_SUFFIX,
)

__all__ = [
    "BEHAVIOUR_EVENT_MARKER",
    "BENIGN_ROLE_CHANGE_TEMPLATE_ID",
    "COMPROMISED_ACCOUNT_TEMPLATE_ID",
    # Re-exported rather than restated: the base-rate ladder below is built from the spine's own
    # belief strength, and a reader of this module should be able to see which one it used.
    "EVIDENCE_STRENGTH",
    "FEATURE_FAMILIES",
    "INSIDER_MISUSE_TEMPLATE_ID",
    "LOWEST_BASE_RATE_PRIOR",
    "PEER_ANOMALY_TEMPLATE_ID",
    "RANK_ODDS_FACTOR",
    "RESIDUAL_PRIOR",
    "BehaviourFamily",
    "BehaviourFamilyPattern",
    "behaviour_event_source_id",
    "behaviour_family_of",
    "behaviour_member_ids",
    "family_of",
    "feature_families",
    "is_behaviour_event",
    "prior_at_rank",
    "sentiel_library",
    "sentiel_templates",
]

logger = logging.getLogger(__name__)

BENIGN_ROLE_CHANGE_TEMPLATE_ID: Final = "benign_role_change"
PEER_ANOMALY_TEMPLATE_ID: Final = "peer_anomaly"
COMPROMISED_ACCOUNT_TEMPLATE_ID: Final = "compromised_account"
INSIDER_MISUSE_TEMPLATE_ID: Final = "insider_misuse"


class BehaviourFamily(str, Enum):
    """The class of behaviour one piece of Sentiel evidence is about.

    ``str``-backed so it serialises readably and can be written into — and read back out of — a
    behaviour event's ``source_id``, which is how a template gets to discriminate on something
    `Evidence` does not carry a field for.

    Members:
        ACCESS: Where and when this person acted from — logons, hours, machines.
        DATA_HANDLING: Where data could go — removable devices, files, mail, web.
        RELATIONSHIP: The first-order structure around this person — new machines, new
            counterparties, who they mail and how much of it leaves the organisation.
        PEER: The same behaviour judged against this person's declared peer group rather than
            against their own past.
    """

    ACCESS = "ACCESS"
    DATA_HANDLING = "DATA_HANDLING"
    RELATIONSHIP = "RELATIONSHIP"
    PEER = "PEER"


_ACTED_FROM_COUNTS: Final[tuple[str, ...]] = (
    "logon_count",
    "distinct_pcs",
    "off_hours_logon_count",
)
"""The starter counts that measure where and when someone acted *from*.

The remaining starter counts measure where data could *go*. The line is the one
`phos.sentiel.RELATIONSHIP_FEATURES`' docstring already draws between a machine and a
counterparty; it is not a new boundary invented by this PART.
"""

_DERIVED_SUFFIXES: Final[tuple[str, ...]] = (
    BASELINE_RELATIVE_SUFFIX,
    DIFFERENCE_SUFFIX,
    TREND_SUFFIX,
)
"""Enrichment suffixes that keep a feature in its base count's family.

A level, its z-score against the person's own past, its first difference and its trailing slope are
one behaviour measured four ways. The peer suffix is deliberately absent: it changes what the
measurement is *against*, which is the one register distinction a template discriminates on.
"""


def _base_count(feature: str) -> str | None:
    """Return the starter count ``feature`` derives from, or ``None`` if it derives from none."""
    for suffix in _DERIVED_SUFFIXES:
        if feature.endswith(suffix):
            stem = feature[: -len(suffix)]
            if stem in STARTER_FEATURES:
                return stem
    return feature if feature in STARTER_FEATURES else None


def feature_families(features: Iterable[str]) -> dict[str, BehaviourFamily]:
    """Return the behaviour family of every feature, refusing one it cannot place.

    Args:
        features: The features to classify, normally `phos.sentiel.PEER_FEATURES`.

    Returns:
        A mapping from feature to family, one entry per input feature.

    Raises:
        ValueError: If a feature belongs to no family. A feature with no family is a departure that
            could never reach a hypothesis, and it would fail silently: the scorer would keep
            counting it and no explanation would ever hear about it. Failing at import is the
            loudest available place to say so.
    """
    families: dict[str, BehaviourFamily] = {}
    for feature in features:
        if feature in PEER_RELATIVE_FEATURES:
            families[feature] = BehaviourFamily.PEER
            continue
        if feature in RELATIONSHIP_FEATURES:
            families[feature] = BehaviourFamily.RELATIONSHIP
            continue
        base = _base_count(feature)
        if base is None:
            raise ValueError(
                f"feature {feature!r} belongs to no behaviour family: it is neither a "
                "peer-relative nor a relationship feature, and it does not derive from any of "
                f"{STARTER_FEATURES}. Give it a family, or a departure in it can never reach an "
                "explanation"
            )
        families[feature] = (
            BehaviourFamily.ACCESS if base in _ACTED_FROM_COUNTS else BehaviourFamily.DATA_HANDLING
        )
    return families


FEATURE_FAMILIES: Final[Mapping[str, BehaviourFamily]] = feature_families(PEER_FEATURES)
"""The declared partition of Sentiel's whole feature vocabulary into behaviour families.

Total over `phos.sentiel.PEER_FEATURES` — which is a strict superset of the enriched and starter
sets — and disjoint, because every feature takes exactly one branch above.
"""


def family_of(feature: str) -> BehaviourFamily | None:
    """Return the behaviour family of ``feature``, or ``None`` if Sentiel does not emit it.

    ``None`` rather than a guess: placing an unrecognised feature in some family would put its
    departures into an explanation nobody argued for.
    """
    return FEATURE_FAMILIES.get(feature)


# ------------------------------------------------------------------------------------------------
# The declared marker a behaviour event carries
# ------------------------------------------------------------------------------------------------

BEHAVIOUR_EVENT_MARKER: Final = "behaviour-event:"
"""Prefix that marks an `Evidence.source_id` as naming a family and its members.

Explicit rather than inferred, exactly as `phos.atlas.grouping.SUBSYSTEM_EVENT_MARKER` is: "which
behaviour is this about?" is a question about a declared marker, never about how identifiers happen
to be spelled.
"""

_FAMILY_SEPARATOR: Final = ":"
_MEMBER_SEPARATOR: Final = ","
"""Separates member ids inside a behaviour event's ``source_id``. Absent from every minted id."""


def behaviour_event_source_id(family: BehaviourFamily, members: Sequence[EvidenceId]) -> str:
    """Return the ``source_id`` of a behaviour event, carrying its family and its members.

    Args:
        family: The behaviour the event is about.
        members: Ids of the per-feature evidence collapsed into it, in the order to record.

    Returns:
        A string of the form ``behaviour-event:FAMILY:ev_1,ev_2``.

    Raises:
        ValueError: If ``members`` is empty, because an event an operator cannot expand back into
            the features underneath it would be a summary rather than a finding (Constitution
            §3.2); or if a member id contains the separator, which would make the list unreadable.
    """
    if not members:
        raise ValueError(
            f"a {family.value} behaviour event must name at least one member: an event that "
            "cannot be expanded back into the feature departures it was built from is a summary, "
            "not a finding"
        )
    for member in members:
        if _MEMBER_SEPARATOR in member or _FAMILY_SEPARATOR in member:
            raise ValueError(
                f"member id {member!r} contains a separator ({_MEMBER_SEPARATOR!r} or "
                f"{_FAMILY_SEPARATOR!r}), so the member list could not be read back"
            )
    return f"{BEHAVIOUR_EVENT_MARKER}{family.value}{_FAMILY_SEPARATOR}" + _MEMBER_SEPARATOR.join(
        members
    )


def is_behaviour_event(evidence: Evidence) -> bool:
    """Return whether this evidence is a grouped behaviour event rather than a per-feature fact."""
    return evidence.source_id.startswith(BEHAVIOUR_EVENT_MARKER)


def _marker_body(evidence: Evidence) -> tuple[str, str] | None:
    """Return ``(family text, member text)`` from a behaviour event's marker, or ``None``."""
    if not is_behaviour_event(evidence):
        return None
    rest = evidence.source_id[len(BEHAVIOUR_EVENT_MARKER) :]
    family_text, separator, members = rest.partition(_FAMILY_SEPARATOR)
    if not separator:
        return None
    return family_text, members


def behaviour_family_of(evidence: Evidence) -> BehaviourFamily | None:
    """Return the behaviour family this evidence is about, or ``None`` if it names none.

    Total by design: a per-feature fact, and a marker written by some future version of this
    module, both read as "no family" rather than raising. This is called from inside a matcher, and
    a matcher that raises on an unfamiliar fact would take the whole reasoning pass down with it.
    """
    body = _marker_body(evidence)
    if body is None:
        return None
    try:
        return BehaviourFamily(body[0])
    except ValueError:
        logger.debug(
            "evidence %s carries behaviour family %r, which this version does not know",
            evidence.id,
            body[0],
        )
        return None


def behaviour_member_ids(event: Evidence) -> tuple[EvidenceId, ...]:
    """Return the ids of the per-feature evidence a behaviour event was built from.

    The front door of the drill-down path: from an event to its members, from each member's
    ``source_id`` to its `Deviation`, and from there to the `Observation` a feature was measured in.

    Raises:
        ValueError: If ``event`` is not a behaviour event, which means the caller is holding a
            per-feature fact and there is nothing to expand.
    """
    body = _marker_body(event)
    if body is None:
        raise ValueError(
            f"evidence {event.id!r} is not a behaviour event (source_id {event.source_id!r}), so "
            "it has no members to expand"
        )
    return tuple(body[1].split(_MEMBER_SEPARATOR))


# ------------------------------------------------------------------------------------------------
# The pattern
# ------------------------------------------------------------------------------------------------


class BehaviourFamilyPattern(EvidencePattern):
    """An `EvidencePattern` that also constrains which behaviour a fact is about.

    4B's pattern language expresses only what is true of one fact and constrains on two closed
    vocabularies combined with AND. This adds a third, also closed and finite, so `overlaps` stays
    exact and `HypothesisTemplate` can still refuse — at construction — to call one fact both
    supporting and contradictory.

    The family is read from the fact's own declared marker rather than resolved through a store,
    which is what lets a template be an immutable value with no run state in it.

    Attributes:
        families: Which `BehaviourFamily` values match. Empty matches every fact, including one
            that carries no family at all — which is what "no constraint on this dimension" means
            on the base class, and is kept identical here.

    Invariants:
        Families are stored sorted and de-duplicated, so two spellings of one pattern are equal
        objects and serialise identically.
    """

    families: tuple[BehaviourFamily, ...] = ()

    @field_validator("families")
    @classmethod
    def _normalise_families(cls, value: tuple[BehaviourFamily, ...]) -> tuple[BehaviourFamily, ...]:
        """Sort and de-duplicate, so order and repetition cannot masquerade as meaning.

        The base class does the same for its own two dimensions under a `TypeVar` bound to their
        enums; this is the third dimension's copy rather than a widening of a shared validator.
        """
        return tuple(sorted(set(value), key=lambda member: member.value))

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether ``evidence`` satisfies the inherited constraints *and* the family one.

        Args:
            evidence: The fact to test. Its family is read from its declared marker.
            entities: Entity lookup, used only by the inherited constraints.

        Returns:
            ``True`` if the evidence matches on every dimension.
        """
        if not super().matches(evidence, entities):
            return False
        if not self.families:
            return True
        return behaviour_family_of(evidence) in self.families

    def overlaps(self, other: EvidencePattern) -> bool:
        """Return whether some piece of evidence could satisfy both patterns.

        Exact when ``other`` also constrains a family. A plain `EvidencePattern` constrains none, so
        it is treated as unconstrained — which is what it means. The reverse call
        (``plain.overlaps(banded)``) runs the base implementation and cannot see the families, so it
        answers conservatively; conservative only ever makes `HypothesisTemplate` refuse a template
        it could have allowed, never allow an ambiguous one.
        """
        if not super().overlaps(other):
            return False
        theirs = other.families if isinstance(other, BehaviourFamilyPattern) else ()
        if not self.families or not theirs:
            return True
        return bool(set(self.families) & set(theirs))


# ------------------------------------------------------------------------------------------------
# The base-rate ladder
# ------------------------------------------------------------------------------------------------

LOWEST_BASE_RATE_PRIOR: Final = ReasoningConfig().pruning_threshold
"""Prior of the rarest explanation, and the anchor the ladder is built up from.

Taken from the reasoning engine's pruning threshold rather than chosen: a hypothesis starting below
it is born marked implausible, which is a verdict reached before any evidence.
"""

RESIDUAL_PRIOR: Final = insufficient_evidence_template(Domain.SENTIEL).prior
"""Prior of "we do not yet know", and the ceiling of the ladder.

Read from the shared template rather than restated, so the two can never drift apart.
"""

RANK_ODDS_FACTOR: Final = math.exp(EVIDENCE_STRENGTH)
"""Odds multiplier for one rank of the base-rate ordering.

Equal to what one fully-trusted piece of evidence multiplies a hypothesis's odds by, so a rank gap
is readable as a number of observations rather than as a preference.
"""

_FLOOR_ODDS: Final = LOWEST_BASE_RATE_PRIOR / (1.0 - LOWEST_BASE_RATE_PRIOR)


def prior_at_rank(rank: int) -> float:
    """Return the prior of an explanation ``rank`` steps above the rarest one.

    Deliberately a re-derivation of the two lines `phos.atlas.templates.prior_at_rank` runs on the
    same two shared constants, rather than an import of it: Sentiel importing from Atlas would
    couple the two engines through a place neither of them owns, and promoting the function into
    `phos.reasoning` would mean editing Atlas to consume it, which PART 6C may not do. A later PART
    free to touch both should promote it once.

    Args:
        rank: How many ranks of base rate this explanation sits above the floor. ``0`` is the
            rarest explanation on offer, and each step multiplies the odds by `RANK_ODDS_FACTOR`.

    Returns:
        A probability in ``[LOWEST_BASE_RATE_PRIOR, RESIDUAL_PRIOR)``.

    Raises:
        ValueError: If ``rank`` is negative, which would place an explanation below the floor and
            have the engine pre-judge it implausible; or if it reaches `RESIDUAL_PRIOR`, which
            would have an explanation leading the competing set before any evidence arrived — a
            place that belongs to "we do not yet know" and to nothing else.
    """
    if rank < 0:
        raise ValueError(
            f"rank must be non-negative, got {rank}: a prior below {LOWEST_BASE_RATE_PRIOR} is one "
            "the reasoning engine marks pruned before any evidence arrives"
        )
    odds = _FLOOR_ODDS * RANK_ODDS_FACTOR**rank
    prior = odds / (1.0 + odds)
    if prior >= RESIDUAL_PRIOR:
        raise ValueError(
            f"rank {rank} gives a prior of {prior:.4f}, at or above the {RESIDUAL_PRIOR} carried "
            "by the insufficient evidence residual. No offered explanation may lead the competing "
            "set before any evidence arrives"
        )
    return prior


# ------------------------------------------------------------------------------------------------
# The explanations
# ------------------------------------------------------------------------------------------------

_ACCESS_DEPARTED: Final = BehaviourFamilyPattern(
    kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.ACCESS,)
)
"""Where and when this person acted from departed from what was learned of them."""

_DATA_HANDLING_DEPARTED: Final = BehaviourFamilyPattern(
    kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.DATA_HANDLING,)
)
"""What this person did with data departed from what was learned of them."""

_STRUCTURE_CHANGED: Final = BehaviourFamilyPattern(
    kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.RELATIONSHIP,)
)
"""The structure around this person changed — the shape a sanctioned change leaves behind."""

_UNLIKE_PEERS: Final = BehaviourFamilyPattern(
    kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.PEER,)
)
"""This person departed from their declared peer group rather than from their own past."""


def sentiel_templates() -> tuple[HypothesisTemplate, ...]:
    """Return the five enterprise explanations Sentiel reasons with, in registration order.

    Registration order is most common first, which is also the order they are ranked in before any
    evidence arrives. Each carries a prior from `prior_at_rank` at the base-rate rank argued for in
    this module's docstring, and a matcher that claims only what per-entity-window behavioural
    features can actually support.

    Returns:
        ``(benign role change, peer anomaly, compromised account, insider misuse, insufficient
        evidence)``.
    """
    return (
        HypothesisTemplate(
            template_id=BENIGN_ROLE_CHANGE_TEMPLATE_ID,
            label="A sanctioned change in this person's role or work",
            domain=Domain.SENTIEL,
            # Rank 2: the modal account of someone behaving unlike themselves at work.
            prior=prior_at_rank(2),
            # The enterprise counterpart of Atlas's planned-change explanation, and it matters for
            # the same reason: without it the engine reads every change as an attack. A departure
            # in access or data handling is deliberately *not* listed as contradictory, because a
            # real role change produces both — calling one evidence against this would be wrong
            # rather than merely weak.
            supported_by=(_STRUCTURE_CHANGED,),
        ),
        HypothesisTemplate(
            template_id=PEER_ANOMALY_TEMPLATE_ID,
            label="Behaviour unlike this person's declared peer group",
            domain=Domain.SENTIEL,
            # Rank 2: as ordinary as a role change, and often the same event seen from the
            # directory's side. See this module's docstring on why they share a rank.
            prior=prior_at_rank(2),
            supported_by=(_UNLIKE_PEERS,),
        ),
        HypothesisTemplate(
            template_id=COMPROMISED_ACCOUNT_TEMPLATE_ID,
            label="This account is being used by someone other than its owner",
            domain=Domain.SENTIEL,
            # Rank 1: rarer per entity-window than either mundane explanation, and commoner than a
            # deliberate insider.
            prior=prior_at_rank(1),
            # Someone who is not the account holder has to establish access before they can use it,
            # so a departure in where and when the account acted from is what distinguishes this
            # explanation from the one below. It is *not* supported by data handling — not because
            # an intruder does not touch data, but because that fact does not tell the two apart,
            # and a template supported by everything is separated from its rivals only by its
            # prior.
            supported_by=(_ACCESS_DEPARTED,),
        ),
        HypothesisTemplate(
            template_id=INSIDER_MISUSE_TEMPLATE_ID,
            label="The account holder is misusing the access they hold",
            domain=Domain.SENTIEL,
            # Rank 0: rarer than every other explanation on offer.
            prior=prior_at_rank(0),
            # The account holder already has access, so what departs is what they do with it. This
            # is the register PART 6B measured r3.1's two labelled insiders in.
            supported_by=(_DATA_HANDLING_DEPARTED,),
        ),
        insufficient_evidence_template(Domain.SENTIEL),
    )


def sentiel_library() -> TemplateLibrary:
    """Return a `TemplateLibrary` holding exactly `sentiel_templates` for `Domain.SENTIEL`."""
    return TemplateLibrary(templates=sentiel_templates())
