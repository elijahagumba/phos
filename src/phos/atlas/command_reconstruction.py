"""Reconstruct a command as a research object: who, what, path, when, state, expected, aftermath.

This is not a lead-rate. Completeness is how much of the story was filled in. Known-station
0/16 and unknown-master 1/4 stay the ranking freeze. Do not retune ``atlas/templates.py``.
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "CommandReconstruction",
    "IssuerKind",
    "reconstruction_completeness",
    "reconstructions_from_attack_config",
]

_COMMAND_TYPES: Final[frozenset[str]] = frozenset({"ROGUE_COMMAND", "MIMIC_COMMAND"})
_KNOWN_ISSUERS: Final[frozenset[str]] = frozenset({"scada", "hmi"})
_UNKNOWN_ISSUERS: Final[frozenset[str]] = frozenset({"engineering"})


class IssuerKind(StrEnum):
    """Issuer class from the *learned graph*, not from the attack-type name."""

    KNOWN_STATION = "known_station"
    UNKNOWN_MASTER = "unknown_master"
    UNKNOWN = "unknown"


class CommandReconstruction(BaseModel):
    """One command, reconstructed as far as the files allow.

    ``lead_rate`` is always ``None``. Ranking contracts live in the breaking reports, not here.
    """

    model_config = ConfigDict(frozen=True)

    issuer_id: str
    issuer_kind: IssuerKind
    function: str
    path: tuple[str, ...] = ()
    timestamp: datetime
    plant_state: str | None = None
    expected: bool | None = None
    downstream_observation_ids: tuple[str, ...] = ()
    lead_rate: None = None


def reconstruction_completeness(record: CommandReconstruction) -> float:
    """Return the fraction of reconstruction slots that are filled.

    Slots: issuer, function, path (non-empty), timestamp (always present), plant_state,
    expected, downstream observations. Completeness is not unique lead.
    """
    slots = (
        bool(record.issuer_id),
        bool(record.function),
        bool(record.path),
        record.timestamp is not None,
        record.plant_state is not None,
        record.expected is not None,
        bool(record.downstream_observation_ids),
    )
    return sum(1.0 for filled in slots if filled) / float(len(slots))


def reconstructions_from_attack_config(path: Path) -> tuple[CommandReconstruction, ...]:
    """Build reconstruction records from a D2 attack TOML.

    Completeness is diagnostic. ``lead_rate`` stays ``None``. This does not retune templates
    and it does not invent a public command corpus. Path, plant state, and downstream
    observations are typically empty in these configs -- that incompleteness is the result.
    """
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    start = raw["start"]
    if not isinstance(start, datetime):
        raise ValueError(f"{path} start is not a datetime")
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    records: list[CommandReconstruction] = []
    for attack in raw.get("attacks", []):
        kind = str(attack.get("type", ""))
        if kind not in _COMMAND_TYPES:
            continue
        issuer = str(attack.get("issuer", ""))
        if issuer in _KNOWN_ISSUERS:
            issuer_kind = IssuerKind.KNOWN_STATION
        elif issuer in _UNKNOWN_ISSUERS:
            issuer_kind = IssuerKind.UNKNOWN_MASTER
        else:
            issuer_kind = IssuerKind.UNKNOWN
        hours = float(attack["start_hours"])
        records.append(
            CommandReconstruction(
                issuer_id=issuer,
                issuer_kind=issuer_kind,
                function=kind,
                path=(),
                timestamp=start + timedelta(hours=hours),
                plant_state=None,
                expected=False,
                downstream_observation_ids=(),
                lead_rate=None,
            )
        )
    return tuple(records)
