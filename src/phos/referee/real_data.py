"""Real-data exam hook for the referee (PART S9).

Grades Atlas on real or public real-world datasets (HAI, DTU lab files, partner plant data),
reported separately from simulated results. No dataset is downloaded here — the person running
this places files locally.

**S0 hard rules still apply:** nothing imports or modifies `phos.atlas`. No red-tier corpus is
read. Everything here is opt-in and explicit about licence and source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from phos.eval import Detector, EvaluationReport

__all__ = [
    "DatasetManifest",
    "ManifestGate",
    "RealDataExam",
    "RealDataReport",
    "run_real_data_exam",
]

MANIFEST_SCHEMA_VERSION: Final = 1


class LicenceError(ValueError):
    """Raised when a dataset's licence is not recorded or is not commercial-safe."""


class ManifestError(ValueError):
    """Raised when a dataset has no manifest entry."""


@dataclass(frozen=True)
class DatasetManifest:
    """A dataset's licence and provenance record.

    Attributes:
        name: The dataset's name (e.g. "hai-22.04", "dtu-lab").
        source: Where it came from (URL, path, partner name).
        licence: The SPDX licence id or name.
        commercial_use: Whether commercial use is allowed.
        citation: Who must be credited.
        file_hashes: sha256 of each file, keyed by filename.
        role: The ADR 0117 data tier role ("development", "validation", "held-out").
    """

    name: str
    source: str
    licence: str
    commercial_use: bool
    citation: str
    file_hashes: dict[str, str]
    role: str

    def is_commercial_safe(self) -> bool:
        """True if the licence is recorded and permits commercial use."""
        return bool(self.licence) and self.commercial_use


class ManifestGate:
    """Checks a dataset's manifest before it may be used in an exam.

    Refuses any dataset without a manifest, and refuses any whose licence is not recorded as
    commercial-safe unless the run is explicitly marked internal-only.
    """

    def __init__(self, manifests: dict[str, DatasetManifest]) -> None:
        """Create the gate with the given manifest entries."""
        self._manifests = dict(manifests)

    def require(self, name: str, *, internal_only: bool = False) -> DatasetManifest:
        """Return the manifest for ``name``, refusing if missing or not commercial-safe.

        Args:
            name: The dataset name.
            internal_only: If True, non-commercial licences are allowed but the report must be
                stamped INTERNAL ONLY and cannot be exported.

        Returns:
            The dataset's manifest.

        Raises:
            ManifestError: If no manifest entry exists for ``name``.
            LicenceError: If the licence is not commercial-safe and the run is not internal-only.
        """
        if name not in self._manifests:
            raise ManifestError(
                f"dataset {name!r} has no manifest entry; register it before using it in an exam"
            )
        manifest = self._manifests[name]
        if not internal_only and not manifest.is_commercial_safe():
            raise LicenceError(
                f"dataset {name!r} licence {manifest.licence!r} is not recorded as "
                "commercial-safe; run with --internal-only or add a commercial-safe licence"
            )
        return manifest

    def register(self, manifest: DatasetManifest) -> None:
        """Add or replace a manifest entry."""
        self._manifests[manifest.name] = manifest


@dataclass(frozen=True)
class RealDataExam:
    """A real-data exam record: dataset, locked split, hashes, versions.

    The test split is locked in the record and may not be changed after the first run.
    """

    exam_id: str
    dataset: str
    manifest: DatasetManifest
    train_files: tuple[str, ...]
    calibration_files: tuple[str, ...]
    test_files: tuple[str, ...]
    scorer_version: str
    code_version: str | None
    internal_only: bool
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        dataset: str,
        manifest: DatasetManifest,
        train_files: tuple[str, ...],
        calibration_files: tuple[str, ...],
        test_files: tuple[str, ...],
        scorer_version: str,
        code_version: str | None,
        internal_only: bool = False,
    ) -> RealDataExam:
        """Create a new exam with a content-derived id."""
        now = datetime.now(UTC).isoformat()
        content = {
            "dataset": dataset,
            "train": sorted(train_files),
            "calibration": sorted(calibration_files),
            "test": sorted(test_files),
            "scorer_version": scorer_version,
            "code_version": code_version,
            "internal_only": internal_only,
        }
        exam_id = hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()
        return cls(
            exam_id=exam_id,
            dataset=dataset,
            manifest=manifest,
            train_files=train_files,
            calibration_files=calibration_files,
            test_files=test_files,
            scorer_version=scorer_version,
            code_version=code_version,
            internal_only=internal_only,
            created_at=now,
        )


@dataclass
class RealDataReport:
    """A real-data exam report, labelled REAL DATA and never merged with simulated results."""

    exam_id: str
    dataset: str
    label: str  # "REAL DATA (named dataset)"
    detector_name: str
    report: EvaluationReport
    internal_only: bool
    limitations: list[str]

    def to_markdown(self) -> str:
        """Render the report as markdown."""
        stamp = " INTERNAL ONLY — not for export" if self.internal_only else ""
        lines = [
            f"# Real-data exam `{self.exam_id[:12]}` — {self.detector_name}",
            "",
            f"**REAL DATA ({self.dataset}).** This report is about real or public real-world data, "
            f"not simulated results. It is never merged with SIMULATED reports in any table, "
            f"chart or summary number.{stamp}",
            "",
            f"- Detector: {self.detector_name}",
            f"- False alarms per normal hour: {self.report.false_positive_rate:.4f}",
            f"- Window recall: {self.report.window_recall:.4f}",
            f"- Expected calibration error: {self.report.expected_calibration_error:.4f}",
            "",
            "## Limitations",
            "",
        ]
        for limitation in self.limitations:
            lines.append(f"- {limitation}")
        return "\n".join(lines) + "\n"


def run_real_data_exam(
    detector: Detector,
    dataset_name: str,
    manifest_gate: ManifestGate,
    *,
    data_dir: Path,
    train_files: tuple[str, ...],
    calibration_files: tuple[str, ...],
    test_files: tuple[str, ...],
    scorer_version: str,
    code_version: str | None = None,
    internal_only: bool = False,
    work_dir: Path | None = None,
) -> tuple[RealDataExam, RealDataReport]:
    """Run a real-data exam: grade a detector on a labelled real dataset.

    Args:
        detector: The detector to grade.
        dataset_name: The dataset's name (must have a manifest entry).
        manifest_gate: The gate that checks manifests and licences.
        data_dir: Directory containing the dataset files.
        train_files: Training file names (locked in the exam record).
        calibration_files: Calibration file names (locked).
        test_files: Test file names (locked — may not change after the first run).
        scorer_version: The scoring code version.
        code_version: The git commit.
        internal_only: If True, the report is stamped INTERNAL ONLY.
        work_dir: Where intermediate files are written.

    Returns:
        The exam record and the report — but see ``Raises``: the scoring half is not built,
        so this function does not currently return.

    Raises:
        ManifestError: If the dataset has no manifest.
        LicenceError: If the licence is not commercial-safe and not internal-only.
        ValueError: If a file's hash does not match the manifest.
        NotImplementedError: Always, once the manifest and hashes have been checked. The
            scoring half of the exam is not built, and this call will not invent a report.
    """
    manifest = manifest_gate.require(dataset_name, internal_only=internal_only)

    # Verify file hashes against the manifest.
    for filename in (*train_files, *calibration_files, *test_files):
        path = data_dir / filename
        if path.exists():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = manifest.file_hashes.get(filename)
            if expected is not None and actual != expected:
                raise ValueError(f"{filename}: hash {actual} does not match manifest {expected}")

    exam = RealDataExam.create(
        dataset=dataset_name,
        manifest=manifest,
        train_files=train_files,
        calibration_files=calibration_files,
        test_files=test_files,
        scorer_version=scorer_version,
        code_version=code_version,
        internal_only=internal_only,
    )

    # The scoring half of this exam is not built. What stood here imported
    # `phos.eval.Observation`, which does not exist, so the call raised ImportError before it
    # scored anything; it then built a `Dataset` it discarded and an `EvaluationReport` whose
    # every field was 0.0. A report of zeros presented as a measurement is a fabricated
    # result, which Constitution §3 and §10 forbid, so the call refuses instead of returning
    # one. The manifest gate, the licence check and the hash verification above are real and
    # still run. Writing the scoring needs its own declaration (GENESIS `declare`).
    raise NotImplementedError(
        f"real-data scoring is not built: exam {exam.exam_id} was recorded for "
        f"dataset {dataset_name!r}, but no detector was run and no report was produced. "
        "The scoring half needs its own declaration before it is written."
    )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "DatasetManifest",
    "LicenceError",
    "ManifestError",
    "ManifestGate",
    "RealDataExam",
    "RealDataReport",
    "run_real_data_exam",
]
