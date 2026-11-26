#!/usr/bin/env python3
"""The per-law discrimination matrix for the six laws in ``declared_law.py``.

Q-0007 asks whether each law fires only on the class of departure its own statement names.
ADR 0465 already established one category error by inspection: under the inlet's default
historian reading (``step_source="row"``) a value written once and held appears as one row per
sample, so a sequence of *readings* is handed to a law that reads a sequence of *writes*. That
record added ``step_source="change"`` and preserved ``"row"`` as the default. It did not ask
whether any other law is misled the same way.

This harness builds one inlet per named class with ground truth known by construction, runs one
``assess_plant`` with all six laws in the register, and records which laws fired. It reads no
corpus and no file: every class is constructed in process, so the ``synth`` corpus in the
declaration names synthetic constructions rather than a dataset on disk.

Two readings are scored, because the inlet has two:

- ``row`` — every listed historian row is a step. The default every earlier record measured.
- ``change`` — one step per tag where its value differs from that tag's previous row.

The difference between the two matrices is the measurement. If the only cell that moves between
them is the held-setpoint class, the inlet's default is what is wrong. If an off-diagonal cell
survives under ``change``, a *law* fires on a class it does not name, and no choice of
``step_source`` repairs that.

Nothing here edits a law, a predicate, a constant, a frozen number or an inlet default. The
digest of the two modules under test is printed so a reader can see which implementation was
measured.

Usage::

    uv run python scripts/law_discrimination_matrix.py
        --report eval_runs/build/lane-law-discrimination/matrix.md
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phos.atlas.declared_law import (  # noqa: E402
    ALLOWED_WRITER,
    BAND_HANDOFF,
    CONTROLLER_VALVE,
    JOINT_MOVE,
    LAWS,
    PROGRAM_TRANSFER,
    SUBFLOOR_WALK,
    LawRegister,
    WriterWrite,
    assess_plant,
)
from phos.atlas.law_inlet import (  # noqa: E402
    PLC1_CONTROLLER_TAGS,
    HistorianRow,
    LawInlet,
    StepSource,
    inlet_from_tables,
)
from phos.atlas.program_transfer import Booking, BookingKind, ProgramAct  # noqa: E402

#: One fixed instant. The matrix is about which law fires, not about when, so the clock is
#: constant and no class can be distinguished by its time of day.
T0: Final = datetime(2026, 1, 1, tzinfo=UTC)

#: All six laws, which is the register every case is scored against.
REGISTER: Final = LawRegister(LAWS)

#: The tag the walk classes use. In the band 6.5-7.5 for every row constructed below.
STEP_TAG: Final = "tank_level_max"
#: The second tag the joint and handoff classes use.
OTHER_TAG: Final = "tank_level_min"

#: The value a held setpoint sits at. Inside the ordinary band, so the only thing that can be
#: said about it is whether many readings of it are many writes.
HELD_VALUE: Final = 7.0

#: Both the classes that must break a named law, and the classes whose ground truth is silence.
_SIX: Final[tuple[str, ...]] = (
    JOINT_MOVE.name,
    SUBFLOOR_WALK.name,
    BAND_HANDOFF.name,
    PROGRAM_TRANSFER.name,
    ALLOWED_WRITER.name,
    CONTROLLER_VALVE.name,
)


@dataclass(frozen=True)
class Case:
    """One constructed inlet and the law, if any, its construction names.

    Attributes:
        key: The class name used in the matrix.
        owns: The one law this class is a departure *of*, or ``None`` when the ground truth is
            silence. A break under any law on a ``None`` case is an unintended break.
        note: What the construction is, in a sentence, for the report.
    """

    key: str
    owns: str | None
    note: str


def _steps(tag: str, count: int, *, start: datetime = T0) -> list[HistorianRow]:
    """Return ``count`` rows one second apart that move across the ordinary band.

    Consecutive values differ, so this is a *walk* under both readings: ``row`` gives ``count``
    steps and ``change`` also gives ``count`` steps. Every value stays inside 6.5-7.5.
    """
    return [
        HistorianRow(tag, start + timedelta(seconds=index), 6.5 + 1.0 * index / count)
        for index in range(count)
    ]


def _held(tag: str, count: int, *, start: datetime = T0) -> list[HistorianRow]:
    """Return ``count`` rows one second apart that all carry the same in-band value.

    This is the ADR 0465 construction: a value written once and then held. ``row`` reads it as
    ``count`` writes; ``change`` reads it as one.
    """
    return [
        HistorianRow(tag, start + timedelta(seconds=index), HELD_VALUE) for index in range(count)
    ]


def _controller_rows(output_valve: float) -> list[HistorianRow]:
    """Return the ten PLC1 rows one controller sample is built from, sharing one time.

    ``level`` sits inside its band, so the input side has no required value and cannot break.
    ``belt`` is below the filler constant and ``bottle_level`` below its maximum, so the output
    rule requires the valve **open** (1.0). ``output_valve`` is what the case supplies.
    """
    values: Final[dict[str, float]] = {
        "level": 7.0,
        "level_min": 6.0,
        "level_max": 8.0,
        "input_valve": 1.0,
        "input_mode": 3.0,
        "bottle_level": 0.0,
        "bottle_max": 10.0,
        "belt": 0.5,
        "output_valve": output_valve,
        "output_mode": 3.0,
    }
    return [HistorianRow(tag, T0, values[field]) for field, tag in PLC1_CONTROLLER_TAGS.items()]


def _case(key: str, reading: StepSource) -> LawInlet:
    """Build the inlet for one class under one historian reading.

    Args:
        key: The class name, as it appears in ``CASES``.
        reading: ``"row"`` or ``"change"``. Classes that carry no historian rows are identical
            under both readings, which is stated in the report.

    Returns:
        One inlet with only the facts that class supplies. Every other inlet is left empty, so a
        law that fires on a class it does not own did so on that class's own facts.

    Raises:
        KeyError: If ``key`` is not a known class.
    """
    if key == "joint_move":
        rows = [
            HistorianRow(STEP_TAG, T0, 7.0),
            HistorianRow(OTHER_TAG, T0 + timedelta(seconds=60), 7.0),
        ]
        return inlet_from_tables(
            register=REGISTER,
            historian=rows,
            setpoint_tags=frozenset({STEP_TAG, OTHER_TAG}),
            step_source=reading,
        )
    if key == "subfloor_walk":
        return inlet_from_tables(
            register=REGISTER,
            historian=_steps(STEP_TAG, 720),
            setpoint_tags=frozenset({STEP_TAG}),
            step_source=reading,
        )
    if key == "band_handoff":
        rows = [
            HistorianRow(STEP_TAG, T0, 7.0),
            HistorianRow(OTHER_TAG, T0 + timedelta(seconds=400), 7.0),
        ]
        return inlet_from_tables(
            register=REGISTER,
            historian=rows,
            setpoint_tags=frozenset({STEP_TAG, OTHER_TAG}),
            step_source=reading,
        )
    if key == "program_transfer":
        return inlet_from_tables(
            register=REGISTER, transfers=((ProgramAct.DOWNLOAD, T0),), step_source=reading
        )
    if key == "allowed_writer":
        return inlet_from_tables(
            register=REGISTER,
            writes=(WriterWrite("rogue-station", T0),),
            allowed_stations=frozenset({"plc1"}),
            step_source=reading,
        )
    if key == "controller_valve":
        return inlet_from_tables(
            register=REGISTER,
            historian=_controller_rows(output_valve=0.0),
            controller_tags=PLC1_CONTROLLER_TAGS,
            step_source=reading,
        )
    if key == "one_in_band_write":
        return inlet_from_tables(
            register=REGISTER,
            historian=[HistorianRow(STEP_TAG, T0, 7.0)],
            setpoint_tags=frozenset({STEP_TAG}),
            step_source=reading,
        )
    if key == "719_steps":
        return inlet_from_tables(
            register=REGISTER,
            historian=_steps(STEP_TAG, 719),
            setpoint_tags=frozenset({STEP_TAG}),
            step_source=reading,
        )
    if key == "booked_transfer":
        return inlet_from_tables(
            register=REGISTER,
            transfers=((ProgramAct.DOWNLOAD, T0),),
            bookings=(
                Booking(
                    kind=BookingKind.DOWNTIME,
                    act=ProgramAct.DOWNLOAD,
                    start=T0 - timedelta(hours=1),
                    end=T0 + timedelta(hours=1),
                ),
            ),
            step_source=reading,
        )
    if key == "allowed_station_write":
        return inlet_from_tables(
            register=REGISTER,
            writes=(WriterWrite("plc1", T0),),
            allowed_stations=frozenset({"plc1"}),
            step_source=reading,
        )
    if key == "controller_agrees":
        return inlet_from_tables(
            register=REGISTER,
            historian=_controller_rows(output_valve=1.0),
            controller_tags=PLC1_CONTROLLER_TAGS,
            step_source=reading,
        )
    if key == "two_distant_writes":
        rows = [
            HistorianRow(STEP_TAG, T0, 6.6),
            HistorianRow(OTHER_TAG, T0 + timedelta(seconds=400), 7.4),
        ]
        return inlet_from_tables(
            register=REGISTER,
            historian=rows,
            setpoint_tags=frozenset({STEP_TAG, OTHER_TAG}),
            step_source=reading,
        )
    if key == "held_setpoint":
        return inlet_from_tables(
            register=REGISTER,
            historian=_held(STEP_TAG, 720),
            setpoint_tags=frozenset({STEP_TAG}),
            step_source=reading,
        )
    raise KeyError(f"no such class: {key}")


#: Every class the matrix scores. Six are departures a law names; the rest are silence.
CASES: Final[tuple[Case, ...]] = (
    Case("joint_move", JOINT_MOVE.name, "Two in-band values on two tags, 60 s apart."),
    Case("subfloor_walk", SUBFLOOR_WALK.name, "720 one-second steps of one tag crossing the band."),
    Case("band_handoff", BAND_HANDOFF.name, "One in-band value on a second tag 400 s later."),
    Case("program_transfer", PROGRAM_TRANSFER.name, "An unbooked download."),
    Case(
        "allowed_writer",
        ALLOWED_WRITER.name,
        "A write from a station outside the declared set.",
    ),
    Case(
        "controller_valve",
        CONTROLLER_VALVE.name,
        "A release-mode sample whose output valve disagrees.",
    ),
    Case("one_in_band_write", None, "One in-band value on one tag, once."),
    Case("719_steps", None, "719 one-second steps: one fewer than the walk length."),
    Case("booked_transfer", None, "A download covered by a downtime booking."),
    Case("allowed_station_write", None, "A write from a station inside the declared set."),
    Case("controller_agrees", None, "A release-mode sample whose output valve agrees."),
    Case(
        "two_distant_writes",
        None,
        "Two in-band values on two tags, 400 s apart, different values.",
    ),
    Case("held_setpoint", None, "One in-band value written once and held for 720 samples."),
)


def _broken(inlet: LawInlet) -> tuple[str, ...]:
    """Return the law names one assessment broke, sorted, from the inlet's own facts."""
    report = assess_plant(
        inlet.steps,
        inlet.transfers,
        register=inlet.register,
        bookings=inlet.bookings,
        work_orders=inlet.work_orders,
        tag_bookings=inlet.tag_bookings,
        writes=inlet.writes,
        allowed_stations=inlet.allowed_stations,
        controller=inlet.controller,
    )
    return tuple(sorted({item.name for item in report.broken}))


def _matrix(reading: StepSource) -> dict[str, tuple[str, ...]]:
    """Return the broken law names per class under one historian reading."""
    return {case.key: _broken(_case(case.key, reading)) for case in CASES}


def _metrics(broken: dict[str, tuple[str, ...]], suffix: str) -> dict[str, float]:
    """Return the three declared metrics for one reading.

    Args:
        broken: Broken law names per class.
        suffix: ``"row"`` or ``"change"``, appended to each metric name as declared.

    Returns:
        ``own_law_breaks_<suffix>``, ``off_diagonal_breaks_<suffix>`` and
        ``silent_class_breaks_<suffix>``.
    """
    named = [case for case in CASES if case.owns is not None]
    silent = [case for case in CASES if case.owns is None]
    own = sum(1 for case in named if case.owns in broken[case.key])
    off = sum(1 for case in named for name in broken[case.key] if name != case.owns)
    quiet = sum(len(broken[case.key]) for case in silent)
    return {
        f"own_law_breaks_{suffix}": float(own),
        f"off_diagonal_breaks_{suffix}": float(off),
        f"silent_class_breaks_{suffix}": float(quiet),
    }


def _digest(path: Path) -> str:
    """Return the sha256 of ``path``, or a note saying it could not be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:  # pragma: no cover - the file is in this repository
        return f"unreadable: {error}"


def _table(reading: str, broken: dict[str, tuple[str, ...]]) -> list[str]:
    """Render one matrix as markdown rows: a class per line, a marker per law."""
    header = "| class | owns | " + " | ".join(_SIX) + " | unintended |"
    rule = "| --- | --- | " + " | ".join("---" for _ in _SIX) + " | --- |"
    lines = [header, rule]
    for case in CASES:
        cells: list[str] = []
        unintended: list[str] = []
        for law in _SIX:
            fired = law in broken[case.key]
            cells.append("**break**" if fired else "·")
            if fired and law != case.owns:
                unintended.append(law)
        own = case.owns if case.owns is not None else "silence"
        unintended_cell = ", ".join(unintended) or "—"
        row = f"| `{case.key}` | `{own}` | " + " | ".join(cells) + f" | {unintended_cell} |"
        lines.append(row)
    lines.append("")
    lines.append(f'Reading: `step_source="{reading}"`.')
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Score both readings, print the metrics the bars name, and write the report."""
    parser = argparse.ArgumentParser(description="Per-law discrimination matrix for the six laws.")
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)

    broken_row = _matrix("row")
    broken_change = _matrix("change")
    metrics = {
        **_metrics(broken_row, "row"),
        **_metrics(broken_change, "change"),
    }

    print("result: atlas-law-discrimination-matrix")
    for name, value in metrics.items():
        print(f"{name}: {value:g}")
    print()

    report = [
        "# The per-law discrimination matrix",
        "",
        "Generated by `scripts/law_discrimination_matrix.py`. Synthetic constructions only: no",
        "corpus, no file, and no plant is read. Class S by construction.",
        "",
        "## What was measured",
        "",
        "`src/phos/atlas/declared_law.py` sha256 "
        f"`{_digest(ROOT / 'src/phos/atlas/declared_law.py')}`",
        "",
        f"`src/phos/atlas/law_inlet.py` sha256 `{_digest(ROOT / 'src/phos/atlas/law_inlet.py')}`",
        "",
        "Every case is scored with all six laws in the register. A `·` is silence; `**break**` is",
        "that law firing on that class. The `unintended` column names a law that fired on a class",
        "its statement does not name, which is the category error Q-0007 asks about.",
        "",
        "## The matrix under the default reading",
        "",
        *_table("row", broken_row),
        "",
        "## The matrix under the write reading",
        "",
        *_table("change", broken_change),
        "",
        "## The metrics the declaration names",
        "",
        "| metric | value |",
        "| --- | --- |",
        *[f"| `{name}` | {value:g} |" for name, value in metrics.items()],
        "",
        "## Classes that carry no historian",
        "",
        "`program_transfer`, `allowed_writer`, `booked_transfer`, `allowed_station_write`,",
        "`controller_valve` and `controller_agrees` supply no historian rows, so their two",
        "matrices are identical by construction. They are scored under both readings anyway so",
        "that every bar is computed over the same thirteen classes.",
        "",
    ]
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text("\n".join(report), encoding="utf-8")
    print(f"wrote {arguments.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
