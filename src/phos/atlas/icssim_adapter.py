"""Read a PHOS ICSSim run into Atlas's telemetry and command inlets (ADR 0122, ADR 0273).

Each generated run writes two files for the same plant over the same minutes:

* ``process.csv`` — ``timestamp`` then one column per signal, the plant as the controllers
  recorded it. This is the telemetry inlet, the matrix `phos.atlas.consistency` already takes.
* ``modbus.csv`` — ``timestamp, client, role, plc, function, tag, value``: every Modbus message,
  with the station that sent it. This is the command inlet, and nothing Atlas has scored before
  has carried it alongside the physics.

The ``role`` column is the reason the corpus is worth generating. A message is attributed to
``operator``, ``plc1``, ``plc2`` or ``attacker``, so "a write arrived, and it came from somewhere
that does not normally write" is recoverable — which no public corpus supports.

**Commands are sparse, and a caller that assumes otherwise will be wrong.** In development run
``normal-96001`` there are 9 writes among 423,561 messages, all from the operator, touching two
tags: ``tank_level_max`` and ``tank_output_valve_mode``. Reads are the overwhelming majority and
are the controllers polling. So `commanded` returns a step function that changes a handful of
times over hours, and most signals are never commanded at all — those columns stay ``NaN`` rather
than being filled with a guess.

Nothing here scores, thresholds or detects. It reads files into arrays.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy
from numpy.typing import NDArray

__all__ = [
    "READ",
    "Command",
    "IcssimRun",
    "commanded",
    "read_run",
    "read_traffic",
]

_Float64 = NDArray[numpy.float64]

#: The ``function`` value that is a poll rather than a command.
READ: Final = "read"


@dataclass(frozen=True)
class Command:
    """One Modbus message that wrote a value.

    Attributes:
        at: Unix seconds, as the file records them.
        role: The station that sent it — ``operator``, ``plc1``, ``plc2`` or ``attacker``.
        function: ``read`` for a poll, otherwise a write.
        tag: The signal touched. May name a column of ``process.csv``, or may not.
        value: The value written, or the value read back.
    """

    at: float
    role: str
    function: str
    tag: str
    value: float


@dataclass(frozen=True)
class IcssimRun:
    """One run's telemetry, with the signal names and the sample times.

    Attributes:
        values: Rows by signals, in ``keys`` order, ready for `phos.atlas.consistency.fit`.
        keys: Signal names, the ``process.csv`` header without ``timestamp``.
        times: Unix seconds, one per row.
    """

    values: _Float64
    keys: tuple[str, ...]
    times: _Float64


def _parse_number(path: Path, line: int, column: str, cell: str) -> float:
    """Return one cell as a finite float, or refuse explaining exactly which cell is wrong.

    Three things are refused here that ``float()`` accepts or reports badly:

    * A cell that is not a number at all. ``float()`` says "could not convert string to float",
      which names neither the file nor the line nor the column, so a plant engineer holding a
      corrupted export cannot find the bad cell.
    * ``nan``, which ``float()`` accepts. A NaN that reaches a consistency detector poisons every
      comparison after it, because ``nan > x`` is false for every x, so the detector goes quiet
      rather than wrong. Silence that looks like a clean plant is the worst outcome this package
      can produce, so a NaN in telemetry is refused rather than carried.
    * ``inf``, for the same reason: one infinite value makes every band comparison meaningless.

    An empty cell is left to the caller, because a never-commanded command column is legitimately
    empty and the docstring says so. This function is for telemetry, where every cell is required.

    Args:
        path: The file, for the message.
        line: The 1-based line number, counting the header as line 1.
        column: The column's name, from the header.
        cell: The raw text.

    Returns:
        The value.

    Raises:
        ValueError: If the cell is empty, not a number, or not finite.
    """
    text = cell.strip()
    if not text:
        raise ValueError(f"{path} line {line}, column {column!r}: the cell is empty")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(
            f"{path} line {line}, column {column!r}: {text!r} is not a number"
        ) from None
    if not numpy.isfinite(value):
        raise ValueError(
            f"{path} line {line}, column {column!r}: {text!r} is not a finite number. A NaN or an "
            "infinity in telemetry makes every comparison after it meaningless without saying so"
        )
    return value


def read_run(directory: Path) -> IcssimRun:
    """Read ``process.csv`` from a run directory into the telemetry inlet.

    Args:
        directory: A run directory, for example ``data/phos-icssim-dev/normal-96001``.

    Returns:
        The run's telemetry.

    Raises:
        FileNotFoundError: If the directory holds no ``process.csv``.
        ValueError: If the file has no data rows, or a row's width does not match the header.
    """
    path = directory / "process.csv"
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path} is empty")
        keys = tuple(header[1:])
        times: list[float] = []
        rows: list[list[float]] = []
        for line, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(f"{path} line {line} has {len(row)} fields, not {len(header)}")
            times.append(_parse_number(path, line, header[0], row[0]))
            rows.append(
                [
                    _parse_number(path, line, keys[index], cell)
                    for index, cell in enumerate(row[1:])
                ]
            )
    if not rows:
        raise ValueError(f"{path} has a header and no rows")
    # Strictly increasing. A repeated timestamp makes two measurements look simultaneous and a
    # backwards one makes any window, rate or duration computed from the series silently wrong.
    # Neither is a corruption the generator can produce, so either means the file is not what it
    # claims and should be refused rather than analysed.
    for index in range(1, len(times)):
        if times[index] <= times[index - 1]:
            where = "repeats" if times[index] == times[index - 1] else "goes backwards"
            raise ValueError(
                f"{path} line {index + 2}: the timestamp {where} ({times[index - 1]!r} then "
                f"{times[index]!r}). A series that is not strictly increasing makes every window "
                "and duration computed from it wrong"
            )
    return IcssimRun(
        values=numpy.asarray(rows, dtype=numpy.float64),
        keys=keys,
        times=numpy.asarray(times, dtype=numpy.float64),
    )


def read_traffic(directory: Path, *, writes_only: bool = True) -> tuple[Command, ...]:
    """Read ``modbus.csv`` from a run directory into the command inlet.

    Args:
        directory: A run directory.
        writes_only: Keep only messages whose ``function`` is not ``read``. The polls are the
            overwhelming majority and carry no command, so the default drops them.

    Returns:
        The messages, in file order.

    Raises:
        FileNotFoundError: If the directory holds no ``modbus.csv``.
    """
    path = directory / "modbus.csv"
    found: list[Command] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if writes_only and row["function"] == READ:
                continue
            found.append(
                Command(
                    at=float(row["timestamp"]),
                    role=row["role"],
                    function=row["function"],
                    tag=row["tag"],
                    value=float(row["value"]),
                )
            )
    return tuple(found)


def commanded(commands: tuple[Command, ...], keys: tuple[str, ...], times: _Float64) -> _Float64:
    """Return the last value commanded for each signal at each sample time.

    A command takes effect from the first sample at or after it was sent and holds until the next
    command to that tag. A signal with no command before a given row is ``NaN`` there, and a
    signal never commanded at all is ``NaN`` throughout — the absence is reported, never filled
    with a zero or a reading, because a caller comparing a reading against its command must be
    able to tell "commanded to zero" from "never commanded".

    Args:
        commands: Messages from `read_traffic`. Messages whose tag is not in ``keys`` are ignored.
        keys: Signal names, in the telemetry's column order.
        times: Sample times, ascending, one per telemetry row.

    Returns:
        Rows by signals, aligned to ``times`` and ``keys``.
    """
    out = numpy.full((times.size, len(keys)), numpy.nan, dtype=numpy.float64)
    column = {key: index for index, key in enumerate(keys)}
    for command in sorted(commands, key=lambda item: item.at):
        index = column.get(command.tag)
        if index is None:
            continue
        start = int(numpy.searchsorted(times, command.at, side="left"))
        if start >= times.size:
            continue
        out[start:, index] = command.value
    return out
