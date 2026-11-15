#!/usr/bin/env python3
"""Draw plants from a family and write them to disk.

PART R3's command line. A sibling of ``scripts/generate_synth.py`` rather than an extension of it,
because the two take different things: that one regenerates the six *committed* corpora from their
TOML configs, and this one draws a new plant from a family and a seed. Merging them would mean one
command whose arguments are mutually exclusive depending on a flag.

Nothing this writes is committed. A plant drawn from a family and a seed is reproduced exactly by
drawing it again, so storing it would put a large binary in a repository whose whole claim is
reproducibility. ``.gitignore`` keeps the payload out, manifest included.

Usage::

    python scripts/generate_plants.py list-families
    python scripts/generate_plants.py generate level_flow 2026001
    python scripts/generate_plants.py generate thermal 2026001 --hours 24 --out data/plants
    python scripts/generate_plants.py generate-batch power 2026001 --count 20
    python scripts/generate_plants.py verify data/plants/level-flow-2026001

Sealed families are absent from ``list-families`` and are refused by name, exactly as a family
that does not exist is. ``PHOS_SYNTH_ALLOW_SEALED=1`` in the environment admits them; see
`phos.synth.families_sealed`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.synth.events import EventCatalogue, EventsError  # noqa: E402
from phos.synth.families import FamilyError, get_family, list_families  # noqa: E402
from phos.synth.outputs import (  # noqa: E402
    GeneratedPlantManifest,
    OutputError,
    generate_plant,
    verify,
)
from phos.synth.validity import Thresholds, ValidityError  # noqa: E402

__all__ = ["DEFAULT_OUTPUT", "describe_families", "main"]

logger = logging.getLogger("phos.synth.generate_plants")

DEFAULT_OUTPUT: Final = REPO_ROOT / "data" / "plants"
"""Generated plants live beside the generated corpora, one directory each.

`tests/eval/test_real_dataset.py` discovers real corpora by globbing ``data/*/manifest.json``, so
a generated plant's manifest must not land at ``data/<name>/manifest.json`` — it is a different
document with a different schema, and writing one there would hand that test a manifest it cannot
read."""


def describe_families() -> None:
    """Print the families a plant may be drawn from, and what each one is."""
    families = list_families()
    logger.info("%d family/families available", len(families))
    for family in families:
        logger.info("")
        logger.info("  %-11s %s", family.family_id, family.label)
        logger.info("  %-11s %s", "", family.industry)
        logger.info("  %-11s %d randomised parameter(s)", "", len(family.bounds()))
        for line in _wrapped(family.summary, width=74):
            logger.info("  %-11s %s", "", line)


def _wrapped(text: str, width: int) -> list[str]:
    """Return text broken into lines no wider than ``width``, for a terminal listing."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if current and sum(len(part) + 1 for part in current) + len(word) > width:
            lines.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _catalogue(arguments: argparse.Namespace) -> EventCatalogue | None:
    """Return the event catalogue the arguments ask for, or ``None`` for a normal corpus.

    One of each kind, scaled by ``--events``, with a short duration so a dense catalogue still
    leaves most of the run normal. The validity of the result — that it fits — is the generator's
    to enforce, and it refuses an over-full run rather than cramming it.
    """
    n = arguments.events
    if n <= 0:
        return None
    return EventCatalogue(
        sensor_replays=n,
        stuck_valves=n,
        pump_trips=n,
        leaks=n,
        sensors_offline=n,
        valves_exercised=n,
        loops_in_manual=n,
        in_transit_changes=n,
        poll_bursts=n,
        traffic_replays=n,
        event_minutes=(6.0, 15.0),
    )


def _generate(arguments: argparse.Namespace) -> int:
    """Draw one plant and write it. Returns a process exit code."""
    family = get_family(arguments.family)
    thresholds = Thresholds(hours=arguments.validity_hours)
    plant = generate_plant(
        family,
        arguments.seed,
        arguments.out,
        hours=arguments.hours,
        traffic_seed=arguments.traffic_seed,
        thresholds=thresholds,
        with_capture=not arguments.no_capture,
        events=_catalogue(arguments),
        event_seed=arguments.event_seed,
        skip_impossible_events=True,
    )
    _report(
        plant.manifest,
        plant.directory,
        plant.schedule.skipped if plant.schedule else (),
    )
    return 0


def _generate_batch(arguments: argparse.Namespace) -> int:
    """Draw a run of plants from consecutive seeds. Returns a process exit code."""
    family = get_family(arguments.family)
    thresholds = Thresholds(hours=arguments.validity_hours)
    rejections = 0
    for offset in range(arguments.count):
        seed = arguments.seed + offset
        plant = generate_plant(
            family,
            seed,
            arguments.out,
            hours=arguments.hours,
            traffic_seed=arguments.traffic_seed + offset,
            thresholds=thresholds,
            with_capture=not arguments.no_capture,
            events=_catalogue(arguments),
            event_seed=arguments.event_seed + offset,
            skip_impossible_events=True,
        )
        rejections += plant.manifest.rejections
        _report(
            plant.manifest,
            plant.directory,
            plant.schedule.skipped if plant.schedule else (),
        )
    logger.info("")
    logger.info(
        "%d plant(s) from %s, %d candidate(s) refused by the validity gate along the way "
        "(%.2f draws per plant)",
        arguments.count,
        family.family_id,
        rejections,
        (arguments.count + rejections) / max(arguments.count, 1),
    )
    return 0


def _report(manifest: GeneratedPlantManifest, directory: Path, skipped: Sequence[str] = ()) -> None:
    """Log one generated plant, what the gate refused, and what the plant could not host.

    The command line asks for whatever a plant can carry rather than for a specific list, because
    the five families have different physics — a generating set stores no inventory, so it has no
    leak to drain. What that excluded is printed rather than left silent.
    """
    logger.info(
        "%s: %d samples, %d event(s), %d rejection(s) -> %s",
        manifest.plant_id,
        manifest.samples,
        len(manifest.events),
        manifest.rejections,
        directory,
    )
    for reason in manifest.rejection_reasons:
        logger.debug("  refused: %s", reason)
    for note in skipped:
        logger.info("  not placed on this process — %s", note)


def _verify(arguments: argparse.Namespace) -> int:
    """Check a written plant against its own manifest. Returns a process exit code."""
    problems = verify(arguments.directory)
    if problems:
        logger.error("%s does not match its manifest:", arguments.directory)
        for problem in problems:
            logger.error("  %s", problem)
        return 1
    logger.info("%s matches its manifest", arguments.directory)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Draw plants from a generator family and write them to disk."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list-families", help="show the families a plant may be drawn from")

    def _common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("family", help="family identifier, from list-families")
        sub.add_argument("seed", type=int, help="master seed")
        sub.add_argument("--hours", type=float, default=24.0, help="hours to simulate (default 24)")
        sub.add_argument(
            "--validity-hours",
            type=float,
            default=Thresholds().hours,
            help="hours each candidate is run before the gate judges it",
        )
        sub.add_argument(
            "--traffic-seed", type=int, default=1, help="seed for the capture's timing jitter"
        )
        sub.add_argument(
            "--out", type=Path, default=DEFAULT_OUTPUT, help="directory to write plants into"
        )
        sub.add_argument(
            "--no-capture", action="store_true", help="write telemetry and documents only"
        )
        sub.add_argument(
            "--events",
            type=int,
            default=0,
            help="place this many of each catalogue event (attack, fault, maintenance, network) "
            "in the run; 0 (the default) is a normal corpus. A dense catalogue on a short run is "
            "refused rather than crammed, so raise --hours if so",
        )
        sub.add_argument("--event-seed", type=int, default=0, help="seed for the event schedule")

    generate = commands.add_parser("generate", help="draw one plant")
    _common(generate)

    batch = commands.add_parser("generate-batch", help="draw a run of plants")
    _common(batch)
    batch.add_argument(
        "--count", type=int, default=10, help="how many consecutive seeds to draw (default 10)"
    )

    check = commands.add_parser("verify", help="check a written plant against its manifest")
    check.add_argument("directory", type=Path, help="a plant's directory")

    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        if arguments.command == "list-families":
            describe_families()
            return 0
        if arguments.command == "generate":
            return _generate(arguments)
        if arguments.command == "generate-batch":
            return _generate_batch(arguments)
        return _verify(arguments)
    except (EventsError, FamilyError, OutputError, ValidityError) as error:
        logger.error("%s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
