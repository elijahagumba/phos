r"""Generate sample .phosrun corpora for the viewer's development and tests.

Usage::

    python scripts/generate_synth_runs.py --all --output ~/PHOS_runs/dev
    python scripts/generate_synth_runs.py \\
        --dataset synth-attack-water-treatment-graded --output ~/PHOS_runs/dev
    python scripts/generate_synth_runs.py --list

Each generated corpus gets a corresponding .phosrun file containing Atlas's
detection output, written to ``--output`` (default ``~/PHOS_runs/dev``).

This script is for development and testing only. It uses development seeds
only; no labelled public command corpus is required.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from phos.referee.record import record_atlas_on_run  # noqa: E402
from phos.synth.attacks.battery import AttackDatasetConfig, load_batteries  # noqa: E402
from phos.synth.attacks.generate import generate_attack_dataset  # noqa: E402

CONFIG_DIRECTORY = REPOSITORY / "configs" / "attacks"
DEFAULT_OUTPUT = Path.home() / "PHOS_runs" / "dev"

logger = logging.getLogger("phos.synth.generate_synth_runs")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="generate every configured dataset")
    selection.add_argument("--dataset", help="generate one dataset by name")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="where to write corpora and .phosrun files",
    )
    parser.add_argument(
        "--no-capture", action="store_true", help="skip the pcap and write telemetry only"
    )
    parser.add_argument("--verbose", action="store_true", help="log what each dataset contains")
    return parser.parse_args(argv)


def chosen(configs: tuple[AttackDatasetConfig, ...], name: str | None) -> list[AttackDatasetConfig]:
    """Return the configs to generate."""
    if name is None:
        return list(configs)
    matched = [config for config in configs if config.name == name]
    if not matched:
        known = ", ".join(config.name for config in configs)
        raise SystemExit(f"no dataset {name!r}; configured datasets are: {known}")
    return matched


def main(argv: list[str] | None = None) -> int:
    """Generate the selected datasets and their .phosrun records."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    configs = load_batteries(CONFIG_DIRECTORY)

    for config in chosen(configs, args.dataset):
        directory, manifest = generate_attack_dataset(
            config, args.output, with_capture=not args.no_capture
        )
        logger.info(
            "%s: %d samples, %d attack(s), %d hostile case(s), %d attacked sample(s) -> %s",
            manifest.name,
            manifest.samples,
            len(manifest.attacks),
            len(manifest.hostile),
            manifest.attacked_samples,
            directory,
        )
        try:
            written = record_atlas_on_run(directory, args.output / f"{config.name}.phosrun")
            logger.info("wrote .phosrun: %s", written)
        except Exception as error:  # recording never kills corpus generation
            logger.warning("%s: could not write .phosrun: %s", config.name, error)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
