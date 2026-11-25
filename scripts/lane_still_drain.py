#!/usr/bin/env python3
"""Does a level that stays still while the tank drains separate a freeze from a real drain?

`still_drain` breaks when a drain of two or more samples never changes the level. The outlet
is open, the inlet is shut, both modes are release, the flow is the plant's own outlet rate,
and the tank holds water. A drain whose level changes is silence. This command opens
`phos-icssim-dev` only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.atlas.declared_law import (  # noqa: E402
    STILL_DRAIN,
    DrainSample,
    LawRegister,
    _draining,
    assess_plant,
)

REGISTER: Final = LawRegister((STILL_DRAIN,))
_COLUMNS: Final = (
    "timestamp",
    "tank_level_value",
    "tank_input_valve_status",
    "tank_input_valve_mode",
    "tank_output_valve_status",
    "tank_output_valve_mode",
    "tank_output_flow_value",
)


@dataclass(frozen=True)
class PlantEvent:
    """One labelled window, in seconds from the run epoch."""

    kind: str
    start: float
    end: float


@dataclass(frozen=True)
class Score:
    """Counts for one run, or the sum of several."""

    quiet_breaks: int
    freeze_applicable: int
    freeze_caught: int
    maintenance_breaks: int
    setpoint_breaks: int
    freezes_without_drain: int

    def metrics(self) -> dict[str, float]:
        """Return the four declared metrics.

        Raises:
            ValueError: If no freeze contains a drain, so a rate would divide by zero.
        """
        if self.freeze_applicable == 0:
            raise ValueError("no freeze contains a drain, so a catch rate would divide by zero")
        return {
            "quiet_breaks": float(self.quiet_breaks),
            "freeze_catch_rate": self.freeze_caught / self.freeze_applicable,
            "maintenance_breaks": float(self.maintenance_breaks),
            "setpoint_breaks": float(self.setpoint_breaks),
        }


def require_dev_corpus(corpus: Path) -> None:
    """Refuse any directory whose name is not `phos-icssim-dev`."""
    if corpus.name != "phos-icssim-dev":
        raise ValueError(f"this harness reads phos-icssim-dev, not {corpus.name}")


def dev_runs(corpus: Path) -> tuple[Path, ...]:
    """Return `normal-` and `mixed-` run directories. `mixed2` is left unread."""
    return tuple(
        path
        for path in sorted(corpus.iterdir())
        if path.is_dir() and path.name.startswith(("normal-", "mixed-"))
    )


def score_plant(
    *,
    events: Sequence[PlantEvent],
    rows: Sequence[DrainSample],
    relatives: Sequence[float],
) -> Score:
    """Score one plant. A break is matched back to the row that started its drain."""
    report = assess_plant(register=REGISTER, drain_samples=rows)
    break_at = {item.time for item in report.broken if item.name == STILL_DRAIN.name}
    if len(break_at) != len(report.broken):
        raise ValueError("the register produced a break this harness does not score")
    break_rel = tuple(
        relative
        for sample, relative in zip(rows, relatives, strict=True)
        if sample.at in break_at
    )
    freezes = tuple(event for event in events if event.kind == "liar_freeze")
    applicable = tuple(event for event in freezes if _has_drain(rows, relatives, event))
    return Score(
        quiet_breaks=sum(1 for relative in break_rel if not _hit_any(freezes, relative)),
        freeze_applicable=len(applicable),
        freeze_caught=sum(1 for event in applicable if _hit(event, break_rel)),
        maintenance_breaks=_inside(events, "maintenance", break_rel),
        setpoint_breaks=_inside(events, "setpoint", break_rel),
        freezes_without_drain=len(freezes) - len(applicable),
    )


def combine(parts: Sequence[Score]) -> Score:
    """Add run counts. The catch rate is computed once, on the total."""
    if not parts:
        raise ValueError("no runs to combine")
    return Score(
        quiet_breaks=sum(part.quiet_breaks for part in parts),
        freeze_applicable=sum(part.freeze_applicable for part in parts),
        freeze_caught=sum(part.freeze_caught for part in parts),
        maintenance_breaks=sum(part.maintenance_breaks for part in parts),
        setpoint_breaks=sum(part.setpoint_breaks for part in parts),
        freezes_without_drain=sum(part.freezes_without_drain for part in parts),
    )


def score_directory(directory: Path) -> Score:
    """Score one run directory."""
    epoch = _epoch(directory / "manifest.json")
    events = _events(directory / "events.json")
    rows, relatives = _rows(directory / "process.csv", epoch)
    return score_plant(events=events, rows=rows, relatives=relatives)


def module_digest() -> str:
    """Return the SHA-256 of the declared-law module this process imported."""
    import phos.atlas.declared_law as module

    return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()


def render(scored: Sequence[tuple[str, Score]], total: Score, path: Path) -> None:
    """Write the report the measurement cites."""
    metrics = total.metrics()
    lines = [
        "# A level that stays still while the tank drains",
        "",
        "Written by `scripts/lane_still_drain.py`.",
        "",
        "A break is a drain of two or more samples whose level never changes. The outlet is "
        "open, the inlet is shut, both modes are release, and the flow is the plant's own "
        "outlet rate. A drain whose level changes is silence.",
        "",
        f"The digest of `src/phos/atlas/declared_law.py` is `{module_digest()}`.",
        "",
        "## Per run",
        "",
        "| run | quiet breaks | freezes caught | maintenance | setpoint | no drain |",
        "|---|---|---|---|---|---|",
    ]
    for name, score in scored:
        lines.append(
            f"| `{name}` | {score.quiet_breaks} | "
            f"{score.freeze_caught}/{score.freeze_applicable} | "
            f"{score.maintenance_breaks} | {score.setpoint_breaks} | "
            f"{score.freezes_without_drain} |"
        )
    lines += [
        "",
        "## The metrics",
        "",
        "| metric | value |",
        "|---|---|",
        f"| `quiet_breaks` | {total.quiet_breaks} |",
        (
            f"| `freeze_catch_rate` | {metrics['freeze_catch_rate']:.12g} "
            f"({total.freeze_caught}/{total.freeze_applicable}) |"
        ),
        f"| `maintenance_breaks` | {total.maintenance_breaks} |",
        f"| `setpoint_breaks` | {total.setpoint_breaks} |",
        "",
        "A freeze that never opens the outlet has no drain, so the law is not stated there. "
        f"Those freezes are counted beside the bars: {total.freezes_without_drain}.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Run the measurement and write the report. 2 means the corpus was refused."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        require_dev_corpus(args.corpus)
    except ValueError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    if not args.corpus.is_dir():
        print(f"refused: {args.corpus} is not a directory", file=sys.stderr)
        return 2
    runs = dev_runs(args.corpus)
    if not runs:
        print(f"refused: {args.corpus} has no normal- or mixed- runs", file=sys.stderr)
        return 2
    try:
        scored = tuple((run.name, score_directory(run)) for run in runs)
        total = combine(tuple(score for _name, score in scored))
        metrics = total.metrics()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    render(scored, total, args.report)
    print("result: atlas-still-drain")
    for key, value in metrics.items():
        print(f"{key}: {value:g}")
    print(f"freezes without a drain: {total.freezes_without_drain}")
    print(f"wrote {args.report}")
    return 0


def _epoch(path: Path) -> float:
    """Return the run epoch from `manifest.json`."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or "epoch" not in loaded:
        raise ValueError(f"{path} has no epoch")
    epoch = float(loaded["epoch"])
    if not math.isfinite(epoch):
        raise ValueError(f"{path} epoch is not finite")
    return epoch


def _events(path: Path) -> tuple[PlantEvent, ...]:
    """Return the labelled windows. Times stay relative to the run epoch."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError(f"{path} is not a list")
    found: list[PlantEvent] = []
    for index, item in enumerate(loaded, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path} event {index} is not an object")
        start = float(item["start"])
        end = float(item["end"])
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            raise ValueError(f"{path} event {index} has a window that is not finite and ordered")
        found.append(PlantEvent(kind=str(item["kind"]), start=start, end=end))
    return tuple(found)


def _rows(path: Path, epoch: float) -> tuple[tuple[DrainSample, ...], tuple[float, ...]]:
    """Return every recorder row and its time relative to the epoch."""
    samples: list[DrainSample] = []
    relatives: list[float] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or ()
        missing = [name for name in _COLUMNS if name not in header]
        if missing:
            raise ValueError(f"{path} is missing column(s): {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            absolute = _finite(path, line, "timestamp", row["timestamp"] or "")
            relative = absolute - epoch
            samples.append(
                DrainSample(
                    at=datetime.fromtimestamp(absolute, UTC),
                    level=_finite(path, line, "tank_level_value", row["tank_level_value"] or ""),
                    input_valve=_finite(
                        path, line, "tank_input_valve_status", row["tank_input_valve_status"] or ""
                    ),
                    input_mode=_finite(
                        path, line, "tank_input_valve_mode", row["tank_input_valve_mode"] or ""
                    ),
                    output_valve=_finite(
                        path,
                        line,
                        "tank_output_valve_status",
                        row["tank_output_valve_status"] or "",
                    ),
                    output_mode=_finite(
                        path, line, "tank_output_valve_mode", row["tank_output_valve_mode"] or ""
                    ),
                    flow=_finite(
                        path, line, "tank_output_flow_value", row["tank_output_flow_value"] or ""
                    ),
                )
            )
            relatives.append(relative)
    return tuple(samples), tuple(relatives)


def _finite(path: Path, line: int, column: str, cell: str) -> float:
    """Return one cell as a finite float, or refuse with the file, line and column."""
    text = cell.strip()
    if not text:
        raise ValueError(f"{path} line {line}, column {column!r}: the cell is empty")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(
            f"{path} line {line}, column {column!r}: {text!r} is not a number"
        ) from None
    if not math.isfinite(value):
        raise ValueError(f"{path} line {line}, column {column!r}: {text!r} is not finite")
    return value


def _has_drain(
    rows: Sequence[DrainSample], relatives: Sequence[float], event: PlantEvent
) -> bool:
    """Return whether the window holds two draining rows in a row.

    The same predicate the law uses, applied to the rows inside the window, so a freeze
    whose outlet never opens is not asked to produce a break.
    """
    run = 0
    for sample, relative in zip(rows, relatives, strict=True):
        if not (event.start <= relative <= event.end):
            continue
        if _draining(sample):
            run += 1
            if run >= 2:
                return True
        else:
            run = 0
    return False


def _hit_any(events: Sequence[PlantEvent], relative: float) -> bool:
    """Return whether `relative` falls inside any of `events`."""
    return any(event.start <= relative <= event.end for event in events)


def _hit(event: PlantEvent, relatives: Sequence[float]) -> bool:
    """Return whether a break falls inside the window, both ends included."""
    return any(event.start <= relative <= event.end for relative in relatives)


def _inside(events: Sequence[PlantEvent], kind: str, relatives: Sequence[float]) -> int:
    """Return how many breaks fall inside a window of `kind`."""
    return sum(
        1
        for relative in relatives
        if any(event.start <= relative <= event.end for event in events if event.kind == kind)
    )


if __name__ == "__main__":
    sys.exit(main())
