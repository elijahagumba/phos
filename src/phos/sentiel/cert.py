"""Reading a CERT Insider Threat release: five activity logs and a directory, into one stream.

CERT publishes a release as a directory tree of per-activity CSVs — ``logon.csv``, ``device.csv``,
``file.csv``, ``email.csv``, ``http.csv`` — beside an ``LDAP/`` directory of monthly org-chart
snapshots. Nothing in PHOS could read that before this module: `phos.eval.LabelledCsvAdapter`
reads exactly one labelled table, and a release is neither one table nor labelled.

Three properties shape the implementation.

**Headers are introspected, never assumed.** Each log declares the columns it requires and the ones
it knowingly ignores. A header missing a required column raises, naming what was actually found; a
header carrying a column this reader has never heard of *also* raises, because releases genuinely
disagree and a schema drift that is silently ignored is a schema drift that silently changes every
number downstream.

That strictness paid for itself immediately. The published CERT schema and this project's own
registry both describe ``email.csv`` as carrying ``user`` and ``pc`` columns like every other log.
**Release 3.1's does not**: its header is ``id, date, to, from, size, attachments, content``, and
the actor is identifiable only by resolving the ``from`` address against the LDAP directory. A
reader
that had assumed the documented schema would have produced no email features at all, or crashed;
one that had quietly skipped unreadable rows would have reported a zero that looked like a
measurement. The release's own ``readme.txt`` disagrees with its own header too — it calls the
attachment column ``attachment_count`` where the file says ``attachments``. The header is the
authority, and this reader reads it.

Because of that, **attributing email needs the directory**, which is why `CertReader.for_release`
exists: it reads ``LDAP/`` first and builds an address-to-user index. A message whose sender is not
a known employee is inbound mail from outside the organisation — not an action by a monitored user
— so it is skipped and *counted*, and the count is logged. Inbound mail is real signal, but it is
relationship signal, and relationships are PART 6A.

**The memory strategy is a streaming k-way merge.** Each log is read one row at a time by
`csv.reader` and yielded as it goes; the five resulting iterators are combined with
`heapq.merge` on the timestamp. Peak memory is therefore five rows plus the merge heap, not the
corpus — which matters because an uncompressed release is tens of gigabytes and ``http.csv`` alone
is most of it. The merge is only correct if each file is itself time-ordered, so rather than
trusting that, `_rows` checks it as it streams and raises the moment a timestamp goes backwards.

**Timestamps are naive in the source and are read as UTC.** CERT records local wall-clock with no
offset. Interpreting it as UTC is the same choice `phos.eval.LabelledCsvAdapter` documents, and it
is what keeps a run reproducible on any machine. It shifts every event and every label by the same
unknown constant, so no interval, duration or ordering is affected — but "8pm is off-hours" is a
statement about the corpus's own clock, which is exactly what the featuriser wants.
"""

import csv
import heapq
import logging
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.events import (
    DETAIL_ACTIVITY,
    DETAIL_EVENT_ID,
    DETAIL_FILENAME,
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_RECIPIENTS,
    DETAIL_SENDER,
    DETAIL_URL,
    DETAIL_URL_HOST,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
    domain_of,
    host_of,
)

__all__ = ["CERT_TIMESTAMP_FORMAT", "CertFormatError", "CertReader", "CertRelease", "LogSpec"]

logger = logging.getLogger(__name__)

CERT_TIMESTAMP_FORMAT: Final = "%m/%d/%Y %H:%M:%S"
"""The format every CERT activity log stamps its rows with. Naive; read as UTC — see the module
docstring."""

_PROGRESS_EVERY: Final = 2_000_000


class CertFormatError(ValueError):
    """Raised when a release's layout or a file's header is not what this reader can read.

    Deliberately fatal rather than survivable. A CERT release that does not look like a CERT
    release is a corpus PHOS does not understand, and every metric computed from a
    half-understood corpus is a number that looks fine and means nothing.
    """


class LogSpec(BaseModel):
    """What one activity log looks like and how its rows become events.

    Attributes:
        filename: The log's file within the release, e.g. ``"logon.csv"``.
        required: Columns without which the log cannot be read at all.
        ignored: Columns this reader knows about and deliberately does not read — CERT's free-text
            ``content`` bodies, chiefly, which are megabytes per thousand rows and feed no starter
            feature. Listing them is what lets an *unlisted* column be treated as a schema change.
    """

    model_config = ConfigDict(frozen=True)

    filename: str
    required: frozenset[str]
    ignored: frozenset[str] = frozenset()

    def known_columns(self) -> frozenset[str]:
        """Return every column this spec accounts for."""
        return self.required | self.ignored


_COMMON: Final = frozenset({"id", "date", "user", "pc"})

# Every spec below was written against a real Release 3.1 header, read off the file rather than
# off the published schema. Where the two disagree, the file wins — see the module docstring.
LOGON_SPEC: Final = LogSpec(filename="logon.csv", required=_COMMON | {"activity"})
DEVICE_SPEC: Final = LogSpec(filename="device.csv", required=_COMMON | {"activity"})
HTTP_SPEC: Final = LogSpec(
    filename="http.csv",
    required=_COMMON | {"url"},
    ignored=frozenset({"content"}),
)
EMAIL_SPEC: Final = LogSpec(
    filename="email.csv",
    # No `user` and no `pc`: r3.1's email log identifies its actor by the `from` address alone.
    required=frozenset({"id", "date", "to", "from"}),
    ignored=frozenset({"size", "attachments", "content"}),
)
FILE_SPEC: Final = LogSpec(
    filename="file.csv",
    required=_COMMON | {"filename"},
    ignored=frozenset({"content"}),
)

_LOGON_ACTIVITIES: Final = {"logon": EventKind.LOGON, "logoff": EventKind.LOGOFF}
_DEVICE_ACTIVITIES: Final = {
    "connect": EventKind.DEVICE_CONNECT,
    "insert": EventKind.DEVICE_CONNECT,
    "disconnect": EventKind.DEVICE_DISCONNECT,
    "remove": EventKind.DEVICE_DISCONNECT,
}
"""Removable-media wording differs between releases; both vocabularies map to the same kinds.

The raw word is kept on `DETAIL_ACTIVITY` so the mapping stays checkable against the source.
"""


class CertRelease(BaseModel):
    """Where the files of one extracted CERT release live.

    Attributes:
        root: The directory holding the activity CSVs and the ``LDAP`` directory.
        name: The release's name, e.g. ``"r3.1"``, taken from the directory name.
    """

    model_config = ConfigDict(frozen=True)

    root: Path
    name: str

    @classmethod
    def discover(cls, path: Path) -> Self:
        """Locate a release under ``path``, descending one level if the archive nested it.

        ``tar -xjf r3.1.tar.bz2`` produces ``r3.1/`` rather than unpacking in place, so both the
        release directory and its parent are accepted and the caller need not know which they hold.

        Args:
            path: A release directory, or a directory containing exactly one.

        Returns:
            The located release.

        Raises:
            CertFormatError: If no directory at or one level below ``path`` holds the activity
                logs, naming what was looked for.
        """
        if not path.is_dir():
            raise CertFormatError(f"CERT release directory not found at {path}")
        candidates = [path, *sorted(child for child in path.iterdir() if child.is_dir())]
        for candidate in candidates:
            if all((candidate / spec.filename).is_file() for spec in ALL_SPECS):
                return cls(root=candidate, name=candidate.name)
        wanted = ", ".join(spec.filename for spec in ALL_SPECS)
        raise CertFormatError(
            f"no CERT release found at {path} or one level below it; a release directory holds "
            f"{wanted} and an LDAP/ directory"
        )

    def path_for(self, spec: LogSpec) -> Path:
        """Return the path of one activity log within this release."""
        return self.root / spec.filename

    @property
    def ldap_directory(self) -> Path:
        """Return the release's ``LDAP`` directory of monthly org-chart snapshots."""
        return self.root / "LDAP"


ALL_SPECS: Final[tuple[LogSpec, ...]] = (
    LOGON_SPEC,
    DEVICE_SPEC,
    HTTP_SPEC,
    EMAIL_SPEC,
    FILE_SPEC,
)


class CertReader(BaseModel):
    """Reads a CERT release into a single time-ordered stream of `EnterpriseEvent`.

    Attributes:
        release: The release to read.
        email_senders: ``lowercased address -> user_id``, used to attribute ``email.csv`` rows,
            whose only actor field is the ``from`` address. Build it with `for_release` rather than
            by hand; an empty index means no email event can be attributed and every row is
            skipped, which `events` reports.

    Note:
        `events` is a generator and the class holds no mutable state, so a reader may be iterated
        more than once and two iterations are independent.
    """

    model_config = ConfigDict(frozen=True)

    release: CertRelease
    email_senders: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def for_release(cls, release: CertRelease) -> Self:
        """Build a reader with the email index resolved from the release's own LDAP directory.

        Args:
            release: The release to read.

        Returns:
            A reader able to attribute every log, email included.

        Raises:
            CertFormatError: If the LDAP directory is missing or unreadable.
        """
        catalogue = EntityCatalogue.from_ldap_directory(release.ldap_directory)
        index = {
            address.lower(): user_id
            for user_id, entity in catalogue.entities.items()
            if (address := entity.attributes.get("email", ""))
        }
        logger.info("resolved %d employee email addresses for release %s", len(index), release.name)
        return cls(release=release, email_senders=index)

    def events(self) -> Iterator[EnterpriseEvent]:
        """Yield every attributable activity in the release, in non-decreasing timestamp order.

        The five logs are streamed independently and merged on the timestamp, so peak memory is a
        handful of rows rather than the corpus. See the module docstring for why that matters and
        what it assumes.

        Yields:
            Normalised events.

        Raises:
            CertFormatError: If a log is missing, its header is not one this reader understands,
                a timestamp will not parse, or a file's rows are not time-ordered.
        """
        skipped: Counter[str] = Counter()
        streams = [
            self._events_from(spec, builder, skipped)
            for spec, builder in (
                (LOGON_SPEC, _logon_event),
                (DEVICE_SPEC, _device_event),
                (HTTP_SPEC, _http_event),
                (EMAIL_SPEC, self._email_event),
                (FILE_SPEC, _file_event),
            )
        ]
        emitted = 0
        for event in heapq.merge(*streams, key=lambda event: event.timestamp):
            emitted += 1
            if emitted % _PROGRESS_EVERY == 0:
                logger.info("  read %d events (at %s)", emitted, event.timestamp.date())
            yield event
        logger.info("read %d events from release %s", emitted, self.release.name)
        for reason, count in sorted(skipped.items()):
            logger.warning("  skipped %d row(s): %s", count, reason)

    def catalogue(self) -> EntityCatalogue:
        """Read the release's LDAP directory into an `EntityCatalogue`."""
        return EntityCatalogue.from_ldap_directory(self.release.ldap_directory)

    def _email_event(self, row: dict[str, str], stamp: datetime) -> EnterpriseEvent | None:
        """Map an ``email.csv`` row onto a send, resolving the actor from the ``from`` address.

        Returns:
            The event, or ``None`` when the sender is not a known employee — inbound mail from
            outside the organisation, which is not an action by a monitored user. The caller counts
            those rather than discarding them silently.
        """
        sender = row.get("from", "").strip().lower()
        user_id = self.email_senders.get(sender)
        if user_id is None:
            return None
        recipients = [
            address.strip()
            for address in row.get("to", "").split(DETAIL_VALUE_SEPARATOR)
            if address.strip()
        ]
        domains = sorted({domain for address in recipients if (domain := domain_of(address))})
        return EnterpriseEvent(
            timestamp=stamp,
            user_id=user_id,
            event_kind=EventKind.EMAIL_SEND,
            details={
                **_base_details(row),
                DETAIL_SENDER: sender,
                DETAIL_RECIPIENTS: DETAIL_VALUE_SEPARATOR.join(recipients),
                DETAIL_RECIPIENT_DOMAINS: DETAIL_VALUE_SEPARATOR.join(domains),
            },
        )

    def _events_from(
        self,
        spec: LogSpec,
        builder: Callable[[dict[str, str], datetime], EnterpriseEvent | None],
        skipped: Counter[str],
    ) -> Iterator[EnterpriseEvent]:
        """Stream one log, checking its header once and its ordering as it goes."""
        path = self.release.path_for(spec)
        for row, stamp in _rows(path, spec):
            event = builder(row, stamp)
            if event is None:
                skipped[f"{spec.filename}: sender is not a known employee"] += 1
                continue
            yield event


def _rows(path: Path, spec: LogSpec) -> Iterator[tuple[dict[str, str], datetime]]:
    """Stream one activity log's rows with their parsed timestamps.

    Reads with `csv.reader` and indexes by position rather than using `csv.DictReader`, so a row
    costs one small dict of the columns actually wanted instead of one dict of every column. That
    matters here and nowhere else in PHOS: r3.1's ``http.csv`` is 11 GB, nearly all of it the
    free-text ``content`` column, which is parsed once and never touched. The ``ignored`` columns
    on a `LogSpec` are therefore genuinely ignored rather than materialised and discarded.

    Positional reading is safe because every column this reader wants precedes the free-text ones,
    which are always last — so an unquoted comma inside ``content`` lengthens a row without
    shifting anything that is read.

    Raises:
        CertFormatError: If the file is missing or empty, the header is unreadable, a row is too
            short to hold its own columns, a timestamp will not parse, or the rows are not in
            non-decreasing timestamp order.
    """
    if not path.is_file():
        raise CertFormatError(f"activity log not found: {path}")

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        raw_header = next(reader, None)
        if raw_header is None:
            raise CertFormatError(f"{path}: file is empty")
        indexes = _check_header([name.strip() for name in raw_header], path, spec)
        widest = max(indexes.values())

        previous: datetime | None = None
        for line_number, raw in enumerate(reader, start=2):
            if len(raw) <= widest:
                raise CertFormatError(
                    f"{path}:{line_number}: row has {len(raw)} field(s), too few to hold the "
                    f"{len(raw_header)} the header declares; it cannot be read positionally"
                )
            row = {name: raw[index].strip() for name, index in indexes.items()}
            stamp = _parse_timestamp(row["date"], path, line_number)
            if previous is not None and stamp < previous:
                raise CertFormatError(
                    f"{path}:{line_number}: rows are not time-ordered ({stamp} follows "
                    f"{previous}). This reader merges the logs by streaming them in parallel, "
                    "which assumes each is sorted; an unsorted log would silently produce an "
                    "out-of-order event stream."
                )
            previous = stamp
            yield row, stamp


def _check_header(header: Sequence[str], path: Path, spec: LogSpec) -> dict[str, int]:
    """Refuse a header that is missing a required column or carries an unfamiliar one.

    Returns:
        ``{required column: position}``, which is what lets rows be read positionally.

    Raises:
        CertFormatError: In either failure case, naming exactly what was wrong and what was found.
    """
    present = set(header)
    missing = spec.required - present
    if missing:
        raise CertFormatError(
            f"{path}: missing required column(s) {', '.join(sorted(missing))}; the file has: "
            f"{', '.join(header) or '(no header)'}"
        )
    unknown = present - spec.known_columns()
    if unknown:
        raise CertFormatError(
            f"{path}: unrecognised column(s) {', '.join(sorted(unknown))}. This reader accounts "
            f"for {', '.join(sorted(spec.known_columns()))}; a release with a different schema "
            "must have the reader taught it rather than have the column silently dropped."
        )
    return {name: header.index(name) for name in sorted(spec.required)}


def _parse_timestamp(text: str, path: Path, line_number: int) -> datetime:
    """Parse a CERT timestamp as UTC.

    Raises:
        CertFormatError: If the cell is blank or does not match `CERT_TIMESTAMP_FORMAT`.
    """
    if not text:
        raise CertFormatError(f"{path}:{line_number}: empty date cell")
    try:
        return datetime.strptime(text, CERT_TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError as error:
        raise CertFormatError(
            f"{path}:{line_number}: date {text!r} does not match {CERT_TIMESTAMP_FORMAT!r}: {error}"
        ) from error


def _base_details(row: dict[str, str]) -> dict[str, str]:
    """Return the details every log contributes: the source record id and the machine."""
    return {DETAIL_EVENT_ID: row.get("id", ""), DETAIL_PC: row.get("pc", "")}


def _logon_event(row: dict[str, str], stamp: datetime) -> EnterpriseEvent:
    """Map a ``logon.csv`` row onto a `EventKind.LOGON` or `EventKind.LOGOFF`."""
    activity = row.get("activity", "")
    kind = _LOGON_ACTIVITIES.get(activity.lower())
    if kind is None:
        raise CertFormatError(
            f"logon.csv: unrecognised activity {activity!r}; expected one of "
            f"{', '.join(sorted(_LOGON_ACTIVITIES))}"
        )
    return EnterpriseEvent(
        timestamp=stamp,
        user_id=row.get("user", ""),
        event_kind=kind,
        details={**_base_details(row), DETAIL_ACTIVITY: activity},
    )


def _device_event(row: dict[str, str], stamp: datetime) -> EnterpriseEvent:
    """Map a ``device.csv`` row onto a removable-media connect or disconnect."""
    activity = row.get("activity", "")
    kind = _DEVICE_ACTIVITIES.get(activity.lower())
    if kind is None:
        raise CertFormatError(
            f"device.csv: unrecognised activity {activity!r}; expected one of "
            f"{', '.join(sorted(_DEVICE_ACTIVITIES))}"
        )
    return EnterpriseEvent(
        timestamp=stamp,
        user_id=row.get("user", ""),
        event_kind=kind,
        details={**_base_details(row), DETAIL_ACTIVITY: activity},
    )


def _http_event(row: dict[str, str], stamp: datetime) -> EnterpriseEvent:
    """Map an ``http.csv`` row onto a request, normalising the host once, here."""
    url = row.get("url", "")
    return EnterpriseEvent(
        timestamp=stamp,
        user_id=row.get("user", ""),
        event_kind=EventKind.HTTP_REQUEST,
        details={**_base_details(row), DETAIL_URL: url, DETAIL_URL_HOST: host_of(url)},
    )


def _file_event(row: dict[str, str], stamp: datetime) -> EnterpriseEvent:
    """Map a ``file.csv`` row onto a file access."""
    return EnterpriseEvent(
        timestamp=stamp,
        user_id=row.get("user", ""),
        event_kind=EventKind.FILE_ACCESS,
        details={**_base_details(row), DETAIL_FILENAME: row.get("filename", "")},
    )
