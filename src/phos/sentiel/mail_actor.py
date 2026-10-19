"""Who sent a CERT email, and which addresses it named.

r3.1's email log has no ``user`` column, so the actor is the directory user for
the ``from`` address. r4.2 adds ``user``, and also ``cc`` and ``bcc``. This module
is that rule. It does not score anything.
"""

from __future__ import annotations

from collections.abc import Mapping

from phos.sentiel.events import DETAIL_VALUE_SEPARATOR

__all__ = ["email_actor", "recipient_addresses"]


def email_actor(named_user: str, sender: str, senders: Mapping[str, str]) -> str | None:
    """Return the actor of one email row, or ``None`` for inbound mail.

    A non-empty ``named_user`` is the actor. When that cell is absent or blank,
    the actor is the directory user for ``sender``. An unknown sender with no
    named user is not an action by a monitored user.

    Args:
        named_user: The ``user`` cell, or ``""`` when the release has no such column.
        sender: The ``from`` address.
        senders: Lowercased address to user id, from the directory.
    """
    named = named_user.strip()
    if named:
        return named
    return senders.get(sender.strip().lower())


def recipient_addresses(row: Mapping[str, str], columns: tuple[str, ...]) -> list[str]:
    """Return the non-blank addresses in ``columns``, split on ';'.

    A missing column contributes nothing, so an r3.1 row that only has ``to``
    keeps the recipient list it already had.
    """
    found: list[str] = []
    for column in columns:
        for address in row.get(column, "").split(DETAIL_VALUE_SEPARATOR):
            cleaned = address.strip()
            if cleaned:
                found.append(cleaned)
    return found
