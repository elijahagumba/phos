"""The ``phos`` command: ``phos demo`` and ``phos onboard`` (ADR 0341)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from phos.atlas.onboarding import ONBOARD_SUMMARY, build_parser
from phos.atlas.onboarding import main as onboard_main
from phos.demo.pipeline import PLANT, Scenario, Stage, run_demo
from phos.demo.render import Style, render_header, render_result, render_stage

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phos",
        description="PHOS: behavioural security that tells you what it doesn't know.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    demo = commands.add_parser(
        "demo",
        help="run one simulated incident through Atlas and read its brief",
        description=(
            "Simulate a water plant, stage an incident on its control network, and show the brief "
            "Atlas writes, then what actually happened. A demonstration, not a measurement."
        ),
    )
    demo.add_argument(
        "--scenario",
        choices=[scenario.value for scenario in Scenario],
        default=Scenario.UNAUTHORISED.value,
        help="which incident to stage (default: unauthorised)",
    )
    demo.add_argument("--seed", type=int, default=11, help="seed for both runs (default: 11)")
    demo.add_argument("--no-colour", action="store_true", help="plain text, no ANSI styling")
    build_parser(
        commands.add_parser(
            "onboard",
            help="read a historian export and propose a role and a kind for each tag",
            description=(
                ONBOARD_SUMMARY + " Reads local files only: it makes no network calls, starts no "
                "agents, and nothing leaves your machine. A capture is optional; a historian "
                "export on its own produces a brief."
            ),
        )
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``phos`` command line."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "onboard":
        return onboard_main(_onboard_argv(argv))
    if args.command != "demo":
        parser.print_help()
        return 0

    colour = not args.no_colour and "NO_COLOR" not in os.environ and sys.stdout.isatty()
    style = Style(colour=colour)
    label = "simulated " + PLANT.replace("-", " ") + " plant"

    def show(stage: Stage) -> None:
        print(render_stage(stage, style), flush=True)

    print(render_header(label, args.seed, style), flush=True)
    result = run_demo(Scenario(args.scenario), seed=args.seed, on_stage=show)
    print(render_result(result, style), flush=True)
    return 0


def _onboard_argv(argv: Sequence[str] | None) -> list[str]:
    """Return the arguments after ``onboard``, for `phos.atlas.onboarding.main`.

    The subcommand's own parser has already accepted them, so re-parsing is a formality that keeps
    one implementation of the brief rather than two (ADR 0341).

    Args:
        argv: What `main` was given, or ``None`` to read ``sys.argv``.

    Returns:
        Every argument following the ``onboard`` word.
    """
    words = list(sys.argv[1:] if argv is None else argv)
    return words[words.index("onboard") + 1 :]


if __name__ == "__main__":
    raise SystemExit(main())
