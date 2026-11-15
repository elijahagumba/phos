"""The on-disk GENESIS record: atomic, locked, and willing to report its own damage.

The store is a tree of JSON files under ``docs/genesis/``: one file per question, experiment and
finding. Plain files rather than a database, for three reasons. A git diff of a one-object file is
reviewable by eye, which is what makes "never silently alter historical experimental results"
checkable by the same history that holds the ADRs. Two branches editing different records do not
conflict. And Cursor, which drives the CLI like any shell, can read the record with ``cat``.

The first version of this module was unsafe in three ways, measured rather than suspected: eight
concurrent ``ask`` calls produced **one** record, because each read the same highest id, computed
the same name and wrote the same path; ``Path.write_text`` is not atomic, so an interrupted write
left a half-written file; and nothing noticed that the path being written already held something.
ADR 0415 is the fix. Allocation and writing now happen under one exclusive lock, every write goes
through a temporary file and ``os.replace``, and a create that would overwrite is refused.

A corrupt record no longer stops the world either. The accessors skip what will not load and
``snapshot`` reports it, so one truncated file cannot disable the gate or the state command. The
safe direction matters here: a gate that cannot read the declaration covering a command sees no
declaration, which is a refusal, not an allow.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeVar

from pydantic import BaseModel, ValidationError

from phos.genesis.records import Experiment, Finding, Question

#: Where the record lives, relative to the repository root. Under ``docs/`` because it is the
#: machine-readable half of the same scientific record ``docs/adr/`` holds in prose.
RECORD_DIR: Final = Path("docs/genesis")

#: Subdirectory per kind, and the id prefix each uses.
KINDS: Final[dict[str, str]] = {
    "questions": "Q",
    "experiments": "E",
    "findings": "F",
}

#: The lock file guarding id allocation. ``flock`` is released by the kernel when the holding
#: process dies, so a killed session leaves no stale lock to clear by hand.
LOCK_NAME: Final = ".lock"

_Model = TypeVar("_Model", bound=BaseModel)
_Record = TypeVar("_Record", Question, Experiment, Finding)


@dataclass(frozen=True)
class Broken:
    """One record that does not load, or one reference that points at nothing.

    Attributes:
        path: The file the problem is in.
        problem: What is wrong, in one line.
    """

    path: str
    problem: str


@dataclass(frozen=True)
class Snapshot:
    """Everything the store holds, plus everything it could not read.

    Attributes:
        questions: Questions by id.
        experiments: Experiments by id.
        findings: Findings by id.
        unreadable: One entry per file that would not load. A caller that reports a state must
            report these too, or it is describing a record it has not fully read.
    """

    questions: dict[str, Question]
    experiments: dict[str, Experiment]
    findings: dict[str, Finding]
    unreadable: tuple[Broken, ...]


class Store:
    """Read and write the GENESIS record tree.

    Attributes:
        root: The repository root.
        base: ``root / docs/genesis``.
    """

    def __init__(self, root: Path) -> None:
        """Open the store under ``root``.

        Args:
            root: The repository root. The record directory need not exist yet.
        """
        self.root = root
        self.base = root / RECORD_DIR

    # -- locking ---------------------------------------------------------------------------

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold an exclusive lock on the store for the duration of the block.

        Two sessions allocating an id at the same moment is the ordinary case here, not an edge
        one: the whole point of the shared record is that Claude Code and Cursor both write it.
        ``flock`` is advisory between cooperating processes, which is exactly what this is, and
        the kernel drops it if the holder dies.

        Yields:
            Nothing. The lock is held inside the block and released on the way out.
        """
        self.base.mkdir(parents=True, exist_ok=True)
        handle = (self.base / LOCK_NAME).open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    # -- reading ---------------------------------------------------------------------------

    def _dir(self, kind: str) -> Path:
        return self.base / kind

    def _load_all(self, kind: str, model: type[_Model]) -> tuple[dict[str, _Model], list[Broken]]:
        """Return the records of ``kind``, and one `Broken` per file that would not load."""
        found: dict[str, _Model] = {}
        broken: list[Broken] = []
        directory = self._dir(kind)
        if not directory.is_dir():
            return found, broken
        for path in sorted(directory.glob("*.json")):
            try:
                loaded = model.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValidationError, OSError, ValueError) as error:
                relative = (RECORD_DIR / kind / path.name).as_posix()
                broken.append(Broken(relative, f"will not load: {error}"))
                continue
            found[str(loaded.id)] = loaded  # type: ignore[attr-defined]
        return found, broken

    def questions(self) -> dict[str, Question]:
        """Return every question that loads, by id. Unreadable files are skipped."""
        return self._load_all("questions", Question)[0]

    def experiments(self) -> dict[str, Experiment]:
        """Return every experiment that loads, by id. Unreadable files are skipped."""
        return self._load_all("experiments", Experiment)[0]

    def findings(self) -> dict[str, Finding]:
        """Return every finding that loads, by id. Unreadable files are skipped."""
        return self._load_all("findings", Finding)[0]

    def snapshot(self) -> Snapshot:
        """Return everything the store holds and everything it could not read.

        Returns:
            The snapshot. ``unreadable`` is empty when every file parsed.
        """
        questions, q_broken = self._load_all("questions", Question)
        experiments, e_broken = self._load_all("experiments", Experiment)
        findings, f_broken = self._load_all("findings", Finding)
        return Snapshot(
            questions=questions,
            experiments=experiments,
            findings=findings,
            unreadable=tuple(q_broken + e_broken + f_broken),
        )

    # -- writing ---------------------------------------------------------------------------

    def path_for(self, record_id: str) -> Path:
        """Return the file a record id belongs in.

        Args:
            record_id: ``Q-NNNN``, ``E-NNNN`` or ``F-NNNN``.

        Returns:
            The path, whether or not it exists.

        Raises:
            ValueError: If the prefix names no kind.
        """
        prefix = record_id.split("-", 1)[0]
        for kind, kind_prefix in KINDS.items():
            if kind_prefix == prefix:
                return self._dir(kind) / f"{record_id}.json"
        raise ValueError(f"{record_id!r} has no known kind prefix")

    @staticmethod
    def _render(record: Question | Experiment | Finding) -> str:
        """Return the JSON text one record is stored as."""
        return json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"

    @staticmethod
    def _write_atomic(path: Path, text: str) -> None:
        """Write ``text`` to ``path`` so that no reader ever sees a partial file.

        The temporary file is created in the destination's own directory, because ``os.replace``
        is only atomic within one filesystem. A killed process leaves the temporary file behind
        and the real record untouched, which is the failure this is for.

        Args:
            path: The destination.
            text: The whole file's contents.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def write(self, record: Question | Experiment | Finding) -> Path:
        """Write one record, replacing what is there.

        This is the update path: ``result`` and ``promote`` write a record whose id already
        exists. Use `create` when the record is new, which refuses to overwrite.

        Args:
            record: The record to write. Its id decides the path.

        Returns:
            The path written.
        """
        path = self.path_for(record.id)
        self._write_atomic(path, self._render(record))
        return path

    def create(self, kind: str, build: Callable[[str], _Record]) -> tuple[_Record, Path]:
        """Allocate the next id of ``kind`` and write the record it builds, under one lock.

        Allocation and writing are one critical section on purpose. Separately, two sessions
        read the same highest id, build the same name and write the same path, and the second
        silently replaces the first — which is what eight concurrent ``ask`` calls did before
        ADR 0415, producing one record out of eight.

        Args:
            kind: One of ``questions``, ``experiments``, ``findings``.
            build: Given the allocated id, returns the record to write.

        Returns:
            ``(record, path)``.

        Raises:
            FileExistsError: If the allocated path already holds a record. That means the
                allocator and the tree disagree, and overwriting would destroy evidence.
        """
        with self.locked():
            record = build(self.next_id(kind))
            path = self.path_for(record.id)
            if path.exists():
                raise FileExistsError(
                    f"{path.relative_to(self.root)} already exists; refusing to overwrite a "
                    "record that was not read first"
                )
            self._write_atomic(path, self._render(record))
        return record, path

    def next_id(self, kind: str) -> str:
        """Return the next free id of ``kind``, counting ids on every visible ref.

        A second branch that cannot see this one would otherwise hand the same number to a
        different record, which is the collision ``scripts/check_number_allocation.py`` was
        written for. Callers that then write the record should hold `locked` across both, or
        use `create`, which does.

        Args:
            kind: One of ``questions``, ``experiments``, ``findings``.

        Returns:
            The id, zero-padded to four digits.

        Raises:
            ValueError: If ``kind`` is not one of the three.
        """
        if kind not in KINDS:
            raise ValueError(f"{kind!r} is not a record kind: {', '.join(KINDS)}")
        prefix = KINDS[kind]
        taken = {
            int(path.stem.split("-")[1])
            for path in self._dir(kind).glob(f"{prefix}-*.json")
            if path.stem.split("-")[-1].isdigit()
        }
        taken |= self._numbers_on_refs(kind, prefix)
        return f"{prefix}-{(max(taken) + 1) if taken else 1:04d}"

    def _numbers_on_refs(self, kind: str, prefix: str) -> set[int]:
        """Return the record numbers of ``kind`` present on any ref in this clone."""
        found: set[int] = set()
        try:
            refs = subprocess.run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            return found
        for ref in refs:
            try:
                listing = subprocess.run(
                    ["git", "ls-tree", "-r", "--name-only", ref, "--", str(RECORD_DIR / kind)],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            except (OSError, subprocess.CalledProcessError):
                continue
            for line in listing.splitlines():
                stem = Path(line).stem
                if stem.startswith(f"{prefix}-") and stem[2:].isdigit():
                    found.add(int(stem[2:]))
        return found

    # -- integrity -------------------------------------------------------------------------

    def audit(self) -> list[Broken]:
        """Return every record that will not load and every reference that resolves to nothing.

        Charter section VIII forbids fabricated findings and fabricated citations. The half of
        that a machine can check is whether the record's own cross-references exist: a finding
        citing an experiment that is not there, an experiment serving a question that is not
        there, a question listing an experiment that is not there, a measurement naming a report
        file that is absent, an ADR reference pointing at no file, and a verdict that disagrees
        with its own numbers against its own declared bars.

        Returns:
            One entry per problem, the unreadable files first.
        """
        snapshot = self.snapshot()
        broken: list[Broken] = list(snapshot.unreadable)
        questions, experiments, findings = (
            snapshot.questions,
            snapshot.experiments,
            snapshot.findings,
        )

        for experiment_id, record in experiments.items():
            path = (RECORD_DIR / "experiments" / f"{experiment_id}.json").as_posix()
            if record.question not in questions:
                broken.append(Broken(path, f"serves {record.question}, which does not exist"))
            if record.measured is not None:
                if not (self.root / record.measured.report).exists():
                    broken.append(
                        Broken(path, f"names report {record.measured.report}, which is absent")
                    )
                recomputed = record.compute_verdict()
                if record.verdict is not None and record.verdict.outcome != recomputed.outcome:
                    broken.append(
                        Broken(
                            path,
                            f"verdict says {record.verdict.outcome!r} but the measured values "
                            f"against the declared bars give {recomputed.outcome!r}",
                        )
                    )
            if record.verdict is not None and record.verdict.adr is not None:
                if not (self.root / record.verdict.adr).exists():
                    broken.append(Broken(path, f"cites {record.verdict.adr}, which is absent"))

        for question_id, question in questions.items():
            path = (RECORD_DIR / "questions" / f"{question_id}.json").as_posix()
            for experiment_id in question.experiments:
                if experiment_id not in experiments:
                    broken.append(Broken(path, f"lists {experiment_id}, which does not exist"))

        for finding_id, finding in findings.items():
            path = (RECORD_DIR / "findings" / f"{finding_id}.json").as_posix()
            for experiment_id in finding.evidence:
                if experiment_id not in experiments:
                    broken.append(
                        Broken(path, f"cites {experiment_id} as evidence, which does not exist")
                    )

        return broken
