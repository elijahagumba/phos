"""Bounded request/response pairing.

The caller supplies the transaction id as bytes and says which observation is
the request. This module does not know Modbus, and it does not write into a
`ModbusMessage`. An open pair that ages out is returned as a miss and only
then dropped. ADR 0345.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.packet.reassembly import FlowKey

__all__ = [
    "EXPIRED",
    "MAX_OPEN_PAIRS",
    "PAIR_CAP",
    "PAIR_EXPIRY",
    "SUPERSEDED",
    "UNSOLICITED",
    "PairMatch",
    "PairMiss",
    "PairMissReason",
    "PairTable",
    "PairWaiting",
]

MAX_OPEN_PAIRS: Final = 256
"""Most unmatched requests one flow may hold. ADR 0345."""

PAIR_EXPIRY: Final = timedelta(seconds=60)
"""How far apart, in capture time, a pair may still match. ADR 0345."""


class PairMissReason(str):
    """Why a pair was not completed. A string subclass so tests can match the literal."""


PAIR_CAP: Final[PairMissReason] = PairMissReason("PAIR_CAP")
EXPIRED: Final[PairMissReason] = PairMissReason("EXPIRED")
UNSOLICITED: Final[PairMissReason] = PairMissReason("UNSOLICITED")
SUPERSEDED: Final[PairMissReason] = PairMissReason("SUPERSEDED")


@dataclass(frozen=True)
class PairMiss:
    """A pair that will not complete, recorded before it is dropped.

    Attributes:
        key: The flow.
        tx_id: The transaction id the caller supplied.
        reason: Cap, expiry, a response with no request, or a request replaced.
    """

    key: FlowKey
    tx_id: bytes
    reason: PairMissReason


@dataclass(frozen=True)
class PairMatch:
    """A request and the later response that named the same transaction id.

    Attributes:
        key: The flow.
        tx_id: The transaction id.
        request: The token stored with the request. Opaque to this module.
        response: The token offered with the response.
    """

    key: FlowKey
    tx_id: bytes
    request: object
    response: object


@dataclass(frozen=True)
class PairWaiting:
    """A request stored, with no response yet.

    Attributes:
        key: The flow.
        tx_id: The transaction id.
    """

    key: FlowKey
    tx_id: bytes


@dataclass
class _Open:
    """One unmatched request."""

    at: datetime
    token: object


class PairTable:
    """Pairs observations inside `MAX_OPEN_PAIRS` and `PAIR_EXPIRY`."""

    def __init__(self) -> None:
        """Start with nothing open."""
        self._open: dict[tuple[FlowKey, bytes], _Open] = {}

    def open_count(self, key: FlowKey) -> int:
        """How many requests are unmatched on ``key``."""
        return sum(1 for flow, _tx in self._open if flow == key)

    def offer(
        self,
        key: FlowKey,
        tx_id: bytes,
        *,
        is_request: bool,
        at: datetime,
        token: object,
    ) -> tuple[PairMiss | PairMatch | PairWaiting, ...]:
        """Offer one observation.

        Expiry is applied first, against ``at``. A response with no stored
        request is an `UNSOLICITED` miss and is not stored. A second request
        for the same id records the first as `SUPERSEDED` and stores the new
        one. The 257th open request on the flow is a `PAIR_CAP` miss and is
        not stored.

        Args:
            key: The flow. Both directions of a conversation share one key if
                the caller wants them paired; this module does not reverse it.
            tx_id: The protocol's transaction id, already bytes.
            is_request: True when the caller says this observation is the request.
            at: Capture timestamp. Must be timezone-aware.
            token: Whatever the caller wants back when the pair completes.

        Returns:
            The misses that were dropped, then the outcome of this observation.

        Raises:
            ValueError: If ``at`` is naive. That is a caller bug, not a capture.
        """
        if at.tzinfo is None:
            raise ValueError("capture time must be timezone-aware")
        events: list[PairMiss | PairMatch | PairWaiting] = []
        self._expire(at, events)
        slot = (key, tx_id)
        if is_request:
            previous = self._open.get(slot)
            if previous is not None:
                events.append(PairMiss(key, tx_id, SUPERSEDED))
                del self._open[slot]
            if self.open_count(key) >= MAX_OPEN_PAIRS:
                events.append(PairMiss(key, tx_id, PAIR_CAP))
                return tuple(events)
            self._open[slot] = _Open(at, token)
            events.append(PairWaiting(key, tx_id))
            return tuple(events)

        previous = self._open.get(slot)
        if previous is None:
            events.append(PairMiss(key, tx_id, UNSOLICITED))
            return tuple(events)
        del self._open[slot]
        events.append(PairMatch(key, tx_id, previous.token, token))
        return tuple(events)

    def _expire(self, at: datetime, events: list[PairMiss | PairMatch | PairWaiting]) -> None:
        """Drop open requests more than `PAIR_EXPIRY` behind ``at``, and record each."""
        stale = [
            (slot, open_pair)
            for slot, open_pair in self._open.items()
            if at - open_pair.at > PAIR_EXPIRY
        ]
        for (key, tx_id), _open_pair in stale:
            del self._open[(key, tx_id)]
            events.append(PairMiss(key, tx_id, EXPIRED))
