"""The narrow interface to GENESIS. FORGE delegates; it never duplicates.

Every function here either **reads** through :mod:`phos.genesis` or **shells out** to
``scripts/genesis.py``. Nothing in this module constructs a declaration, a measurement or a
verdict, and nothing writes a file under ``docs/genesis``. That is the whole design: the record's
own validation, its lock and its atomic write stay in one place, and a second writer with its own
rules is the failure this layer exists to avoid.

The reason the write paths shell out rather than import is that ``scripts/genesis.py`` is the
surface both editors already drive and the one the rules document. Calling it keeps one behaviour
instead of two.

``tests/forge/test_genesis_api.py`` asserts the separation by reading this package's source: no
forbidden constructor appears, and no path under ``docs/genesis`` is opened for writing.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.genesis.gatehost import GateDecision, decide
from phos.genesis.records import Experiment
from phos.genesis.store import Store
from phos.genesis.tiercheck import TierVerdict, resolve

#: The command line both editors drive. Every write goes through it.
GENESIS_SCRIPT: Final = Path("scripts/genesis.py")

#: How long a genesis subcommand may take. A declaration or a result is fast; a hung process is a
#: failure worth reporting rather than waiting on.
TIMEOUT_S: Final = 300


class GenesisUnavailableError(RuntimeError):
    """The GENESIS command line could not be run, so nothing was recorded."""


class DeclarationProblemError(ValueError):
    """A declaration is absent, in the wrong phase, or not covered by the record."""


@dataclass(frozen=True)
class CommandOutcome:
    """What one ``scripts/genesis.py`` call did.

    Attributes:
        command: The argv that ran, for the record.
        returncode: Its exit code.
        stdout: Verbatim standard output.
        stderr: Verbatim standard error.
    """

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return whether the command exited zero."""
        return self.returncode == 0


def _run_genesis(root: Path, *args: str) -> CommandOutcome:
    """Run one ``scripts/genesis.py`` subcommand.

    Args:
        root: The repository root.
        *args: The subcommand and its flags.

    Returns:
        The outcome.

    Raises:
        GenesisUnavailableError: If the interpreter or the script could not be started.
    """
    script = root / GENESIS_SCRIPT
    if not script.is_file():
        raise GenesisUnavailableError(f"{GENESIS_SCRIPT.as_posix()} is not in {root}")
    argv = ("uv", "run", "python", GENESIS_SCRIPT.as_posix(), *args)
    try:
        completed = subprocess.run(
            list(argv),
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GenesisUnavailableError(f"could not run {' '.join(argv)}: {error}") from error
    return CommandOutcome(
        command=argv,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def tier(root: Path, corpus: str, declared: str | None = None) -> TierVerdict:
    """Return what the tier rule says about one corpus.

    A read. FORGE calls this before it touches any path, so a never-tier corpus is refused before a
    directory is listed rather than after.

    Args:
        root: The repository root.
        corpus: The corpus name as a declaration would give it.
        declared: The tier the declaration asserted, when there is one.

    Returns:
        The resolver's verdict.
    """
    return resolve(root, corpus, declared)


def gate(root: Path, command: str) -> GateDecision | None:
    """Return the gate's decision about one shell command.

    A read. ``None`` means the gate has no opinion because the command names no harness entry
    point, which is a different answer from "allowed".

    Args:
        root: The repository root.
        command: The command a role wants to run.

    Returns:
        The decision, or None when the command is not the gate's business.
    """
    return decide(command, Store(root))


def declaration(root: Path, experiment_id: str) -> Experiment:
    """Return one experiment record.

    Args:
        root: The repository root.
        experiment_id: ``E-NNNN``.

    Returns:
        The record.

    Raises:
        DeclarationProblemError: If there is no such record.
    """
    experiments = Store(root).experiments()
    record = experiments.get(experiment_id)
    if record is None:
        raise DeclarationProblemError(
            f"{experiment_id} is not in docs/genesis/experiments. A role builds against a "
            "committed declaration or it does not build."
        )
    return record


def require_declared(root: Path, experiment_id: str) -> Experiment:
    """Return a record only if it is a declaration, not a result.

    Args:
        root: The repository root.
        experiment_id: ``E-NNNN``.

    Returns:
        The record, in phase ``declared``.

    Raises:
        DeclarationProblemError: If the record is missing, or already carries a measurement or a
            verdict.
    """
    record = declaration(root, experiment_id)
    if record.phase != "declared":
        raise DeclarationProblemError(
            f"{experiment_id} is in phase {record.phase!r}. Only a declaration may be built "
            "against: a measured or judged record is a result, and building against one is "
            "building against the answer."
        )
    return record


def snapshot(root: Path) -> tuple[int, int, int]:
    """Return how many questions, experiments and findings the record holds.

    A read, for a status line. It is deliberately a count rather than a copy: FORGE never needs the
    records themselves, and handing them out would invite reading a result before it is judged.

    Args:
        root: The repository root.

    Returns:
        ``(questions, experiments, findings)``.
    """
    taken = Store(root).snapshot()
    return len(taken.questions), len(taken.experiments), len(taken.findings)


def declare(root: Path, payload: Path) -> CommandOutcome:
    """Register a declaration through the GENESIS command line.

    Args:
        root: The repository root.
        payload: The JSON file holding the declaration.

    Returns:
        The outcome. A refusal is the command's own, not FORGE's.
    """
    return _run_genesis(root, "declare", "--from", str(payload))


def result(root: Path, experiment_id: str, measurement: Path) -> CommandOutcome:
    """Attach measurements and compute the verdict through the GENESIS command line.

    FORGE never computes a verdict. This call does, from the numbers against the declared bars.

    Args:
        root: The repository root.
        experiment_id: ``E-NNNN``.
        measurement: The JSON file holding the measured values.

    Returns:
        The outcome.
    """
    return _run_genesis(root, "result", experiment_id, "--from", str(measurement))


def audit(root: Path) -> CommandOutcome:
    """Check the record's own cross-references through the GENESIS command line.

    Args:
        root: The repository root.

    Returns:
        The outcome.
    """
    return _run_genesis(root, "audit")


def declaration_fields() -> tuple[str, ...]:
    """Return the field names of a GENESIS experiment, so a test can prove FORGE holds none.

    Returns:
        The field names.
    """
    return tuple(sorted(Experiment.model_fields))


def declaration_json(root: Path, experiment_id: str) -> dict[str, object]:
    """Return one declaration's JSON as the record stores it.

    A read, for the baseline harness, which needs the declared command and corpus without judging
    them.

    Args:
        root: The repository root.
        experiment_id: ``E-NNNN``.

    Returns:
        The parsed record.

    Raises:
        DeclarationProblemError: If the file is absent or will not parse.
    """
    path = root / "docs" / "genesis" / "experiments" / f"{experiment_id}.json"
    if not path.is_file():
        raise DeclarationProblemError(f"{path.as_posix()} does not exist")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DeclarationProblemError(f"{path.as_posix()} will not parse: {error}") from error
    if not isinstance(parsed, dict):
        raise DeclarationProblemError(f"{path.as_posix()} is not a JSON object")
    return parsed
