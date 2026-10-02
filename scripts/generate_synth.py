#!/usr/bin/env python3
"""Regenerate the standard normal datasets from their committed configs.

Nothing this script writes is committed. That is the point: a corpus defined by a plant, a seed
and a duration does not need to be stored, because it can be produced again exactly, on any
machine, from the numbers in ``configs/synth/*.toml``. What is committed is the generator and the
config; ``.gitignore`` keeps the payload out — manifest included, because unlike a downloaded
corpus even the manifest is a generated artefact here.

This file is a command line and nothing else. What a corpus *is* lives in `phos.synth.generate`,
so it is tested as part of the package rather than as a script nothing imports.

Usage::

    python scripts/generate_synth.py --list
    python scripts/generate_synth.py --all
    python scripts/generate_synth.py synth-water-treatment-train
    python scripts/generate_synth.py --all --output data --no-capture
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

from phos.synth.catalogue import DatasetConfig, load_configs  # noqa: E402
from phos.synth.generate import GenerationError, generate_dataset  # noqa: E402

CONFIG_DIR: Final = REPO_ROOT / "configs" / "synth"
DEFAULT_OUTPUT: Final = REPO_ROOT / "data" / "synth"
"""Generated corpora live one level below the downloaded ones.

`tests/eval/test_real_dataset.py` discovers real corpora by globbing ``data/*/manifest.json`` and
reading each hit as a `LabelledCsvAdapter` config. A synthetic manifest is a different document
with a different schema, so writing one at ``data/<name>/manifest.json`` would be handing that
test a manifest it cannot read.
"""

logger = logging.getLogger("phos.synth.generate")


def describe(configs: Sequence[DatasetConfig]) -> None:
    """Print the standard datasets and what each one is."""
    logger.info("%d standard dataset(s) in %s", len(configs), CONFIG_DIR)
    for config in configs:
        spec = config.run_spec()
        logger.info(
            "  %-38s %-18s %-8s seed=%-8d %6d samples @ %gs",
            config.name,
            config.plant_id,
            config.role,
            config.seed,
            spec.n_steps,
            spec.interval_seconds,
        )


def select(
    configs: Sequence[DatasetConfig], names: Sequence[str], every: bool
) -> list[DatasetConfig]:
    """Return the configs the arguments asked for.

    Raises:
        GenerationError: If a requested name is not one of the standard datasets. The message
            names the ones that are, because a typo would otherwise look like a corpus that
            silently was not generated.
    """
    if every:
        return list(configs)
    by_name = {config.name: config for config in configs}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise GenerationError(f"no such dataset: {', '.join(unknown)}. Known: {', '.join(by_name)}")
    return [by_name[name] for name in names]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Regenerate the standard synthetic normal datasets from their configs."
    )
    parser.add_argument("names", nargs="*", help="dataset names to generate")
    parser.add_argument("--all", action="store_true", help="generate every standard dataset")
    parser.add_argument("--list", action="store_true", help="show the standard datasets and exit")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="directory to write corpora into"
    )
    parser.add_argument(
        "--no-capture", action="store_true", help="write telemetry and topology only"
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        configs = load_configs(CONFIG_DIR)
        if arguments.list or (not arguments.names and not arguments.all):
            describe(configs)
            return 0
        for config in select(configs, arguments.names, arguments.all):
            directory, manifest = generate_dataset(
                config, arguments.output, with_capture=not arguments.no_capture
            )
            logger.info(
                "%s: %d samples, %d benign event(s) -> %s",
                config.name,
                manifest.samples,
                len(manifest.events),
                ", ".join(f"{file.filename} ({file.records})" for file in manifest.files),
            )
            logger.debug("written to %s", directory)
    except (GenerationError, ValueError) as error:
        logger.error("%s", error)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
