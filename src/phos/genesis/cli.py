"""The entry point ``scripts/genesis.py`` calls.

The subcommands are in ``cli_commands`` and the argparse wiring is in ``cli_parser``; this module
is only the dispatch, so that the import path ``phos.genesis.cli.main`` stays the one thing the
script and the tests depend on.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Final

from phos.genesis.cli_commands import EXIT_REFUSED, EXIT_USAGE
from phos.genesis.cli_parser import build_parser
from phos.genesis.store import Store

__all__ = ["EXIT_REFUSED", "EXIT_USAGE", "main"]

#: Re-exported so callers need only one import.
_EXIT: Final = (EXIT_REFUSED, EXIT_USAGE)


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand.

    Args:
        argv: Arguments, or ``None`` for ``sys.argv[1:]``.

    Returns:
        ``0`` fine, ``2`` bad arguments, ``3`` refused.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "today"):
        args.today = subprocess.run(
            ["date", "+%Y-%m-%d"], capture_output=True, text=True, check=False
        ).stdout.strip()
    store = Store(args.root)
    try:
        result: int = args.fn(store, args)
    except (ValueError, SystemExit) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    return result
