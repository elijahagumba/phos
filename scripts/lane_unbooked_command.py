#!/usr/bin/env python3
"""Does an uncovered valve force separate mimic maintenance from genuine maintenance?

`unbooked_command` breaks a valve-mode write that is not release when no work order covers that
tag and time. A release write is silence. The work order names the asset `tank_output_valve`;
it covers `tank_output_valve_mode`, the setpoint `roles.toml` records for that valve. An asset
outside that table is refused. This command opens `phos-icssim-dev` only.
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

from phos.atlas.declared_law import UNBOOKED_COMMAND, LawRegister, assess_plant  # noqa: E402
from phos.atlas.icssim_adapter import read_traffic  # noqa: E402
from phos.atlas.joint_setpoint import SetpointStep  # noqa: E402
from phos.atlas.program_transfer import TransferWorkOrder  # noqa: E402

#: Mode tags `roles.toml` names as valve setpoints. The conveyor mode is not a valve.
VALVE_TAGS: Final[frozenset[str]] = frozenset({"tank_input_valve_mode", "tank_output_valve_mode"})

#: The generator's `VALVE_RELEASE`, which `declared_law._MODE_RELEASE` already uses.
RELEASE_VALUE: Final = 3.0

#: Work-order asset to the mode tag that asset's service writes. Cited from
#: `scripts/icssim/phos_icssim.py`, which writes the asset and the mode tag for the same job.
ASSET_MODE_TAG: Final[dict[str, str]] = {
    "tank_output_valve": "tank_output_valve_mode",
}

REGISTER: Final = LawRegister((UNBOOKED_COMMAND,))

_ORDER_COLUMNS: Final = ("work_order", "start", "end", "asset", "action")


@dataclass(frozen=True)
class PlantEvent:
    """One labelled window, in seconds from the run epoch."""

    kind: str
    label: str
    start: float
    end: float


@dataclass(frozen=True)
class ValveWrite:
    """One command, in seconds from the run epoch."""

    tag: str
    relative: float
    value: float
    role: str


@dataclass(frozen=True)
class Cover:
    """One work order, already joined to the mode tag it covers, in seconds from the epoch."""

    tag: str
    start: float
    end: float


@dataclass(frozen=True)
class Score:
    """Counts for one run, or the sum of several. Rates are computed on the total."""

    mimic_events: int
    mimic_caught: int
    maintenance_breaks: int
    setpoint_breaks: int
    release_breaks: int
    replay_events: int
    replay_caught: int
    rogue_events: int
    rogue_caught: int
    unlabelled_breaks: int
    breaks: int

    def metrics(self) -> dict[str, float]:
        """Return the four declared metrics.

        Raises:
            ValueError: If there is no mimic window, so a rate would divide by zero.
        """
        if self.mimic_events == 0:
            raise ValueError("no mimic_maintenance window, so a catch rate would divide by zero")
        return {
            "mimic_catch_rate": self.mimic_caught / self.mimic_events,
            "maintenance_breaks": float(self.maintenance_breaks),
            "setpoint_breaks": float(self.setpoint_breaks),
            "release_breaks": float(self.release_breaks),
        }


def require_dev_corpus(corpus: Path) -> None:
    """Refuse any directory whose name is not `phos-icssim-dev`."""
    if corpus.name != "phos-icssim-dev":
        raise ValueError(f"this harness reads phos-icssim-dev, not {corpus.name}")


def dev_runs(corpus: Path) -> tuple[Path, ...]:
    """Return `normal-` and `mixed-` run directories. `mixed2` is left unread."""
    found = [
        path
        for path in sorted(corpus.iterdir())
        if path.is_dir() and path.name.startswith(("normal-", "mixed-"))
    ]
    return tuple(found)


def read_orders(path: Path, epoch: float) -> tuple[Cover, ...]:
    """Join each work-order asset to its mode tag. An unknown asset is refused."""
    found: list[Cover] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or ()
        missing = [name for name in _ORDER_COLUMNS if name not in header]
        if missing:
            raise ValueError(f"{path} is missing column(s): {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            asset = (row["asset"] or "").strip()
            if asset not in ASSET_MODE_TAG:
                raise ValueError(
                    f"{path} line {line}: asset {asset!r} has no declared mode tag. "
                    "This harness does not prefix-match an asset name"
                )
            start = _finite(path, line, "start", row["start"] or "")
            end = _finite(path, line, "end", row["end"] or "")
            if end < start:
                raise ValueError(f"{path} line {line}: the order ends before it starts")
            found.append(Cover(tag=ASSET_MODE_TAG[asset], start=start - epoch, end=end - epoch))
    return tuple(found)


def score_plant(
    *,
    epoch: float,
    events: Sequence[PlantEvent],
    writes: Sequence[ValveWrite],
    orders: Sequence[Cover],
) -> Score:
    """Score one plant. A break that matches none or many writes is refused."""
    steps = tuple(
        SetpointStep(write.tag, _stamp(epoch, write.relative), write.value) for write in writes
    )
    work_orders = tuple(
        TransferWorkOrder(
            start=_stamp(epoch, order.start),
            end=_stamp(epoch, order.end),
            tag=order.tag,
        )
        for order in orders
    )
    report = assess_plant(
        steps,
        register=REGISTER,
        work_orders=work_orders,
        valve_tags=VALVE_TAGS,
    )
    matched: list[ValveWrite] = []
    for item in report.broken:
        if item.name != UNBOOKED_COMMAND.name:
            raise ValueError(
                f"the register produced {item.name}, which this harness does not score"
            )
        hits = [
            write
            for write in writes
            if _stamp(epoch, write.relative) == item.time
            and f"{write.tag} was forced to " in item.statement
        ]
        if len(hits) != 1:
            raise ValueError(
                f"a break at {item.time.isoformat()} matched {len(hits)} writes: {item.statement}"
            )
        matched.append(hits[0])
    relatives = tuple(write.relative for write in matched)
    mimic_caught, mimic_events = _caught(events, "mimic_maintenance", relatives)
    replay_caught, replay_events = _caught(events, "replay", relatives)
    rogue_caught, rogue_events = _caught(events, "rogue_command", relatives)
    return Score(
        mimic_events=mimic_events,
        mimic_caught=mimic_caught,
        maintenance_breaks=_inside_kind(events, "maintenance", relatives),
        setpoint_breaks=_inside_kind(events, "setpoint", relatives),
        release_breaks=sum(1 for write in matched if write.value == RELEASE_VALUE),
        replay_events=replay_events,
        replay_caught=replay_caught,
        rogue_events=rogue_events,
        rogue_caught=rogue_caught,
        unlabelled_breaks=sum(1 for relative in relatives if not _in_any(events, relative)),
        breaks=len(matched),
    )


def combine(parts: Sequence[Score]) -> Score:
    """Add run counts. The catch rate is computed once, on the total."""
    if not parts:
        raise ValueError("no runs to combine")
    return Score(
        mimic_events=sum(part.mimic_events for part in parts),
        mimic_caught=sum(part.mimic_caught for part in parts),
        maintenance_breaks=sum(part.maintenance_breaks for part in parts),
        setpoint_breaks=sum(part.setpoint_breaks for part in parts),
        release_breaks=sum(part.release_breaks for part in parts),
        replay_events=sum(part.replay_events for part in parts),
        replay_caught=sum(part.replay_caught for part in parts),
        rogue_events=sum(part.rogue_events for part in parts),
        rogue_caught=sum(part.rogue_caught for part in parts),
        unlabelled_breaks=sum(part.unlabelled_breaks for part in parts),
        breaks=sum(part.breaks for part in parts),
    )


def score_directory(directory: Path) -> Score:
    """Score one run. Maintenance with no work-order file is refused."""
    epoch = _epoch(directory / "manifest.json")
    events = _events(directory / "events.json")
    order_path = directory / "work_orders.csv"
    if any(event.kind == "maintenance" for event in events) and not order_path.is_file():
        raise ValueError(f"{directory.name}: maintenance is labelled and work_orders.csv is absent")
    orders = read_orders(order_path, epoch) if order_path.is_file() else ()
    writes = _writes(directory, epoch)
    return score_plant(epoch=epoch, events=events, writes=writes, orders=orders)


def module_digest() -> str:
    """Return the SHA-256 of the declared-law module this process imported."""
    import phos.atlas.declared_law as module

    return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()


def render(rows: Sequence[tuple[str, Score]], total: Score, path: Path) -> None:
    """Write the report the measurement cites."""
    metrics = total.metrics()
    lines = [
        "# Unbooked valve commands on the development plant",
        "",
        "Written by `scripts/lane_unbooked_command.py`.",
        "",
        "A break is a valve-mode write whose value is not release and whose tag and time no "
        "work order covers. The work order asset `tank_output_valve` covers "
        "`tank_output_valve_mode`. Release writes are not breaks.",
        "",
        f"The digest of `src/phos/atlas/declared_law.py` is `{module_digest()}`.",
        "",
        "## Per run",
        "",
        "| run | mimic | maintenance | setpoint | release | replay | rogue | unlabelled |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, score in rows:
        lines.append(
            (
                "| `{name}` | {mimic} | {maint} | {setpoint} | {release} "
                "| {replay} | {rogue} | {free} |"
            ).format(
                name=name,
                mimic=f"{score.mimic_caught}/{score.mimic_events}",
                maint=score.maintenance_breaks,
                setpoint=score.setpoint_breaks,
                release=score.release_breaks,
                replay=f"{score.replay_caught}/{score.replay_events}",
                rogue=f"{score.rogue_caught}/{score.rogue_events}",
                free=score.unlabelled_breaks,
            )
        )
    lines += [
        "",
        "## The metrics",
        "",
        "| metric | value |",
        "|---|---|",
        (
            f"| `mimic_catch_rate` | {metrics['mimic_catch_rate']:.12g} "
            f"({total.mimic_caught}/{total.mimic_events}) |"
        ),
        f"| `maintenance_breaks` | {total.maintenance_breaks} |",
        f"| `setpoint_breaks` | {total.setpoint_breaks} |",
        f"| `release_breaks` | {total.release_breaks} |",
        "",
        "Replay and rogue command are reported beside the bars. Both force a valve with no work "
        "order, so a break there is the law doing what it says. They are not part of the question, "
        "which is whether mimic maintenance and genuine maintenance come apart.",
        "",
        f"Breaks in total: {total.breaks}. "
        f"Breaks outside every labelled window: {total.unlabelled_breaks}.",
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
    print("result: atlas-unbooked-command")
    for key, value in metrics.items():
        print(f"{key}: {value:g}")
    print(
        f"mimic {total.mimic_caught}/{total.mimic_events}, "
        f"replay {total.replay_caught}/{total.replay_events}, "
        f"rogue {total.rogue_caught}/{total.rogue_events}, "
        f"unlabelled {total.unlabelled_breaks}"
    )
    print(f"wrote {args.report}")
    return 0


def _stamp(epoch: float, relative: float) -> datetime:
    """Return one timezone-aware time. The same pair always returns equal datetimes."""
    return datetime.fromtimestamp(epoch + relative, UTC)


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
        found.append(
            PlantEvent(kind=str(item["kind"]), label=str(item["label"]), start=start, end=end)
        )
    return tuple(found)


def _writes(directory: Path, epoch: float) -> tuple[ValveWrite, ...]:
    """Return every write in `modbus.csv`, relative to `epoch`."""
    found: list[ValveWrite] = []
    for command in read_traffic(directory, writes_only=True):
        if not math.isfinite(command.at) or not math.isfinite(command.value):
            raise ValueError(
                f"{directory.name}: command on {command.tag!r} at {command.at!r} is not finite"
            )
        found.append(
            ValveWrite(
                tag=command.tag,
                relative=command.at - epoch,
                value=command.value,
                role=command.role,
            )
        )
    return tuple(found)


def _caught(events: Sequence[PlantEvent], kind: str, relatives: Sequence[float]) -> tuple[int, int]:
    """Return how many windows of `kind` contain a break, and how many such windows there are."""
    chosen = tuple(event for event in events if event.kind == kind)
    caught = sum(1 for event in chosen if any(_covers(event, relative) for relative in relatives))
    return caught, len(chosen)


def _inside_kind(events: Sequence[PlantEvent], kind: str, relatives: Sequence[float]) -> int:
    """Return how many breaks fall inside a window of `kind`."""
    return sum(
        1
        for relative in relatives
        if any(_covers(event, relative) for event in events if event.kind == kind)
    )


def _in_any(events: Sequence[PlantEvent], relative: float) -> bool:
    """Return whether `relative` falls inside any labelled window."""
    return any(_covers(event, relative) for event in events)


def _covers(event: PlantEvent, relative: float) -> bool:
    """Return whether `relative` is inside the window, both ends included."""
    return event.start <= relative <= event.end


if __name__ == "__main__":
    sys.exit(main())
