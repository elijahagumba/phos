"""The sealed batch registry: what a sealed batch is registered as, without its seeds.

`data/registry.json` is the catalogue of public corpora. Every entry there has a homepage, a
licence and a fetchable URL, and several tests assert its exact contents because it is the list
the tier resolver reads. A sealed synthetic batch is not any of those things: it has no homepage,
no licence, no URL, and its whole point is that no file of it is anywhere a repository can reach.
Putting one in that registry would have meant weakening tests about public corpora to make room
for something that is not one.

So sealed batches have their own file, `data/sealed-registry.json`, with their own schema. It
holds what can safely be committed: the fingerprint, the family, the count, who generated it and
when, and the fact that the payload is on the encrypted volume. It holds no seed, no plant id and
no path into a corpus.

**What this registry can and cannot prove.** It proves which set of seeds a batch is, because the
fingerprint is checked against the seeds at every run. It does not prove the batch was generated
honestly, and it does not prove the plants are any good. It is an identity, not an audit.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from phos.referee.sealed_batch import fingerprint
from phos.referee.seeds import SeedEntry

__all__ = [
    "REGISTRY_PATH",
    "SCHEMA_VERSION",
    "SealedBatchEntry",
    "SealedRegistry",
    "SealedRegistryError",
    "load",
]

#: Where the registry lives, relative to the checkout root.
REGISTRY_PATH: Final = Path("data") / "sealed-registry.json"

#: The registry's shape. Bumped if a field's meaning changes.
SCHEMA_VERSION: Final = 1


class SealedRegistryError(ValueError):
    """Raised when the sealed registry cannot be read or a batch is not registered in it."""


class SealedBatchEntry(BaseModel):
    """One sealed batch, as the registry records it.

    Attributes:
        name: The batch's identifier, e.g. ``phos-referee-sealed-1``.
        family: The sealed generator family every plant in the batch draws from.
        plants: How many plants the batch holds.
        fingerprint: The SHA-256 digest over the sorted ``(family, seed)`` pairs. Never a seed.
        generated_on: When the batch was generated, or ``None`` while it has not been.
        generated_by: Who ran the generation, as they named themselves.
        payload: Where the payload is, described rather than pathed. A description, because a
            path into an encrypted volume is useless to anyone reading this file and would tell a
            reader where the volume is mounted.
        note: Anything a reader must know about this batch in particular.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    plants: int = Field(ge=1)
    fingerprint: str = Field(min_length=64, max_length=64)
    generated_on: date | None = None
    generated_by: str = ""
    payload: str = ""
    note: str = ""

    @field_validator("fingerprint")
    @classmethod
    def _fingerprint_is_hex(cls, value: str) -> str:
        """Refuse a digest that is not 64 lowercase hex characters.

        A digest in the wrong case or with a stray character would silently never match, and the
        failure would appear as a refused run rather than as the typo it is.

        Args:
            value: The digest as written.

        Returns:
            The same digest, unchanged.

        Raises:
            ValueError: If it is not 64 lowercase hex characters.
        """
        if set(value) - set("0123456789abcdef"):
            raise ValueError(f"{value!r} is not a lowercase hex SHA-256 digest")
        return value


class SealedRegistry(BaseModel):
    """The whole file.

    Attributes:
        schema_version: The registry's shape.
        batches: Every sealed batch, in the order they were registered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    batches: tuple[SealedBatchEntry, ...] = ()


def load(root: Path) -> SealedRegistry:
    """Read the registry, refusing a missing or malformed file rather than defaulting to empty.

    A default of empty would mean "no batch is registered", which is indistinguishable from a
    registry that failed to load, and the difference matters: the first is a normal state and the
    second is a reason to stop.

    Args:
        root: The checkout root.

    Returns:
        The registry.

    Raises:
        SealedRegistryError: If the file is absent, will not parse, or does not match the schema.
    """
    path = root / REGISTRY_PATH
    if not path.is_file():
        raise SealedRegistryError(f"{REGISTRY_PATH.as_posix()} is missing from {root}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SealedRegistryError(f"{REGISTRY_PATH.as_posix()} will not parse: {error}") from error
    try:
        return SealedRegistry.model_validate(raw)
    except Exception as error:
        raise SealedRegistryError(
            f"{REGISTRY_PATH.as_posix()} does not match the schema: {error}"
        ) from error


def find(registry: SealedRegistry, name: str) -> SealedBatchEntry:
    """Return one batch by name.

    Args:
        registry: The registry.
        name: The batch's identifier.

    Returns:
        The entry.

    Raises:
        SealedRegistryError: If no batch has that name.
    """
    for entry in registry.batches:
        if entry.name == name:
            return entry
    raise SealedRegistryError(f"no sealed batch named {name!r} is registered")


def entry_for(name: str, entries: Sequence[SeedEntry], **details: object) -> SealedBatchEntry:
    """Build a registry entry from a batch's seeds, computing the fingerprint here.

    Args:
        name: The batch's identifier.
        entries: The batch's pairs. Used only to compute the digest.
        **details: Passed through to `SealedBatchEntry`.

    Returns:
        The entry. The seeds are not stored.
    """
    return SealedBatchEntry(
        name=name,
        fingerprint=fingerprint(entries),
        plants=len(entries),
        **details,  # type: ignore[arg-type]
    )
