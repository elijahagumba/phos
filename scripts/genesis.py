"""GENESIS — one command-line surface for the PHOS research record, in Cursor and in Claude Code.

The charter is ``docs/rules/genesis-charter.md``. This script is the part of it a tool executes.
Claude Code has skills and hooks; Cursor has neither, so anything that exists only as a skill is
absent from half the work. Everything here is a plain command, which both tools run and a human
can run by hand.

Subcommands::

    uv run python scripts/genesis.py state                  # reconstruct the research state
    uv run python scripts/genesis.py next -n 5              # what to work on, ranked (section XII)
    uv run python scripts/genesis.py template experiment    # a skeleton to fill
    uv run python scripts/genesis.py ask --from q.json      # register a research question
    uv run python scripts/genesis.py declare --from e.json  # declare an experiment, before any run
    uv run python scripts/genesis.py gate --command '<cmd>' # may this command run? exit 3 if not
    uv run python scripts/genesis.py result E-0001 --from m.json   # attach numbers, judge them
    uv run python scripts/genesis.py finding --from f.json  # open a claim at level 0
    uv run python scripts/genesis.py promote F-0001 --level 3 --reason '<why>'
    uv run python scripts/genesis.py adr E-0001 --number 0413 --title '<sentence>'
    uv run python scripts/genesis.py report                 # the session report, from the record
    uv run python scripts/genesis.py audit                  # integrity of the record

The work is in ``phos.genesis.cli`` so that it is typed, tested and importable; this file only
makes it runnable from a shell.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.genesis.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
