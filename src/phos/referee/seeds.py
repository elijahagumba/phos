"""Seed pools for the referee's exams: development, public, private and retired.

PART S6. Four pools, four files, each named by an environment variable so none of them has to
live inside the repository:

- ``PHOS_SEEDS_DEV`` — open, used while building and testing detectors.
- ``PHOS_SEEDS_PUBLIC`` — published scenarios, anyone may tune against these.
- ``PHOS_SEEDS_PRIVATE`` — the secret exam. Never read by anything that is being tuned.
- ``PHOS_SEEDS_RETIRED`` — seeds a private exam has already used. A retired seed has been seen by
  whoever ran that exam, so it can no longer stand in for a secret, and only a retired seed may
  later be copied into the public pool by a human publishing it.

**A seed may never appear in more than one pool.** `SeedVault.check_disjoint` is the enforcement;
it is not a convention anyone has to remember. **Sealed generator families are for the private
exam only** — `assert_no_sealed_in_open_pools` is the check that a development or public seed
never draws from one, and it is a referee-owned concern precisely because `phos.synth.families`
says so in its own docstring: a generator that knew which of its plants were the exam could favour
them, so it is this package, not that one, that is allowed to ask the sealed question.

**Pool files are never committed.** They are seed numbers, not data, but a seed number that names
which plants are secret is itself the secret. Every path this module writes to lives wherever the
environment variable points — see ``docs/referee/recon.md`` for why none of the fixtures below
point inside the repository — and `.gitignore` carries a defensive pattern in case one ever does:
a file is a seed vault to this convention only if its name ends in ``.seedvault.json``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.synth.families import SEALED_ENV_VAR, FamilyError, get_family

__all__ = [
    "DEV_ENV_VAR",
    "PRIVATE_ENV_VAR",
    "PUBLIC_ENV_VAR",
    "RETIRED_ENV_VAR",
    "SeedEntry",
    "SeedPool",
    "SeedVault",
    "SeedVaultError",
    "assert_no_sealed_in_open_pools",
]

DEV_ENV_VAR: Final = "PHOS_SEEDS_DEV"
PUBLIC_ENV_VAR: Final = "PHOS_SEEDS_PUBLIC"
PRIVATE_ENV_VAR: Final = "PHOS_SEEDS_PRIVATE"
RETIRED_ENV_VAR: Final = "PHOS_SEEDS_RETIRED"


class SeedVaultError(ValueError):
    """Raised when a seed pool cannot be loaded, or a pool invariant would be violated."""


class SeedPool(StrEnum):
    """The four pools a seed can live in, and never more than one at a time."""

    DEV = "dev"
    PUBLIC = "public"
    PRIVATE = "private"
    RETIRED = "retired"


_ENV_VAR_BY_POOL: Final[Mapping[SeedPool, str]] = {
    SeedPool.DEV: DEV_ENV_VAR,
    SeedPool.PUBLIC: PUBLIC_ENV_VAR,
    SeedPool.PRIVATE: PRIVATE_ENV_VAR,
    SeedPool.RETIRED: RETIRED_ENV_VAR,
}


class SeedEntry(BaseModel):
    """One (family, seed) pair living in exactly one pool.

    Attributes:
        family: The generator family id, e.g. ``"level_flow"``.
        seed: The plant's master seed.
    """

    model_config = ConfigDict(frozen=True)

    family: str = Field(min_length=1)
    seed: int

    def key(self) -> tuple[str, int]:
        """Return the identity a seed is compared and retired by."""
        return (self.family, self.seed)


class SeedVault:
    """Four pool files on disk, loaded, checked and retired as one unit.

    Nothing here generates a plant or runs an exam; it only answers which seeds exist and which
    pool each belongs to. `phos.referee.exam` is where a pool becomes an `Exam`.
    """

    def __init__(self, paths: Mapping[SeedPool, Path]) -> None:
        """Construct a vault from explicit paths, one per pool.

        Raises:
            SeedVaultError: If a pool has no path.
        """
        missing = [pool.value for pool in SeedPool if pool not in paths]
        if missing:
            raise SeedVaultError(f"no path given for pool(s): {', '.join(missing)}")
        self._paths: dict[SeedPool, Path] = dict(paths)

    @classmethod
    def from_env(cls) -> SeedVault:
        """Construct a vault from the four ``PHOS_SEEDS_*`` environment variables.

        Raises:
            SeedVaultError: If any of the four is unset.
        """
        missing = [name for name in _ENV_VAR_BY_POOL.values() if not os.environ.get(name)]
        if missing:
            raise SeedVaultError(
                f"environment variable(s) not set: {', '.join(missing)}; a seed vault needs all "
                "four pools named, even a retired or public pool that is empty so far"
            )
        return cls({pool: Path(os.environ[name]) for pool, name in _ENV_VAR_BY_POOL.items()})

    def path(self, pool: SeedPool) -> Path:
        """Return the file backing one pool."""
        return self._paths[pool]

    def load(self, pool: SeedPool) -> tuple[SeedEntry, ...]:
        """Return a pool's entries, or an empty tuple if its file does not exist yet.

        Raises:
            SeedVaultError: If the file exists but is not valid JSON, or does not hold a list of
                seed entries.
        """
        path = self._paths[pool]
        if not path.exists():
            return ()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SeedVaultError(f"{path}: not valid JSON: {error}") from error
        if not isinstance(raw, list):
            raise SeedVaultError(f"{path}: expected a JSON list of seed entries")
        try:
            return tuple(SeedEntry.model_validate(item) for item in raw)
        except Exception as error:  # re-raised narrowly below: any shape here is a vault error
            raise SeedVaultError(f"{path}: not a list of seed entries: {error}") from error

    def all_pools(self) -> dict[SeedPool, tuple[SeedEntry, ...]]:
        """Return every pool's entries, keyed by pool."""
        return {pool: self.load(pool) for pool in SeedPool}

    def check_disjoint(self) -> None:
        """Raise if any ``(family, seed)`` pair appears in more than one pool.

        Raises:
            SeedVaultError: Naming the colliding key and both pools it was found in.
        """
        seen: dict[tuple[str, int], SeedPool] = {}
        for pool in SeedPool:
            for entry in self.load(pool):
                key = entry.key()
                owner = seen.get(key)
                if owner is not None and owner is not pool:
                    raise SeedVaultError(
                        f"seed {key} appears in both {owner.value!r} and {pool.value!r}; a seed "
                        "may never appear in more than one pool"
                    )
                seen[key] = pool

    def _write(self, pool: SeedPool, entries: Sequence[SeedEntry]) -> None:
        """Overwrite one pool's file with ``entries``, sorted for a stable diff."""
        path = self._paths[pool]
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(entries, key=lambda entry: entry.key())
        path.write_text(
            json.dumps([entry.model_dump() for entry in ordered], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def add(self, pool: SeedPool, entries: Sequence[SeedEntry]) -> None:
        """Add entries to a pool, refusing a key that already exists anywhere in the vault.

        Raises:
            SeedVaultError: If any entry's key already lives in this or another pool.
        """
        self.check_disjoint()
        existing: dict[tuple[str, int], SeedPool] = {}
        for candidate_pool in SeedPool:
            for entry in self.load(candidate_pool):
                existing[entry.key()] = candidate_pool
        for entry in entries:
            if entry.key() in existing:
                raise SeedVaultError(
                    f"{entry.key()} already lives in {existing[entry.key()].value!r}; a seed may "
                    "never appear in more than one pool"
                )
        self._write(pool, (*self.load(pool), *entries))

    def retire(self, entries: Sequence[SeedEntry]) -> None:
        """Move ``entries`` from the private pool to the retired pool.

        A retired seed stops standing in for a secret, because retiring it is how this module
        records that some exam has already used it. Retiring is the only way a seed may later be
        published — see `phos.referee.release` once PART S10 exists.

        Raises:
            SeedVaultError: If any entry is not currently in the private pool.
        """
        private = list(self.load(SeedPool.PRIVATE))
        private_keys = {entry.key() for entry in private}
        for entry in entries:
            if entry.key() not in private_keys:
                raise SeedVaultError(f"{entry.key()} is not in the private pool; cannot retire it")

        moving_keys = {entry.key() for entry in entries}
        remaining_private = [entry for entry in private if entry.key() not in moving_keys]
        retired = list(self.load(SeedPool.RETIRED))
        retired_keys = {entry.key() for entry in retired}
        newly_retired = [*retired, *(entry for entry in entries if entry.key() not in retired_keys)]

        self._write(SeedPool.PRIVATE, remaining_private)
        self._write(SeedPool.RETIRED, newly_retired)
        self.check_disjoint()


def assert_no_sealed_in_open_pools(vault: SeedVault) -> None:
    """Raise if a development or public pool entry draws from a sealed generator family.

    Sealed families exist so the generator cannot know which plants are the private exam; this is
    the referee-owned other half of that rule — checking that nobody has put a sealed family's
    seed where it would be tuned against. The check briefly allows sealed families to load so it
    can ask each one whether it is sealed, and restores the environment exactly as it found it
    whether or not the assertion holds.

    Args:
        vault: The vault to check.

    Raises:
        SeedVaultError: Naming the pool, the seed and the sealed family.
    """
    previous = os.environ.get(SEALED_ENV_VAR)
    os.environ[SEALED_ENV_VAR] = "1"
    try:
        for pool in (SeedPool.DEV, SeedPool.PUBLIC):
            for entry in vault.load(pool):
                try:
                    family = get_family(entry.family)
                except FamilyError:
                    continue
                if family.sealed:
                    raise SeedVaultError(
                        f"{pool.value} pool entry {entry.key()} draws from sealed family "
                        f"{entry.family!r}; sealed families are for the private exam only"
                    )
    finally:
        if previous is None:
            os.environ.pop(SEALED_ENV_VAR, None)
        else:
            os.environ[SEALED_ENV_VAR] = previous
