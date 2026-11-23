"""The release package: builds a publishable benchmark folder (PART S10).

Builds a folder that can be published: the simulator package, public scenarios, the scoring
tool, and a fair-comparison harness — so outside researchers can run unlimited fresh tests on
any detector, including Atlas, while the private exam stays secret and Atlas's engine stays
proprietary.

**What must NOT go in the release:**
- anything from `src/phos/atlas/` or any Atlas model, rules or parameters;
- private seeds, sealed generator families, or the seed vault tooling;
- partner or INTERNAL ONLY data and reports;
- the breaker's search code and its archive of undisclosed attacks, unless a decision is
  recorded to publish it.

Enforced with an automated release audit: the build fails if any forbidden path, import of
Atlas, private seed, sealed family, or INTERNAL ONLY stamp is found in the output folder.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "ReleaseAuditError",
    "ReleaseGateError",
    "audit_release_folder",
    "build_release",
    "require_locked_exam",
]

_FORBIDDEN_PATHS: Final[tuple[str, ...]] = (
    "src/phos/atlas",
    "src/phos/referee/seeds.py",
    "src/phos/breaker",
    "eval_runs/log.jsonl",
    "private",
    ".seedvault.json",
    "sealed",
    "INTERNAL ONLY",
)

_FORBIDDEN_IMPORTS: Final[tuple[str, ...]] = (
    "phos.atlas",
    "phos.referee.seeds",
    "phos.referee.integrity",
)

_RELEASE_README_TEMPLATE = """# PHOS Open Benchmark

This folder contains everything needed to run the PHOS benchmark against any detector,
including Atlas, on fresh simulated plants. Every result here is **SIMULATED** — every plant is
a model from `phos.synth`, not a real plant.

## What's inside

- `simulator/` — the plant generator (`phos.synth`), public scenarios only
- `scoring/` — the metric and report code from PART S6 (without seed vault tooling)
- `detector-interface/` — the `Detector` interface and an empty adapter template
- `baselines/` — adapters for open-source baselines with permissive licences, if any
- `results-template.md` — where results appear, failures listed first
- `FINDINGS.md` — Atlas's known failures, public
- `CONTRIBUTING.md` — how to submit new scenarios or detector adapters

## What's NOT inside

- No Atlas model, rules or parameters (`src/phos/atlas/` is excluded)
- No private seeds or sealed generator families
- No partner data or INTERNAL ONLY reports
- No breaker search code or undisclosed attack archive

## How to run

```
phos-bench run --detector <module:function>
phos-bench compare
```

## Exam this release is tied to

Exam hash: {exam_hash}
Scorer version: {scorer_version}
Code version: {code_version}

Run this exam before publishing: the release gate refuses to build without a completed
locked-exam run for the current code version.
"""

_DECISIONS_NEEDED_TEMPLATE = """# Decisions needed (PART S10)

The following legal and licensing questions need a human decision (Elijah) before the release
can be published. Each is marked DRAFT until confirmed.

## Licence choice

- Code: candidate Apache 2.0 or MIT — DRAFT
- Data: candidate CC BY 4.0 — DRAFT

## Commercial benchmarking

- May named commercial products appear in the results table? — DRAFT (no unless recorded here)
- What terms apply to commercial users of the benchmark? — DRAFT

## Real-data partners

- Which partner plants may be benchmarked? — DRAFT (none yet)
- What agreement terms apply to partner data? — DRAFT

## Gate 3 threshold

- Is "under 1 false alarm per hour" the right Gate 3 threshold? — DRAFT (assumption to confirm)
"""


@dataclass(frozen=True)
class ReleaseAuditError(ValueError):
    """Raised when the release audit finds a forbidden item."""


@dataclass(frozen=True)
class ReleaseGateError(ValueError):
    """Raised when the release gate blocks the build."""


def _forbidden_in_text(text: str) -> list[str]:
    found = []
    for pattern in _FORBIDDEN_PATHS:
        if pattern in text:
            found.append(pattern)
    return found


def _forbidden_imports_in_file(path: Path) -> list[str]:
    found: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return found
    for imp in _FORBIDDEN_IMPORTS:
        if f"import {imp}" in content or f"from {imp}" in content:
            found.append(imp)
    return found


def audit_release_folder(folder: Path) -> None:
    """Scan a release folder for forbidden content.

    Raises:
        ReleaseAuditError: If any forbidden path, import of Atlas, private seed, sealed family,
            or INTERNAL ONLY stamp is found.
    """
    violations: list[str] = []
    for path in folder.rglob("*"):
        if path.is_dir():
            continue
        rel = str(path.relative_to(folder))
        for forbidden in _FORBIDDEN_PATHS:
            if forbidden in rel:
                violations.append(f"forbidden path in name: {rel} ({forbidden})")
        for imp in _forbidden_imports_in_file(path):
            violations.append(f"forbidden import in {rel}: {imp}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in ("INTERNAL ONLY", "private seed", "sealed family"):
            if pattern in text:
                violations.append(f"forbidden content in {rel}: {pattern}")
    if violations:
        raise ReleaseAuditError(
            "release audit failed:\n" + "\n".join(f"  - {v}" for v in violations)
        )


def require_locked_exam(exam_report_path: Path | None, code_version: str) -> None:
    """Refuse to build a release unless a completed locked-exam run exists.

    Args:
        exam_report_path: Path to the locked exam's report (from PART S6).
        code_version: The current code version.

    Raises:
        ReleaseGateError: If no exam report exists or it doesn't match the code version.
    """
    if exam_report_path is None or not exam_report_path.exists():
        raise ReleaseGateError(
            f"no locked-exam report found at {exam_report_path}; "
            "run the referee exam (PART S6) before building a release"
        )
    try:
        content = json.loads(exam_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseGateError(f"cannot read exam report: {error}") from error
    if content.get("code_version") != code_version:
        raise ReleaseGateError(
            f"exam report code_version {content.get('code_version')!r} does not match "
            f"current code {code_version!r}; re-run the exam"
        )


def build_release(
    *,
    output_folder: Path,
    simulator_source: Path,
    scoring_source: Path,
    detector_interface_source: Path,
    exam_report_path: Path | None,
    code_version: str,
    scorer_version: str,
    public_scenarios: list[Path] | None = None,
    baselines: list[Path] | None = None,
    findings_md: Path | None = None,
) -> Path:
    """Build the release folder.

    Args:
        output_folder: Where to write the release. Created if needed.
        simulator_source: Path to `phos.synth` source (without sealed families).
        scoring_source: Path to the referee scoring code (without seed vault tooling).
        detector_interface_source: Path to the Detector interface template.
        exam_report_path: Path to a completed locked-exam report (required by the gate).
        code_version: Current code version.
        scorer_version: Current scorer version.
        public_scenarios: Public scenario files to include.
        baselines: Open-source baseline adapters to include.
        findings_md: Path to FINDINGS.md to include.

    Returns:
        The output folder path.

    Raises:
        ReleaseGateError: If the release gate blocks (no locked exam).
        ReleaseAuditError: If the audit finds forbidden content.
    """
    require_locked_exam(exam_report_path, code_version)

    output_folder.mkdir(parents=True, exist_ok=True)

    # Copy the public parts only.
    (output_folder / "simulator").mkdir(exist_ok=True)
    synth_dest = output_folder / "simulator" / "phos" / "synth"
    shutil.copytree(simulator_source, synth_dest, dirs_exist_ok=True)

    scoring_dest = (
        output_folder / "scoring" / "phos" / "referee" / "scoring"
    )
    shutil.copytree(scoring_source, scoring_dest, dirs_exist_ok=True)

    shutil.copytree(
        detector_interface_source, output_folder / "detector-interface",
        dirs_exist_ok=True,
    )

    if public_scenarios:
        (output_folder / "public-scenarios").mkdir(exist_ok=True)
        for scenario in public_scenarios:
            shutil.copy2(scenario, output_folder / "public-scenarios" / scenario.name)

    if baselines:
        (output_folder / "baselines").mkdir(exist_ok=True)
        for baseline in baselines:
            shutil.copy2(baseline, output_folder / "baselines" / baseline.name)

    if findings_md:
        shutil.copy2(findings_md, output_folder / "FINDINGS.md")

    # Write the README.
    readme = _RELEASE_README_TEMPLATE.format(
        exam_hash=json.loads(
            exam_report_path.read_text(encoding="utf-8")
        ).get("exam_id", "unknown"),
        scorer_version=scorer_version,
        code_version=code_version,
    )
    (output_folder / "README.md").write_text(readme, encoding="utf-8")

    # Write DECISIONS_NEEDED.md.
    (output_folder / "DECISIONS_NEEDED.md").write_text(_DECISIONS_NEEDED_TEMPLATE, encoding="utf-8")

    # Write LICENSE templates.
    (output_folder / "LICENSE.code").write_text(
        "DRAFT: Apache 2.0 or MIT — confirm with Elijah\n", encoding="utf-8"
    )
    (output_folder / "LICENSE.data").write_text(
        "DRAFT: CC BY 4.0 — confirm with Elijah\n", encoding="utf-8"
    )

    # Run the audit.
    audit_release_folder(output_folder)

    return output_folder


__all__ = [
    "ReleaseAuditError",
    "ReleaseGateError",
    "audit_release_folder",
    "build_release",
    "require_locked_exam",
]
