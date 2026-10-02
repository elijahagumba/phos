"""The normalised enterprise event: one shape for every kind of organisational activity log.

Atlas watches a plant's numbers — a matrix of continuous signals sampled on a clock. Sentiel
watches an organisation's *events*: discrete, irregular, spread across several log types, and
attributed to people rather than to instruments. That difference is why this type exists rather
than Sentiel reusing `phos.eval.LabelledCsvAdapter`, which reads exactly one labelled table.

The shape, and why:

- **One type across every log.** A logon, a thumb-drive insert, a file read, an email and an HTTP
  request all arrive as `EnterpriseEvent`. Everything downstream — featurisation, the entity
  catalogue, the evaluation — sees a single stream, so adding a sixth log type later changes the
  reader and nothing else.
- **Kind-specific fields live in `details`, keyed by the constants below.** They are ``str -> str``
  for the same reason `Entity.attributes` is: it stays serialisable, and no component can hide
  typed state in it. The reader is the only thing that writes them, so normalisation (lowercased
  hosts, extracted mail domains) happens exactly once, at the boundary.
- **An event is not an `Observation`.** It is raw input. `phos.sentiel.featurise` aggregates events
  into ontology `Observation`s; nothing else in PHOS should consume events directly.

This module holds no I/O and no CERT-specific knowledge. Reading a CERT release is
`phos.sentiel.cert`'s job.
"""

from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology import UtcDatetime

__all__ = [
    "DETAIL_ACTIVITY",
    "DETAIL_EVENT_ID",
    "DETAIL_FILENAME",
    "DETAIL_PC",
    "DETAIL_RECIPIENTS",
    "DETAIL_RECIPIENT_DOMAINS",
    "DETAIL_SENDER",
    "DETAIL_URL",
    "DETAIL_URL_HOST",
    "DETAIL_VALUE_SEPARATOR",
    "EnterpriseEvent",
    "EventKind",
    "domain_of",
    "host_of",
]


class EventKind(str, Enum):
    """What an enterprise actor did.

    ``str``-backed so it serialises to readable JSON, matching the ontology's enum convention.

    The set is deliberately the union of what the activity logs record, not a taxonomy of attacker
    behaviour: PHOS has no signatures (Constitution §3.4), so nothing here names an attack.
    """

    LOGON = "LOGON"
    LOGOFF = "LOGOFF"
    DEVICE_CONNECT = "DEVICE_CONNECT"
    DEVICE_DISCONNECT = "DEVICE_DISCONNECT"
    FILE_ACCESS = "FILE_ACCESS"
    EMAIL_SEND = "EMAIL_SEND"
    HTTP_REQUEST = "HTTP_REQUEST"


DETAIL_EVENT_ID = "event_id"
"""The source log's own opaque record id, kept so an `Observation` traces back to its rows."""

DETAIL_PC = "pc"
"""The machine the activity happened on."""

DETAIL_ACTIVITY = "activity"
"""The source log's raw activity word, kept verbatim beside the `EventKind` it mapped to.

Releases disagree about the wording — r2 writes ``Insert``/``Remove`` for removable media where
r3.1 writes ``Connect``/``Disconnect`` — so the mapped kind is what code reads and this is what an
operator checks the mapping against.
"""

DETAIL_FILENAME = "filename"
"""Path of the file touched by a `EventKind.FILE_ACCESS`."""

DETAIL_URL = "url"
"""The full URL of a `EventKind.HTTP_REQUEST`, verbatim."""

DETAIL_URL_HOST = "url_host"
"""Lowercased host of `DETAIL_URL`, normalised once by the reader."""

DETAIL_SENDER = "sender"
"""Lowercased address a `EventKind.EMAIL_SEND` was sent from.

Kept because it is the only actor field r3.1's email log has: the user id on the event was resolved
*from* it against the directory, and keeping it makes that resolution checkable.
"""

DETAIL_RECIPIENTS = "recipients"
"""Every address a `EventKind.EMAIL_SEND` went to — to, cc and bcc pooled."""

DETAIL_RECIPIENT_DOMAINS = "recipient_domains"
"""Distinct lowercased domains of `DETAIL_RECIPIENTS`, normalised once by the reader."""

DETAIL_VALUE_SEPARATOR = ";"
"""Separator for the multi-valued details above.

``details`` is ``str -> str`` by design, so a list is joined rather than nested. Semicolon because
it is what CERT's own email columns use, so a joined value reads like its source.
"""


class EnterpriseEvent(BaseModel):
    """One thing one user did at one instant, normalised out of one activity log.

    Attributes:
        timestamp: When it happened, UTC. Sources that record naive local times are interpreted as
            UTC by the reader, which documents that choice — see `phos.sentiel.cert`.
        user_id: The corpus's own identifier for the actor, e.g. ``"CSF0929"``. Kept in the
            corpus's vocabulary rather than translated to an `EntityId` here, so the raw stream
            stays checkable against the source file. `phos.sentiel.entities.user_entity_id`
            performs the translation where the ontology needs it.
        event_kind: What was done.
        details: Kind-specific fields, keyed by the ``DETAIL_*`` constants in this module.
            ``str -> str`` so it stays serialisable; multi-valued entries are joined with
            `DETAIL_VALUE_SEPARATOR`.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: UtcDatetime
    user_id: str
    event_kind: EventKind
    details: dict[str, str] = Field(default_factory=dict)


def host_of(url: str) -> str:
    """Return the lowercased host of ``url``, without its port.

    Args:
        url: A URL, with or without a scheme. CERT's http log carries fully-qualified URLs, but a
            schemeless value is accepted rather than silently yielding an empty host.

    Returns:
        The host, lowercased, or ``""`` when ``url`` is blank or carries no host at all.
    """
    text = url.strip()
    if not text:
        return ""
    # Without a scheme, urlsplit files the whole string under `path` and reports no host. Giving
    # it a protocol-relative form makes the leading segment a netloc, which is what it is.
    candidate = text if "://" in text else f"//{text}"
    return urlsplit(candidate).hostname or ""


def domain_of(address: str) -> str:
    """Return the lowercased domain of an email address.

    Args:
        address: An email address, possibly padded with whitespace.

    Returns:
        The part after the final ``@``, lowercased, or ``""`` when there is no ``@`` — which is
        how a malformed or empty cell is reported rather than guessed at.
    """
    text = address.strip().lower()
    _, separator, domain = text.rpartition("@")
    return domain if separator else ""
