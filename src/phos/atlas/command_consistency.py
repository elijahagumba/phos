"""Give the engine the commands. Lane 1 of the stronger-engine programme (ADR 0273).

`phos.atlas.consistency` predicts each signal from the other **signals**. It never sees what the
control system commanded, so "the reading did not follow the order it was given" is a comparison
it cannot make. The command path reaches the explanation layer and stops there (ADR 0108).

The baseline on the ICSSim development corpus says what that costs
(`eval_runs/build/lane-e/baseline-icssim-dev.md`): 24 of 60 attacks caught, with `recon` and
`mimic_maintenance` at **0 of 10** each. Both are missed structurally. `recon` never moves the
plant, so no telemetry-only detector can see it. `mimic_maintenance` writes from the *operator*
station with the same tag and values as the genuine maintenance event in the same run.

Three components, kept apart and never pooled, because `command-ranking.md` and ADR 0034 require
a known station and an unknown master to be scored separately:

* **`unknown_writer`** — a write from a role that issued no write in training. PHOS's unknown
  master (ADR 0035). Learned from training, not a list of bad addresses.
* **`unknown_reader`** — a read from a role that issued no read in training. The reconnaissance
  case, invisible to telemetry by construction.
A third component, **`response_departure`**, was built and removed. It compared the plant's
response after a write with the response training saw after the same instruction, first as one
summary number and then as a trajectory. Neither separated `mimic_maintenance` from genuine
`maintenance`: over ten development runs the two score 0.270 and 0.254 at the median with fully
overlapping ranges, and the single score above the alerting threshold belongs to a *genuine*
maintenance action, so the component only ever cost a false alarm.

The reason is the corpus, not the comparison. Across 39 summary features of the plant's own
behaviour during the two events — mean, spread and range per signal — they differ by a median of
0.17 training spreads and a maximum of 1.29, and **not one feature exceeds two spreads**. The two
events are physically indistinguishable, so nothing recoverable from telemetry and commands can
tell them apart. `mimic_maintenance` is a provenance attack: what makes it an attack is that no
work order authorised it, which is the CMMS inlet of ADR 0069 and criterion A5, not this lane.
`eval_runs/build/lane-e/lane1-development.md` carries the numbers.

Each component is a column appended to the score matrix, calibrated so `THRESHOLD` means what it
means everywhere else, and then run through the unchanged `events` and `budget_alerts` so the
columns compete for the same shift budget rather than being added on top of it.

**The frozen detector is not edited.** This is a separate detector under a separate name
(`atlas-command-consistency`), measured beside `atlas-v1-consistency`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    THRESHOLD,
    ConsistencyModel,
    _all_episodes,
    feature_scores,
)
from phos.atlas.icssim_adapter import READ, Command

__all__ = [
    "COMPONENTS",
    "CommandModel",
    "augmented_scores",
    "component_series",
    "fit_commands",
]

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]

#: The columns, in the order `augmented_scores` appends them.
COMPONENTS: Final = ("unknown_writer", "unknown_reader")

#: A write from a station that never wrote in training is worth this many units. A write is a
#: single deliberate act, so unlike a poll it does not accumulate into evidence by repetition.
_UNKNOWN_WRITE_UNITS: Final = 4.0


@dataclass(frozen=True)
class CommandModel:
    """What training says is ordinary on the command path.

    Attributes:
        base: The per-signal model, unchanged and never edited.
        writers: Roles that issued at least one write in training.
        readers: Roles that issued at least one read in training.
        divisors: One calibration divisor per component, in `COMPONENTS` order.
    """

    base: ConsistencyModel
    writers: frozenset[str]
    readers: frozenset[str]
    divisors: tuple[float, float] = (1.0, 1.0)


def _at(times: _Float64, when: float) -> int:
    """The first sample at or after ``when``, clamped to the last row."""
    index = int(numpy.searchsorted(times, when, side="left"))
    return min(index, times.size - 1)


def fit_commands(
    model: ConsistencyModel,
    training: tuple[tuple[_Float64, _Float64, tuple[Command, ...]], ...],
) -> CommandModel:
    """Learn the ordinary command path from attack-free runs.

    Args:
        model: The fitted per-signal model.
        training: One entry per attack-free run: its telemetry, its sample times, and every
            message in it, reads included.

    Returns:
        The command model, with its three divisors calibrated on the same runs.
    """
    writers: set[str] = set()
    readers: set[str] = set()
    for _values, _times, commands in training:
        for command in commands:
            if command.function == READ:
                readers.add(command.role)
            else:
                writers.add(command.role)

    partial = CommandModel(base=model, writers=frozenset(writers), readers=frozenset(readers))

    peaks: list[list[float]] = [[], []]
    for values, times, commands in training:
        series = component_series(partial, values, times, commands)
        for index in range(2):
            column = series[:, index].reshape(-1, 1)
            for _s, _e, peak, *_rest in _all_episodes(column, THRESHOLD, model.windows.feature_gap):
                peaks[index].append(peak)
    divisors = tuple(
        max(1.0, float(sorted(found)[-CALIBRATION_RANK])) if len(found) >= CALIBRATION_RANK else 1.0
        for found in peaks
    )
    return CommandModel(
        base=model,
        writers=partial.writers,
        readers=partial.readers,
        divisors=(divisors[0], divisors[1]),
    )


def component_series(
    model: CommandModel, values: _Float64, times: _Float64, commands: tuple[Command, ...]
) -> _Float32:
    """Return the uncalibrated component scores, rows by `COMPONENTS`.

    A component is zero except at the samples a message lands on, where it takes its magnitude.
    The frozen model's own per-signal scores supply the plant's response.

    Args:
        model: The command model.
        values: Telemetry, rows by signals.
        times: Sample times, one per row.
        commands: Every message in the scored run, reads included.

    Returns:
        Rows by two columns, in `COMPONENTS` order.
    """
    out = numpy.zeros((times.size, 2), dtype=numpy.float32)

    for command in commands:
        row = _at(times, command.at)
        if command.function == READ:
            if command.role not in model.readers:
                # Count, do not flag. One unfamiliar poll is weak evidence and a scan of
                # thousands is overwhelming; a flat score would rank both below every signal
                # event and lose the shift budget to them.
                out[row, 1] += numpy.float32(THRESHOLD)
            continue
        if command.role not in model.writers:
            out[row, 0] += numpy.float32(THRESHOLD * _UNKNOWN_WRITE_UNITS)
    return out


def augmented_scores(
    model: CommandModel, values: _Float64, times: _Float64, commands: tuple[Command, ...]
) -> _Float32:
    """Return the per-signal scores with the calibrated command columns appended.

    The result has two more columns than ``values``, in `COMPONENTS` order, and goes through
    the unchanged `phos.atlas.consistency.events` and `budget_alerts`.
    """
    series = component_series(model, values, times, commands)
    for index in range(2):
        series[:, index] = series[:, index] / numpy.float32(model.divisors[index])
    plain = feature_scores(model.base, values)
    return numpy.concatenate([plain, series], axis=1).astype(numpy.float32)
