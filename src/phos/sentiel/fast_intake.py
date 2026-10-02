"""Reading 27.3 million CERT rows into entity-day traces without building 27.3 million objects.

`phos.sentiel.cert.CertReader` is the authority on what a CERT release says, and it stays the
authority. It is also slow enough to change what is buildable: it mints one Pydantic
`EnterpriseEvent` and calls `datetime.strptime` per row, which measures **2,189 events/second** on
this machine and puts a single pass over r3.1 at three and a half hours. Two capabilities in this
cycle need the corpus read at all, and every experiment downstream of the trace cache needs it read
*again* whenever the cache format moves. Three and a half hours per attempt is not a build loop.

This module reads the same five logs into the same `phos.sentiel.traces.EntityDayTrace` records
about twenty times faster, by never constructing the intermediate object. Two things make that a
safe trade rather than a second, divergent reader:

**The schema authority is not duplicated.** Headers are checked by `cert._check_header`, against
`cert.ALL_SPECS`, so a release whose columns have drifted is refused here exactly as it is refused
there — including r3.1's `email.csv`, which carries no ``user`` column and whose actor is resolvable
only through the directory.

**The equivalence is proved on the corpus, not asserted in a docstring.** `traces_agree` runs both
readers over the same bounded date range of the real release and compares the resulting traces field
by field. ``scripts/build_sentiel_trace_cache.py --verify-days N`` runs it before it will write a
cache, and `tests/sentiel/test_fast_intake.py` runs it on a fixture. If the two disagree the cache
is not written, because a cache that is *nearly* the featuriser's input is worse than none: every
number downstream would be off by an amount nobody could see.

**What is actually different, and why each is safe.**

* *No `EnterpriseEvent`.* Rows become a lightweight tuple. Nothing downstream of the trace needs the
  object; the trace holds what `_Accumulator` would have held.
* *Timestamps are parsed once per distinct date.* CERT stamps are fixed-width ``MM/DD/YYYY
  HH:MM:SS``. The ten-character date is `strptime`'d through a cache — about 500 distinct values
  across the release — and the time is read by slicing. `parse_stamp` is compared against
  `datetime.strptime` over every second of a day and every date of the release in the tests.
* *Merge order is `CertReader`'s own.* The five streams are merged on the timestamp in the order
  `MERGE_ORDER` gives, which is the order `CertReader.events` builds them in, because
  `heapq.merge` is stable and ties therefore resolve by stream position. That tie-break is
  invisible to every count and every set, and visible to the **sequence**, which is why it is
  pinned here rather than left to chance.

Nothing here reads a label, and nothing here is fitted.
"""

from __future__ import annotations

import csv
import heapq
import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

from phos.sentiel.cert import (
    ALL_SPECS,
    CERT_TIMESTAMP_FORMAT,
    DEVICE_SPEC,
    EMAIL_SPEC,
    FILE_SPEC,
    HTTP_SPEC,
    LOGON_SPEC,
    CertFormatError,
    CertRelease,
    LogSpec,
    _check_header,
)
from phos.sentiel.events import (
    DETAIL_VALUE_SEPARATOR,
    EventKind,
    domain_of,
    host_of,
)
from phos.sentiel.featurise import WorkingHours
from phos.sentiel.traces import DeclaredToken, EntityDayTrace

__all__ = [
    "MERGE_ORDER",
    "RawRow",
    "fast_trace_stream",
    "parse_stamp",
    "traces_agree",
]

logger = logging.getLogger(__name__)

MERGE_ORDER: Final[tuple[LogSpec, ...]] = (
    LOGON_SPEC,
    DEVICE_SPEC,
    HTTP_SPEC,
    EMAIL_SPEC,
    FILE_SPEC,
)
"""The order `phos.sentiel.cert.CertReader.events` builds its five streams in.

`heapq.merge` is stable, so two events sharing an instant are emitted in this order. Counts and
sets cannot see that; an entity-day's ordered sequence can. Pinned here so the fast reader and the
authority produce the same path, and asserted against `cert.ALL_SPECS` on import below.
"""

if {spec.filename for spec in MERGE_ORDER} != {spec.filename for spec in ALL_SPECS}:
    raise ImportError(  # pragma: no cover - a guard against a release gaining a log
        "MERGE_ORDER and cert.ALL_SPECS name different logs; the fast reader would silently skip "
        "or invent one"
    )

_LOGON_ACTIVITY_KINDS: Final = {"logon": EventKind.LOGON, "logoff": EventKind.LOGOFF}
_DEVICE_ACTIVITY_KINDS: Final = {
    "connect": EventKind.DEVICE_CONNECT,
    "insert": EventKind.DEVICE_CONNECT,
    "disconnect": EventKind.DEVICE_DISCONNECT,
    "remove": EventKind.DEVICE_DISCONNECT,
}


class RawRow(NamedTuple):
    """One activity-log row, reduced to what an entity-day trace needs.

    Attributes:
        key: ``(date ordinal, hour, minute, second)`` — orders identically to the `datetime` the
            authority compares, without building one.
        day: Midnight UTC of the row's date.
        user_id: The actor.
        kind: What was done.
        pc: The machine named by the row, or ``""``.
        payload: The filename, url host, or joined recipient list the kind carries, or ``""``.
        external: Whether an email row had any recipient outside the organisation's domains.
        off_hours: Whether a logon fell outside the declared working pattern.
    """

    key: tuple[int, int, int, int]
    day: datetime
    user_id: str
    kind: EventKind
    pc: str
    payload: str
    external: bool
    off_hours: bool


class _DateFacts(NamedTuple):
    """What every row sharing a date needs, computed once for that date."""

    ordinal: int
    midnight: datetime
    is_workday: bool


def parse_stamp(
    text: str, cache: dict[str, _DateFacts], hours: WorkingHours
) -> tuple[tuple[int, int, int, int], datetime, bool]:
    """Return the ordering key, the window's midnight, and whether the instant is off-hours.

    CERT stamps are fixed-width ``MM/DD/YYYY HH:MM:SS``. Only the date half needs `strptime`, and
    only once per distinct date — about 500 across a release — so the per-row cost is a dict lookup
    and three slices rather than a full parse.

    Args:
        text: The raw ``date`` cell.
        cache: Date-string to `_DateFacts`, owned by the caller and reused across rows.
        hours: The declared working pattern.

    Returns:
        ``(key, midnight, off_hours)``.

    Raises:
        CertFormatError: If the cell is blank or does not match `CERT_TIMESTAMP_FORMAT`, matching
            `phos.sentiel.cert` rather than guessing at a partial parse.
    """
    if len(text) != 19 or text[2] != "/" or text[5] != "/" or text[10] != " ":
        raise CertFormatError(f"date {text!r} does not match {CERT_TIMESTAMP_FORMAT!r}")
    date_part = text[:10]
    facts = cache.get(date_part)
    if facts is None:
        try:
            parsed = datetime.strptime(date_part, "%m/%d/%Y").replace(tzinfo=UTC)
        except ValueError as error:
            raise CertFormatError(
                f"date {text!r} does not match {CERT_TIMESTAMP_FORMAT!r}: {error}"
            ) from error
        facts = _DateFacts(
            ordinal=parsed.toordinal(),
            midnight=parsed,
            is_workday=parsed.weekday() in hours.workdays,
        )
        cache[date_part] = facts
    try:
        hour = int(text[11:13])
        minute = int(text[14:16])
        second = int(text[17:19])
    except ValueError as error:
        raise CertFormatError(
            f"date {text!r} does not match {CERT_TIMESTAMP_FORMAT!r}: {error}"
        ) from error
    if hour > 23 or minute > 59 or second > 59:
        raise CertFormatError(f"date {text!r} does not match {CERT_TIMESTAMP_FORMAT!r}")
    off_hours = not (facts.is_workday and hours.start_hour <= hour < hours.end_hour)
    return (facts.ordinal, hour, minute, second), facts.midnight, off_hours


def _rows_of(
    path: Path,
    spec: LogSpec,
    hours: WorkingHours,
    org_domains: frozenset[str],
    senders: Mapping[str, str],
    until_day: datetime | None,
) -> Iterator[RawRow]:
    """Stream one log into `RawRow`s, checking its header with the authority's own rule."""
    if not path.is_file():
        raise CertFormatError(f"activity log not found: {path}")
    cache: dict[str, _DateFacts] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        raw_header = next(reader, None)
        if raw_header is None:
            raise CertFormatError(f"{path}: file is empty")
        indexes = _check_header([name.strip() for name in raw_header], path, spec)
        widest = max(indexes.values())
        get = indexes.get
        i_date = indexes["date"]
        i_user = get("user", -1)
        i_pc = get("pc", -1)
        i_activity = get("activity", -1)
        i_filename = get("filename", -1)
        i_url = get("url", -1)
        i_to = get("to", -1)
        i_from = get("from", -1)

        previous: tuple[int, int, int, int] | None = None
        for line_number, raw in enumerate(reader, start=2):
            if len(raw) <= widest:
                raise CertFormatError(
                    f"{path}:{line_number}: row has {len(raw)} field(s), too few to hold the "
                    f"{len(raw_header)} the header declares; it cannot be read positionally"
                )
            key, day, off_hours = parse_stamp(raw[i_date].strip(), cache, hours)
            # The authority checks this too, and for the same reason: the merge assumes each log
            # is sorted, and an unsorted one would silently produce an out-of-order stream.
            if previous is not None and key < previous:
                raise CertFormatError(
                    f"{path}:{line_number}: rows are not time-ordered. This reader merges the "
                    "logs by streaming them in parallel, which assumes each is sorted"
                )
            previous = key
            if until_day is not None and day >= until_day:
                return
            pc = raw[i_pc].strip() if i_pc >= 0 else ""
            if spec is LOGON_SPEC or spec is DEVICE_SPEC:
                activity = raw[i_activity].strip()
                table = _LOGON_ACTIVITY_KINDS if spec is LOGON_SPEC else _DEVICE_ACTIVITY_KINDS
                kind = table.get(activity.lower())
                if kind is None:
                    raise CertFormatError(
                        f"{spec.filename}: unrecognised activity {activity!r}; expected one of "
                        f"{', '.join(sorted(table))}"
                    )
                yield RawRow(key, day, raw[i_user].strip(), kind, pc, "", False, off_hours)
            elif spec is FILE_SPEC:
                yield RawRow(
                    key,
                    day,
                    raw[i_user].strip(),
                    EventKind.FILE_ACCESS,
                    pc,
                    raw[i_filename].strip(),
                    False,
                    off_hours,
                )
            elif spec is HTTP_SPEC:
                yield RawRow(
                    key,
                    day,
                    raw[i_user].strip(),
                    EventKind.HTTP_REQUEST,
                    pc,
                    host_of(raw[i_url].strip()),
                    False,
                    off_hours,
                )
            else:
                sender = raw[i_from].strip().lower()
                user_id = senders.get(sender)
                if user_id is None:
                    continue
                recipients = [
                    address.strip()
                    for address in raw[i_to].strip().split(DETAIL_VALUE_SEPARATOR)
                    if address.strip()
                ]
                domains = {domain for address in recipients if (domain := domain_of(address))}
                yield RawRow(
                    key,
                    day,
                    user_id,
                    EventKind.EMAIL_SEND,
                    pc,
                    DETAIL_VALUE_SEPARATOR.join(address.lower() for address in recipients),
                    bool(domains - org_domains),
                    off_hours,
                )


class _Bucket:
    """One user's open window: the accumulator's state, held as plain fields."""

    __slots__ = (
        "emails",
        "external_emails",
        "file_accesses",
        "files",
        "hosts",
        "logons",
        "off_hours_logons",
        "pcs",
        "recipients",
        "removable_connects",
        "sequence",
    )

    def __init__(self) -> None:
        self.logons = 0
        self.off_hours_logons = 0
        self.removable_connects = 0
        self.file_accesses = 0
        self.emails = 0
        self.external_emails = 0
        self.pcs: set[str] = set()
        self.files: set[str] = set()
        self.hosts: set[str] = set()
        self.recipients: set[str] = set()
        self.sequence: list[DeclaredToken] = []

    def add(self, row: RawRow) -> None:
        """Fold one row in, mirroring `phos.sentiel.featurise._Accumulator.add` exactly."""
        if row.pc:
            self.pcs.add(row.pc)
        kind = row.kind
        if kind is EventKind.LOGON:
            self.logons += 1
            token = DeclaredToken.LOGON
            if row.off_hours:
                self.off_hours_logons += 1
                token = DeclaredToken.LOGON_OFF_HOURS
        elif kind is EventKind.LOGOFF:
            token = DeclaredToken.LOGOFF
        elif kind is EventKind.DEVICE_CONNECT:
            self.removable_connects += 1
            token = DeclaredToken.DEVICE_CONNECT
        elif kind is EventKind.DEVICE_DISCONNECT:
            token = DeclaredToken.DEVICE_DISCONNECT
        elif kind is EventKind.FILE_ACCESS:
            self.file_accesses += 1
            if row.payload:
                self.files.add(row.payload)
            token = DeclaredToken.FILE_ACCESS
        elif kind is EventKind.HTTP_REQUEST:
            if row.payload:
                self.hosts.add(row.payload)
            token = DeclaredToken.HTTP_REQUEST
        else:
            self.emails += 1
            self.recipients.update(
                address for address in row.payload.split(DETAIL_VALUE_SEPARATOR) if address
            )
            if row.external:
                self.external_emails += 1
            token = DeclaredToken.EMAIL_EXTERNAL if row.external else DeclaredToken.EMAIL_INTERNAL
        if not self.sequence or self.sequence[-1] is not token:
            self.sequence.append(token)

    def as_trace(self, user_id: str, day: datetime) -> EntityDayTrace:
        """Return the finished trace for this window."""
        return EntityDayTrace(
            user_id=user_id,
            day=day,
            logons=self.logons,
            off_hours_logons=self.off_hours_logons,
            removable_connects=self.removable_connects,
            file_accesses=self.file_accesses,
            emails=self.emails,
            external_emails=self.external_emails,
            pcs=tuple(sorted(self.pcs)),
            files=tuple(sorted(self.files)),
            hosts=tuple(sorted(self.hosts)),
            recipients=tuple(sorted(self.recipients)),
            sequence=tuple(self.sequence),
        )


def fast_trace_stream(
    release: CertRelease,
    senders: Mapping[str, str],
    working_hours: WorkingHours,
    org_domains: frozenset[str],
    *,
    until_day: datetime | None = None,
) -> Iterator[EntityDayTrace]:
    """Read a release into entity-day traces, in the featuriser's own emission order.

    Args:
        release: The release to read.
        senders: ``lowercased address -> user_id``, as `CertReader.for_release` builds it. Email
            rows whose sender is not a known employee are inbound mail and are skipped, exactly as
            the authority skips them.
        working_hours: The declared working pattern.
        org_domains: Mail domains the directory says are internal.
        until_day: Stop before this window, so a bounded slice can be compared against the
            authority. ``None`` reads the whole release.

    Yields:
        Traces, day ascending and user ascending within a day — `replay_observations`'s contract.

    Raises:
        CertFormatError: On any schema, ordering or parse failure the authority would also raise on.
    """
    streams = [
        _rows_of(release.path_for(spec), spec, working_hours, org_domains, senders, until_day)
        for spec in MERGE_ORDER
    ]
    buckets: dict[str, _Bucket] = {}
    open_day: datetime | None = None
    read = 0

    for row in heapq.merge(*streams, key=lambda item: item.key):
        read += 1
        if open_day is not None and row.day > open_day:
            yield from _drain(buckets, open_day)
        elif open_day is not None and row.day < open_day:
            raise CertFormatError(
                f"rows are not time-ordered: {row.day.date()} follows {open_day.date()}"
            )
        open_day = row.day
        bucket = buckets.get(row.user_id)
        if bucket is None:
            bucket = buckets[row.user_id] = _Bucket()
        bucket.add(row)

    if open_day is not None:
        yield from _drain(buckets, open_day)
    logger.info("fast intake read %d row(s) from release %s", read, release.name)


def _drain(buckets: dict[str, _Bucket], day: datetime) -> Iterator[EntityDayTrace]:
    """Emit every open bucket for ``day``, user ascending, and clear them."""
    for user_id in sorted(buckets):
        yield buckets[user_id].as_trace(user_id, day)
    buckets.clear()


def traces_agree(
    fast: Sequence[EntityDayTrace], authority: Sequence[EntityDayTrace]
) -> tuple[bool, str]:
    """Return whether two trace sequences are identical, and the first disagreement if not.

    Args:
        fast: Traces from `fast_trace_stream`.
        authority: Traces from `phos.sentiel.traces.trace_stream` over `CertReader.events`.

    Returns:
        ``(True, "")`` when every trace matches field for field, otherwise ``(False, reason)``
        naming the first entity-day that differs and what differs on it.
    """
    if len(fast) != len(authority):
        return False, (
            f"count differs: fast produced {len(fast)} trace(s), the authority {len(authority)}"
        )
    for quick, slow in zip(fast, authority, strict=True):
        if quick != slow:
            differing = [
                name
                for name in type(slow).model_fields
                if getattr(quick, name) != getattr(slow, name)
            ]
            return False, (
                f"{slow.user_id} on {slow.day.date()} differs in {', '.join(differing)}: "
                f"fast={ {name: getattr(quick, name) for name in differing} } "
                f"authority={ {name: getattr(slow, name) for name in differing} }"
            )
    return True, ""
