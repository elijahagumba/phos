#!/usr/bin/env python3
"""Derive the valve law and report ADR 0382's seven bars on the guard form.

ADR 0382 declares this run. The command it names is::

    uv run python scripts/lane_h_guard_form.py --icssim data/icssim-source/repo

Run it only when that record is in ``HEAD``. The result name is
``code-law:guard-form`` and the report path is
``eval_runs/build/lane-h/h1-guard-form.md``.

**What this command does.** It reads three files of the pinned checkout as text,
checking each sha256 against the digest ADR 0370 records; derives the valve law
from their syntax trees, including the forced actuator writes at modes 1 and 2;
and reports, for each of ADR 0382's seven bars, met or not met. It lists every
disagreement on the extended enumeration. It writes one file.

**What it does not do.** It does not import, execute or simulate the controller
source. It does not read ``data/phos-icssim-dev/roles.toml``. It does not open a
corpus, a capture or a historian file. It does not append to the experiment log under
``eval_runs/``.
It does not edit ``controller_valve`` or any of the six law predicates. It does
not place the derived law on the law page. It reports no rate, no percentage and
no score. It does not rerun ``scripts/lane_h_code_laws.py``.

A digest that does not match is a refusal of the run: the refusal is written to
the report path and the command exits non-zero. A bar that is not met is a
different thing: a result, written out in full, with the exit status saying so
and the hand-written law untouched. Either way the verdict is ADR 0383, written
by an agent that did not build the guard type.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phos.atlas.code_law import (  # noqa: E402
    check_agreement,
    derive_valve_law,
    read_pinned_source,
)
from phos.atlas.code_law.report import (  # noqa: E402
    RESULT_NAME,
    refusal_markdown,
    report_markdown,
)

DEFAULT_ICSSIM: Final = ROOT / "data" / "icssim-source" / "repo"
DEFAULT_REPORT: Final = ROOT / "eval_runs" / "build" / "lane-h" / "h1-guard-form.md"

logger = logging.getLogger("lane_h_guard_form")


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--icssim",
        type=Path,
        default=DEFAULT_ICSSIM,
        help="the pinned ICSSim checkout, the directory that holds src/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORT,
        help="where to write the report ADR 0382 names",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the declared command once and write its report.

    Args:
        argv: The command line, or None to read `sys.argv`.

    Returns:
        0 when every bar ADR 0382 computes is met, 1 when a bar is not met or
        the run was refused before a law could be derived.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    arguments = _parse_arguments(argv)
    out: Path = arguments.out
    out.parent.mkdir(parents=True, exist_ok=True)

    read = read_pinned_source(arguments.icssim)
    if read.source is None:
        out.write_text(refusal_markdown(read.refusals))
        for refusal in read.refusals:
            logger.info("refused %s: %s", refusal.relative, refusal.reason.value)
        logger.info("%s: the run was refused; report at %s", RESULT_NAME, out)
        return 1

    derivation = derive_valve_law(read.source)
    if derivation.law is None:
        out.write_text(
            "# "
            + RESULT_NAME
            + " - refused\n\nThe declared source was read, and it did not hold what"
            + " ADR 0382's bars require:\n\n"
            + "\n".join(f"- {line}" for line in derivation.refusals)
            + "\n"
        )
        for line in derivation.refusals:
            logger.info("refused: %s", line)
        logger.info("%s: no law was derived; report at %s", RESULT_NAME, out)
        return 1

    result = check_agreement(derivation.law)
    out.write_text(report_markdown(derivation.law, result))
    for bar in result.bars:
        logger.info("bar %s: %s", bar.name, "met" if bar.met else "not met")
    logger.info(
        "%s: disagreements listed = %s; all bars met = %s; report at %s",
        RESULT_NAME,
        len(result.disagreements),
        result.met,
        out,
    )
    return 0 if result.met else 1


if __name__ == "__main__":
    raise SystemExit(main())
