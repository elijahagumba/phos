#!/usr/bin/env python3
"""Run Atlas against D2's graded adversary and report, honestly, where it goes blind.

This is D3's command line. It runs the whole Atlas vertical over every attacked corpus D2 shipped,
finds the subtlety at which each attack type crosses from caught to missed, measures separately what
the software does when handed corrupted input, and writes one regenerable report stamped with the
commit and the seed.

**It measures. It does not improve.** No Atlas module is touched, no threshold is tuned to make a
number look better, and nothing here feeds a result back into a detector.

The corpora are generated rather than committed, so both generators must have run first. This script
names the command instead of guessing:

    python scripts/generate_synth.py --all      # the normal corpora Atlas fits on
    python scripts/generate_attacks.py --all    # D2's graded battery

Usage::

    python scripts/evaluate_breaking_points.py
    python scripts/evaluate_breaking_points.py synth-attack-water-treatment-graded
    python scripts/evaluate_breaking_points.py --no-log      # write the report, log nothing
    python scripts/evaluate_breaking_points.py --no-commands # skip the with-commands pass
    python scripts/evaluate_breaking_points.py --hostile-only  # software-survival; never detection
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

from phos.breaking import (  # noqa: E402
    AttackCorpus,
    BreakingConfig,
    CorpusBreakdown,
    CorpusNotFoundError,
    CorpusRobustness,
    assemble,
    discover_attack_corpora,
    load_attack_corpus,
    load_normal_corpus,
    render,
    run_breaking,
    run_robustness,
    write_report,
)
from phos.synth.attacks import AttackFlavour, load_batteries  # noqa: E402

DATA_DIR: Final = REPO_ROOT / "data" / "synth"
ATTACK_DIR: Final = DATA_DIR / "attacks"
CONFIG_DIR: Final = REPO_ROOT / "configs" / "attacks"
REPORT_DIR: Final = REPO_ROOT / "eval_runs" / "breaking"
CANONICAL_REPORT_STEM: Final = "breaking-report"
HOSTILE_REPORT_STEM: Final = "input-hostile-robustness"

logger = logging.getLogger("phos.breaking.cli")


def declared_flavours() -> dict[str, AttackFlavour]:
    """Return each committed battery's flavour, keyed by dataset name."""
    try:
        return {config.name: config.flavour for config in load_batteries(CONFIG_DIR)}
    except ValueError as error:
        logger.error("cannot read the committed attack configs from %s: %s", CONFIG_DIR, error)
        return {}


def hostile_only_selection_error(
    names: Sequence[str], flavours: dict[str, AttackFlavour]
) -> str | None:
    """Return an error if ``--hostile-only`` was pointed only at detection corpora.

    Args:
        names: Corpus directory names the caller asked for. Empty means "all".
        flavours: Committed dataset name to flavour.

    Returns:
        An error to print, or ``None`` if the selection includes an INPUT_HOSTILE corpus
        or no names were given (in which case the on-disk filter decides).
    """
    if not names:
        return None
    if any(flavours.get(name) is AttackFlavour.INPUT_HOSTILE for name in names):
        return None
    listed = ", ".join(names)
    return (
        f"--hostile-only was given only detection corpus names ({listed}); no INPUT_HOSTILE "
        "corpus was selected. Refusing rather than write a detection report."
    )


def reproducible(directories: Sequence[Path]) -> list[Path]:
    """Keep only the corpora a committed config can regenerate, naming any that are dropped.

    ``data/synth`` is a working directory: an earlier development run can leave a corpus behind that
    no config produces any more. A number measured on one of those cannot be re-created by anybody
    else, which Constitution §3.7 says makes it not a measurement — so it is skipped loudly rather
    than reported quietly. Nothing is deleted; the directory is simply not read.
    """
    try:
        declared = {config.name for config in load_batteries(CONFIG_DIR)}
    except ValueError as error:
        logger.error("cannot read the committed attack configs from %s: %s", CONFIG_DIR, error)
        return list(directories)

    kept: list[Path] = []
    for directory in directories:
        if directory.name in declared:
            kept.append(directory)
        else:
            logger.warning(
                "skipping %s: no committed config in %s declares it, so a result measured on it "
                "could not be regenerated. Delete it, or add the config that produces it",
                directory.name,
                CONFIG_DIR,
            )
    return kept


def normal_for(plant_id: str, role: str) -> Path:
    """Return the directory of a plant's normal corpus for one role.

    D1 names its corpora ``synth-<plant>-<role>``, so the path is derivable rather than configured.
    """
    return DATA_DIR / f"synth-{plant_id}-{role}"


def run_detection(corpus: AttackCorpus, config: BreakingConfig) -> CorpusBreakdown | None:
    """Measure one attacked corpus, or explain why it was skipped and carry on."""
    train = normal_for(corpus.manifest.plant_id, "train")
    try:
        normal = load_normal_corpus(train)
    except CorpusNotFoundError as error:
        logger.error("%s: %s", corpus.name, error)
        return None

    logger.info("measuring %s against a baseline fitted on %s", corpus.name, normal.name)
    return run_breaking(corpus, normal, config)


def run_hostile(directory: Path, corpus: AttackCorpus | None) -> CorpusRobustness:
    """Measure one input-hostile corpus for robustness, never for detection.

    ``corpus`` is ``None`` when the corruption defeated the reader outright, which is not a failure
    of this run: a corpus that cannot be loaded is itself the measurement, and `run_robustness`
    classifies the exception that stopped it.
    """
    if corpus is None:
        return run_robustness(directory)

    clean = holdout = None
    try:
        clean = load_normal_corpus(normal_for(corpus.manifest.plant_id, "train"))
        holdout = load_normal_corpus(normal_for(corpus.manifest.plant_id, "holdout"))
    except CorpusNotFoundError as error:
        logger.warning("%s: no clean comparison baseline (%s)", corpus.name, error)
    return run_robustness(directory, clean, holdout)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the breaking harness over every corpus asked for and write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="corpus directory names; default is all of them")
    parser.add_argument("--no-log", action="store_true", help="write the report, log nothing")
    parser.add_argument(
        "--no-commands", action="store_true", help="skip the with-commands reasoning pass"
    )
    parser.add_argument("--seed", type=int, default=7, help="seed for the calibrators")
    parser.add_argument(
        "--output-stem",
        default=None,
        help=(
            "On a detection run, copy the report to eval_runs/breaking/<stem>.md and .json so "
            "known-station and unknown-master remeasures stay in separate files. Does not "
            "replace the canonical breaking-report.md write. On --hostile-only, this is the "
            "write stem itself (default input-hostile-robustness); the canonical file is never "
            "written."
        ),
    )
    parser.add_argument(
        "--hostile-only",
        action="store_true",
        help=(
            "Measure INPUT_HOSTILE corpora only (software-survival, never detection or lead "
            "rate). Writes input-hostile-robustness.md and never breaking-report.md."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log at DEBUG")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    flavours = declared_flavours()
    write_stem = HOSTILE_REPORT_STEM
    if args.hostile_only:
        write_stem = Path(args.output_stem).name if args.output_stem else HOSTILE_REPORT_STEM
        if write_stem == CANONICAL_REPORT_STEM:
            print(
                "--hostile-only must not write breaking-report.md; that file holds the "
                "detection maps. Use a different --output-stem.",
                file=sys.stderr,
            )
            return 1
        selection_error = hostile_only_selection_error(tuple(args.names), flavours)
        if selection_error is not None:
            print(selection_error, file=sys.stderr)
            return 1

    directories = reproducible(discover_attack_corpora(ATTACK_DIR, tuple(args.names)))
    if args.hostile_only:
        directories = [
            directory
            for directory in directories
            if flavours.get(directory.name) is AttackFlavour.INPUT_HOSTILE
        ]
    if not directories:
        if args.hostile_only:
            print(
                f"No input-hostile corpora under {ATTACK_DIR}.\n"
                "Produce them with:\n"
                "  python scripts/generate_attacks.py --dataset synth-hostile-poisoned-baseline",
                file=sys.stderr,
            )
        else:
            print(
                f"No attack corpora under {ATTACK_DIR}.\n"
                "D2's battery is generated rather than committed. Produce it with:\n"
                "  python scripts/generate_attacks.py --all",
                file=sys.stderr,
            )
        return 1

    config = BreakingConfig(seed=args.seed, measure_commands=not args.no_commands)
    breakdowns: list[CorpusBreakdown] = []
    robustness: list[CorpusRobustness] = []

    for directory in directories:
        # Loading is attempted once, here, and a failure is routed to the robustness pass rather
        # than allowed to end the run. D2 ships corpora built to defeat a reader; one of them
        # defeating this one is a result to record, not a crash to propagate.
        corpus: AttackCorpus | None
        try:
            corpus = load_attack_corpus(directory)
        except Exception as error:
            logger.warning(
                "%s could not be loaded (%s); measuring it for robustness instead",
                directory.name,
                type(error).__name__,
            )
            robustness.append(run_hostile(directory, None))
            continue

        if corpus.flavour is AttackFlavour.DETECTION:
            detection = run_detection(corpus, config)
            if detection is not None:
                breakdowns.append(detection)
            continue
        robustness.append(run_hostile(directory, corpus))

    if not breakdowns and not robustness:
        print("Nothing was measured.", file=sys.stderr)
        return 1

    report = assemble(breakdowns, robustness, config)
    if args.hostile_only:
        markdown, machine = write_report(report, REPORT_DIR, log=not args.no_log, stem=write_stem)
    else:
        markdown, machine = write_report(report, REPORT_DIR, log=not args.no_log)
        if args.output_stem:
            copy_stem = Path(args.output_stem).name
            copied_md = REPORT_DIR / f"{copy_stem}.md"
            copied_json = REPORT_DIR / f"{copy_stem}.json"
            copied_md.write_text(markdown.read_text(encoding="utf-8"), encoding="utf-8")
            copied_json.write_text(machine.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("copied the breaking report to %s and %s", copied_md, copied_json)
    print(render(report))
    print(f"\nWritten to {markdown} and {machine}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
