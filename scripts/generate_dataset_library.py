#!/usr/bin/env python3
"""Generate the dataset library: OT plant packs and IT person-days.

Payloads land under ``dataset library/*/generated/`` and are git-ignored. The catalogues
are committed. These are attacks and personas we designed; see `phos.library.caveats`.

Usage::

    python scripts/generate_dataset_library.py
    python scripts/generate_dataset_library.py --it-only
    python scripts/generate_dataset_library.py --ot-limit 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from phos.library import (  # noqa: E402
    generate_it_library,
    generate_ot_library,
    library_root,
    ot_packs,
    ot_scenario_count,
    ot_trains,
)

logger = logging.getLogger("phos.library.generate")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--it-only", action="store_true", help="write the IT library only")
    parser.add_argument("--ot-only", action="store_true", help="write the OT library only")
    parser.add_argument(
        "--ot-limit",
        type=int,
        default=None,
        help="generate only the first N OT attack packs (plus all three trains)",
    )
    parser.add_argument(
        "--with-capture",
        action="store_true",
        help="also write pcaps (slow; not required for telemetry scoring)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate the selected halves of the library."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    root = library_root(REPOSITORY)
    root.mkdir(parents=True, exist_ok=True)
    if not args.ot_only:
        generate_it_library(root)
        logger.info("IT library written under %s", root / "IT")
    if not args.it_only:
        packs = list(ot_packs())
        if args.ot_limit is not None:
            packs = packs[: args.ot_limit]
        logger.info("OT catalogue declares %d labelled windows", ot_scenario_count())
        generate_ot_library(
            root,
            with_capture=args.with_capture,
            packs=packs,
            trains=ot_trains(),
        )
        logger.info("OT library written under %s", root / "OT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
