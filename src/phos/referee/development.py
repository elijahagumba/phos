"""The published development pool: seeds anyone may build a detector against.

This is the counterpart to `phos.referee.seeds`, and the difference is the whole point. A vault
pool is named by an environment variable and never committed, because the seeds in it are secret.
The development pool is the opposite: it is committed, published, and deliberately readable,
because a detector author with no plants to build against cannot build anything.

**What a development exam can and cannot tell you.** It tells you whether a detector runs, what it
alerts on, and how it compares with a baseline on plants whose seeds everybody has. It cannot tell
you whether the detector would catch an attack it has never seen, because every plant in it was
available to be tuned against by anyone, including its author. A number from this pool is a
description of behaviour, not a claim about unseen attacks, and nothing here may be cited as one.

**The pool is a file, not a vault.** `load` reads `data/development-pool.json` from the checkout.
There is no environment variable and no missing-file tolerance: a repository without its
development pool is broken, not merely unconfigured, and a silent empty pool would look exactly
like a pool whose seeds were all refused.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.referee.exam import DEFAULT_EXAM_SIZE, Exam, ExamEntry, ExamError
from phos.referee.seeds import SeedEntry, SeedPool

__all__ = [
    "DEVELOPMENT_POOL_PATH",
    "DevelopmentPool",
    "DevelopmentPoolError",
    "PoolEntry",
    "development_exam",
    "load",
]

#: Where the published pool lives, relative to the checkout root.
DEVELOPMENT_POOL_PATH: Final = Path("data") / "development-pool.json"


class DevelopmentPoolError(ValueError):
    """Raised when the development pool cannot be read, or is not what it says it is."""


class PoolEntry(BaseModel):
    """One published seed.

    Attributes:
        family: The generator family id.
        seed: The plant's master seed. Published on purpose.
    """

    model_config = ConfigDict(frozen=True)

    family: str = Field(min_length=1)
    seed: int

    def as_seed_entry(self) -> SeedEntry:
        """Return this row as the `SeedEntry` the rest of the referee speaks in."""
        return SeedEntry(family=self.family, seed=self.seed)


class DevelopmentPool(BaseModel):
    """The whole file.

    Attributes:
        pool: Always ``"dev"``. A file claiming to be a private pool is refused, because a secret
            seed in a committed file is the failure this module exists to prevent.
        entries: The published seeds.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pool: str
    entries: tuple[PoolEntry, ...] = Field(min_length=1)


def load(root: Path) -> DevelopmentPool:
    """Read the published pool from a checkout.

    Args:
        root: The checkout root.

    Returns:
        The pool.

    Raises:
        DevelopmentPoolError: If the file is missing, will not parse, does not match the schema,
            or claims to be a pool other than ``dev``.
    """
    path = root / DEVELOPMENT_POOL_PATH
    if not path.is_file():
        raise DevelopmentPoolError(
            f"{DEVELOPMENT_POOL_PATH.as_posix()} is missing from {root}. A checkout without its "
            "development pool cannot run a development exam, and an empty pool would look the "
            "same as one whose seeds were all refused"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DevelopmentPoolError(
            f"{DEVELOPMENT_POOL_PATH.as_posix()} will not parse: {error}"
        ) from error
    try:
        pool = DevelopmentPool.model_validate(raw)
    except Exception as error:
        raise DevelopmentPoolError(
            f"{DEVELOPMENT_POOL_PATH.as_posix()} does not match the schema: {error}"
        ) from error
    if pool.pool != SeedPool.DEV.value:
        raise DevelopmentPoolError(
            f"{DEVELOPMENT_POOL_PATH.as_posix()} describes a {pool.pool!r} pool. Only a "
            "development pool may be committed: a public or private pool in the repository would "
            "publish, or disclose the existence of, seeds that are meant to be secret"
        )
    return pool


def development_exam(
    pool: DevelopmentPool,
    *,
    scorer_version: str,
    code_version: str | None,
    size: int = DEFAULT_EXAM_SIZE,
    hours: float = 24.0,
) -> Exam:
    """Build an exam from the published pool.

    Args:
        pool: The pool, as `load` returned it.
        scorer_version: Recorded on the exam.
        code_version: Recorded on the exam.
        size: How many entries to take, from the start of the file in its own order.
        hours: How long each plant's run simulates.

    Returns:
        The exam. Its id is a function of its content, like any other exam's.

    Raises:
        ExamError: If the pool holds fewer entries than ``size``.
    """
    if len(pool.entries) < size:
        raise ExamError(
            f"the development pool holds {len(pool.entries)} seed(s), fewer than the {size} an "
            "exam of this size needs"
        )
    entries = tuple(
        ExamEntry(
            family=entry.family,
            seed=entry.seed,
            hours=hours,
            event_seed=entry.seed,
            pool=SeedPool.DEV,
        )
        for entry in pool.entries[:size]
    )
    return Exam.build(entries, scorer_version, code_version)
