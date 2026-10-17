"""PHOS's ICSSim runs as matrices the plant map and the frozen detector read (ADR 0122, ADR 0128).

One run directory (``data/phos-icssim-dev/<scenario>-<seed>/``) holds what the control system
reported (``process.csv``), the plant's true state on the same grid (``truth.csv``, for judging
only, ADR 0017), and the declared events (``events.json``). This module reads them into arrays,
in the column order ``process.csv`` gives, and refuses the held-out corpus: it may not be opened
until a declaration names the configuration and the command (ADR 0122 §4).

The roles and loops are ``data/phos-icssim-dev/roles.toml``, read from ICSSim's own source. This
module holds no detection logic and produces no evaluation number.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.interventions import Intervention
from phos.atlas.network_links import Exchange

__all__ = [
    "HELD_OUT_DIRECTORY",
    "ROLES_FILE",
    "IcssimEvent",
    "IcssimRun",
    "load_exchanges",
    "load_interventions",
    "load_run",
]

#: The held-out corpus's directory name. Nothing here opens it.
HELD_OUT_DIRECTORY: Final = "phos-icssim-heldout"
#: The roles and loops, beside the development runs.
ROLES_FILE: Final = "roles.toml"


@dataclass(frozen=True)
class IcssimEvent:
    """One declared event, in seconds from the run's start."""

    kind: str
    start: float
    end: float
    label: str

    @property
    def is_attack(self) -> bool:
        """Whether the event is declared an attack."""
        return self.label == "attack"


@dataclass(frozen=True)
class IcssimRun:
    """One run: names, Unix seconds, reported values, true values and its events."""

    name: str
    scenario: str
    seed: int
    names: tuple[str, ...]
    time: NDArray[numpy.float64]
    values: NDArray[numpy.float64]
    truth: NDArray[numpy.float64]
    events: tuple[IcssimEvent, ...]
    epoch: float

    def rows(self, event: IcssimEvent) -> tuple[int, int]:
        """The first and last rows inside an event's window."""
        start = int(numpy.searchsorted(self.time, self.epoch + event.start))
        end = int(numpy.searchsorted(self.time, self.epoch + event.end, side="right")) - 1
        return start, max(start, min(end, self.time.size - 1))


def _read(path: Path) -> tuple[tuple[str, ...], NDArray[numpy.float64]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [[float(cell) for cell in row] for row in reader]
    return tuple(header), numpy.asarray(rows, dtype=numpy.float64)


def load_run(directory: Path) -> IcssimRun:
    """Read one development run.

    Raises:
        ValueError: If the run is in the held-out corpus, or ``process.csv`` and ``truth.csv``
            disagree about their columns or rows.
        FileNotFoundError: If a file is missing.
    """
    if HELD_OUT_DIRECTORY in directory.resolve().parts:
        raise ValueError(f"{directory} is held out (ADR 0122 §4); a declaration must name it first")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    header, process = _read(directory / "process.csv")
    truth_header, truth = _read(directory / "truth.csv")
    if truth_header != header or truth.shape != process.shape:
        raise ValueError(f"{directory}: process.csv and truth.csv disagree")
    if header[0] != "timestamp":
        raise ValueError(f"{directory}: the first column must be the timestamp")
    events = tuple(
        IcssimEvent(str(e["kind"]), float(e["start"]), float(e["end"]), str(e["label"]))
        for e in json.loads((directory / "events.json").read_text(encoding="utf-8"))
    )
    return IcssimRun(
        name=directory.name,
        scenario=str(manifest["scenario"]),
        seed=int(manifest["seed"]),
        names=header[1:],
        time=process[:, 0].copy(),
        values=process[:, 1:].copy(),
        truth=truth[:, 1:].copy(),
        events=events,
        epoch=float(manifest["epoch"]),
    )


def load_exchanges(directory: Path) -> tuple[Exchange, ...]:
    """One run's network traffic (``modbus.csv``) as exchanges, client by its declared role.

    The harness names each client by the device it is (``plc1``, ``operator``, ``attacker``) and
    each server by its PLC, so a PLC reading another PLC appears as client ``plc1``, server
    ``plc2``, the same device name it serves under (ADR 0122).

    Raises:
        ValueError: If the run is in the held-out corpus.
    """
    if HELD_OUT_DIRECTORY in directory.resolve().parts:
        raise ValueError(f"{directory} is held out (ADR 0122 §4); a declaration must name it first")
    with (directory / "modbus.csv").open(newline="", encoding="utf-8") as handle:
        return tuple(
            Exchange(row["role"], row["plc"], row["function"], row["tag"])
            for row in csv.DictReader(handle)
        )


def load_interventions(directory: Path, run: IcssimRun, file: int) -> tuple[Intervention, ...]:
    """Every logged write in one run that changed its point's value, as a row of ``run``.

    A write of the value a point already holds changes nothing and is not an intervention. The
    point's value before the first write is taken from the first row of ``process.csv``.

    Raises:
        ValueError: If the run is in the held-out corpus.
    """
    if HELD_OUT_DIRECTORY in directory.resolve().parts:
        raise ValueError(f"{directory} is held out (ADR 0122 §4); a declaration must name it first")
    last = {name: float(run.values[0, j]) for j, name in enumerate(run.names)}
    found: list[Intervention] = []
    with (directory / "modbus.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["function"] != "write" or row["tag"] not in last:
                continue
            value = float(row["value"])
            if value == last[row["tag"]]:
                continue
            last[row["tag"]] = value
            index = int(numpy.searchsorted(run.time, float(row["timestamp"])))
            found.append(Intervention(file, min(index, run.time.size - 1), row["tag"]))
    return tuple(found)
