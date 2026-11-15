"""The argument parser for ``scripts/genesis.py``.

Kept apart from the subcommands so that each file stays under the project's 500-line ceiling and so
that the wiring -- which subcommand takes which flag -- can be read on its own. Every subcommand's
callable is attached with ``set_defaults(fn=...)``, which is what ``cli.main`` dispatches on.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from phos.genesis.cli_commands import (
    ROOT,
    cmd_adr,
    cmd_ask,
    cmd_audit,
    cmd_declare,
    cmd_finding,
    cmd_gate,
    cmd_next,
    cmd_promote,
    cmd_report,
    cmd_result,
    cmd_state,
    cmd_template,
)
from phos.genesis.templates import TEMPLATES


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for every subcommand."""
    parser = argparse.ArgumentParser(
        prog="genesis", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("state", help="reconstruct the research state").set_defaults(fn=cmd_state)

    following = subparsers.add_parser("next", help="open questions, ranked")
    following.add_argument("-n", "--number", type=int, default=5)
    following.set_defaults(fn=cmd_next)

    template = subparsers.add_parser("template", help="print a JSON skeleton")
    template.add_argument("kind", choices=sorted(TEMPLATES))
    template.set_defaults(fn=cmd_template)

    ask = subparsers.add_parser("ask", help="register a research question")
    ask.add_argument("--from", dest="source", type=Path, required=True)
    ask.set_defaults(fn=cmd_ask)

    declare = subparsers.add_parser("declare", help="declare an experiment before it runs")
    declare.add_argument("--from", dest="source", type=Path, required=True)
    declare.set_defaults(fn=cmd_declare)

    gate = subparsers.add_parser("gate", help="refuse an undeclared command")
    gate.add_argument("--command", required=True)
    gate.set_defaults(fn=cmd_gate)

    result = subparsers.add_parser("result", help="attach numbers and judge them")
    result.add_argument("experiment")
    result.add_argument("--from", dest="source", type=Path, required=True)
    result.set_defaults(fn=cmd_result)

    finding = subparsers.add_parser("finding", help="open a claim at level 0")
    finding.add_argument("--from", dest="source", type=Path, required=True)
    finding.set_defaults(fn=cmd_finding)

    promote = subparsers.add_parser("promote", help="move a finding up the ladder")
    promote.add_argument("finding")
    promote.add_argument("--level", type=int, required=True, choices=range(1, 6))
    promote.add_argument("--reason", required=True)
    promote.set_defaults(fn=cmd_promote)

    adr = subparsers.add_parser("adr", help="render the prose record")
    adr.add_argument("experiment")
    adr.add_argument("--number", required=True)
    adr.add_argument("--title", required=True)
    adr.add_argument("--out", type=Path, default=None)
    adr.set_defaults(fn=cmd_adr)

    report = subparsers.add_parser("report", help="the session research report")
    report.add_argument("--since", default="0000-00-00")
    report.set_defaults(fn=cmd_report)

    subparsers.add_parser("audit", help="integrity of the record").set_defaults(fn=cmd_audit)
    return parser
