"""Peer groups: who this user is supposed to behave like, and how far from them they sit.

PART 6A asked one question about a user — *is this unlike them?* — and answered it from that user's
own trailing history. It cannot ask the other one. An account quietly operating at a level its own
history fully supports, but that its whole team never approaches, is unremarkable to every feature
in `phos.sentiel.history` and is exactly the insider this module exists to find.

The baseline here is therefore a **distribution across people**, not across time-and-one-person: for
a feature and a window, the values that the entity's peers produced. The deviation is where the
entity sits in that distribution, in the peers' own units of spread.

Four commitments hold, and the tests are written to break an implementation that loses any of them.

- **Groups are declared, never inferred.** A peer group is a value of one `EntityCatalogue`
  attribute — by default the user's ``role``. Nothing here clusters users by behaviour. A
  behaviourally-derived group would define "normal" using the very anomaly being hunted: put the
  three users who exfiltrate data together and their exfiltration becomes their group's normal.
  Atlas refused the same circularity for topology (ADR 0010) and this refuses it for people.
- **Causality, on 6A's terms exactly.** A peer baseline read for window *t* pools only windows
  strictly before *t*. `PeerHistory.deviation` is pure; `PeerHistory.observe` is the only mutator
  and takes a **whole completed window at once**, so no user in a window can appear in the pool
  another user of that same window is judged against.
- **A user's own past is left out of their own peer baseline.** The pool is leave-one-out. Without
  it the peer feature would be part self-baseline, collinear with 6A's ``_dev`` family, and the
  multiplicity cost of the extra features would buy a question already answered.
- **Too few peers means no feature, not a fabricated one.** Below `PeerPolicy.min_group_size` there
  is no peer distribution to speak of, and unknown is not anomalous.

The two absences are different and are kept different, because they are different claims:

- **No group attribute, or a group below the minimum size** — *no observation at all*. The feature
  does not exist for this entity, and it never will while the directory says what it says.
- **A real group whose trailing pool cannot speak yet** — `NEUTRAL_VALUE`. The feature exists and
  has nothing to say *yet*, which is 6A's cold-start policy applied unchanged one level out.
"""

import logging
import math
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.history import NEUTRAL_VALUE, HistoryPolicy

__all__ = [
    "DEFAULT_GROUP_ATTRIBUTE",
    "PeerGroups",
    "PeerHistory",
    "PeerPolicy",
]

logger = logging.getLogger(__name__)

DEFAULT_GROUP_ATTRIBUTE: Final = "role"
"""The `EntityCatalogue` attribute a peer group is cut from by default.

**Role, because a peer group is meant to be people who should behave alike, and what determines
how somebody uses a computer is the job they do.** A salesperson mails outside the organisation all
day and an electrical engineer does not; a night-shift technician logs on at 03:00 and an
accountant does not. Neither fact is predicted by who signs their timesheet or which division pays
them.

The alternatives on a CERT release are real and are the seam `PeerPolicy.group_attribute` exists
for: ``department`` and ``team`` are organisational rather than functional, ``supervisor`` is a
reporting line, and ``business_unit`` on r3.1 holds a single value for the entire company — a group
of everybody, which is a population baseline and not a peer baseline at all. See ADR 0022 for the
coverage each attribute gives on r3.1 and why role won.
"""


class PeerPolicy(BaseModel):
    """Which declared attribute makes a peer group, and how small a group may be and still count.

    Attributes:
        group_attribute: The `phos.ontology.Entity.attributes` key whose value names the group.
            Defaults to `DEFAULT_GROUP_ATTRIBUTE`.
        min_group_size: Fewest **declared members** a group may have before its members get peer
            features at all. Five by default, so a leave-one-out baseline rests on at least four
            other people.

            Five is a judgement and is stated as one rather than dressed up. It is deliberately
            *not* PHOS's existing answer to "how many points before you may claim a baseline"
            (eight — `phos.models.BehaviouralModel.min_samples` and
            `HistoryPolicy.min_history_windows`), because that question is about **sample count**
            and this one is about **distinct people**. The pool's sample count is members times
            populated windows and passes eight almost immediately; what eight cannot tell you is
            whether "the group's normal" is really one idiosyncratic colleague. Below four peers a
            single member is more than a quarter of the spread being divided by, so the sample
            count is gated at `HistoryPolicy.min_history_windows` — PHOS's one answer, reused — and
            the *person* count is gated here.

    Invariants:
        ``min_group_size >= 2``, since a group of one has no peers at all, and
        ``group_attribute`` is non-empty.
    """

    model_config = ConfigDict(frozen=True)

    group_attribute: str = DEFAULT_GROUP_ATTRIBUTE
    min_group_size: int = Field(default=5, ge=2)

    @field_validator("group_attribute")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        """Reject an unnamed attribute, which would group every user under ``""``."""
        if not value.strip():
            raise ValueError("group_attribute must name an Entity.attributes key")
        return value.strip()


class PeerGroups(BaseModel):
    """Every user's declared peer group, read once from the catalogue and then never revised.

    Frozen and derived only from `EntityCatalogue`, which is what makes "declared, not inferred" a
    property of the type rather than a promise in a docstring: there is no method here that takes
    an `phos.ontology.Observation`, so no amount of behaviour can move anybody between groups.

    Attributes:
        group_attribute: The attribute the groups were cut from.
        min_group_size: The minimum declared size that was applied.
        membership: ``user_id -> group name``, holding **only** users whose group cleared
            `min_group_size`. A user absent from this mapping has no peer features.
        declared_sizes: ``group name -> declared member count``, for **every** group including the
            ones too small to use. Kept so a report can say how much of the population the grouping
            actually covers, rather than only describing the part that worked.
        ungrouped: How many catalogued users ended with no usable group, for the same reason.
    """

    model_config = ConfigDict(frozen=True)

    group_attribute: str
    min_group_size: int = Field(ge=2)
    membership: Mapping[str, str] = Field(default_factory=dict)
    declared_sizes: Mapping[str, int] = Field(default_factory=dict)
    ungrouped: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _membership_respects_the_minimum(self) -> Self:
        """Reject a membership naming a group too small to have one.

        `from_catalogue` applies the minimum, but a `PeerGroups` built directly — in a test, or by
        a later PART with its own source of groups — could otherwise carry a membership the size
        gate would have refused, and `PeerHistory` would then use ``min_group_size - 1`` as a peer
        floor that the group can never reach. Making it an invariant of the type is what stops that
        being a possible state at all.
        """
        for user_id, group in self.membership.items():
            size = self.declared_sizes.get(group)
            if size is None:
                raise ValueError(
                    f"user {user_id} is in group {group!r}, which declared_sizes does not name"
                )
            if size < self.min_group_size:
                raise ValueError(
                    f"user {user_id} is in group {group!r}, which has {size} declared member(s) "
                    f"and the minimum is {self.min_group_size}"
                )
        return self

    @classmethod
    def from_catalogue(cls, catalogue: EntityCatalogue, policy: PeerPolicy | None = None) -> Self:
        """Cut ``catalogue`` into peer groups on one declared attribute.

        Args:
            catalogue: The organisation's directory, as read from the corpus.
            policy: Which attribute and what minimum size. Defaults to `PeerPolicy`.

        Returns:
            The groups. A user whose entity carries no value for the attribute, or whose group has
            fewer than `PeerPolicy.min_group_size` declared members, is left out of `membership`
            and counted in `ungrouped`.

        Raises:
            ValueError: If **no** catalogued entity carries the attribute. That configuration
                would emit a peer feature for nobody, forever, and say nothing about it — the same
                silent-and-permanent failure `HistoryPolicy` rejects at construction.
        """
        settings = policy or PeerPolicy()
        assigned: dict[str, str] = {}
        for user_id, entity in catalogue.entities.items():
            group = entity.attributes.get(settings.group_attribute, "").strip()
            if group:
                assigned[user_id] = group

        if not assigned:
            known = sorted(
                {key for entity in catalogue.entities.values() for key in entity.attributes}
            )
            raise ValueError(
                f"no catalogued user carries the attribute {settings.group_attribute!r}, so every "
                "peer feature would be absent for every user forever. The directory offers: "
                f"{', '.join(known) or '(nothing)'}"
            )

        sizes: dict[str, int] = {}
        for group in assigned.values():
            sizes[group] = sizes.get(group, 0) + 1

        membership = {
            user_id: group
            for user_id, group in assigned.items()
            if sizes[group] >= settings.min_group_size
        }
        logger.info(
            "peer groups on %r: %d of %d groups reach %d members, covering %d of %d users",
            settings.group_attribute,
            sum(1 for size in sizes.values() if size >= settings.min_group_size),
            len(sizes),
            settings.min_group_size,
            len(membership),
            len(catalogue.entities),
        )
        return cls(
            group_attribute=settings.group_attribute,
            min_group_size=settings.min_group_size,
            membership=membership,
            declared_sizes=dict(sorted(sizes.items())),
            ungrouped=len(catalogue.entities) - len(membership),
        )

    @property
    def min_peers(self) -> int:
        """Fewest *other* members a pool must draw on before it may speak.

        One fewer than `PeerPolicy.min_group_size`, because the pool is leave-one-out: the entity
        being judged is never in the distribution it is judged against.
        """
        return self.min_group_size - 1

    def group_of(self, user_id: str) -> str | None:
        """Return the user's usable peer group, or ``None`` if they have none.

        ``None`` is the structural answer and the caller must emit **no peer observation** for it:
        the user is absent from the directory, carries no value for the grouping attribute, or
        belongs to a group too small to have a distribution. None of those is evidence of anything.
        """
        return self.membership.get(user_id)

    @property
    def usable_groups(self) -> int:
        """How many groups cleared `min_group_size`."""
        return sum(1 for size in self.declared_sizes.values() if size >= self.min_group_size)

    def summary(self) -> str:
        """Return the one line a report carries so its grouping can be judged, not assumed."""
        sizes = sorted(size for size in self.declared_sizes.values() if size >= self.min_group_size)
        span = f"{sizes[0]}-{sizes[-1]}" if sizes else "none"
        return (
            f"peer groups by {self.group_attribute}: {self.usable_groups} of "
            f"{len(self.declared_sizes)} groups reach the {self.min_group_size}-member minimum "
            f"(sizes {span}), covering {len(self.membership)} users; {self.ungrouped} ungrouped "
            "and emitting no peer feature"
        )


class _MemberTotals:
    """One member's running contribution to a pool, so it can be subtracted back out."""

    __slots__ = ("count", "total", "total_sq")

    def __init__(self, width: int) -> None:
        self.count = 0
        self.total = [0.0] * width
        self.total_sq = [0.0] * width


class _GroupPool:
    """One group's trailing pooled values, per feature, with per-member totals held apart.

    Totals are maintained incrementally — added when a window is pushed, subtracted when it falls
    out of the window — rather than recomputed, because the read happens once per member per
    feature per window and the update once per window.

    The pooled features are **integer counts**, so the running sums and sums of squares are exact
    in float64 for any realistic corpus and the usual catastrophic-cancellation worry about a
    ``E[x^2] - E[x]^2`` variance does not arise: a perfectly constant group yields exactly zero
    rather than a small positive number that would read as an enormous z-score. The
    ``max(0.0, ...)`` guard in `leave_one_out` is belt and braces for a caller that pools something
    else.
    """

    __slots__ = ("_limit", "_members", "_width", "_windows", "count", "total", "total_sq")

    def __init__(self, width: int, limit: int) -> None:
        self._width = width
        self._limit = limit
        self._windows: deque[dict[str, tuple[float, ...]]] = deque()
        self._members: dict[str, _MemberTotals] = {}
        self.count = 0
        self.total = [0.0] * width
        self.total_sq = [0.0] * width

    def push(self, window: Mapping[str, Sequence[float]]) -> None:
        """Fold one completed window into the pool, evicting the oldest if the memory is full."""
        if len(self._windows) == self._limit:
            for user_id, values in self._windows.popleft().items():
                member = self._members[user_id]
                member.count -= 1
                self.count -= 1
                for index, value in enumerate(values):
                    member.total[index] -= value
                    member.total_sq[index] -= value * value
                    self.total[index] -= value
                    self.total_sq[index] -= value * value
                if member.count == 0:
                    del self._members[user_id]

        frozen = {user_id: tuple(values) for user_id, values in window.items()}
        self._windows.append(frozen)
        for user_id, values in frozen.items():
            totals = self._members.get(user_id)
            if totals is None:
                totals = _MemberTotals(self._width)
                self._members[user_id] = totals
            totals.count += 1
            self.count += 1
            for index, value in enumerate(values):
                totals.total[index] += value
                totals.total_sq[index] += value * value
                self.total[index] += value
                self.total_sq[index] += value * value

    def leave_one_out(self, user_id: str, index: int) -> tuple[int, int, float, float]:
        """Return ``(samples, distinct peers, mean, stddev)`` for one feature, excluding a member.

        Excluding the member is what makes this a question about *other* people. With the member
        left in, the answer would be part self-baseline and would duplicate the ``_dev`` family
        `phos.sentiel.history` already provides.
        """
        member = self._members.get(user_id)
        samples = self.count - (member.count if member is not None else 0)
        peers = len(self._members) - (1 if member is not None else 0)
        if samples <= 0:
            return (0, peers, 0.0, 0.0)
        total = self.total[index] - (member.total[index] if member is not None else 0.0)
        total_sq = self.total_sq[index] - (member.total_sq[index] if member is not None else 0.0)
        mean = total / samples
        variance = max(0.0, total_sq / samples - mean * mean)
        return (samples, peers, mean, math.sqrt(variance))


class PeerHistory:
    """What this user's peers were recently doing — the mechanism behind every peer feature.

    Mutable run state, not a value in the ontology, and deliberately not a Pydantic model for the
    same reason `phos.sentiel.history.TrailingHistory` is not: it is written once per window over
    hundreds of thousands of windows. It is created inside the call that uses it and never shared,
    so there is no global mutable state (Constitution §6).

    `deviation` is pure with respect to this object. `observe` is the only mutator, and it takes a
    **whole window at once** — that signature *is* the causality guarantee. A per-user ``observe``
    would let the first user of a window into the pool that judges the second user of the same
    window, which is a leak that produces no error and no absurd number: it would quietly drag the
    peer mean toward the very cohort being judged.

    Attributes:
        groups: The declared peer groups. Read-only here; nothing in this class can change them.
        policy: The trailing-window length, cold-start minimum and cap, shared with
            `phos.sentiel.history` so PHOS gives one answer to each of those questions.
        features: The features pooled, in order.
    """

    __slots__ = ("_index", "_pools", "features", "groups", "policy")

    def __init__(
        self,
        groups: PeerGroups,
        features: Sequence[str],
        policy: HistoryPolicy | None = None,
    ) -> None:
        """Create an empty peer history.

        Args:
            groups: The declared groups, already cut from the catalogue.
            features: The features to pool, in the order `observe` will be given their values.
            policy: Window length, cold-start minimum and deviation cap. Defaults to
                `HistoryPolicy`, the same defaults 6A's per-entity history uses.

        Raises:
            ValueError: If ``features`` is empty or names a feature twice.
        """
        ordered = tuple(features)
        if not ordered:
            raise ValueError("a peer history must pool at least one feature")
        if len(set(ordered)) != len(ordered):
            raise ValueError(f"peer history features contain duplicates: {ordered}")
        self.groups = groups
        self.policy = policy or HistoryPolicy()
        self.features = ordered
        self._index = {feature: position for position, feature in enumerate(ordered)}
        self._pools: dict[str, _GroupPool] = {}

    def deviation(self, user_id: str, feature: str, value: float) -> float | None:
        """Return ``value`` as a signed z-score against this user's peers, excluding themselves.

        Args:
            user_id: The corpus's own identifier for the user.
            feature: A pooled feature.
            value: The current window's value, which is **not** in the pool it is judged against.

        Returns:
            ``None`` when the user has no usable peer group — the caller must then emit no
            observation, because the feature does not exist for this person. Otherwise a signed,
            capped z-score against the peers' trailing distribution, with the same three documented
            special cases `phos.sentiel.history.TrailingHistory.deviation` uses:

            - A pool drawing on fewer than `PeerPolicy.min_peers` other members, or holding fewer
              than `HistoryPolicy.min_history_windows` samples: `NEUTRAL_VALUE`. The group exists;
              its pool cannot speak yet.
            - Peers who have never varied and a ``value`` equal to their mean: ``0.0``.
            - Peers who have never varied and any other value: the cap, signed.

        Raises:
            KeyError: If ``feature`` is not one this history pools. Returning a neutral would
                report a configuration mistake as a measurement.
        """
        group = self.groups.group_of(user_id)
        if group is None:
            return None
        index = self._index[feature]
        pool = self._pools.get(group)
        if pool is None:
            return NEUTRAL_VALUE
        samples, peers, mean, stddev = pool.leave_one_out(user_id, index)
        if peers < self.groups.min_peers or samples < self.policy.min_history_windows:
            return NEUTRAL_VALUE
        cap = self.policy.deviation_cap
        if stddev == 0.0:
            return 0.0 if value == mean else math.copysign(cap, value - mean)
        return max(-cap, min(cap, (value - mean) / stddev))

    def observe(self, window: Mapping[str, Sequence[float]]) -> None:
        """Fold one **completed window** into the pools, after every user in it has been emitted.

        Args:
            window: ``user_id -> that user's values, in `features` order`` for the window that has
                just been emitted. Users with no usable peer group are ignored; pooling them would
                put a person into a distribution nobody is judged against.

        Raises:
            ValueError: If a user's values are not the width this history pools, which would
                silently attribute one feature's value to another.
        """
        by_group: dict[str, dict[str, Sequence[float]]] = {}
        for user_id, values in window.items():
            if len(values) != len(self.features):
                raise ValueError(
                    f"peer history pools {len(self.features)} feature(s) {self.features} but was "
                    f"given {len(values)} value(s) for user {user_id}"
                )
            group = self.groups.group_of(user_id)
            if group is None:
                continue
            by_group.setdefault(group, {})[user_id] = values

        for group, members in by_group.items():
            pool = self._pools.get(group)
            if pool is None:
                pool = _GroupPool(len(self.features), self.policy.trailing_windows)
                self._pools[group] = pool
            pool.push(members)
