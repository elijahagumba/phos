"""The plant map's settings, types and scores (ADR 0123).

The design is stated in `phos.atlas.plant_map`, which re-exports everything public here.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.signal_roles import SignalRole

__all__ = [
    "DEFAULT_SETTINGS",
    "RESULT_NAME",
    "Equation",
    "Form",
    "Link",
    "MapSettings",
    "PlantMap",
    "TargetModel",
    "distinct_samples",
    "equation_scores",
    "map_scores",
    "prediction",
    "residuals",
    "samples_for",
]

logger = logging.getLogger(__name__)

RESULT_NAME: Final = "atlas-plant-map-v1"
"""The challenger's result name (ADR 0123 §7). Never ``atlas-v1-consistency``."""

_Float = NDArray[numpy.float64]


@dataclass(frozen=True)
class MapSettings:
    """Every window and constant of the map, windows in seconds (ADR 0123 §2, §4, §6)."""

    lag_seconds: tuple[int, ...] = (5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)
    horizon_seconds: tuple[int, ...] = (60, 300, 900, 3600)
    form_horizon_seconds: int = 900
    fit_step_seconds: int = 5
    max_drivers: int = 6
    max_lags_per_driver: int = 2
    folds: int = 5
    min_gain: float = 0.01
    ridge: float = 1.0
    band_quantile: float = 0.9999
    free_run_quantile: float = 0.99
    free_run_step_seconds: int = 60
    free_run_max_seconds: int = 6 * 3600
    anchor_every_seconds: int = 600
    anchor_lookback_seconds: int = 6 * 3600
    #: Which naming rules name an instrument (`phos.atlas.plant_map_naming.NAMING_RULES`).
    naming_rules: str = "adr-0125"
    #: How the challenger's facts are weighted in the liar assembly: ADR 0114's isotonic step
    #: function, or a Platt logistic, strictly increasing in magnitude (ADR 0137).
    calibrator: str = "isotonic"


DEFAULT_SETTINGS: Final = MapSettings()


def samples_for(seconds: int, period_seconds: float) -> int:
    """ADR 0112's rule: a span of seconds is ``max(1, floor(seconds / period + 0.5))`` samples."""
    return max(1, math.floor(seconds / period_seconds + 0.5))


def distinct_samples(seconds: Sequence[int], period: float) -> tuple[int, ...]:
    """Each span of seconds in samples, distinct and ascending."""
    return tuple(sorted({samples_for(s, period) for s in seconds}))


class Form(str, Enum):
    """What a target's model predicts: its value, or its change over one sample."""

    LEVEL = "level"
    INCREMENT = "increment"


@dataclass(frozen=True)
class Equation:
    """Terms ``(driver, lag)``, coefficients (terms then intercept), and normal-error bands.

    A level form has one band; an increment form has one per horizon of the map.
    """

    terms: tuple[tuple[int, int], ...]
    coef: _Float
    bands: _Float


@dataclass(frozen=True)
class Link:
    """``driver`` predicts ``target`` at ``lags`` beyond what the target's other drivers do.

    ``drop_one`` is the target's model without this driver: its bands are the link's band.
    ``error_share`` is the share of the target's out-of-block error the driver removes.
    """

    driver: int
    target: int
    lags: tuple[int, ...]
    coefficients: tuple[float, ...]
    error_share: float
    drop_one: Equation


@dataclass(frozen=True)
class TargetModel:
    """One target's map: its form, its equation, its links, and its free-run band."""

    target: int
    form: Form
    equation: Equation
    links: tuple[Link, ...]
    free_run: _Float | None
    sse: float
    baseline_sse: float


@dataclass(frozen=True)
class PlantMap:
    """A fitted plant map. Arrays are indexed by signal column; windows are in samples."""

    names: tuple[str, ...]
    roles: tuple[SignalRole | None, ...]
    mean: _Float
    spread: _Float
    low: _Float
    high: _Float
    period_seconds: float
    lags: tuple[int, ...]
    horizons: tuple[int, ...]
    free_run_step: int
    anchor_lookback: int
    targets: Mapping[int, TargetModel]
    preliminary_descendants: Mapping[int, tuple[int, ...]]
    level_exclusions: Mapping[int, tuple[int, ...]]
    settings: MapSettings = field(default=DEFAULT_SETTINGS)

    def drivers_of(self, target: int) -> tuple[int, ...]:
        """The target's drivers, or nothing if it has no model."""
        model = self.targets.get(target)
        return () if model is None else tuple(link.driver for link in model.links)

    def children_of(self, signal: int) -> tuple[int, ...]:
        """Every target this signal drives, in column order."""
        return tuple(t for t in sorted(self.targets) if signal in self.drivers_of(t))

    def ancestors_of(self, signal: int) -> frozenset[int]:
        """Every signal with a path of links into this one."""
        seen: set[int] = set()
        stack = list(self.drivers_of(signal))
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(self.drivers_of(node))
        return frozenset(seen)

    def describe(self) -> tuple[str, ...]:
        """One line per link, ``driver -> target (form, lags in seconds)``, in target order."""
        lines = []
        for target in sorted(self.targets):
            model = self.targets[target]
            for link in model.links:
                lags = ", ".join(f"{round(lag * self.period_seconds)} s" for lag in link.lags)
                lines.append(
                    f"{self.names[link.driver]} -> {self.names[target]} "
                    f"({model.form.value}, {lags}, share {link.error_share:.3f})"
                )
        return tuple(lines)


# ---------------------------------------------------------------------------- scoring


def prediction(equation: Equation, z: _Float) -> tuple[_Float, int]:
    """The equation's prediction at every row (``NaN`` before its longest lag), and that row."""
    first = max((lag for _driver, lag in equation.terms), default=1)
    out = numpy.full(z.shape[0], numpy.nan)
    if z.shape[0] <= first:
        return out, first
    rows = numpy.arange(first, z.shape[0])
    total = numpy.full(rows.size, equation.coef[-1])
    for (driver, lag), beta in zip(equation.terms, equation.coef[:-1], strict=True):
        total += beta * z[rows - lag, driver]
    out[first:] = total
    return out, first


def residuals(
    form: Form, equation: Equation, z: _Float, target: int, horizons: tuple[int, ...]
) -> _Float:
    """Rows by bands: the level error, or each horizon's change error. ``NaN`` where undefined."""
    predicted, first = prediction(equation, z)
    n = z.shape[0]
    if form is Form.LEVEL:
        return (z[:, target] - predicted)[:, None]
    step = numpy.where(numpy.isnan(predicted), 0.0, predicted)
    implied = numpy.cumsum(step)
    out = numpy.full((n, len(horizons)), numpy.nan)
    for index, h in enumerate(horizons):
        start = first + h
        if start < n:
            actual = z[start:, target] - z[start - h : n - h, target]
            out[start:, index] = actual - (implied[start:] - implied[start - h : n - h])
    return out


def equation_scores(
    form: Form, equation: Equation, z: _Float, target: int, horizons: tuple[int, ...]
) -> _Float:
    """Each row's largest error over its band; ``NaN`` where no error is defined."""
    scaled = numpy.abs(residuals(form, equation, z, target, horizons)) / equation.bands
    out = numpy.full(z.shape[0], numpy.nan)
    defined = ~numpy.all(numpy.isnan(scaled), axis=1)
    out[defined] = numpy.nanmax(scaled[defined], axis=1)
    return out


def map_scores(model: PlantMap, values: _Float) -> NDArray[numpy.float32]:
    """Each mapped signal's score at every row, rows by signals; 0 where it has none."""
    z = (values - model.mean) / model.spread
    out = numpy.zeros(values.shape, dtype=numpy.float32)
    for target, target_model in model.targets.items():
        scores = equation_scores(
            target_model.form, target_model.equation, z, target, model.horizons
        )
        out[:, target] = numpy.nan_to_num(scores, nan=0.0)
    return out
