"""Run the U5 crude non-operator instrument check and write the labelled report.

Not a field study. Not operational usefulness. Never appends to eval_runs/log.jsonl.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from phos.eval.decision_cases import (
    case_pack,
    mechanical_non_operator_response,
    primary_cases,
    render_arm,
)
from phos.eval.decision_report import (
    StudyResult,
    arm_order,
    render_study_json,
    render_study_markdown,
)
from phos.eval.decision_study import (
    Arm,
    SubjectKind,
    aggregate_arm,
    score_trial,
)

SEED = 11
REPORT = Path("eval_runs/usefulness/u5-decision-study.md")
REPORT_JSON = Path("eval_runs/usefulness/u5-decision-study.json")


def _commit() -> str:
    """Return HEAD, or ``unknown`` if git is unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_instrument_check(*, git_commit: str | None = None, seed: int = SEED) -> StudyResult:
    """Score every case under every arm with the mechanical non-operator policy.

    Args:
        git_commit: Stamp for the report. Defaults to HEAD.
        seed: Recorded for traceability. The fixtures are deterministic; the seed is not drawn.

    Returns:
        A study result whose markdown states the limitations before any table.
    """
    pack = case_pack()
    atlas = primary_cases(pack)
    sentiel = tuple(item for item in pack if not item.in_primary_comparison)
    scores = []
    for case in pack:
        for arm in Arm:
            stimulus = render_arm(case, arm)
            response = mechanical_non_operator_response(case.case_id, arm, stimulus)
            scores.append(score_trial(case.gold, response))
    order = arm_order()
    atlas_ids = {case.case_id for case in atlas}
    sentiel_ids = {case.case_id for case in sentiel}
    primary = tuple(
        aggregate_arm(arm, [item for item in scores if item.case_id in atlas_ids]) for arm in order
    )
    sentiel_rows = tuple(
        aggregate_arm(arm, [item for item in scores if item.case_id in sentiel_ids])
        for arm in order
    )
    return StudyResult(
        subject_kind=SubjectKind.MECHANICAL_NON_OPERATOR,
        n_human=0,
        n_mechanical=1,
        seed=seed,
        git_commit=git_commit if git_commit is not None else _commit(),
        n_atlas_cases=len(atlas),
        n_sentiel_cases=len(sentiel),
        primary=primary,
        sentiel=sentiel_rows,
        scores=scores,
        sentiel_settling_is_weak=any(case.sentiel_settling_is_weak for case in pack),
    )


def main(argv: list[str] | None = None) -> int:
    """Write the crude-run report, or print it with ``--no-write``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print markdown to stdout instead of writing eval_runs files.",
    )
    args = parser.parse_args(argv)
    result = run_instrument_check()
    markdown = render_study_markdown(result)
    payload = render_study_json(result)
    if args.no_write:
        print(markdown)
        return 0
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(markdown, encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
