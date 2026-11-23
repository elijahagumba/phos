"""Command line for the breaker: ``phos-breaker round`` (PART S7).

Runs one breaker round against Atlas on development seeds, records attempts, and prints a
round report. All flags are documented; nothing here touches real devices or networks.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from phos.breaker.genome import AttackTechnique
from phos.breaker.round_runner import run_round
from phos.referee.seeds import SeedVault

__all__ = ["build_parser", "main"]

_DEFAULT_DETECTOR_PATHS: Final[tuple[str, ...]] = (
    "src/phos/breaker",
    "src/phos/referee",
    "src/phos/atlas",
    "src/phos/models",
)

_TECHNIQUES: Final[tuple[AttackTechnique, ...]] = (
    AttackTechnique.LEVEL_EXCURSION,
    AttackTechnique.TEMPERATURE_RAMP,
    AttackTechnique.PRESSURE_SPIKE,
    AttackTechnique.FLOW_MANIPULATION,
    AttackTechnique.VALVE_STUCK,
    AttackTechnique.SENSOR_DRIFT,
    AttackTechnique.SETPOINT_WALK,
)


def build_parser() -> argparse.ArgumentParser:
    """Return the ``phos-breaker`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="phos-breaker",
        description="Run one breaker round against Atlas (development seeds only).",
    )
    parser.add_argument(
        "--detector",
        default="phos.eval:ThresholdDetector",
        help='detector factory as "module:function" (default: the harness test fixture)',
    )
    parser.add_argument(
        "--strategy",
        choices=["random", "evolutionary", "hillclimb"],
        default="random",
        help="search strategy (default: random)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=50,
        help="max queries per plant (default: 50)",
    )
    parser.add_argument(
        "--plants",
        type=int,
        default=5,
        help="how many dev plants to search on (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261116,
        help="master seed for the search (default: 20261116)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="where generated plants and attempt logs are written",
    )
    parser.add_argument(
        "--detector-paths",
        nargs="*",
        default=_DEFAULT_DETECTOR_PATHS,
        help="paths checked clean before the round runs",
    )
    return parser


def _resolve_detector(factory_path: str) -> object:
    """Import and call a ``module:function`` factory, returning what it builds."""
    import importlib

    module_name, _, function_name = factory_path.partition(":")
    if not module_name or not function_name:
        raise ValueError(f"{factory_path!r} is not a module:function factory string")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise ValueError(
            f"{factory_path!r}: could not import {module_name!r}: {error}"
        ) from error
    try:
        factory = getattr(module, function_name)
    except AttributeError as error:
        raise ValueError(
            f"{factory_path!r}: {module_name!r} has no {function_name!r}"
        ) from error
    return factory()


def _build_strategy(name: str, seed: int) -> object:
    import random

    rng = random.Random(seed)
    tag_pool = (
        "tank_level",
        "outlet_flow",
        "inlet_valve",
        "pump_status",
        "tank_temperature",
    )
    if name == "evolutionary":
        from phos.breaker.search import EvolutionarySearch

        return EvolutionarySearch(
            rng=rng, tag_pool=tag_pool, techniques=_TECHNIQUES, hours=24.0
        )
    if name == "hillclimb":
        from phos.breaker.search import HillClimber

        return HillClimber(
            rng=rng, tag_pool=tag_pool, techniques=_TECHNIQUES, hours=24.0
        )
    from phos.breaker.search import RandomSearch

    return RandomSearch(rng=rng, tag_pool=tag_pool, techniques=_TECHNIQUES, hours=24.0)


def _cmd_round(arguments: argparse.Namespace) -> int:
    vault = SeedVault.from_env()
    detector = _resolve_detector(arguments.detector)
    strategy = _build_strategy(arguments.strategy, arguments.seed)

    report = run_round(
        detector=detector,
        vault=vault,
        budget_per_plant=arguments.budget,
        n_plants=arguments.plants,
        search_strategy=strategy,
        seed=arguments.seed,
        work_dir=arguments.work_dir,
    )

    print(
        json_report(report)
    )
    return 0


def json_report(report: object) -> str:
    """Return a round report as a JSON string."""
    import json

    return json.dumps(
        {
            "round_id": report.round_id,
            "detector_name": report.detector_name,
            "n_dev_seeds": report.n_dev_seeds,
            "n_attempts": report.n_attempts,
            "n_successes": report.n_successes,
            "n_queries": report.n_queries,
            "open_findings": report.open_findings,
        },
        indent=2,
    )


_COMMANDS = {
    "round": _cmd_round,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``phos-breaker`` command line.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    arguments = build_parser().parse_args(argv)
    try:
        return _COMMANDS[arguments.command](arguments)
    except (ValueError, OSError) as error:
        print(f"phos-breaker {arguments.command}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
