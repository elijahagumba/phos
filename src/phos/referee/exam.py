"""The Exam: a frozen list of plants to run, identified by a hash of its own content.

PART S6. An exam is "append-only" because its id *is* a hash of its entries, its scorer version
and its code version: there is no way to change what an exam asks for without changing its id, so
`Exam.verify` refusing a mismatched id is the whole enforcement. Nothing here mutates an `Exam`
after construction — a different exam is a different object with a different id, never an edit in
place.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.referee.seeds import SeedPool, SeedVault

__all__ = [
    "DEFAULT_EXAM_SIZE",
    "Exam",
    "ExamEntry",
    "ExamError",
    "exam_hash",
    "make_exam",
]

DEFAULT_EXAM_SIZE: Final = 300
"""How many plants an exam holds, unless the caller asks for a different size."""


class ExamError(ValueError):
    """Raised when an exam cannot be built, loaded or verified as what it claims to be."""


class ExamEntry(BaseModel):
    """One plant to generate and score.

    Attributes:
        family: The generator family id.
        seed: The plant's master seed.
        hours: How long the run simulates.
        event_seed: Seeds the event schedule, kept apart from ``seed`` so that changing which
            events are planned can never move a physical parameter (`phos.synth.events.plan_events`
            takes the same two seeds apart for the same reason).
        pool: Which seed pool this entry was drawn from.
    """

    model_config = ConfigDict(frozen=True)

    family: str = Field(min_length=1)
    seed: int
    hours: float = Field(gt=0.0)
    event_seed: int
    pool: SeedPool

    def content_tuple(self) -> tuple[str, int, float, int, str]:
        """Return this entry as a fixed-order tuple, for hashing."""
        return (self.family, self.seed, self.hours, self.event_seed, self.pool.value)


class Exam(BaseModel):
    """A frozen record: which plants, which scorer, which code version.

    Attributes:
        exam_id: SHA-256 hex over every entry (in the order given), the scorer version and the
            code version. Computed, never supplied — see `Exam.build`.
        entries: The plants, in the order they were drawn. Order is part of the hash, so a
            re-sorted exam is a different exam.
        scorer_version: Identifies the scoring code that will grade this exam.
        code_version: The git commit the exam was built from, or ``None`` when it could not be
            determined (the same honesty `phos.synth.outputs.git_commit` already applies).
    """

    model_config = ConfigDict(frozen=True)

    exam_id: str = Field(min_length=64, max_length=64)
    entries: tuple[ExamEntry, ...] = Field(min_length=1)
    scorer_version: str = Field(min_length=1)
    code_version: str | None = None

    @model_validator(mode="after")
    def _check_hash(self) -> Self:
        expected = exam_hash(self.entries, self.scorer_version, self.code_version)
        if self.exam_id != expected:
            raise ValueError(
                f"exam_id {self.exam_id!r} does not match its own entries, scorer_version and "
                f"code_version (expected {expected!r}); the entries were edited after the exam "
                "was built, which an exam record must refuse"
            )
        return self

    @classmethod
    def build(
        cls, entries: Sequence[ExamEntry], scorer_version: str, code_version: str | None
    ) -> Exam:
        """Construct an exam and compute its id from its own content."""
        fixed = tuple(entries)
        return cls(
            exam_id=exam_hash(fixed, scorer_version, code_version),
            entries=fixed,
            scorer_version=scorer_version,
            code_version=code_version,
        )

    def to_json(self) -> str:
        """Return this exam as pretty, sorted-key JSON."""
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Exam:
        """Parse an exam, refusing one whose id does not match its own content.

        Raises:
            ExamError: Wrapping any validation failure, including a hash mismatch.
        """
        try:
            return cls.model_validate_json(text)
        except Exception as error:  # every failure here is an exam-record problem
            raise ExamError(f"not a valid exam record: {error}") from error


def exam_hash(entries: Sequence[ExamEntry], scorer_version: str, code_version: str | None) -> str:
    """Return the SHA-256 hex digest that identifies an exam's exact content.

    Deliberately over the entries *in the given order*, not sorted: `S9`'s real-data exam locks a
    test split the same way, and an exam whose plants are reordered is a different sequence to run
    even though it would grade the same.
    """
    digest = hashlib.sha256()
    digest.update(str(len(entries)).encode("utf-8"))
    for entry in entries:
        digest.update(b"\0")
        for part in entry.content_tuple():
            digest.update(b"\x1f")
            digest.update(str(part).encode("utf-8"))
    digest.update(b"\0scorer\0")
    digest.update(scorer_version.encode("utf-8"))
    digest.update(b"\0code\0")
    digest.update((code_version or "").encode("utf-8"))
    return digest.hexdigest()


def make_exam(
    vault: SeedVault,
    pool: SeedPool,
    scorer_version: str,
    code_version: str | None,
    *,
    size: int = DEFAULT_EXAM_SIZE,
    hours: float = 24.0,
) -> Exam:
    """Build an exam from the first ``size`` entries of one seed pool.

    Entries are taken in the pool file's own stored order (see `SeedVault._write`: sorted by
    ``(family, seed)`), which makes `make_exam` deterministic for a given pool file. The event
    schedule seed for each entry is the plant's own seed — events get their own named seed so they
    are not drawn from the plant's, but reusing the plant's number for it keeps one exam
    deterministic from one pool file with nothing extra to record alongside it.

    Args:
        vault: Where the pool lives.
        pool: Which pool to draw from.
        scorer_version: Recorded on the exam.
        code_version: Recorded on the exam.
        size: How many entries to take. Defaults to `DEFAULT_EXAM_SIZE`.
        hours: How long each plant's run simulates.

    Returns:
        The built exam.

    Raises:
        ExamError: If the pool holds fewer than ``size`` entries.
    """
    available = vault.load(pool)
    if len(available) < size:
        raise ExamError(
            f"the {pool.value!r} pool holds {len(available)} seed(s), fewer than the {size} "
            "an exam of this size needs"
        )
    chosen = available[:size]
    entries = tuple(
        ExamEntry(
            family=entry.family, seed=entry.seed, hours=hours, event_seed=entry.seed, pool=pool
        )
        for entry in chosen
    )
    return Exam.build(entries, scorer_version, code_version)
