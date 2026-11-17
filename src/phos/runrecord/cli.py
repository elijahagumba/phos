"""The ``phos-run`` command line tool.

Usage:
    phos-run inspect FILE     -- print a plain-language summary of a run
    phos-run verify FILE      -- check every member hash and the run_id
    phos-run list DIR         -- describe every .phosrun in a directory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .reader import RunRecord, read_header, verify


def _fmt_size(size_bytes: int) -> str:
    """Format a byte count in human-readable units."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def cmd_inspect(path: Path) -> int:
    """Print a plain-language summary of a run file."""
    try:
        with RunRecord(path) as run:
            h = run.header
            print(f"Run: {h.get('title', '(untitled)')}")
            print(f"  ID: {run.run_id}")
            print(f"  Kind: {run.kind}")
            print(f"  Pool: {run.pool}")
            print(f"  Created by: {h.get('created_by', '(unknown)')}")
            print(f"  Summary: {h.get('plain_language_summary', '(none)')}")
            if h.get("model_not_reality_caveat"):
                print(f"  Caveat: {h['model_not_reality_caveat']}")
            print()
            print("Contents:")
            print("  Plant:        yes")
            print("  Structure:    yes")
            print("  Timeline:     yes")
            print("  Telemetry:    yes")
            print("  Labels:       yes")
            atlas = run.atlas()
            print(f"  Atlas data:   {'yes' if atlas else 'no'}")
            scores = run.scores()
            print(f"  Scores:       {'yes' if scores else 'no'}")
            traffic = run.traffic()
            print(f"  Traffic:      {'yes' if traffic else 'no'}")
    except Exception as exc:
        print(f"error: cannot inspect {path}: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_verify(path: Path) -> int:
    """Verify every member hash and the run_id of a .phosrun file."""
    problems = verify(path)
    if problems:
        print(f"{path}: INVALID", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"{path}: OK")
    return 0


def cmd_list(directory: Path) -> int:
    """List every .phosrun in a directory with header info."""
    runs_dir = Path(directory)
    if not runs_dir.is_dir():
        print(f"error: not a directory: {runs_dir}", file=sys.stderr)
        return 1

    phosrun_files = sorted(runs_dir.glob("*.phosrun"))
    if not phosrun_files:
        print(f"No .phosrun files found in {runs_dir}")
        return 0

    print(f"{'Run ID':<16} {'Kind':<14} {'Pool':<10} {'Title'}")
    print("-" * 80)
    for path in phosrun_files:
        try:
            header = read_header(path)
            run_id = header.get("run_id", "(unknown)")[:14]
            kind = header.get("kind", "(unknown)")
            pool = header.get("pool", "(unknown)")
            title = header.get("plain_language_summary", "(untitled)")
            print(f"{run_id:<16} {kind:<14} {pool:<10} {title}")
        except Exception as exc:
            print(f"{path.name:<16} ERROR: {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the phos-run CLI."""
    parser = argparse.ArgumentParser(
        prog="phos-run",
        description="Inspect, verify, and list .phosrun run records.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_p = subparsers.add_parser("inspect", help="print a plain-language summary")
    inspect_p.add_argument("file", type=Path, help="path to a .phosrun file")

    verify_p = subparsers.add_parser("verify", help="check every member hash and run_id")
    verify_p.add_argument("file", type=Path, help="path to a .phosrun file")

    list_p = subparsers.add_parser("list", help="describe every .phosrun in a directory")
    list_p.add_argument("directory", type=Path, help="directory of .phosrun files")

    args = parser.parse_args(argv)

    if args.command == "inspect":
        return cmd_inspect(args.file)
    if args.command == "verify":
        return cmd_verify(args.file)
    if args.command == "list":
        return cmd_list(args.directory)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
