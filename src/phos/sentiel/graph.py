"""The relationship structure the directory *declares*, and nothing the behaviour implies.

Sentiel has never had a structure to reason over. `phos.sentiel.peers` reads one attribute off the
directory to make peer groups and stops there; the four `RELATIONSHIP_FEATURES` count new machines
and new counterparties without knowing what any of them *are*. This module builds the org chart the
corpus actually ships — users, the accounts they own, their roles, the units that contain them, and
who reports to whom — so that "did this activity go somewhere this person has no declared
relationship to?" becomes a question with an answer.

**The one rule that makes it worth having: an edge is declared or it does not exist.** Every edge
here comes from a row of `LDAP/*.csv`. None comes from an event, a count, a co-occurrence or a
history. That is not fastidiousness; it is the difference between a measurement and a tautology.
A graph inferred from behaviour defines *normal* using the very anomaly being hunted — put the
people who exfiltrate together and exfiltration becomes their neighbourhood's normal — which is
exactly the circularity ADR 0010 refused for Atlas's topology and ADR 0022 refused for peer groups.
The refusal is enforced by construction, on `phos.sentiel.PeerGroups`' pattern: **there is no
method on this class that accepts an `Observation`, an `EnterpriseEvent` or an
`phos.sentiel.EntityDayTrace`**, so no amount of activity can move anybody.

**What r3.1 declares, and what it conspicuously does not.** The directory carries ``role``,
``business_unit``, ``functional_unit``, ``department``, ``team``, ``supervisor`` and ``email``. It
carries **nothing about devices and nothing about files or hosts**: no row anywhere in the release
says which machine belongs to which person, and ``psychometric.csv`` is five personality scores.
`UNDECLARED_DEVICE_OWNERSHIP` records that as a finding rather than leaving it to be discovered.
The consequence is concrete and limiting: a user-to-device or user-to-resource edge **cannot** be
built from this corpus without inferring it from activity, so this graph has no such edge, and
`phos.sentiel.paths` may not ask a path question that needs one.

**Containment is read off the directory's own column order, not invented.** r3.1 spells its units
``1``, ``5 - SalesAndMarketing``, ``3 - FieldService``, ``3 - RegionalFieldService`` — a business
unit containing functional units containing departments containing teams. `ORG_LEVELS` is that
nesting, outermost first, and `relation_between` reports the **narrowest shared container** of two
people. On r3.1 the outermost level is vacuous: every employee is in business unit ``1``, so
`DeclaredRelation.SAME_BUSINESS_UNIT` means "a colleague" and separates nobody.
`GraphSummary.vacuous_levels` says which levels are like that, measured rather than assumed, so a
path finding built on one can be discounted by a reader who never opened the corpus.

**Supervisors are declared by name and resolved through the same file.** The ``supervisor`` column
holds an ``employee_name``, not a ``user_id``, so the edge exists only once that name is matched
against the directory's own ``employee_name`` column. A name matching two employees is left
unresolved and counted, because guessing which colleague someone reports to would fabricate exactly
the kind of edge this module exists to refuse.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology import Entity
from phos.sentiel.entities import ABSENT_FROM_DIRECTORY, DIRECTORY_RECORD_ATTRIBUTE, EntityCatalogue

__all__ = [
    "ORG_LEVELS",
    "RELATION_HOPS",
    "UNDECLARED_DEVICE_OWNERSHIP",
    "UNDECLARED_RESOURCE_OWNERSHIP",
    "DeclaredGraph",
    "DeclaredRelation",
    "GraphSummary",
]

logger = logging.getLogger(__name__)

UNDECLARED_DEVICE_OWNERSHIP: Final = (
    "CERT r3.1 DECLARES NO USER-TO-DEVICE RELATIONSHIP. The LDAP directory carries role, unit, "
    "supervisor and email and nothing about machines; psychometric.csv carries five personality "
    "scores. Every user-device pair in the release exists only in the activity logs, so any "
    "'this person has no relationship to that machine' edge would be inferred from behaviour — "
    "the circularity this graph refuses. No such edge is built, and no path finding rests on one."
)

UNDECLARED_RESOURCE_OWNERSHIP: Final = (
    "CERT r3.1 DECLARES NO OWNER FOR ANY FILE OR WEB HOST. Filenames and hosts appear only as "
    "fields of activity rows. A 'resource this person should not reach' claim would therefore be "
    "a claim about what they have reached before, which is the self-baseline PART 6A already "
    "measures, not a statement about declared structure."
)

ORG_LEVELS: Final[tuple[str, ...]] = (
    "business_unit",
    "functional_unit",
    "department",
    "team",
)
"""The directory's containment hierarchy, outermost first.

Read off r3.1's own column set and its own values, which nest exactly this way. Ordering matters:
`relation_between` reports the **narrowest** shared container, so a pair sharing a team is reported
as sharing a team rather than as sharing a business unit.
"""


class DeclaredRelation(str, Enum):
    """What the directory says two people are to each other.

    Ordered narrowest first in `RELATION_HOPS`. ``UNDECLARED`` is not a weak relationship; it is
    the absence of a record, and `phos.sentiel.paths` must treat it as insufficient rather than as
    an anomaly — the rule `phos.sentiel.interaction` already states for interaction structure.
    """

    SELF = "SELF"
    SUPERVISOR = "SUPERVISOR"
    DIRECT_REPORT = "DIRECT_REPORT"
    SAME_TEAM = "SAME_TEAM"
    SAME_DEPARTMENT = "SAME_DEPARTMENT"
    SAME_FUNCTIONAL_UNIT = "SAME_FUNCTIONAL_UNIT"
    SAME_BUSINESS_UNIT = "SAME_BUSINESS_UNIT"
    ORG_UNRELATED = "ORG_UNRELATED"
    UNDECLARED = "UNDECLARED"


RELATION_HOPS: Final[Mapping[DeclaredRelation, int]] = {
    DeclaredRelation.SELF: 0,
    DeclaredRelation.SUPERVISOR: 1,
    DeclaredRelation.DIRECT_REPORT: 1,
    DeclaredRelation.SAME_TEAM: 2,
    DeclaredRelation.SAME_DEPARTMENT: 4,
    DeclaredRelation.SAME_FUNCTIONAL_UNIT: 6,
    DeclaredRelation.SAME_BUSINESS_UNIT: 8,
    DeclaredRelation.ORG_UNRELATED: 10,
    DeclaredRelation.UNDECLARED: 10,
}
"""Route length between two user nodes, in declared edges traversed.

A shared container at depth *d* is reached by walking *d* edges up from one person and *d* back
down to the other, so a shared team is 2 and a shared department 4 — each level of the hierarchy
costs one edge each way. A reporting line is a single edge and therefore 1, which is the point of
including it: a supervisor is *closer* than a teammate in the structure the directory declares,
even when the two sit in different departments.

``ORG_UNRELATED`` and ``UNDECLARED`` share a length because neither has a route. They are kept
apart as *relations* because they are different claims — "the directory knows this person and
places them nowhere near you" against "the directory has never heard of this address" — and
`phos.sentiel.paths` treats them differently for exactly that reason.
"""


class GraphSummary(BaseModel):
    """What the directory actually supported, so a reader can judge the structure it produced.

    Attributes:
        users: Directory rows read.
        accounts: Distinct email addresses the directory declares.
        supervisor_edges: Reporting lines resolved from a name to a user.
        unresolved_supervisors: Rows naming a supervisor no unique employee matches. Counted, never
            guessed at.
        rootless_users: Rows naming no supervisor at all.
        level_sizes: ``level -> distinct declared values``. A level with one value places nobody.
        vacuous_levels: Levels holding a single value across the whole directory, so membership of
            them separates nobody. On r3.1 this is expected to be ``business_unit``.
        blank_levels: ``level -> rows leaving it empty``.
    """

    model_config = ConfigDict(frozen=True)

    users: int = Field(default=0, ge=0)
    accounts: int = Field(default=0, ge=0)
    supervisor_edges: int = Field(default=0, ge=0)
    unresolved_supervisors: int = Field(default=0, ge=0)
    rootless_users: int = Field(default=0, ge=0)
    level_sizes: dict[str, int] = Field(default_factory=dict)
    vacuous_levels: tuple[str, ...] = ()
    blank_levels: dict[str, int] = Field(default_factory=dict)

    def note(self) -> str:
        """Return the one line a report carries so the graph's limits travel with its findings."""
        sizes = ", ".join(f"{level}={self.level_sizes.get(level, 0)}" for level in ORG_LEVELS)
        vacuous = ", ".join(self.vacuous_levels) or "none"
        return (
            f"DECLARED GRAPH: {self.users:,} users, {self.accounts:,} accounts, "
            f"{self.supervisor_edges:,} reporting lines ({self.unresolved_supervisors:,} "
            f"unresolvable, {self.rootless_users:,} rootless). Distinct values per level: "
            f"{sizes}. Levels that separate nobody: {vacuous}. No user-device or user-resource "
            f"edge exists — the directory declares none."
        )


class DeclaredGraph(BaseModel):
    """Every relationship CERT's directory states, and no relationship it does not.

    Frozen, and derived only from an `EntityCatalogue`. There is deliberately no method that takes
    behaviour of any kind: that is what makes "declared, not inferred" a property of the type
    rather than a promise in a docstring.

    Attributes:
        roles: ``user_id -> declared role``.
        levels: ``level -> {user_id: declared value}`` for each of `ORG_LEVELS`. A user missing
            from a level's mapping left that column blank.
        supervisor_of: ``user_id -> supervisor's user_id``, resolved by name.
        accounts: ``lowercased email address -> user_id``.
        summary: What the directory supported.
    """

    model_config = ConfigDict(frozen=True)

    roles: dict[str, str] = Field(default_factory=dict)
    levels: dict[str, dict[str, str]] = Field(default_factory=dict)
    supervisor_of: dict[str, str] = Field(default_factory=dict)
    accounts: dict[str, str] = Field(default_factory=dict)
    summary: GraphSummary = GraphSummary()

    @classmethod
    def from_catalogue(cls, catalogue: EntityCatalogue) -> Self:
        """Build the declared graph from a directory, resolving reporting lines by name.

        Args:
            catalogue: The directory, as `EntityCatalogue.from_ldap_directory` read it. Entities
                marked absent from the directory are skipped: a synthesised entity carries no
                declared attribute, and inventing structure for it would be the opposite of this
                module's purpose.

        Returns:
            The graph, carrying a `GraphSummary` of what the directory actually supported.
        """
        declared = {
            user_id: entity
            for user_id, entity in catalogue.entities.items()
            if entity.attributes.get(DIRECTORY_RECORD_ATTRIBUTE) != ABSENT_FROM_DIRECTORY
        }
        roles = {
            user_id: role
            for user_id, entity in declared.items()
            if (role := entity.attributes.get("role", "").strip())
        }
        levels: dict[str, dict[str, str]] = {}
        blank: dict[str, int] = {}
        for level in ORG_LEVELS:
            values = {
                user_id: value
                for user_id, entity in declared.items()
                if (value := entity.attributes.get(level, "").strip())
            }
            levels[level] = values
            blank[level] = len(declared) - len(values)

        accounts = {
            address.lower(): user_id
            for user_id, entity in declared.items()
            if (address := entity.attributes.get("email", "").strip())
        }
        supervisors, unresolved, rootless = _resolve_supervisors(declared)

        level_sizes = {level: len(set(values.values())) for level, values in levels.items()}
        summary = GraphSummary(
            users=len(declared),
            accounts=len(accounts),
            supervisor_edges=len(supervisors),
            unresolved_supervisors=unresolved,
            rootless_users=rootless,
            level_sizes=level_sizes,
            vacuous_levels=tuple(level for level in ORG_LEVELS if level_sizes.get(level, 0) <= 1),
            blank_levels=blank,
        )
        logger.info("%s", summary.note())
        return cls(
            roles=roles,
            levels=levels,
            supervisor_of=supervisors,
            accounts=accounts,
            summary=summary,
        )

    def knows(self, user_id: str) -> bool:
        """Return whether the directory declares anything at all about ``user_id``."""
        return user_id in self.roles or any(user_id in values for values in self.levels.values())

    def owner_of(self, address: str) -> str | None:
        """Return the user who owns an email address, or ``None`` if the directory declares none.

        ``None`` is the honest answer for every address outside the organisation, and it is what
        makes an external counterparty *undeclared* rather than *unrelated*.
        """
        return self.accounts.get(address.strip().lower())

    def role_of(self, user_id: str) -> str | None:
        """Return the declared role, or ``None``."""
        return self.roles.get(user_id)

    def relation_between(self, one: str, other: str) -> DeclaredRelation:
        """Return what the directory says these two people are to each other.

        Reporting lines are checked before containment, because a reporting line is a single
        declared edge and a shared container is two or more — so a supervisor in another
        department is correctly reported as a supervisor rather than as a distant colleague.

        Args:
            one: The acting user.
            other: The counterparty.

        Returns:
            The narrowest declared relation, or `DeclaredRelation.UNDECLARED` when the directory
            does not know one of them.
        """
        if one == other:
            return DeclaredRelation.SELF
        if not self.knows(one) or not self.knows(other):
            return DeclaredRelation.UNDECLARED
        if self.supervisor_of.get(one) == other:
            return DeclaredRelation.SUPERVISOR
        if self.supervisor_of.get(other) == one:
            return DeclaredRelation.DIRECT_REPORT
        for level, relation in reversed(list(zip(ORG_LEVELS, _LEVEL_RELATIONS, strict=True))):
            values = self.levels.get(level, {})
            mine = values.get(one)
            theirs = values.get(other)
            if mine is not None and mine == theirs:
                return relation
        return DeclaredRelation.ORG_UNRELATED

    def hops_between(self, one: str, other: str) -> int:
        """Return the declared route length between two people, per `RELATION_HOPS`."""
        return RELATION_HOPS[self.relation_between(one, other)]

    def separates(self, level: str) -> bool:
        """Return whether a level's declared values distinguish anybody on this corpus.

        A level holding one value across the whole directory places every employee together, so a
        finding that rests on it says nothing. Measured off the directory rather than assumed.
        """
        return self.summary.level_sizes.get(level, 0) > 1


_LEVEL_RELATIONS: Final[tuple[DeclaredRelation, ...]] = (
    DeclaredRelation.SAME_BUSINESS_UNIT,
    DeclaredRelation.SAME_FUNCTIONAL_UNIT,
    DeclaredRelation.SAME_DEPARTMENT,
    DeclaredRelation.SAME_TEAM,
)
"""The relation each of `ORG_LEVELS` produces, in the same order."""


def _resolve_supervisors(declared: Mapping[str, Entity]) -> tuple[dict[str, str], int, int]:
    """Resolve the ``supervisor`` name column against the directory's own ``employee_name``.

    Returns:
        ``(supervisor_of, unresolved, rootless)``. A name matching no employee or more than one is
        left out and counted: a reporting line is a declared fact, and a guessed one would be
        precisely the fabricated edge this module refuses.
    """
    by_name: dict[str, list[str]] = {}
    for user_id, entity in declared.items():
        name = entity.attributes.get("employee_name", "").strip()
        if name:
            by_name.setdefault(name, []).append(user_id)

    supervisor_of: dict[str, str] = {}
    unresolved = 0
    rootless = 0
    for user_id, entity in declared.items():
        name = entity.attributes.get("supervisor", "").strip()
        if not name:
            rootless += 1
            continue
        matches = by_name.get(name, [])
        if len(matches) != 1 or matches[0] == user_id:
            unresolved += 1
            continue
        supervisor_of[user_id] = matches[0]
    if unresolved:
        logger.info(
            "%d directory row(s) name a supervisor that matches no unique employee; left "
            "unresolved rather than guessed",
            unresolved,
        )
    return supervisor_of, unresolved, rootless
