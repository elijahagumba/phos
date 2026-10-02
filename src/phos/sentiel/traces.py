"""One entity-day of raw enterprise activity, kept whole so it can be asked new questions.

PART 6B's featuriser reduces an entity-day to 34 numbers and drops everything else. That is the
right reduction for a per-day score and the wrong one for every capability built on top of it: an
episode needs to reach back to the individual event, a declared-graph path needs to know *which*
counterparty was touched, and a sequence needs to know what happened *in what order*. All three
facts exist in the corpus, survive to `phos.sentiel.featurise._Accumulator`, and are then discarded.

This module keeps them, and it keeps them in a form that regenerates the featuriser's own output
**exactly** rather than approximately.

**The cache is a materialisation, not a re-implementation.** `EntityDayTrace` stores precisely the
state `_Accumulator` holds at the end of a window, and `replay_observations` reconstructs a real
`_Accumulator` from it and calls the featuriser's own `observations`, `values` and `counterparties`.
Nothing here re-derives a feature. The consequence is the one that matters: a run scored from the
cache and a run scored from the corpus are the same run, and `tests/sentiel/test_traces.py` asserts
it observation by observation on a fixture corpus. Reading CERT r3.1 end to end costs about three
and a half hours at the measured 3,392 events/second; every experiment downstream of the cache
costs seconds. That ratio is the whole reason this file exists.

**The ordering *is* the causality guarantee, restated rather than reinvented.** `Featuriser._flush`
advances a user's own trailing history only after that user's window has been emitted, and advances
the peer pool only after *every* user in the window has been emitted. `replay_observations`
reproduces both, which is why it takes traces grouped by day with users in sorted order and refuses
a stream that is not. Getting this wrong would not raise; it would quietly leak each window into
the baseline that judges it.

**The sequence alphabet is declared, and run-collapsed on purpose.** A token is an `EventKind`
refined by two facts the corpus itself declares — `phos.sentiel.WorkingHours`, which is the same
policy `off_hours_logon_count` is measured against, and whether a message's recipient domain is the
organisation's own, which `phos.sentiel.EntityCatalogue.dominant_email_domain` reads off the
directory. Neither is learned from the entity's behaviour. Consecutive identical tokens collapse to
one, because **volume is already measured by the count features and order is what this is for**: a
user who makes four hundred web requests and one who makes four produce the same path, and a
sequence model that did not collapse them would rediscover `distinct_http_hosts` in a more
expensive way. The collapse is a declared rule, applied to everybody, and it is stated here so a
reader can see it was chosen before any n-gram was scored.

Nothing in this module reads a label, and nothing in it is fitted.
"""

from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology import Observation, UtcDatetime
from phos.sentiel.events import (
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
)
from phos.sentiel.featurise import (
    STARTER_FEATURES,
    Featuriser,
    WorkingHours,
    _Accumulator,
)
from phos.sentiel.history import TrailingHistory
from phos.sentiel.peers import PeerHistory

__all__ = [
    "CACHE_FORMAT_VERSION",
    "SEQUENCE_COLLAPSE_RULE",
    "DeclaredToken",
    "EntityDayTrace",
    "read_traces",
    "replay_observations",
    "token_for",
    "trace_stream",
    "write_traces",
]

logger = logging.getLogger(__name__)

CACHE_FORMAT_VERSION: Final = 1
"""Bumped whenever a stored field changes meaning, so a stale cache is refused rather than read."""

SEQUENCE_COLLAPSE_RULE: Final = (
    "Consecutive identical tokens collapse to one. Volume is already measured by the count "
    "features; the sequence measures ORDER. A declared rule applied to every entity-day, chosen "
    "before any n-gram was scored, and never tuned."
)


class DeclaredToken(str, Enum):
    """What one event contributes to an entity-day's ordered path.

    An `EventKind`, refined only by facts the corpus **declares** — the working-hours policy and
    the organisation's own mail domain — never by anything learned from the entity's own history.
    A token that depended on the actor's past would make the sequence baseline partly a self
    baseline, which is the collinearity `phos.sentiel.peers` refuses one layer down.
    """

    LOGON = "L"
    LOGON_OFF_HOURS = "l"
    LOGOFF = "O"
    DEVICE_CONNECT = "D"
    DEVICE_DISCONNECT = "d"
    FILE_ACCESS = "F"
    EMAIL_INTERNAL = "E"
    EMAIL_EXTERNAL = "X"
    HTTP_REQUEST = "H"


def token_for(
    event: EnterpriseEvent,
    working_hours: WorkingHours,
    org_domains: frozenset[str],
) -> DeclaredToken:
    """Return the declared token one event contributes.

    Args:
        event: The event.
        working_hours: The declared working pattern — the same one `off_hours_logon_count` uses.
        org_domains: Mail domains the directory says are internal.

    Returns:
        The token. The two refinements are exactly the two the count features already make, so the
        alphabet introduces no judgement the feature set has not already declared.
    """
    if event.event_kind is EventKind.LOGON:
        if working_hours.contains(event.timestamp):
            return DeclaredToken.LOGON
        return DeclaredToken.LOGON_OFF_HOURS
    if event.event_kind is EventKind.LOGOFF:
        return DeclaredToken.LOGOFF
    if event.event_kind is EventKind.DEVICE_CONNECT:
        return DeclaredToken.DEVICE_CONNECT
    if event.event_kind is EventKind.DEVICE_DISCONNECT:
        return DeclaredToken.DEVICE_DISCONNECT
    if event.event_kind is EventKind.FILE_ACCESS:
        return DeclaredToken.FILE_ACCESS
    if event.event_kind is EventKind.HTTP_REQUEST:
        return DeclaredToken.HTTP_REQUEST
    domains = {
        domain
        for domain in event.details.get(DETAIL_RECIPIENT_DOMAINS, "").split(DETAIL_VALUE_SEPARATOR)
        if domain
    }
    if domains - org_domains:
        return DeclaredToken.EMAIL_EXTERNAL
    return DeclaredToken.EMAIL_INTERNAL


class EntityDayTrace(BaseModel):
    """Everything one user did in one window, in the shape the featuriser reduces to numbers.

    The six counts and four sets are `phos.sentiel.featurise._Accumulator`'s complete state, so a
    trace reconstructs it exactly. The sequence is the extra fact the accumulator never held.

    Attributes:
        user_id: The corpus's own identifier for the actor.
        day: Start of the window, midnight UTC.
        logons: Logon events.
        off_hours_logons: Logons outside the declared working pattern.
        removable_connects: Removable-device connections.
        file_accesses: File-access events.
        emails: Messages sent.
        external_emails: Messages with any recipient outside the organisation's own domains.
        pcs: Distinct machines the window's events named.
        files: Distinct filenames touched.
        hosts: Distinct web hosts requested.
        recipients: Distinct lowercased addresses mailed.
        sequence: The window's declared tokens in order, with consecutive repeats collapsed
            (`SEQUENCE_COLLAPSE_RULE`).

    Invariants:
        Every set is stored sorted, so two runs over one corpus serialise identically and a cache
        file is comparable byte for byte.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    day: UtcDatetime
    logons: int = Field(default=0, ge=0)
    off_hours_logons: int = Field(default=0, ge=0)
    removable_connects: int = Field(default=0, ge=0)
    file_accesses: int = Field(default=0, ge=0)
    emails: int = Field(default=0, ge=0)
    external_emails: int = Field(default=0, ge=0)
    pcs: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    sequence: tuple[DeclaredToken, ...] = ()

    def as_accumulator(self) -> _Accumulator:
        """Return the featuriser's own accumulator, restored to this window's end state.

        This is what makes the cache a materialisation rather than a second implementation: every
        feature downstream is computed by `phos.sentiel.featurise`, from this object, exactly as it
        would have been computed from the events.
        """
        accumulator = _Accumulator()
        accumulator.logons = self.logons
        accumulator.off_hours_logons = self.off_hours_logons
        accumulator.removable_connects = self.removable_connects
        accumulator.file_accesses = self.file_accesses
        accumulator.emails = self.emails
        accumulator.external_emails = self.external_emails
        accumulator.distinct_pcs = set(self.pcs)
        accumulator.distinct_files = set(self.files)
        accumulator.distinct_hosts = set(self.hosts)
        accumulator.recipients = set(self.recipients)
        return accumulator

    def to_row(self) -> dict[str, object]:
        """Return the compact JSON record written to a cache file."""
        return {
            "u": self.user_id,
            "d": self.day.strftime("%Y-%m-%d"),
            "c": [
                self.logons,
                self.off_hours_logons,
                self.removable_connects,
                self.file_accesses,
                self.emails,
                self.external_emails,
            ],
            "p": list(self.pcs),
            "f": list(self.files),
            "h": list(self.hosts),
            "r": list(self.recipients),
            "s": "".join(token.value for token in self.sequence),
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> EntityDayTrace:
        """Return the trace a `to_row` record describes.

        Args:
            row: One decoded JSON object from a cache file. Typed as ``Any`` values because that
                is what `json.loads` returns; every field is narrowed by the constructor below,
                and a malformed record fails Pydantic validation rather than being half-read.
        """
        counts = [int(value) for value in row["c"]]
        return cls(
            user_id=str(row["u"]),
            day=datetime.strptime(str(row["d"]), "%Y-%m-%d").replace(tzinfo=UTC),
            logons=counts[0],
            off_hours_logons=counts[1],
            removable_connects=counts[2],
            file_accesses=counts[3],
            emails=counts[4],
            external_emails=counts[5],
            pcs=tuple(str(item) for item in row["p"]),
            files=tuple(str(item) for item in row["f"]),
            hosts=tuple(str(item) for item in row["h"]),
            recipients=tuple(str(item) for item in row["r"]),
            sequence=tuple(DeclaredToken(char) for char in str(row["s"])),
        )


class _Bucket:
    """One user's window while it is still open. Mutable, local, and never shared."""

    __slots__ = ("accumulator", "sequence")

    def __init__(self) -> None:
        self.accumulator = _Accumulator()
        self.sequence: list[DeclaredToken] = []

    def add(
        self, event: EnterpriseEvent, working_hours: WorkingHours, org_domains: frozenset[str]
    ) -> None:
        """Fold one event into the counts and the collapsed path."""
        self.accumulator.add(event, working_hours, org_domains)
        token = token_for(event, working_hours, org_domains)
        if not self.sequence or self.sequence[-1] is not token:
            self.sequence.append(token)


def _window_start(when: datetime) -> datetime:
    """Return midnight UTC of ``when``'s day — the featuriser's one-day window grid."""
    return datetime(when.year, when.month, when.day, tzinfo=UTC)


def trace_stream(
    events: Iterable[EnterpriseEvent],
    working_hours: WorkingHours,
    org_domains: frozenset[str],
) -> Iterator[EntityDayTrace]:
    """Aggregate an event stream into one trace per ``(user, day)``, day by day.

    Args:
        events: The event stream, in non-decreasing timestamp order.
        working_hours: The declared working pattern.
        org_domains: Mail domains the directory says are internal.

    Yields:
        Traces in the featuriser's own emission order — window ascending, and within a window user
        ascending — which is the order `replay_observations` requires.

    Raises:
        ValueError: If the events are not time-ordered, for the reason `Featuriser.stream` gives:
            a completed window would be reopened after it had been reported.

    Note:
        Peak memory is one day's buckets, not the corpus.
    """
    buckets: dict[str, _Bucket] = {}
    open_window: datetime | None = None
    previous: datetime | None = None

    for event in events:
        if previous is not None and event.timestamp < previous:
            raise ValueError(
                f"events must be time-ordered; {event.timestamp} follows {previous}. A completed "
                "window would be reopened after it had already been emitted"
            )
        previous = event.timestamp
        window_start = _window_start(event.timestamp)
        if open_window is not None and window_start > open_window:
            yield from _drain(buckets, open_window)
        open_window = window_start
        buckets.setdefault(event.user_id, _Bucket()).add(event, working_hours, org_domains)

    if open_window is not None:
        yield from _drain(buckets, open_window)


def _drain(buckets: dict[str, _Bucket], day: datetime) -> Iterator[EntityDayTrace]:
    """Emit every open bucket for ``day``, user ascending, and clear them."""
    for user_id in sorted(buckets):
        bucket = buckets[user_id]
        accumulator = bucket.accumulator
        yield EntityDayTrace(
            user_id=user_id,
            day=day,
            logons=accumulator.logons,
            off_hours_logons=accumulator.off_hours_logons,
            removable_connects=accumulator.removable_connects,
            file_accesses=accumulator.file_accesses,
            emails=accumulator.emails,
            external_emails=accumulator.external_emails,
            pcs=tuple(sorted(accumulator.distinct_pcs)),
            files=tuple(sorted(accumulator.distinct_files)),
            hosts=tuple(sorted(accumulator.distinct_hosts)),
            recipients=tuple(sorted(accumulator.recipients)),
            sequence=tuple(bucket.sequence),
        )
    buckets.clear()


def replay_observations(
    traces: Iterable[EntityDayTrace],
    featuriser: Featuriser,
) -> Iterator[Observation]:
    """Re-emit the featuriser's exact observation stream from cached traces.

    The two history advances of `Featuriser._flush` are reproduced here rather than approximated:
    a user's own trailing history is folded in only after that user's window has been emitted, and
    the peer pool only after **every** user of the window has been. Reversing either would let a
    window into the baseline that judges it, silently.

    Args:
        traces: Traces in `trace_stream`'s order — day ascending, user ascending within a day.
        featuriser: The featuriser whose feature set, window, history policy and peer groups the
            replay must match. Its `phos.sentiel.Featuriser.stream` is not called; its
            configuration and its accumulator's own methods are what produce the numbers.

    Yields:
        `Observation` objects identical to the ones the featuriser would have emitted from the
        events the traces were built from — same ids, features, values, timestamps and context.

    Raises:
        ValueError: If the traces are not in day-ascending, user-ascending order, which would
            corrupt both histories without raising anywhere else.
    """
    history = (
        TrailingHistory(featuriser.history_policy) if featuriser.feature_set.needs_history else None
    )
    peers = (
        PeerHistory(featuriser.peer_groups, STARTER_FEATURES, featuriser.history_policy)
        if featuriser.feature_set.needs_peers and featuriser.peer_groups is not None
        else None
    )

    open_day: datetime | None = None
    previous_user: str | None = None
    pending: dict[str, tuple[float, ...]] = {}

    for trace in traces:
        if open_day is not None and trace.day < open_day:
            raise ValueError(
                f"traces must be day-ascending; {trace.day.date()} follows {open_day.date()}"
            )
        if open_day is not None and trace.day > open_day:
            if peers is not None:
                peers.observe(pending)
            pending = {}
            previous_user = None
        if previous_user is not None and trace.user_id <= previous_user:
            raise ValueError(
                f"traces within {trace.day.date()} must be user-ascending; {trace.user_id!r} "
                f"follows {previous_user!r}"
            )
        open_day = trace.day
        previous_user = trace.user_id

        accumulator = trace.as_accumulator()
        yield from accumulator.observations(
            trace.user_id, trace.day, featuriser.window, featuriser.feature_set, history, peers
        )
        starter = accumulator.values()
        if history is not None:
            history.observe(
                trace.user_id,
                dict(zip(STARTER_FEATURES, starter, strict=True)),
                accumulator.counterparties(),
            )
        if peers is not None:
            pending[trace.user_id] = starter

    if peers is not None and pending:
        peers.observe(pending)


def write_traces(traces: Iterable[EntityDayTrace], path: Path, *, every: int = 25_000) -> int:
    """Stream traces into a gzipped JSON-lines cache, logging progress.

    Args:
        traces: The traces, in emission order.
        path: Destination. Its parent must exist.
        every: How often to log progress, in records.

    Returns:
        How many records were written.
    """
    written = 0
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as handle:
        handle.write(json.dumps({"format": CACHE_FORMAT_VERSION}) + "\n")
        for trace in traces:
            handle.write(json.dumps(trace.to_row(), separators=(",", ":")) + "\n")
            written += 1
            if written % every == 0:
                logger.info("  cached %d entity-day trace(s), at %s", written, trace.day.date())
    logger.info("wrote %d entity-day trace(s) to %s", written, path)
    return written


def read_traces(path: Path) -> Iterator[EntityDayTrace]:
    """Yield every trace in a cache file, in the order it was written.

    Raises:
        ValueError: If the file's format version is not `CACHE_FORMAT_VERSION`. A cache whose
            fields have changed meaning must be rebuilt, not reinterpreted.
    """
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        if header.get("format") != CACHE_FORMAT_VERSION:
            raise ValueError(
                f"{path} is cache format {header.get('format')!r}, but this build reads "
                f"{CACHE_FORMAT_VERSION}. Rebuild it rather than reading fields that may have "
                "changed meaning"
            )
        for line in handle:
            if line.strip():
                yield EntityDayTrace.from_row(json.loads(line))


def days_spanned(traces: Sequence[EntityDayTrace]) -> timedelta:
    """Return the span from the earliest trace's day to the latest's, or zero if empty."""
    if not traces:
        return timedelta(0)
    return max(trace.day for trace in traces) - min(trace.day for trace in traces)
