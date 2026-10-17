"""The arena: research tasks, a budget enforced in code, and what a candidate may not touch.

Stage S3 of `docs/learning-engine.md` (ADR 0120), and the arena ADR 0117 promised. The 4 October
sandbox limited its agent to 25 scored runs in a prompt, not in code. Here a `ResearchTask`
declares at most three competing hypotheses and a run budget before anything is scored, and
`AttemptLog`, an append-only hash-chained file like the learning ledger, refuses an attempt past
that budget. Every attempt, failures included, is a line in it.

Two checks keep the fast loop away from the slow gate:

* `forbidden_candidate_paths`: a candidate's diff may only touch its own directory under
  ``experiments/arena/<task>/<hypothesis>/``. The scorer, the gate, the registry, the records and
  the frozen detector are outside it by construction.
* `payloads_present`: lists any data file of a ``validation`` or ``held-out`` corpus found in a
  worktree. A fresh git worktree has none, because data is never committed (ADR 0006).

Nothing here scores a detector or promotes one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.eval.learning_records import GENESIS_HASH, LearningRecord, sha256_text
from phos.ontology.ids import UtcDatetime, utc_now

__all__ = [
    "ARENA_ROOT",
    "MAX_HYPOTHESES",
    "MAX_RUNS_PER_HYPOTHESIS",
    "Attempt",
    "AttemptLog",
    "BudgetExhaustedError",
    "Hypothesis",
    "ResearchTask",
    "candidate_sha256",
    "forbidden_candidate_paths",
    "payloads_present",
]

#: Where candidates live. A candidate's diff may touch only its own directory under here.
ARENA_ROOT: Final = "experiments/arena"
#: ADR 0084's precedent: at most three competing candidates, declared before any score.
MAX_HYPOTHESES: Final = 3
#: The sandbox's budget, now enforced.
MAX_RUNS_PER_HYPOTHESIS: Final = 25


class BudgetExhaustedError(ValueError):
    """Raised when an attempt would exceed its hypothesis's declared run budget."""


class Hypothesis(BaseModel):
    """One competing explanation of a failure, and the change that would test it.

    Attributes:
        id: Short slug, unique within the task; also the candidate's directory name.
        statement: What the hypothesis says is wrong.
        change: What a candidate under it may vary.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    statement: str = Field(min_length=1)
    change: str = Field(min_length=1)


class ResearchTask(BaseModel):
    """A failure turned into bounded research, declared before any arena run.

    Attributes:
        id: Short slug; the task's directory name.
        opened_at: When it was declared.
        learning_record_ids: The eligible learning records that motivate it (their decision ids).
        mechanism: The diagnosed mechanism they share.
        capability: What the task tries to improve.
        competing_explanations: Other explanations of the failure, kept in view.
        hypotheses: One to three competing hypotheses.
        runs_per_hypothesis: The scored-run budget for each.
        expected_benefit: What a success would change.
        expected_regressions: What a success might break.
        regression_slices: Slices the scorecard must not get worse on.
        evaluation_plan: How a candidate is judged, and what reaches the gate.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,59}$")
    opened_at: UtcDatetime = Field(default_factory=utc_now)
    learning_record_ids: tuple[str, ...] = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    competing_explanations: tuple[str, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = Field(min_length=1, max_length=MAX_HYPOTHESES)
    runs_per_hypothesis: int = Field(ge=1, le=MAX_RUNS_PER_HYPOTHESIS)
    expected_benefit: str = Field(min_length=1)
    expected_regressions: str = Field(min_length=1)
    regression_slices: tuple[str, ...] = Field(min_length=1)
    evaluation_plan: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [h.id for h in self.hypotheses]
        if len(set(ids)) != len(ids):
            raise ValueError("hypothesis ids must be unique within a task")
        return self

    def hypothesis(self, hypothesis_id: str) -> Hypothesis:
        """Return the declared hypothesis ``hypothesis_id``.

        Raises:
            KeyError: If the task does not declare it.
        """
        for item in self.hypotheses:
            if item.id == hypothesis_id:
                return item
        raise KeyError(f"task {self.id} declares no hypothesis {hypothesis_id!r}")

    def check_motivation(self, records: Iterable[LearningRecord]) -> None:
        """Refuse a task motivated by anything but eligible records with its mechanism.

        Raises:
            ValueError: If a cited record is missing, ineligible, or of another mechanism.
        """
        by_id = {record.decision_id: record for record in records}
        for decision_id in self.learning_record_ids:
            record = by_id.get(decision_id)
            if record is None:
                raise ValueError(f"no learning record for {decision_id}")
            if not record.eligible:
                raise ValueError(f"{decision_id} is not eligible: {record.reason}")
            if record.mechanism != self.mechanism:
                raise ValueError(f"{decision_id} is {record.mechanism}, not {self.mechanism}")


class Attempt(BaseModel):
    """One scored run of one candidate under one hypothesis.

    Attributes:
        task_id: The task.
        hypothesis_id: The hypothesis it was run under.
        number: 1 for the first attempt under that hypothesis, and so on.
        candidate: The candidate's parameters, as declared.
        candidate_sha256: sha256 of ``candidate`` as canonical JSON.
        scorer: The scorer's name.
        scorer_sha256: sha256 of the scorer's source, pinned on every attempt.
        scorecard: Every number the scorer returned.
        compute_seconds: Wall time spent scoring.
        at: When it was recorded.
        note: What was tried and why, in words.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    hypothesis_id: str
    number: int = Field(ge=1)
    candidate: dict[str, object]
    candidate_sha256: str = Field(min_length=64, max_length=64)
    scorer: str = Field(min_length=1)
    scorer_sha256: str = Field(min_length=64, max_length=64)
    scorecard: dict[str, object]
    compute_seconds: float = Field(ge=0.0)
    at: UtcDatetime = Field(default_factory=utc_now)
    note: str = ""


def candidate_sha256(candidate: Mapping[str, object]) -> str:
    """Return the sha256 of a candidate's parameters as canonical JSON."""
    return sha256_text(json.dumps(candidate, sort_keys=True, separators=(",", ":")))


class AttemptLog:
    """A task's attempts, append-only and hash-chained, with the budget enforced on append."""

    def __init__(self, path: Path, task: ResearchTask) -> None:
        """Open the log at ``path`` for ``task``, verifying any existing chain.

        Raises:
            ValueError: If an existing line does not follow its predecessor, belongs to another
                task, or breaks the budget or numbering.
        """
        self._path = path
        self._task = task
        self._attempts: list[Attempt] = []
        self._head = GENESIS_HASH
        if path.is_file():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                raw = json.loads(line)
                if raw.get("prev") != self._head:
                    raise ValueError(f"attempt line {number} does not follow line {number - 1}")
                attempt = Attempt.model_validate(raw.get("attempt"))
                self._check(attempt)
                self._attempts.append(attempt)
                self._head = sha256_text(line)

    def attempts(self, hypothesis_id: str | None = None) -> tuple[Attempt, ...]:
        """Every attempt in order, optionally only one hypothesis's."""
        return tuple(
            a for a in self._attempts if hypothesis_id is None or a.hypothesis_id == hypothesis_id
        )

    def remaining(self, hypothesis_id: str) -> int:
        """Scored runs left under ``hypothesis_id``."""
        self._task.hypothesis(hypothesis_id)
        return self._task.runs_per_hypothesis - len(self.attempts(hypothesis_id))

    def next_number(self, hypothesis_id: str) -> int:
        """The number the next attempt under ``hypothesis_id`` must carry."""
        return len(self.attempts(hypothesis_id)) + 1

    def append(self, attempt: Attempt) -> None:
        """Append one attempt.

        Raises:
            BudgetExhaustedError: If its hypothesis has no runs left.
            ValueError: If it belongs to another task or hypothesis, or is misnumbered.
        """
        self._check(attempt)
        line = json.dumps(
            {"prev": self._head, "attempt": attempt.model_dump(mode="json")},
            separators=(",", ":"),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._attempts.append(attempt)
        self._head = sha256_text(line)

    def _check(self, attempt: Attempt) -> None:
        if attempt.task_id != self._task.id:
            raise ValueError(f"attempt is for task {attempt.task_id!r}, not {self._task.id!r}")
        self._task.hypothesis(attempt.hypothesis_id)
        if self.remaining(attempt.hypothesis_id) <= 0:
            raise BudgetExhaustedError(
                f"{attempt.hypothesis_id} has used all {self._task.runs_per_hypothesis} runs"
            )
        if attempt.number != self.next_number(attempt.hypothesis_id):
            raise ValueError(
                f"attempt {attempt.number} under {attempt.hypothesis_id}; "
                f"expected {self.next_number(attempt.hypothesis_id)}"
            )
        if attempt.candidate_sha256 != candidate_sha256(attempt.candidate):
            raise ValueError("candidate_sha256 does not match the candidate")


def forbidden_candidate_paths(
    changed: Iterable[str], task_id: str, hypothesis_id: str
) -> list[str]:
    """Return every changed path outside the candidate's own arena directory.

    An empty list means the diff is allowed. Paths are repository-relative, as ``git diff
    --name-only`` prints them.
    """
    allowed = f"{ARENA_ROOT}/{task_id}/{hypothesis_id}/"
    return sorted(path for path in changed if not path.startswith(allowed))


def payloads_present(root: Path, roles: Mapping[str, str | None]) -> list[str]:
    """Return every data file under ``root/data`` of a ``validation`` or ``held-out`` corpus.

    ``manifest.json`` is committed metadata, not a payload, and is ignored. An empty list means
    the worktree is safe to hand to an agent.
    """
    found: list[str] = []
    for name, role in sorted(roles.items()):
        if role not in {"validation", "held-out"}:
            continue
        directory = root / "data" / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                found.append(str(path.relative_to(root)))
    return found
