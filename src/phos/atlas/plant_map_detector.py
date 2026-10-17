"""The plant-map challenger, `atlas-plant-map-v1`: the frozen detector with the map's score added.

ADR 0123 §7. **It extends, it does not replace.** `phos.atlas.consistency` is untouched. The
challenger fits it exactly as the champion does, fits `phos.atlas.plant_map` beside it, and takes
each signal's element-wise maximum of three calibrated scores: the frozen range score, the frozen
loop score and the map score. The map score passes through the same hourly detrend; the
per-signal divisor is the frozen rule (the third-largest training episode peak, at least 1)
applied to that maximum, as the champion applies it to its two. Events, onsets and the
8-per-shift budget are the frozen ones.

**An event is map-carried** when, at its alert cell, the calibrated map score is above
`THRESHOLD` and at least the loop and range scores there. Only then may the map name a link, an
instrument and a reconstruction (`phos.atlas.plant_map_evidence`).

**The replace arm** (map and range only, ADR 0123 §7) is diagnosis, never a candidate: it asks
whether the map alone can detect.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    THRESHOLD,
    ConsistencyEvent,
    ConsistencyModel,
    TrainFile,
    _all_episodes,
    _detrend,
    budget_alerts,
    events,
    feature_components,
    fit,
)
from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, MapSettings, PlantMap, map_scores
from phos.atlas.signal_roles import SignalRoles

__all__ = [
    "RESULT_NAME",
    "Arm",
    "Components",
    "PlantMapDetector",
    "detect_alerts",
    "detector_components",
    "detector_events",
    "fit_detector",
    "map_carried",
]

RESULT_NAME: Final = "atlas-plant-map-v1"

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]


class Arm(str, Enum):
    """Which scores the challenger's maximum takes."""

    EXTEND = "extend"
    REPLACE = "replace"


@dataclass(frozen=True)
class Components:
    """The three calibrated scores, rows by signals; the loop is zero in the replace arm."""

    loop: _Float32
    rng: _Float32
    map: _Float32

    def combined(self) -> _Float32:
        """The element-wise maximum, the challenger's score."""
        out: _Float32 = numpy.maximum(numpy.maximum(self.loop, self.rng), self.map)
        return out


@dataclass(frozen=True)
class PlantMapDetector:
    """A fitted challenger.

    ``consistency`` is the frozen fit with the challenger's divisor in place of its own, so its
    loop score and `phos.atlas.consistency.loop_expectation` band are on the challenger's scale.
    """

    consistency: ConsistencyModel
    plant: PlantMap
    arm: Arm


def _raw(
    model: ConsistencyModel, plant: PlantMap, values: _Float64, arm: Arm
) -> tuple[_Float32, _Float32, _Float32]:
    """Detrended, undivided loop, range and map scores."""
    loop, rng = feature_components(model, values)
    loop = loop * model.divisor.astype(numpy.float32)
    rng = rng * model.divisor.astype(numpy.float32)
    if arm is Arm.REPLACE:
        loop = numpy.zeros_like(loop)
    mapped = _detrend(map_scores(plant, values), model.windows)
    return loop, rng, mapped


def fit_detector(
    train: Sequence[TrainFile],
    names: Sequence[str],
    roles: SignalRoles,
    period_seconds: float,
    windows: Windows = FROZEN_WINDOWS,
    settings: MapSettings = DEFAULT_SETTINGS,
    arm: Arm = Arm.EXTEND,
) -> PlantMapDetector:
    """Fit the frozen detector and the map on the same training files, then the joint divisor.

    Args:
        train: Training files sharing one signal order; attack rows are left out of every fit.
        names: One name per column.
        roles: Every column's declared role and the corpus's declared loops.
        period_seconds: Seconds between samples.
        windows: The frozen detector's windows for this period (ADR 0112).
        settings: The map's settings, ADR 0123's by default.
        arm: Extend (the challenger) or replace (diagnosis only).
    """
    frozen = fit(train, windows)
    plant = fit_map(train, names, roles, period_seconds, settings)
    n_signals = train[0].values.shape[1]
    peaks: list[list[float]] = [[] for _ in range(n_signals)]
    for f in train:
        loop, rng, mapped = _raw(frozen, plant, f.values, arm)
        raw = numpy.maximum(numpy.maximum(loop, rng), mapped)
        raw[f.attack] = 0.0
        for _s, _e, peak, _at, j in _all_episodes(raw, THRESHOLD, windows.feature_gap):
            peaks[j].append(peak)
    divisor = numpy.ones(n_signals)
    for j in range(n_signals):
        if len(peaks[j]) >= CALIBRATION_RANK:
            divisor[j] = max(1.0, sorted(peaks[j])[-CALIBRATION_RANK])
    return PlantMapDetector(replace(frozen, divisor=divisor), plant, arm)


def detector_components(detector: PlantMapDetector, values: _Float64) -> Components:
    """The three calibrated scores of one scored file."""
    loop, rng, mapped = _raw(detector.consistency, detector.plant, values, detector.arm)
    divisor = detector.consistency.divisor.astype(numpy.float32)
    return Components(loop / divisor, rng / divisor, mapped / divisor)


def detector_events(detector: PlantMapDetector, values: _Float64) -> list[ConsistencyEvent]:
    """The frozen events over the challenger's score."""
    scores = detector_components(detector, values).combined()
    return events(scores, windows=detector.consistency.windows)


def map_carried(components: Components, event: ConsistencyEvent) -> bool:
    """Whether the map carries the event at its alert cell."""
    row, column = event.onset, event.column
    score = float(components.map[row, column])
    return (
        score > THRESHOLD
        and score >= float(components.loop[row, column])
        and score >= float(components.rng[row, column])
    )


def detect_alerts(
    detector: PlantMapDetector, values: _Float64, time: _Float64
) -> tuple[list[int], list[int], list[float]]:
    """The challenger's budgeted alerts for one file, as `phos.atlas.consistency.budget_alerts`."""
    found = detector_events(detector, values)
    return budget_alerts(found, time, detector.consistency.windows)
