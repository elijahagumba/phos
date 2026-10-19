"""Which hosts, destinations and machines a person touched, by declared name.

This is not ``phos.sentiel.identity``. That module scores the Clock B layers and
leaves the peer slot empty. Peer-group advantage stays retired.

The 34 features in ``phos.sentiel.featurise.PEER_FEATURES`` count how many distinct
machines, recipients and web hosts a person touched. They stay that way. This module
does not edit them, does not weight them, and does not feed them into Bet 001.

What it adds is a separate observation stream. A caller supplies a register of names
before any score. On each active day the stream reports how many of those names
appeared, which ones they were, and — once the user's own history can support the
claim — which of them were new for that user. An empty register is the default, and
an empty register reports zeros. Nothing here is learned from labelled insiders, and
nothing here reads another user's events to judge this one.

Matched names are carried on the observation, in ``matched_identities``, so a count
can be reconstructed as a set of names. A new-name count that the history cannot yet
support is ``0`` with ``new_status`` of ``insufficient_history``, the same silence
``phos.sentiel.history.NEUTRAL_VALUE`` already uses, labelled so the zero is not read
as "none of them were new".
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, deque
from collections.abc import Collection, Iterable, Iterator, Mapping
from datetime import UTC, datetime, time, timedelta
from typing import Final, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from phos.ontology import Domain, Observation
from phos.sentiel.entities import user_entity_id
from phos.sentiel.events import (
    DETAIL_PC,
    DETAIL_RECIPIENTS,
    DETAIL_URL,
    DETAIL_URL_HOST,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
    domain_of,
    host_of,
)
from phos.sentiel.history import HistoryPolicy

__all__ = [
    "IDENTITY_FEATURES",
    "IDENTITY_FEATURE_SET",
    "MATCHED_IDENTITIES",
    "NEW_STATUS",
    "NEW_STATUS_INSUFFICIENT",
    "NEW_STATUS_MEASURED",
    "REGISTER_SHA256",
    "DeclaredIdentities",
    "IdentityFeaturiser",
    "register_sha256",
]

logger = logging.getLogger(__name__)

IDENTITY_FEATURE_SET: Final = "sentiel-identity-v1"
"""Context value marking an observation as coming from this stream, not from the 34."""

MATCHED_IDENTITIES: Final = "matched_identities"
"""Context key: the names that produced the count, sorted and joined with ``;``."""

NEW_STATUS: Final = "new_status"
"""Context key on the new-name features: whether the history could support the claim."""

NEW_STATUS_MEASURED: Final = "measured"
NEW_STATUS_INSUFFICIENT: Final = "insufficient_history"
REGISTER_SHA256: Final = "register_sha256"
"""Context key: hash of the register, so a later reader can see which names were declared."""

_HOST: Final = "host"
_DESTINATION: Final = "destination"
_PC: Final = "pc"
_FORBIDDEN_CHARS: Final = frozenset({DETAIL_VALUE_SEPARATOR, ",", "\n", "\r"})


class _Kind(NamedTuple):
    """One declared kind: the count feature, the new-name feature, and the memory key."""

    count_feature: str
    new_feature: str
    kind: str


_KINDS: Final[tuple[_Kind, ...]] = (
    _Kind("declared_host_count", "declared_new_host_count", _HOST),
    _Kind("declared_destination_count", "declared_new_destination_count", _DESTINATION),
    _Kind("declared_pc_count", "declared_new_pc_count", _PC),
)

IDENTITY_FEATURES: Final[tuple[str, ...]] = tuple(
    name for kind in _KINDS for name in (kind.count_feature, kind.new_feature)
)
"""The six identity features, in emission order.

Hosts, email destinations, and machines are separate. Pooling them is how a steady
trickle of new web hosts hides one new machine, which is the split the relationship
features already draw and this stream keeps.
"""


class DeclaredIdentities(BaseModel):
    """Names the identity features are allowed to notice.

    The register is an input. It is not fitted, and it is not filled from a labelled
    insider's own traffic. Matching is exact after case-folding and stripping. A
    destination entry may be a full address or a domain; a domain entry matches every
    address at that domain. A host entry does not match a suffix or a parent domain.

    Attributes:
        hosts: Web hosts, compared to the event's host.
        destinations: Email addresses or domains, compared to recipients.
        pcs: Machine names, compared to the event's ``pc`` field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hosts: frozenset[str] = Field(default_factory=frozenset)
    destinations: frozenset[str] = Field(default_factory=frozenset)
    pcs: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("hosts", "destinations", "pcs", mode="before")
    @classmethod
    def _fold_names(cls, value: object) -> frozenset[str]:
        """Case-fold the names and refuse a blank or an ambiguous one.

        Raises:
            ValueError: If ``value`` is a single string, a mapping, or contains a name
                that is blank or that would make the joined context ambiguous.
        """
        if (
            isinstance(value, str)
            or isinstance(value, Mapping)
            or not isinstance(value, Collection)
        ):
            raise ValueError("a declared-identity field is a collection of names, not one string")
        folded: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("a declared identity must be a string")
            name = item.strip().casefold()
            if not name:
                raise ValueError("a declared identity cannot be blank")
            if any(char in name for char in _FORBIDDEN_CHARS):
                raise ValueError(
                    "a declared identity cannot contain ';' or ',', or a line break, "
                    "because matched names are joined on ';'"
                )
            folded.add(name)
        return frozenset(folded)


def register_sha256(register: DeclaredIdentities) -> str:
    """Return a stable hash of ``register``.

    Field order and name order are fixed, so two registers with the same names hash
    alike whatever order they were written in.

    Args:
        register: The declared names.

    Returns:
        The hex SHA-256 of the canonical text.
    """
    lines = (
        "destinations=" + ",".join(sorted(register.destinations)),
        "hosts=" + ",".join(sorted(register.hosts)),
        "pcs=" + ",".join(sorted(register.pcs)),
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _destination_matches(address: str, register: frozenset[str]) -> bool:
    """Return whether ``address`` is a declared destination, exactly or by domain."""
    if address in register:
        return True
    domain = domain_of(address)
    return domain != "" and domain in register


def _join(names: frozenset[str]) -> str:
    """Return ``names`` sorted and joined, or ``""`` when there are none."""
    return DETAIL_VALUE_SEPARATOR.join(sorted(names))


class _Day:
    """Distinct hosts, destinations and machines one user touched in one window."""

    __slots__ = ("destinations", "hosts", "pcs")

    def __init__(self) -> None:
        self.hosts: set[str] = set()
        self.destinations: set[str] = set()
        self.pcs: set[str] = set()

    def add(self, event: EnterpriseEvent) -> None:
        """Fold one event's names into this window. Names are case-folded."""
        pc = event.details.get(DETAIL_PC, "").strip().casefold()
        if pc and not any(char in pc for char in _FORBIDDEN_CHARS):
            self.pcs.add(pc)
        if event.event_kind is EventKind.HTTP_REQUEST:
            raw = event.details.get(DETAIL_URL_HOST, "").strip()
            host = raw.casefold() if raw else host_of(event.details.get(DETAIL_URL, ""))
            if host and not any(char in host for char in _FORBIDDEN_CHARS):
                self.hosts.add(host)
        elif event.event_kind is EventKind.EMAIL_SEND:
            for address in event.details.get(DETAIL_RECIPIENTS, "").split(DETAIL_VALUE_SEPARATOR):
                folded = address.strip().casefold()
                if folded and not any(char in folded for char in _FORBIDDEN_CHARS):
                    self.destinations.add(folded)


class _RollingNames:
    """Names one user was seen with recently, forgotten once they age out of the window."""

    __slots__ = ("_counts", "_limit", "_windows")

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._windows: deque[frozenset[str]] = deque()
        self._counts: Counter[str] = Counter()

    @property
    def windows(self) -> int:
        """How many populated windows this memory holds."""
        return len(self._windows)

    def contains(self, name: str) -> bool:
        """Return whether ``name`` appears in any remembered window."""
        return self._counts[name] > 0

    def push(self, names: frozenset[str]) -> None:
        """Remember one window, dropping the oldest when the memory is full."""
        if len(self._windows) == self._limit:
            for name in self._windows.popleft():
                count = self._counts[name]
                if count <= 1:
                    del self._counts[name]
                else:
                    self._counts[name] = count - 1
        self._windows.append(names)
        self._counts.update(names)


class _IdentityMemory:
    """Per-user rolling memory of hosts, destinations and machines.

    Reads see only windows already observed. ``observe`` is the only mutator, and the
    featuriser calls it after the window has been emitted.
    """

    __slots__ = ("_kinds", "policy")

    def __init__(self, policy: HistoryPolicy) -> None:
        self.policy = policy
        self._kinds: dict[tuple[str, str], _RollingNames] = {}

    def status_and_new(
        self, user_id: str, kind: str, matched: frozenset[str]
    ) -> tuple[str, frozenset[str]]:
        """Return which of ``matched`` are new, or silence when the history is too short.

        Args:
            user_id: The corpus's own identifier for the user.
            kind: ``host``, ``destination`` or ``pc``.
            matched: Declared names seen in the current window. They are not yet in memory.

        Returns:
            ``(insufficient_history, empty)`` until ``min_history_windows`` prior windows
            exist, otherwise ``(measured, names in matched that the memory does not hold)``.
        """
        memory = self._kinds.get((user_id, kind))
        seen = 0 if memory is None else memory.windows
        if memory is None or seen < self.policy.min_history_windows:
            return NEW_STATUS_INSUFFICIENT, frozenset()
        novel = frozenset(name for name in matched if not memory.contains(name))
        return NEW_STATUS_MEASURED, novel

    def observe(
        self,
        user_id: str,
        hosts: frozenset[str],
        destinations: frozenset[str],
        pcs: frozenset[str],
    ) -> None:
        """Fold one completed window into this user's memory.

        An empty set still counts as a window, so a day with no mail still advances the
        destination history the cold start is waiting on.
        """
        for kind, names in ((_HOST, hosts), (_DESTINATION, destinations), (_PC, pcs)):
            key = (user_id, kind)
            memory = self._kinds.get(key)
            if memory is None:
                memory = _RollingNames(self.policy.trailing_windows)
                self._kinds[key] = memory
            memory.push(names)


def _window_start(when: datetime, window: timedelta) -> datetime:
    """Return the start of the window ``when`` falls in, aligned to midnight UTC."""
    midnight = datetime.combine(when.date(), time.min, tzinfo=UTC)
    if window >= timedelta(days=1):
        return midnight
    elapsed = when - midnight
    return midnight + window * int(elapsed // window)


class IdentityFeaturiser(BaseModel):
    """Aggregate events into the six identity observations, leaving the 34 untouched.

    Attributes:
        window: Aggregation window, one day by default, aligned to midnight UTC. The
            same alignment the 34 use.
        history_policy: How many of the user's own prior windows are required before a
            new-name feature may speak, and how long a name is remembered. Inherited
            from `HistoryPolicy`; not a threshold chosen for an insider.
        identities: The declared names. Empty by default, in which case every count is
            zero and every matched-name list is empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    window: timedelta = timedelta(days=1)
    history_policy: HistoryPolicy = Field(default_factory=HistoryPolicy)
    identities: DeclaredIdentities = Field(default_factory=DeclaredIdentities)

    def observations(self, events: Iterable[EnterpriseEvent]) -> list[Observation]:
        """Aggregate ``events`` into identity observations.

        Args:
            events: The event stream, in non-decreasing timestamp order.

        Returns:
            One observation per active user, window and identity feature. A day with
            any event emits all six features, zeros included.
        """
        return list(self.stream(events))

    def stream(self, events: Iterable[EnterpriseEvent]) -> Iterator[Observation]:
        """Yield identity observations as each window completes.

        Args:
            events: The event stream, in non-decreasing timestamp order.

        Yields:
            Observations ordered by window, then user id, then `IDENTITY_FEATURES`.

        Raises:
            ValueError: If the events are not time-ordered.
        """
        buckets: dict[str, _Day] = {}
        open_window: datetime | None = None
        previous: datetime | None = None
        memory = _IdentityMemory(self.history_policy)
        emitted = 0
        for event in events:
            if previous is not None and event.timestamp < previous:
                raise ValueError(
                    f"events must be time-ordered; {event.timestamp} follows {previous}"
                )
            previous = event.timestamp
            start = _window_start(event.timestamp, self.window)
            if open_window is not None and start > open_window:
                for observation in self._flush(buckets, open_window, memory):
                    emitted += 1
                    yield observation
                buckets = {}
            open_window = start
            buckets.setdefault(event.user_id, _Day()).add(event)
        if open_window is not None:
            for observation in self._flush(buckets, open_window, memory):
                emitted += 1
                yield observation
        logger.info(
            "identity featuriser emitted %d observations (%d features, register %s)",
            emitted,
            len(IDENTITY_FEATURES),
            register_sha256(self.identities),
        )

    def _flush(
        self,
        buckets: dict[str, _Day],
        window_start: datetime,
        memory: _IdentityMemory,
    ) -> Iterator[Observation]:
        """Emit one window, then fold it into memory. Emission comes first."""
        for user_id in sorted(buckets):
            day = buckets[user_id]
            yield from self._user_observations(user_id, window_start, day, memory)
            memory.observe(
                user_id,
                frozenset(day.hosts),
                frozenset(day.destinations),
                frozenset(day.pcs),
            )

    def _user_observations(
        self,
        user_id: str,
        window_start: datetime,
        day: _Day,
        memory: _IdentityMemory,
    ) -> Iterator[Observation]:
        """Yield the six features for one user-window, reading memory and not writing it."""
        fingerprint = register_sha256(self.identities)
        base = {
            "user_id": user_id,
            "window_seconds": str(int(self.window.total_seconds())),
            "feature_set": IDENTITY_FEATURE_SET,
            REGISTER_SHA256: fingerprint,
        }
        matched = {
            _HOST: frozenset(name for name in day.hosts if name in self.identities.hosts),
            _DESTINATION: frozenset(
                name
                for name in day.destinations
                if _destination_matches(name, self.identities.destinations)
            ),
            _PC: frozenset(name for name in day.pcs if name in self.identities.pcs),
        }
        entity_id = user_entity_id(user_id)
        index = 0
        for kind in _KINDS:
            names = matched[kind.kind]
            yield _observation(
                user_id,
                entity_id,
                window_start,
                index,
                kind.count_feature,
                float(len(names)),
                {**base, MATCHED_IDENTITIES: _join(names)},
            )
            index += 1
            status, novel = memory.status_and_new(user_id, kind.kind, names)
            yield _observation(
                user_id,
                entity_id,
                window_start,
                index,
                kind.new_feature,
                float(len(novel)),
                {**base, MATCHED_IDENTITIES: _join(novel), NEW_STATUS: status},
            )
            index += 1


def _observation(
    user_id: str,
    entity_id: str,
    window_start: datetime,
    index: int,
    feature: str,
    value: float,
    context: dict[str, str],
) -> Observation:
    """Return one identity observation with a deterministic id."""
    return Observation(
        id=f"idn_{user_id}_{window_start:%Y%m%d}_{index:02d}",
        entity_ids=[entity_id],
        feature=feature,
        value=value,
        timestamp=window_start,
        domain=Domain.SENTIEL,
        context=context,
    )
