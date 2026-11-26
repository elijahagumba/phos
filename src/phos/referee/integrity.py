"""Two integrity checks: a detector cannot see labels or seeds, and a private exam is not tuned on.

PART S6.

**What `run_detector_isolated` actually guarantees, stated precisely so it is not oversold.** The
subprocess it launches is handed a working directory holding a label-free copy of the telemetry
(`phos.referee.corpus.strip_labels`) and, when the plant has one, the capture — nothing else. A
detector that looks for ground truth *where it was given its input*, which is the realistic shape
of accidental overfitting this check exists to catch, finds nothing there. This is **not** an
adversarial sandbox: a detector written specifically to locate the real plant directory by some
other route — an absolute path baked in at import time, an environment variable, a shared cache —
is not stopped by a subprocess boundary alone. The project's threat model here is "a detector that
was tuned by accidentally reading the exam," not "a detector designed to defeat the referee," and
the check is sized to that.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.eval import Detection
from phos.referee.corpus import strip_labels
from phos.synth.outputs import CAPTURE_FILE, GeneratedPlant

__all__ = [
    "DirtyWorkingTreeError",
    "IntegrityError",
    "opaque_name_for",
    "refuse_if_dirty_for_private_exam",
    "run_detector_isolated",
]

logger = logging.getLogger(__name__)

_WORKER_MODULE: Final = "phos.referee._isolated_worker"
_ISOLATED_RUN_TIMEOUT_SECONDS: Final = 600


class IntegrityError(RuntimeError):
    """Raised when an isolated detector run cannot be completed or trusted."""


class DirtyWorkingTreeError(RuntimeError):
    """Raised when a private exam is asked to run from an uncommitted working tree."""


def opaque_name_for(plant: GeneratedPlant) -> str:
    """Return the name a detector sees in place of the plant's real id.

    A generated plant's id carries its family and its master seed (``level-flow-96011``). Handing
    that to a detector would hand over the seed through the detector's own input: it could
    regenerate the plant exactly, or infer which family it belongs to, without opening any label
    file. This replaces it with a digest that is stable for one plant and discloses nothing.

    Stable, so a detector that keys anything on the dataset's name behaves the same way across
    repeated runs on the same plant, and so two plants in one exam cannot collide. One-way, so the
    name cannot be turned back into the seed by anyone who only ever sees the name.

    Args:
        plant: The plant whose real id is being replaced.

    Returns:
        ``plant-`` followed by the first 16 hex characters of a SHA-256 digest of the real id.
        Truncated because the name goes into a dataset's entity id and observation ids, and 64 hex
        characters there would be unreadable for no gain: 16 is 64 bits, and a collision between
        two plants in one exam is what matters, not a collision across all time.
    """
    digest = hashlib.sha256(plant.manifest.plant_id.encode("utf-8")).hexdigest()
    return f"plant-{digest[:16]}"


def run_detector_isolated(
    detector_factory: str, plant: GeneratedPlant, work_dir: Path
) -> list[Detection]:
    """Run a detector in a subprocess given only this plant's telemetry and capture.

    Args:
        detector_factory: ``"module:function"``. The function is imported and called with no
            arguments inside the subprocess, and must return a `phos.eval.Detector`. A factory
            string rather than a pickled object, so nothing about the detector's own state has to
            survive a process boundary — only the recipe for building it fresh does.
        plant: The plant to run the detector against.
        work_dir: Where to build the isolated directory. A fresh subdirectory is created under
            it, named after the plant, so two plants scored in the same exam cannot collide.

    Returns:
        The detections the isolated run produced, parsed back from its stdout.

    Raises:
        IntegrityError: If the subprocess exits non-zero or does not print a JSON array of
            detections.
    """
    isolated_dir = work_dir / f"isolated-{plant.manifest.plant_id}"
    telemetry_path = strip_labels(plant, isolated_dir)
    capture_source = plant.directory / CAPTURE_FILE
    if capture_source.exists():
        (isolated_dir / CAPTURE_FILE).write_bytes(capture_source.read_bytes())

    result = subprocess.run(  # fixed argv, no shell, every part is ours or a path
        [
            sys.executable,
            "-I",
            "-m",
            _WORKER_MODULE,
            detector_factory,
            str(telemetry_path),
            opaque_name_for(plant),
        ],
        cwd=isolated_dir,
        capture_output=True,
        text=True,
        timeout=_ISOLATED_RUN_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise IntegrityError(
            f"isolated run of {detector_factory!r} on {plant.manifest.plant_id!r} failed "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise IntegrityError(
            f"isolated run of {detector_factory!r} did not print a JSON array: {error}"
        ) from error
    try:
        return [Detection.model_validate(item) for item in payload]
    except Exception as error:  # any shape failure here is an integrity problem
        raise IntegrityError(
            f"isolated run of {detector_factory!r} printed invalid detections: {error}"
        ) from error


class CommitRecord(BaseModel):
    """What `refuse_if_dirty_for_private_exam` records when it allows a private exam to run.

    Attributes:
        commit: The working tree's current commit.
        checked_at: When the check ran, UTC.
        checked_paths: The paths that had to be clean.
    """

    model_config = ConfigDict(frozen=True)

    commit: str
    checked_at: datetime
    checked_paths: tuple[str, ...]


def refuse_if_dirty_for_private_exam(
    repo_root: Path, detector_and_scorer_paths: tuple[str, ...]
) -> CommitRecord:
    """Refuse to run a private exam unless ``detector_and_scorer_paths`` are committed.

    "No tuning on the private exam" means the code that will be scored cannot have been edited
    since it was last committed — otherwise a result could be the product of a change nobody
    reviewed, made specifically to pass this one exam. This checks only the given paths, not the
    whole tree, so an unrelated in-progress change elsewhere does not block a private run.

    Args:
        repo_root: The repository to check.
        detector_and_scorer_paths: Paths, relative to ``repo_root``, that must have no
            uncommitted changes.

    Returns:
        The commit hash and when this check ran, to be recorded on the exam run.

    Raises:
        DirtyWorkingTreeError: If `git status` reports any change under the given paths, or if
            the current commit cannot be determined.
    """
    status = subprocess.run(  # fixed argv, no shell
        ["git", "status", "--porcelain", "--", *detector_and_scorer_paths],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        raise DirtyWorkingTreeError(f"git status failed: {status.stderr.strip()}")
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    if dirty:
        raise DirtyWorkingTreeError(
            "a private exam refuses to run with uncommitted changes to detector or scorer code: "
            + "; ".join(dirty)
        )

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if commit.returncode != 0 or not commit.stdout.strip():
        raise DirtyWorkingTreeError("could not determine the current commit")

    return CommitRecord(
        commit=commit.stdout.strip(),
        checked_at=datetime.now(UTC),
        checked_paths=detector_and_scorer_paths,
    )
