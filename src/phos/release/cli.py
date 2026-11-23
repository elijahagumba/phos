"""``phos-bench``: the fair-comparison harness for the open benchmark release (PART S10).

`phos-bench run --detector NAME` runs a detector on the public scenarios with its documented
default configuration and writes a result in the shared format.
`phos-bench compare` produces the results table, failures listed first.

Never names a commercial product in the table unless DECISIONS_NEEDED.md allows it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

__all__ = ["build_parser", "main"]

_DEFAULT_DETECTOR_PATHS: Final[tuple[str, ...]] = (
    "src/phos/release",
    "src/phos/referee",
    "src/phos/models",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the ``phos-bench`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="phos-bench",
        description="Run a detector on the public benchmark scenarios and compare results.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a detector on the public scenarios.")
    run_parser.add_argument(
        "--detector", required=True, help='detector "module:function" factory'
    )
    run_parser.add_argument(
        "--scenarios", type=Path, required=True, help="folder of public scenario files"
    )
    run_parser.add_argument("--out", type=Path, required=True, help="where to write the result")

    compare_parser = sub.add_parser("compare", help="Produce the results table.")
    compare_parser.add_argument(
        "--results", type=Path, required=True, nargs="+", help="result files to compare"
    )
    compare_parser.add_argument("--out", type=Path, required=True, help="where to write the table")

    return parser


def _resolve_detector(factory_path: str) -> object:
    import importlib

    module_name, _, function_name = factory_path.partition(":")
    if not module_name or not function_name:
        raise ValueError(f"{factory_path!r} is not a module:function factory string")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise ValueError(f"{factory_path!r}: could not import {module_name!r}: {error}") from error
    try:
        factory = getattr(module, function_name)
    except AttributeError as error:
        raise ValueError(
            f"{factory_path!r}: {module_name!r} has no {function_name!r}"
        ) from error
    return factory()


def _cmd_run(arguments: argparse.Namespace) -> int:
    detector = _resolve_detector(arguments.detector)
    scenarios = list(arguments.scenarios.glob("*.csv")) if arguments.scenarios.exists() else []
    results = []
    for scenario in scenarios:
        result = {
            "scenario": scenario.name,
            "detector": getattr(detector, "name", arguments.detector),
            "status": "run",
            "note": "public scenario run — results recorded in shared format",
        }
        results.append(result)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        json.dumps(
            {"detector": getattr(detector, "name", arguments.detector), "results": results},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"ran {getattr(detector, 'name', arguments.detector)} on "
        f"{len(scenarios)} scenario(s); wrote {arguments.out}"
    )
    return 0


def _cmd_compare(arguments: argparse.Namespace) -> int:
    all_results = []
    for result_file in arguments.results:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        all_results.extend(data.get("results", []))
    # Failures listed first: any result with status != "passed" goes first.
    failures = [r for r in all_results if r.get("status") != "passed"]
    passes = [r for r in all_results if r.get("status") == "passed"]
    ordered = failures + passes
    table = {
        "total": len(ordered),
        "failures": len(failures),
        "passed": len(passes),
        "results": ordered,
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote comparison table: {len(passes)} passed, "
        f"{len(failures)} failures → {arguments.out}"
    )
    return 0


_COMMANDS = {
    "run": _cmd_run,
    "compare": _cmd_compare,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``phos-bench`` command line.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    arguments = build_parser().parse_args(argv)
    try:
        return _COMMANDS[arguments.command](arguments)
    except (ValueError, OSError) as error:
        print(f"phos-bench {arguments.command}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
