#!/usr/bin/env python3
"""Describe a directory of generated plants: what is in it, and nothing about how good it is.

PART R5's distribution summary. Over a folder of generated runs it prints counts per family, the
range of each key parameter, how often the validity gate refused a candidate, and the fraction of
each run that is normal as against attack, fault and maintenance.

**It describes the data and scores no detector.** There is nowhere in this script to put a
detection, a recall, a false-alarm rate or a verdict, and that is deliberate rather than
unfinished. A summary that could also grade something would be read as a grade, and PART S6's
referee is the only thing in this programme entitled to produce one. What this answers is the
question that comes *before* any score: what did we actually generate?

It reads the manifests and the label files and opens no payload, so it is fast on a large batch
and says nothing that depends on the telemetry it did not read.

Usage::

    python scripts/summarise_plants.py data/plants
    python scripts/summarise_plants.py data/plants --parameters tank_area_m2 level_span_m
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

__all__ = ["Summary", "load_plants", "main", "summarise"]

logger = logging.getLogger("phos.synth.summarise")

MANIFEST_FILE: Final = "manifest.json"
LABELS_FILE: Final = "labels.json"

HEADLINE_PARAMETERS: Final = (
    "trains",
    "stages",
    "segments",
    "feeders",
    "scan_period_s",
)
"""Parameters printed for every family by default: the structural ones, which every family has
some of and which say most about what a batch actually contains. Anything else is asked for by
name, because a family has forty parameters and a table of all of them describes nothing."""


@dataclass(frozen=True)
class PlantRecord:
    """One generated plant, read from its manifest and labels and nothing else.

    Attributes:
        plant_id: The plant.
        family_id: The family it was drawn from.
        master_seed: The seed it came from.
        rejections: How many candidates the validity gate refused before this one.
        samples: How many samples the run holds.
        parameters: Every free number the physics read.
        scripted: The scripted events, as the labels file carries them.
        benign: How many benign operational events the run contained.
    """

    plant_id: str
    family_id: str
    master_seed: int
    rejections: int
    samples: int
    parameters: Mapping[str, float]
    scripted: tuple[Mapping[str, object], ...] = ()
    benign: int = 0

    def covered_fraction(self, kind: str) -> float:
        """Return the fraction of this run's samples inside an event of one kind.

        Computed from the event windows against the run's own span rather than from a per-sample
        label column, because the label file carries windows. Overlapping windows of the same kind
        are not double-counted; windows of *different* kinds may overlap and each is reported
        against its own kind, so the fractions can sum past one and are not a partition. They are
        not presented as one.
        """
        windows = sorted(
            (str(event["started_at"]), str(event["ended_at"]))
            for event in self.scripted
            if event["kind"] == kind
        )
        if not windows or self.samples == 0:
            return 0.0
        return _merged_span(windows) / max(_run_span(self.scripted), 1e-9)


def _merged_span(windows: Sequence[tuple[str, str]]) -> float:
    """Return the total seconds a set of ISO windows covers, merging overlaps."""
    from datetime import datetime

    spans = sorted(
        (datetime.fromisoformat(start), datetime.fromisoformat(end)) for start, end in windows
    )
    covered = 0.0
    current_end = None
    for start, end in spans:
        if current_end is None or start >= current_end:
            covered += (end - start).total_seconds()
            current_end = end
        elif end > current_end:
            covered += (end - current_end).total_seconds()
            current_end = end
    return covered


def _run_span(scripted: Sequence[Mapping[str, object]]) -> float:
    """Return the seconds from the earliest event start to the latest end, as a denominator.

    A rough stand-in for the run's own length, which the labels file does not carry. It is the
    honest denominator available from what this script reads: a fraction computed against it says
    "of the stretch events were placed over", which is what the printed caption says too.
    """
    from datetime import datetime

    if not scripted:
        return 0.0
    starts = [datetime.fromisoformat(str(event["started_at"])) for event in scripted]
    ends = [datetime.fromisoformat(str(event["ended_at"])) for event in scripted]
    return (max(ends) - min(starts)).total_seconds()


@dataclass
class Summary:
    """What a batch of generated plants contains.

    Attributes:
        plants: Every plant read.
        unreadable: Directories that held no manifest, with why.
    """

    plants: list[PlantRecord] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    def by_family(self) -> Mapping[str, list[PlantRecord]]:
        """Return the plants grouped by family, in family order."""
        grouped: dict[str, list[PlantRecord]] = defaultdict(list)
        for plant in self.plants:
            grouped[plant.family_id].append(plant)
        return dict(sorted(grouped.items()))


def load_plants(root: Path) -> Summary:
    """Read every generated plant under a directory.

    Args:
        root: A directory holding one subdirectory per plant.

    Returns:
        The summary, with anything unreadable listed rather than skipped silently.

    Raises:
        FileNotFoundError: If the directory does not exist. A typo'd path that reported "0 plants"
            would read as an empty batch, which is a different and much more alarming thing.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory")
    summary = Summary()
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = directory / MANIFEST_FILE
        if not manifest_path.is_file():
            summary.unreadable.append(f"{directory.name}: no {MANIFEST_FILE}")
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            summary.unreadable.append(f"{directory.name}: {error}")
            continue
        labels_path = directory / LABELS_FILE
        scripted: tuple[Mapping[str, object], ...] = ()
        benign = 0
        if labels_path.is_file():
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            scripted = tuple(labels.get("scripted_events", ()))
            benign = len(labels.get("benign_events", ()))
        summary.plants.append(
            PlantRecord(
                plant_id=manifest["plant_id"],
                family_id=manifest["family_id"],
                master_seed=manifest["master_seed"],
                rejections=manifest["rejections"],
                samples=manifest["samples"],
                parameters=manifest["parameters"],
                scripted=scripted,
                benign=benign,
            )
        )
    return summary


def _range_line(name: str, values: Sequence[float]) -> str:
    """Return one parameter's range, with its spread, for the printed table."""
    if not values:
        return f"    {name:28} —"
    low, high = min(values), max(values)
    middle = statistics.median(values)
    return f"    {name:28} {low:>12.4g} to {high:<12.4g} median {middle:.4g}"


def summarise(summary: Summary, parameters: Sequence[str]) -> list[str]:
    """Return the report, line by line.

    Args:
        summary: The plants read.
        parameters: Extra parameter names to report ranges for, beyond the structural ones.

    Returns:
        The report lines. Built as a list rather than printed so a test can read them.
    """
    lines: list[str] = []
    if not summary.plants:
        lines.append("No generated plants found.")
        for problem in summary.unreadable:
            lines.append(f"  unreadable: {problem}")
        return lines

    wanted = list(HEADLINE_PARAMETERS) + [
        name for name in parameters if name not in HEADLINE_PARAMETERS
    ]
    lines.append(
        f"{len(summary.plants)} generated plant(s) in {len(summary.by_family())} famil(y/ies)"
    )
    lines.append("")

    for family, plants in summary.by_family().items():
        rejections = [plant.rejections for plant in plants]
        drawn = len(plants) + sum(rejections)
        lines.append(f"{family} — {len(plants)} plant(s)")
        lines.append(
            f"    samples               {min(p.samples for p in plants)} to "
            f"{max(p.samples for p in plants)}"
        )
        lines.append(
            f"    gate                  {sum(rejections)} candidate(s) refused for "
            f"{len(plants)} kept ({drawn / len(plants):.2f} draws per plant)"
        )
        for name in wanted:
            values = [float(plant.parameters[name]) for plant in plants if name in plant.parameters]
            if values:
                lines.append(_range_line(name, values))

        scripted = Counter(str(event["kind"]) for plant in plants for event in plant.scripted)
        layers = Counter(str(event["layer"]) for plant in plants for event in plant.scripted)
        benign = sum(plant.benign for plant in plants)
        if scripted:
            lines.append(
                f"    scripted events       {dict(sorted(scripted.items()))} "
                f"over layer(s) {dict(sorted(layers.items()))}"
            )
            physical = sum(
                1 for plant in plants for event in plant.scripted if event.get("physical_effect")
            )
            stealthy = sum(
                1
                for plant in plants
                for event in plant.scripted
                if event.get("within_normal_range")
            )
            total = sum(len(plant.scripted) for plant in plants)
            lines.append(
                f"    of those              {physical}/{total} moved the process, "
                f"{stealthy}/{total} stayed inside normal ranges"
            )
            for kind in ("attack", "fault", "maintenance"):
                fractions = [plant.covered_fraction(kind) for plant in plants]
                covered = [value for value in fractions if value > 0.0]
                if covered:
                    lines.append(
                        f"    {kind:21} covers {min(covered):.1%} to {max(covered):.1%} of the "
                        "stretch events were placed over"
                    )
        else:
            lines.append("    scripted events       none — every sample of these runs is normal")
        lines.append(f"    benign operations     {benign} across the family")
        lines.append("")

    lines.append(
        "These figures describe the data. Nothing here scores a detector, and the fractions by "
        "kind are not a partition — a maintenance window and an attack window may overlap, and "
        "each is reported against its own kind."
    )
    if summary.unreadable:
        lines.append("")
        lines.append(f"{len(summary.unreadable)} directory/ies could not be read:")
        for problem in summary.unreadable:
            lines.append(f"    {problem}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Describe a directory of generated plants. Scores nothing."
    )
    parser.add_argument("directory", type=Path, help="a directory holding generated plants")
    parser.add_argument(
        "--parameters",
        nargs="*",
        default=(),
        help="extra parameter names to report ranges for",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        summary = load_plants(arguments.directory)
    except FileNotFoundError as error:
        logger.error("%s", error)
        return 2
    for line in summarise(summary, arguments.parameters):
        logger.info("%s", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
