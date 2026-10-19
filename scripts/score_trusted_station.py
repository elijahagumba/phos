#!/usr/bin/env python3
"""Score lane T's known-operator command effect.

Development (97801-97820) may be repeated. Held-back is refused unless the declaration ADR is
already in HEAD and the output file does not exist. The score is a simulated diagnosis.

Usage::

    uv run python scripts/score_trusted_station.py
    uv run python scripts/score_trusted_station.py --split held-back
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from phos.atlas.command_effect import (
    OUTSIDE_OPERATING_MODE,
    SETPOINT_JUMP,
    TOWARD_LIMIT_AGAINST_STATE,
    WRITE_AND_HIDE,
)
from phos.eval.trusted_station import (
    RESULT_NAME,
    challenger_sha256,
    held_back_allowed,
    render_development,
    render_held_back,
    score_development,
    score_held_back,
)

DEVELOPMENT_OUTPUT = Path("eval_runs/build/d/trusted/h1-development.md")
HELD_BACK_OUTPUT = Path("eval_runs/build/d/trusted/held-back.md")
DECLARATION = Path("docs/adr/0254-trusted-station-held-back-is-declared.md")
KNOWN_LINK_TESTS = (
    "tests/atlas/test_templates.py::test_a_function_change_on_a_known_link_still_supports_both",
    "tests/atlas/test_templates.py::test_a_silent_known_link_still_supports_both",
    "tests/atlas/test_templates.py::test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence",
)


def _in_head(path: Path) -> bool:
    """Return whether ``path`` is already committed at HEAD."""
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path.as_posix()}"],
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def main(argv: list[str] | None = None) -> int:
    """Score one split and write its report. Held-back exits without writing when refused."""
    parser = argparse.ArgumentParser(description="Score lane T trusted-station runs.")
    parser.add_argument("--split", choices=("development", "held-back"), default="development")
    parser.add_argument(
        "--features",
        default=TOWARD_LIMIT_AGAINST_STATE,
        help="Comma-separated command-effect features.",
    )
    args = parser.parse_args(argv)
    enabled = frozenset(part for part in args.features.split(",") if part)
    if args.split == "development":
        heading = "Lane T development"
        output = DEVELOPMENT_OUTPUT
        if enabled == frozenset({SETPOINT_JUMP, OUTSIDE_OPERATING_MODE}):
            heading = "Lane T H2 development"
            output = Path("eval_runs/build/d/trusted/h2-development.md")
        elif enabled == frozenset({WRITE_AND_HIDE}):
            heading = "Lane T H3 development"
            output = Path("eval_runs/build/d/trusted/h3-development.md")
        text = render_development(
            score_development(enabled=enabled),
            heading=heading,
            features=", ".join(sorted(enabled)),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(text)
        return 0
    allowed = held_back_allowed(
        output_exists=HELD_BACK_OUTPUT.exists(),
        declaration_in_head=_in_head(DECLARATION),
    )
    if not allowed:
        print(
            f"refusing held-back score for {RESULT_NAME}: "
            "the declaration must be in HEAD and the output must not already exist",
            file=sys.stderr,
        )
        return 2
    declared = subprocess.run(
        ["git", "show", f"HEAD:{DECLARATION.as_posix()}"],
        check=False,
        capture_output=True,
        text=True,
    )
    digest = challenger_sha256()
    if declared.returncode != 0 or digest not in declared.stdout:
        print(
            f"refusing held-back score for {RESULT_NAME}: "
            f"HEAD does not declare challenger sha256 {digest}",
            file=sys.stderr,
        )
        return 2
    tests = subprocess.run(
        ["uv", "run", "pytest", "-q", *KNOWN_LINK_TESTS],
        check=False,
    )
    text = render_held_back(score_held_back(), tests_green=tests.returncode == 0)
    HELD_BACK_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HELD_BACK_OUTPUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if tests.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
