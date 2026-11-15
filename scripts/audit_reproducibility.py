#!/usr/bin/env python3
"""Generate the same plant twice in fresh processes and prove the files are identical.

PART R5's reproducibility audit. The simulator's whole claim is that a corpus defined by a family
and a seed does not need to be stored, because it can be produced again exactly. Everything else
in this package rests on that: the payload is git-ignored, the manifest carries digests rather
than data, and PART S6's exam will reproduce a plant from a seed months after it was first drawn.

**Fresh processes, not two calls in one.** Two generations inside one interpreter share more than
they should — an import-time cache, a module-level dictionary, a random stream somebody forgot to
reseed — and would agree for reasons that have nothing to do with determinism. Each generation here
is a separate `python scripts/generate_plants.py` run, so the only thing the two share is the seed.
That is also why this is a script rather than only a test: it is the audit PART R5 asks for, and it
can be run by hand on any machine to check that machine.

**And the converse, which matters as much.** A generator that returned the same bytes for every
seed would pass the first half of this audit perfectly. So the second half changes only the seed
and insists the plant is *structurally* different — a different shape, different parameters,
different tag names. Determinism without variety is a fixture, not a generator.

Usage::

    python scripts/audit_reproducibility.py
    python scripts/audit_reproducibility.py --family thermal --seed 2026001 --hours 6
    python scripts/audit_reproducibility.py --all-families --hours 2
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.synth.families import family_ids  # noqa: E402
from phos.synth.manifest import digest_of  # noqa: E402

__all__ = ["Comparison", "audit_family", "generate_once", "main", "structure_of"]

logger = logging.getLogger("phos.synth.audit_reproducibility")

GENERATOR: Final = REPO_ROOT / "scripts" / "generate_plants.py"


class AuditError(RuntimeError):
    """Raised when a generation the audit depends on could not be run at all."""


def generate_once(
    family: str, seed: int, hours: float, destination: Path, *, events: int, validity_hours: float
) -> Path:
    """Run the generator in a **fresh process** and return the plant's directory.

    Args:
        family: Which family to draw from.
        seed: The master seed.
        hours: How long to simulate.
        destination: Directory to generate into.
        events: How many of each catalogue event to place.
        validity_hours: How long the gate runs each candidate for.

    Returns:
        The one directory the generator created.

    Raises:
        AuditError: If the generator failed, or did not produce exactly one plant. Either is a
            broken audit rather than a reproducibility finding, and the two must not be confused.
    """
    finished = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "generate",
            family,
            str(seed),
            "--hours",
            str(hours),
            "--validity-hours",
            str(validity_hours),
            "--events",
            str(events),
            "--out",
            str(destination),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if finished.returncode != 0:
        raise AuditError(
            f"generating {family}/{seed} failed with exit {finished.returncode}:\n"
            f"{finished.stderr.strip()}"
        )
    produced = sorted(path for path in destination.iterdir() if path.is_dir())
    if len(produced) != 1:
        raise AuditError(
            f"generating {family}/{seed} produced {len(produced)} directories, expected one"
        )
    return produced[0]


def digests(directory: Path) -> dict[str, str]:
    """Return the SHA-256 of every file in a plant's directory, by filename."""
    return {path.name: digest_of(path)[0] for path in sorted(directory.iterdir()) if path.is_file()}


def structure_of(directory: Path) -> dict[str, object]:
    """Return what makes one plant structurally different from another.

    Read from ``plant.json``, which is the plant's own description — so this asks whether a
    different seed drew a different *plant*, not merely whether it produced different numbers.
    Noise alone would change every digest while leaving the plant identical, and that is the
    failure this half of the audit is looking for.
    """
    spec = json.loads((directory / "plant.json").read_text(encoding="utf-8"))
    return {
        "signals": len(spec["signals"]),
        "components": len(spec["components"]),
        "controllers": len(spec["controllers"]),
        "units": len(spec["units"]),
        "first_tag": spec["signals"][0]["key"],
        "parameters": tuple(sorted((name, value) for name, value in spec["parameters"].items())),
    }


@dataclass(frozen=True)
class Comparison:
    """What the audit found for one family.

    Attributes:
        family: The family audited.
        seed: The seed generated twice.
        identical: Whether the two fresh-process generations produced identical files.
        differences: The files that differed, with both digests. Empty when identical.
        files: How many files were compared.
        structurally_varied: Whether a different seed gave a structurally different plant.
        varied_fields: Which fields of the plant's own description differed between seeds.
    """

    family: str
    seed: int
    identical: bool
    differences: tuple[str, ...]
    files: int
    structurally_varied: bool
    varied_fields: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Whether both halves of the audit held."""
        return self.identical and self.structurally_varied

    def summary(self) -> str:
        """Return one line for the report."""
        verdict = "pass" if self.passed else "FAIL"
        return (
            f"{self.family:11} seed {self.seed}: {verdict} — {self.files} file(s) identical "
            f"across fresh processes; {len(self.varied_fields)} field(s) differ on a new seed"
        )


def audit_family(
    family: str, seed: int, hours: float, *, events: int, validity_hours: float
) -> Comparison:
    """Audit one family: identical twice from one seed, different from another.

    Args:
        family: Which family.
        seed: The master seed to generate twice.
        hours: How long to simulate.
        events: How many of each catalogue event to place.
        validity_hours: How long the gate runs each candidate for.

    Returns:
        What was found.

    Raises:
        AuditError: If a generation could not be run.
    """
    with tempfile.TemporaryDirectory(prefix="phos-audit-") as scratch:
        root = Path(scratch)
        first = generate_once(
            family, seed, hours, root / "a", events=events, validity_hours=validity_hours
        )
        second = generate_once(
            family, seed, hours, root / "b", events=events, validity_hours=validity_hours
        )
        other = generate_once(
            family, seed + 1, hours, root / "c", events=events, validity_hours=validity_hours
        )

        left, right = digests(first), digests(second)
        differences = tuple(
            sorted(name for name in set(left) | set(right) if left.get(name) != right.get(name))
        )
        one, another = structure_of(first), structure_of(other)
        varied = tuple(sorted(key for key in one if one[key] != another[key]))

        return Comparison(
            family=family,
            seed=seed,
            identical=not differences,
            differences=differences,
            files=len(left),
            structurally_varied=bool(varied),
            varied_fields=varied,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Generate the same plant twice in fresh processes and compare every file."
    )
    parser.add_argument("--family", default="level_flow", help="family to audit")
    parser.add_argument(
        "--all-families", action="store_true", help="audit every open family instead of one"
    )
    parser.add_argument("--seed", type=int, default=2026001, help="master seed")
    parser.add_argument(
        "--hours",
        type=float,
        default=12.0,
        help="hours to simulate. Long enough by default that one of each catalogue event fits "
        "with the quiet stretches between them; a shorter run with --events is refused by the "
        "generator rather than crammed",
    )
    parser.add_argument(
        "--validity-hours", type=float, default=2.0, help="hours the gate runs each candidate for"
    )
    parser.add_argument(
        "--events", type=int, default=1, help="how many of each catalogue event to place"
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    families = list(family_ids()) if arguments.all_families else [arguments.family]

    logger.info(
        "Reproducibility audit: %d famil(y/ies), %gh runs, %d event(s) of each kind",
        len(families),
        arguments.hours,
        arguments.events,
    )
    results: list[Comparison] = []
    try:
        for family in families:
            comparison = audit_family(
                family,
                arguments.seed,
                arguments.hours,
                events=arguments.events,
                validity_hours=arguments.validity_hours,
            )
            results.append(comparison)
            logger.info("  %s", comparison.summary())
            for name in comparison.differences:
                logger.error("    differs: %s", name)
    except AuditError as error:
        logger.error("%s", error)
        return 2

    failed = [comparison for comparison in results if not comparison.passed]
    if failed:
        logger.error("")
        logger.error("%d famil(y/ies) failed the audit:", len(failed))
        for comparison in failed:
            if not comparison.identical:
                logger.error(
                    "  %s is not reproducible: %s", comparison.family, comparison.differences
                )
            if not comparison.structurally_varied:
                logger.error(
                    "  %s drew the same plant for two seeds, which makes it a fixture rather "
                    "than a generator",
                    comparison.family,
                )
        return 1
    logger.info("")
    logger.info("Every family is reproducible across fresh processes and varies with its seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
