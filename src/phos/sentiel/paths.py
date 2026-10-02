"""Did today's activity travel somewhere the directory declares no relationship to?

`phos.sentiel.graph` holds the structure the corpus states. `phos.sentiel.traces` holds what each
entity-day actually touched. This module is the join, and the join is where the discipline has to
be spelled out, because it is the one place a declared fact and an observed fact meet.

**The rule: the route is observed, the judgement is declared.** Every hop this module considers is
a field of a *single* activity row — this message went to that address, this day's events named
that machine. Nothing is aggregated into a profile first. The **anomaly** is then decided
exclusively by the directory: "the org chart places this counterparty nowhere near you." At no
point does "unusual" mean "unlike what you have done before" — that question is already asked, and
answered, by PART 6A's ``_dev`` family and PART 6B's peer family. Keeping the two apart is what
stops this becoming a second, worse self-baseline wearing a graph costume.

**Three findings, and only one of them is new.**

* `undeclared_recipients` counts mail to addresses the directory does not own. It is *reported and
  then discounted*, because `external_email_count` already measures it: a reader must not be shown
  the same fact twice under two names. `PathFindings.novel_beyond_counts` says so on every record.
* `distant_internal_recipients` counts mail to **colleagues the directory places outside the
  sender's own department** — not a supervisor, not a report, not a shared team or department.
  This is the finding no existing Sentiel feature can express: it is invisible to
  `external_email_count` (the recipient is internal), to `distinct_email_recipients` (a count says
  nothing about who), and to every ``_dev`` (a first-time colleague and a first-time stranger look
  identical to a self-baseline).
* `shared_device_distant` counts machines that carried activity from this entity **and** from a
  declared-distant colleague on the same day. The co-presence is one day's observed fact, never a
  learned "whose machine this is" — r3.1 declares no device owner at all
  (`phos.sentiel.graph.UNDECLARED_DEVICE_OWNERSHIP`), so the alternative would have been to invent
  one. This is the shape of CERT scenarios 3 and 4; **neither is present in r3.1**, whose two
  labelled insiders are scenarios 1 and 2, so this finding has no positive case on this corpus and
  may not be presented as a validated detector.

**Why "distant" and not "unrelated", and how that was decided.** The obvious cut is
`DeclaredRelation.ORG_UNRELATED` — the directory knows both people and places them nowhere near
each other. Measured against r3.1's actual directory, **that relation never occurs**: every one of
the 1,000 employees is in business unit ``1``, so the outermost container holds everybody and any
two colleagues share it. A finding built on ``ORG_UNRELATED`` would have been identically zero on
every entity-day, for a structural reason, and would have looked like a clean negative result
rather than an unaskable question. `DISTANT_HOPS` therefore cuts one level in, at "no closer than a
shared functional unit" — which is to say **outside your department**. The choice is made from the
directory's own shape and nothing else: ``department`` takes 22 distinct values and separates
people, ``business_unit`` takes one and separates nobody, and `phos.sentiel.graph.DeclaredGraph`
measures which is which. ``team`` was not used as the boundary because 159 of the 1,000 rows leave
it blank, so a team-based cut would silently reclassify a sixth of the organisation.

**The role-interaction policy is wired, and on CERT it refuses.**
`phos.sentiel.interaction.interaction_is_expected` has existed unused since Session S2. It is
called here, on every internal counterparty, and on CERT it returns ``None`` for every pair — the
release declares no policy about which roles may talk to which. `InteractionVerdict.INSUFFICIENT`
is that answer carried forward as insufficient evidence rather than as an anomaly, which is the
rule `UNDECLARED_INTERACTION_CAVEAT` states and which nothing had ever exercised end to end. A run
in which every verdict is ``INSUFFICIENT`` is this module working correctly, not failing.

**A long route is not automatically a suspicious one.** `RELATION_HOPS` gives a route length, and
`PathFindings.max_hops` reports the longest the day travelled — but on r3.1 the outermost
containment level is vacuous (every employee shares business unit ``1``), so the ladder has fewer
usable rungs than it appears to. `phos.sentiel.graph.GraphSummary.vacuous_levels` measures that,
and a report must carry it beside any hop count.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.graph import RELATION_HOPS, DeclaredGraph, DeclaredRelation
from phos.sentiel.interaction import DeclaredCounterpartyDirectory, interaction_is_expected
from phos.sentiel.traces import EntityDayTrace

__all__ = [
    "DISTANT_HOPS",
    "PATH_FEATURES",
    "PATH_NOT_VALIDATED_CAVEAT",
    "VACUOUS_TOP_LEVEL_FINDING",
    "DayDeviceIndex",
    "InteractionVerdict",
    "PathFindings",
    "device_index_for_day",
    "path_findings",
]

logger = logging.getLogger(__name__)

PATH_NOT_VALIDATED_CAVEAT: Final = (
    "PATH FINDINGS HAVE NO LABELLED POSITIVE ON CERT r3.1. The two labelled insiders are "
    "scenarios 1 and 2 — a user who begins working after hours and using removable drives, and a "
    "user who escalates thumb-drive use before leaving. Neither is a path scenario. The CERT "
    "scenarios that ARE path-shaped — 3 (a sysadmin plants a keylogger on his supervisor's "
    "machine and then logs in as him) and 4 (a user works from another user's machine) — appear "
    "in r4.2 and r5.2, whose event archives are not on disk. Anything measured here describes how "
    "often these findings FIRE, never how well they DETECT."
)

VACUOUS_TOP_LEVEL_FINDING: Final = (
    "r3.1's directory puts all 1,000 employees in business unit '1', so DeclaredRelation."
    "ORG_UNRELATED — the directory knows both people and places them nowhere near each other — "
    "NEVER OCCURS on this corpus. A path finding cut at that relation would read zero on every "
    "entity-day for a structural reason and would be mistaken for a measured negative. The cut is "
    "therefore DISTANT_HOPS, one level in, decided from the directory's own shape: department "
    "takes 22 distinct values, business unit takes one."
)

DISTANT_HOPS: Final = RELATION_HOPS[DeclaredRelation.SAME_FUNCTIONAL_UNIT]
"""Route length at which a counterparty counts as outside the actor's declared department.

Six — a shared functional unit and no closer. Derived from `phos.sentiel.graph.RELATION_HOPS`
rather than written as a literal, so the ladder and the cut cannot drift apart. Everything at or
above it (a shared functional unit, a shared business unit, no shared container at all) is
*distant*; a supervisor, a direct report, a teammate and a department colleague are not.

`DeclaredRelation.UNDECLARED` is deliberately **not** distant. An address the directory has never
heard of is an absence of a record, and `phos.sentiel.interaction` already states the rule that an
absence is insufficient rather than an alert. It is counted separately, as `undeclared_recipients`.
"""

PATH_FEATURES: Final[tuple[str, ...]] = (
    "distant_internal_recipients",
    "shared_device_distant",
    "max_declared_hops",
    "mean_declared_hops",
)
"""The path quantities an entity-day yields, in reporting order.

`undeclared_recipients` is **not** here: it duplicates `external_email_count`, and a feature set
that carried both would let one behaviour raise a score twice — the multiplicity PART 6B removed.
"""


class InteractionVerdict(str, Enum):
    """What a declared interaction policy says about a role pair.

    ``INSUFFICIENT`` is the answer on every corpus PHOS reads, because none of them ships a policy.
    It is a first-class member rather than a ``None`` so that a report can state how many pairs
    were unjudgeable instead of silently reporting zero anomalies.
    """

    EXPECTED = "EXPECTED"
    UNEXPECTED = "UNEXPECTED"
    INSUFFICIENT = "INSUFFICIENT"


class DayDeviceIndex(BaseModel):
    """Which users a machine carried on one day.

    One day's observed co-presence, and nothing more. This is **not** a claim about whose machine
    anything is: r3.1 declares no device owner, so there is nothing to claim. It exists so that
    "two declared-unrelated people used one machine today" can be stated as a fact about today.

    Attributes:
        day_users_by_pc: ``pc -> the user ids whose events named it that day``.
    """

    model_config = ConfigDict(frozen=True)

    day_users_by_pc: dict[str, frozenset[str]] = Field(default_factory=dict)

    def others_on(self, pc: str, user_id: str) -> frozenset[str]:
        """Return the other users this machine carried that day."""
        return frozenset(self.day_users_by_pc.get(pc, frozenset())) - {user_id}


def device_index_for_day(traces: Sequence[EntityDayTrace]) -> DayDeviceIndex:
    """Build the machine-to-users index for one day's traces.

    Args:
        traces: Every entity-day trace sharing one ``day``. A caller that mixes days would produce
            co-presence that never happened, so this is asserted rather than assumed.

    Returns:
        The index.

    Raises:
        ValueError: If the traces do not all share one day.
    """
    days = {trace.day for trace in traces}
    if len(days) > 1:
        raise ValueError(
            f"device_index_for_day was given {len(days)} distinct days; co-presence on a machine "
            "is a fact about ONE day and pooling days would invent it"
        )
    by_pc: dict[str, set[str]] = {}
    for trace in traces:
        for pc in trace.pcs:
            by_pc.setdefault(pc, set()).add(trace.user_id)
    return DayDeviceIndex(day_users_by_pc={pc: frozenset(users) for pc, users in by_pc.items()})


class PathFindings(BaseModel):
    """What one entity-day's activity did against the declared structure.

    Attributes:
        user_id: The actor.
        day: The window.
        internal_recipients: Mail recipients the directory owns.
        undeclared_recipients: Mail recipients it does not. Reported, then discounted — see
            `novel_beyond_counts`.
        distant_internal_recipients: Internal recipients the directory places outside the sender's
            department (`DISTANT_HOPS` or further). The finding no existing feature expresses.
        shared_device_distant: Machines this day that also carried a declared-distant colleague's
            activity.
        max_hops: Longest declared route length the day travelled, over internal recipients only.
            Zero when the day mailed no colleague.
        total_hops: Every internal recipient's route length summed, so a mean can be taken without
            keeping the recipients.
        relations: ``relation -> recipients``, so a finding can be opened rather than trusted.
        interaction_verdicts: ``verdict -> internal recipient pairs judged``. On CERT every pair
            lands in ``INSUFFICIENT``, which is the declared-policy module refusing correctly.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    day: object
    internal_recipients: int = Field(default=0, ge=0)
    undeclared_recipients: int = Field(default=0, ge=0)
    distant_internal_recipients: int = Field(default=0, ge=0)
    shared_device_distant: int = Field(default=0, ge=0)
    max_hops: int = Field(default=0, ge=0)
    total_hops: int = Field(default=0, ge=0)
    relations: dict[str, int] = Field(default_factory=dict)
    interaction_verdicts: dict[str, int] = Field(default_factory=dict)

    @property
    def mean_hops(self) -> float:
        """Average declared route length over the day's internal mail. Zero when it sent none."""
        if not self.internal_recipients:
            return 0.0
        return self.total_hops / self.internal_recipients

    @property
    def novel_beyond_counts(self) -> int:
        """How much of this day's path evidence PART 6B's feature set cannot already express.

        `undeclared_recipients` is excluded on purpose: `external_email_count` measures the same
        behaviour, and adding it here would let one act raise a score twice.
        """
        return self.distant_internal_recipients + self.shared_device_distant

    def values(self) -> dict[str, float]:
        """Return the `PATH_FEATURES`, ready to be judged like any other quantity."""
        return {
            "distant_internal_recipients": float(self.distant_internal_recipients),
            "shared_device_distant": float(self.shared_device_distant),
            "max_declared_hops": float(self.max_hops),
            "mean_declared_hops": self.mean_hops,
        }


def path_findings(
    trace: EntityDayTrace,
    graph: DeclaredGraph,
    devices: DayDeviceIndex,
    directory: DeclaredCounterpartyDirectory | None = None,
) -> PathFindings:
    """Judge one entity-day's routes against the declared structure.

    Args:
        trace: The entity-day. Its ``recipients`` and ``pcs`` are single-row facts, never profiles.
        graph: The declared graph. The only source of any judgement made here.
        devices: The machine-to-users index for **this trace's day**.
        directory: A declared role-interaction policy, when the corpus ships one. CERT ships none,
            so the default ``None`` is the honest case and yields `InteractionVerdict.INSUFFICIENT`
            for every pair.

    Returns:
        The findings.
    """
    policy = directory if directory is not None else DeclaredCounterpartyDirectory()
    actor_role = graph.role_of(trace.user_id)

    relations: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    internal = 0
    undeclared = 0
    distant = 0
    max_hops = 0
    total_hops = 0

    for address in trace.recipients:
        owner = graph.owner_of(address)
        if owner is None:
            undeclared += 1
            continue
        internal += 1
        relation = graph.relation_between(trace.user_id, owner)
        relations[relation.value] = relations.get(relation.value, 0) + 1
        hops = graph.hops_between(trace.user_id, owner)
        max_hops = max(max_hops, hops)
        total_hops += hops
        if relation is not DeclaredRelation.UNDECLARED and hops >= DISTANT_HOPS:
            distant += 1
        verdict = _verdict(policy, actor_role, graph.role_of(owner))
        verdicts[verdict.value] = verdicts.get(verdict.value, 0) + 1

    shared = 0
    for pc in trace.pcs:
        others = devices.others_on(pc, trace.user_id)
        if any(_is_distant(graph, trace.user_id, other) for other in others):
            shared += 1

    return PathFindings(
        user_id=trace.user_id,
        day=trace.day,
        internal_recipients=internal,
        undeclared_recipients=undeclared,
        distant_internal_recipients=distant,
        shared_device_distant=shared,
        max_hops=max_hops,
        total_hops=total_hops,
        relations=relations,
        interaction_verdicts=verdicts,
    )


def _is_distant(graph: DeclaredGraph, one: str, other: str) -> bool:
    """Return whether the directory places two people outside each other's department.

    An undeclared counterparty is **not** distant: it is unjudgeable, which is a different claim.
    """
    relation = graph.relation_between(one, other)
    if relation is DeclaredRelation.UNDECLARED:
        return False
    return RELATION_HOPS[relation] >= DISTANT_HOPS


def _verdict(
    policy: DeclaredCounterpartyDirectory, actor_role: str | None, other_role: str | None
) -> InteractionVerdict:
    """Return what a declared interaction policy says, or that it says nothing.

    This is the call `phos.sentiel.interaction` was written for and never received. A missing role
    on either side, or a role the policy does not name, is `InteractionVerdict.INSUFFICIENT` — the
    absence of a declaration, never an anomaly.
    """
    if actor_role is None or other_role is None:
        return InteractionVerdict.INSUFFICIENT
    expected = interaction_is_expected(policy, actor_role, other_role)
    if expected is None:
        return InteractionVerdict.INSUFFICIENT
    return InteractionVerdict.EXPECTED if expected else InteractionVerdict.UNEXPECTED


def summarise_verdicts(findings: Sequence[PathFindings]) -> Mapping[str, int]:
    """Pool the interaction verdicts across a run, so 'the policy never spoke' is visible."""
    pooled: dict[str, int] = {}
    for finding in findings:
        for verdict, count in finding.interaction_verdicts.items():
            pooled[verdict] = pooled.get(verdict, 0) + count
    return pooled
