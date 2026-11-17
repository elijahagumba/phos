"""The command line over `phos.referee`: ``phos-referee make-exam|run|report|retire-seeds``.

PART S6. Argument parsing and exit codes live here, following the division
`scripts/generate_synth.py` already uses: the work is in the package, so it is covered by the
package's own tests, and this module owns only how a person drives it and how a failure is
reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

from phos.eval import Detector, current_git_commit
from phos.referee.exam import Exam, ExamError, make_exam
from phos.referee.findings import FindingRegistry
from phos.referee.findings.regression import replay_findings
from phos.referee.integrity import DirtyWorkingTreeError, refuse_if_dirty_for_private_exam
from phos.referee.report import load_raw_scores, write_raw_scores, write_report
from phos.referee.runner import run_exam
from phos.referee.scoring import ScoringError, aggregate
from phos.referee.seeds import (
    SeedEntry,
    SeedPool,
    SeedVault,
    SeedVaultError,
    assert_no_sealed_in_open_pools,
)

__all__ = ["build_parser", "main"]

_DEFAULT_DETECTOR_PATHS: Final[tuple[str, ...]] = (
    "src/phos/referee",
    "src/phos/atlas",
    "src/phos/models",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the ``phos-referee`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="phos-referee", description="Build, run and report PHOS exams."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    make_exam_parser = sub.add_parser("make-exam", help="Build an exam from a seed pool.")
    make_exam_parser.add_argument(
        "--pool", choices=[pool.value for pool in SeedPool], required=True
    )
    make_exam_parser.add_argument("--scorer-version", required=True)
    make_exam_parser.add_argument("--size", type=int, default=None)
    make_exam_parser.add_argument("--hours", type=float, default=24.0)
    make_exam_parser.add_argument("--out", type=Path, required=True)
    make_exam_parser.add_argument("--repo-root", type=Path, default=Path())

    run_parser = sub.add_parser("run", help="Run a detector against an exam.")
    run_parser.add_argument("--exam", type=Path, required=True)
    run_parser.add_argument(
        "--detector", required=True, help='a "module:function" factory, called with no arguments'
    )
    run_parser.add_argument("--work-dir", type=Path, required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--repo-root", type=Path, default=Path())
    run_parser.add_argument(
        "--detector-paths",
        nargs="*",
        default=_DEFAULT_DETECTOR_PATHS,
        help="checked clean before a private-pool exam runs",
    )

    report_parser = sub.add_parser("report", help="Render a report from an already-scored run.")
    report_parser.add_argument("--exam", type=Path, required=True)
    report_parser.add_argument("--run", type=Path, required=True, help="the --out of `run`")
    report_parser.add_argument("--out", type=Path, required=True)

    retire_parser = sub.add_parser("retire-seeds", help="Move seeds from private to retired.")
    retire_parser.add_argument("--family", required=True)
    retire_parser.add_argument("--seed", type=int, action="append", required=True, dest="seeds")

    round_parser = sub.add_parser("round", help="Run one breaker round (development seeds only).")
    round_parser.add_argument(
        "--detector", required=True, help='detector "module:function" factory'
    )
    round_parser.add_argument("--budget", type=int, default=50, help="max queries per plant")
    round_parser.add_argument("--plants", type=int, default=5, help="dev plants to search")
    round_parser.add_argument("--seed", type=int, default=20261116, help="search master seed")
    round_parser.add_argument("--work-dir", type=Path, default=None)
    round_parser.add_argument("--findings-dir", type=Path, default=None)

    replay_parser = sub.add_parser(
        "replay-findings", help="Replay every finding through a detector (regression suite)."
    )
    replay_parser.add_argument(
        "--detector", required=True, help='detector "module:function" factory'
    )
    replay_parser.add_argument("--findings-dir", type=Path, required=True)
    replay_parser.add_argument("--out", type=Path, required=True)
    replay_parser.add_argument("--n-variants", type=int, default=5)

    return parser


def _resolve_detector(factory_path: str) -> Detector:
    """Import and call a ``module:function`` factory, returning what it builds.

    Raises:
        ValueError: If the string is not ``module:function``, the module cannot be imported, or
            the module has no such attribute. Every failure here is reported the same way the
            other refusals are, rather than as a traceback.
    """
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
        raise ValueError(f"{factory_path!r}: {module_name!r} has no {function_name!r}") from error
    return cast(Detector, factory())


def _cmd_make_exam(arguments: argparse.Namespace) -> int:
    vault = SeedVault.from_env()
    assert_no_sealed_in_open_pools(vault)
    pool = SeedPool(arguments.pool)
    kwargs: dict[str, object] = {"hours": arguments.hours}
    if arguments.size is not None:
        kwargs["size"] = arguments.size
    exam = make_exam(
        vault,
        pool,
        arguments.scorer_version,
        current_git_commit(arguments.repo_root),
        **kwargs,  # type: ignore[arg-type]
    )
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(exam.to_json(), encoding="utf-8")
    print(f"wrote exam {exam.exam_id} ({len(exam.entries)} plant(s)) to {arguments.out}")
    return 0


def _cmd_run(arguments: argparse.Namespace) -> int:
    exam = Exam.from_json(arguments.exam.read_text(encoding="utf-8"))
    private_entries = {entry.pool for entry in exam.entries}
    if SeedPool.PRIVATE in private_entries:
        record = refuse_if_dirty_for_private_exam(
            arguments.repo_root, tuple(arguments.detector_paths)
        )
        print(f"private exam: working tree clean at {record.commit}")

    detector = _resolve_detector(arguments.detector)
    plants = run_exam(exam, detector, arguments.work_dir)
    write_raw_scores(getattr(detector, "name", arguments.detector), plants, arguments.out)
    print(f"scored {len(plants)} plant(s); wrote raw scores to {arguments.out}")
    return 0


def _cmd_report(arguments: argparse.Namespace) -> int:
    exam = Exam.from_json(arguments.exam.read_text(encoding="utf-8"))
    detector_name, plants = load_raw_scores(arguments.run)
    score = aggregate(detector_name, plants)
    markdown_path, json_path = write_report(exam, score, arguments.out)
    print(f"wrote {markdown_path} and {json_path}")
    return 0


def _cmd_retire_seeds(arguments: argparse.Namespace) -> int:
    vault = SeedVault.from_env()
    entries = [SeedEntry(family=arguments.family, seed=seed) for seed in arguments.seeds]
    vault.retire(entries)
    print(f"retired {len(entries)} seed(s) for family {arguments.family!r}")
    return 0


def _cmd_round(arguments: argparse.Namespace) -> int:
    vault = SeedVault.from_env()
    detector = _resolve_detector(arguments.detector)

    from phos.breaker.round_runner import run_round as breaker_run_round

    report = breaker_run_round(
        detector=detector,
        vault=vault,
        budget_per_plant=arguments.budget,
        n_plants=arguments.plants,
        seed=arguments.seed,
        work_dir=arguments.work_dir,
        findings_dir=arguments.findings_dir,
    )

    print(
        f"breaker round {report.round_id}: "
        f"{report.n_attempts} attempts, {report.n_successes} successes, "
        f"{report.n_queries} queries on {report.n_dev_seeds} dev seeds"
    )
    return 0


def _cmd_replay_findings(arguments: argparse.Namespace) -> int:
    detector = _resolve_detector(arguments.detector)
    registry = FindingRegistry(arguments.findings_dir)
    results = replay_findings(
        registry=registry,
        detector=detector,
        n_variants=arguments.n_variants,
    )
    still_missed = [r for r in results if r.still_missed]
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        json.dumps(
            {
                "total_findings": len(results),
                "still_missed": len(still_missed),
                "regressions": [r.finding_id for r in still_missed],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"replayed {len(results)} finding(s); {len(still_missed)} still missed")
    return 0


_COMMANDS = {
    "make-exam": _cmd_make_exam,
    "run": _cmd_run,
    "report": _cmd_report,
    "retire-seeds": _cmd_retire_seeds,
    "round": _cmd_round,
    "replay-findings": _cmd_replay_findings,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``phos-referee`` command line.

    Returns:
        ``0`` on success, ``1`` when the command refuses to run (a bad exam, a dirty private
        exam, a bad seed-pool state). A refusal is reported as one line naming why rather than a
        traceback.
    """
    arguments = build_parser().parse_args(argv)
    try:
        return _COMMANDS[arguments.command](arguments)
    except (ExamError, ScoringError, SeedVaultError, DirtyWorkingTreeError, ValueError) as error:
        print(f"phos-referee {arguments.command}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
