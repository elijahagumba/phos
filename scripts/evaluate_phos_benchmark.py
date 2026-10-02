#!/usr/bin/env python3
"""Print PHOS Benchmark v1. Cite frozen public rows. Do not search thresholds.

Usage::

    python scripts/evaluate_phos_benchmark.py
    python scripts/evaluate_phos_benchmark.py --write --output-dir eval_runs/benchmark
    python scripts/evaluate_phos_benchmark.py --write --ablation --adversary --research
"""

from __future__ import annotations

import argparse
from pathlib import Path

from phos.eval.ablation import render_fixture_ladder_markdown, run_atlas_fixture_ladder
from phos.eval.adversary import render_adversary_markdown
from phos.eval.benchmark import (
    BENCHMARK_SEED,
    assemble_v1_table,
    render_v1_json,
    render_v1_markdown,
)
from phos.eval.clock_b_research import assemble_clock_b_research


def main(argv: list[str] | None = None) -> int:
    """Assemble the frozen table, print it, optionally write Markdown and JSON."""
    parser = argparse.ArgumentParser(
        description=("PHOS Benchmark v1: cite frozen public rows; refuse unsupported cells.")
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write phos-benchmark-v1.md and .json under --output-dir.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval_runs/benchmark"),
        help="Directory for --write (default: eval_runs/benchmark).",
    )
    parser.add_argument(
        "--ablation",
        action="store_true",
        help="Also write ablation-fixture.md (toy ladder, not a public row).",
    )
    parser.add_argument(
        "--adversary",
        action="store_true",
        help="Also write adversary-catalogue.md (spec, not detection).",
    )
    parser.add_argument(
        "--research",
        action="store_true",
        help="Also write clock-b-research.md (Wave 3 scoreboard behind the freeze).",
    )
    args = parser.parse_args(argv)
    table = assemble_v1_table()
    markdown = render_v1_markdown(table)
    print(markdown, end="" if markdown.endswith("\n") else "\n")
    if args.write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "phos-benchmark-v1.md").write_text(markdown, encoding="utf-8")
        (args.output_dir / "phos-benchmark-v1.json").write_text(
            render_v1_json(table), encoding="utf-8"
        )
    if args.ablation:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        ladder = render_fixture_ladder_markdown(run_atlas_fixture_ladder(seed=BENCHMARK_SEED))
        (args.output_dir / "ablation-fixture.md").write_text(ladder, encoding="utf-8")
    if args.adversary:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "adversary-catalogue.md").write_text(
            render_adversary_markdown(), encoding="utf-8"
        )
    if args.research:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        repo_root = Path(__file__).resolve().parents[1]
        (args.output_dir / "clock-b-research.md").write_text(
            assemble_clock_b_research(repo_root), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
