"""Regenerate the standard attack battery from its committed configs.

Argument parsing and where the repository keeps its configs, and nothing else. What a corpus *is*
lives in `phos.synth.attacks.generate`, inside the package, so it is covered by the package's
tests rather than by a script nothing imports.

Usage::

    python scripts/generate_attacks.py --all
    python scripts/generate_attacks.py --dataset synth-attack-water-treatment-graded
    python scripts/generate_attacks.py --all --no-capture
"""

import argparse
import logging
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from phos.synth.attacks.battery import AttackDatasetConfig, load_batteries  # noqa: E402
from phos.synth.attacks.generate import generate_attack_dataset  # noqa: E402

CONFIG_DIRECTORY = REPOSITORY / "configs" / "attacks"
OUTPUT_DIRECTORY = REPOSITORY / "data" / "synth" / "attacks"

logger = logging.getLogger("phos.synth.attacks.generate_attacks")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="generate every configured dataset")
    selection.add_argument("--dataset", help="generate one dataset by name")
    parser.add_argument(
        "--output", type=Path, default=OUTPUT_DIRECTORY, help="where to write the corpora"
    )
    parser.add_argument(
        "--no-capture", action="store_true", help="skip the pcap and write telemetry only"
    )
    parser.add_argument("--verbose", action="store_true", help="log what each dataset contains")
    return parser.parse_args(argv)


def chosen(configs: tuple[AttackDatasetConfig, ...], name: str | None) -> list[AttackDatasetConfig]:
    """Return the configs to generate.

    Raises:
        SystemExit: If a named dataset is not configured. The message lists the ones that are,
            because a typo here would otherwise surface as a missing corpus much later.
    """
    if name is None:
        return list(configs)
    matched = [config for config in configs if config.name == name]
    if not matched:
        known = ", ".join(config.name for config in configs)
        raise SystemExit(f"no dataset {name!r}; configured datasets are: {known}")
    return matched


def main(argv: list[str] | None = None) -> int:
    """Generate the selected datasets and report what was written."""
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
