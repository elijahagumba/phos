"""Which link broke, which instrument lies, and what it should read (ADR 0123 §5, §6).

**A broken link.** Link *k* → *y* is broken at a row when *y*'s model is out of band there and
its model without *k* is back in band: every other driver still explains *y*; only *k* disagrees.

**A lying instrument.** The candidates are *y* and the driver of each broken link. A candidate is
named only if it disagrees with its drivers (out of band in its model, and no drop-one model is
**decisively** in band, ADR 0125), its drivers are in band in theirs, and at least half of its
**downstream** children (driven by it, and not also its ancestors) are out of band with its
reported value and back in band with its reconstruction. A controller downstream of a reading
follows the reading whether it is true or false, so it cannot testify. With no downstream child,
the first two checks decide, and the naming says no downstream check was possible.
Two passing candidates are not separable.

**Decisive or inconclusive (ADR 0125).** At the full model's deciding band (the one that puts it
furthest out of band; an increment form has one per horizon), a drop-one model is decisive when
its band there is narrower than the full model's residual: it could have seen what the full model
saw. An inconclusive one, too wide to tell or with no driver left, neither blocks nor supports,
and the check lists it by driver. A decisive one in band blocks naming only as a single liar can
(ADR 0126): it is the only one, and its driver is not itself in band. A candidate's driver is
judged without the candidate, so the candidate's lie cannot count against its own drivers.

**ADR 0135's rules** (``rules="adr-0135"``; ADR 0125's stay the default, so earlier records
reproduce). A downstream child testifies only when it is **decisive**: substituting the
reconstruction for the reading moves its residual by more than its band, so it could tell the two
apart. A child that cannot is inconclusive and is left out of both the downstream check and
"reading true, plant changed". And a candidate is named only when **everything upstream of it,
outside its own loop, is in band**: every ancestor that is not also a descendant, judged without
the candidate. A disturbance that started upstream cannot be blamed on the reading it reached.

**Reading true, plant changed.** When *y* is out of band but most of its downstream children
follow its reported value, the reading is probably true and the relation into it changed. That
verdict is recorded, never emitted as a lying instrument (§5.3).

**A reconstruction** is what the instrument's own drivers imply, never using its own reading
during the event. A level form is the model's prediction. An increment form is anchored at the
last row before the onset where the instrument was in band at every horizon (at most six hours
back), integrated from there, with the free-run band at the elapsed time. Beyond the calibrated
time the band is unknown. A band wider than 10% of the signal's normal range is too uncertain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy
from numpy.typing import NDArray

from phos.atlas.plant_map_model import (
    Equation,
    Form,
    PlantMap,
    equation_scores,
    prediction,
    residuals,
)

__all__ = [
    "NAMING_RULES",
    "InstrumentCheck",
    "Naming",
    "Reconstruction",
    "Verdict",
    "name_instrument",
    "reconstruct",
]

_Float = NDArray[numpy.float64]

#: A reconstruction band wider than this share of the signal's normal range is too uncertain.
UNCERTAIN_SHARE = 0.10
#: The naming rules: ADR 0125's (the default, as first measured) or ADR 0135's.
NAMING_RULES = ("adr-0125", "adr-0135")


class Verdict(str, Enum):
    """What the map can say about the instrument behind an event."""

    NAMED = "named"
    NOT_SEPARABLE = "not_separable"
    PLANT_CHANGED = "reading_true_plant_changed"
    UNNAMED = "unnamed"
    NO_MODEL = "no_model"


@dataclass(frozen=True)
class Reconstruction:
    """The value an instrument's drivers imply over ``rows``, in its own units."""

    column: int
    form: Form
    anchor: int | None
    rows: NDArray[numpy.int64]
    centre: _Float
    half_width: _Float
    too_uncertain: NDArray[numpy.bool_]
    degraded_by: tuple[int, ...]


@dataclass(frozen=True)
class InstrumentCheck:
    """The three checks for one candidate instrument at one row.

    ``inconclusive`` and ``decisively_in_band`` name the drivers whose drop-one models could not
    testify, and those that explained the candidate away (ADR 0125).
    """

    candidate: int
    disagrees_with_drivers: bool
    drivers_in_band: bool
    downstream: tuple[int, ...]
    downstream_out_with_reading: int
    downstream_agree_with_reconstruction: int
    inconclusive: tuple[int, ...] = ()
    decisively_in_band: tuple[int, ...] = ()
    upstream_in_band: bool = True

    @property
    def downstream_checked(self) -> bool:
        """Whether any downstream child could testify."""
        return bool(self.downstream)

    @property
    def passes(self) -> bool:
        """All three checks hold (the third vacuously with no downstream child)."""
        majority = 2 * self.downstream_agree_with_reconstruction >= len(self.downstream)
        upstream = self.upstream_in_band
        return self.disagrees_with_drivers and self.drivers_in_band and majority and upstream

    @property
    def follows_reading(self) -> bool:
        """Most downstream children agree with the reported value."""
        out = self.downstream_out_with_reading
        return bool(self.downstream) and 2 * out < len(self.downstream)


@dataclass(frozen=True)
class Naming:
    """What the map says about the event at ``(row, column)``."""

    row: int
    column: int
    verdict: Verdict
    instrument: int | None
    broken_links: tuple[int, ...]
    checks: tuple[InstrumentCheck, ...]
    reconstruction: Reconstruction | None


def _pad(model: PlantMap) -> int:
    return max(model.lags, default=1) + max(model.horizons, default=1) + 1


def _scores(
    model: PlantMap, z: _Float, target: int, equation: Equation, start: int, end: int
) -> _Float:
    """One equation's scores at rows ``start..end`` inclusive, computed on a padded window."""
    low = max(0, start - _pad(model))
    form = model.targets[target].form
    window = equation_scores(form, equation, z[low : end + 1], target, model.horizons)
    return window[start - low :]


def _at(model: PlantMap, z: _Float, target: int, equation: Equation, row: int) -> float:
    value = float(_scores(model, z, target, equation, row, row)[0])
    return value if numpy.isfinite(value) else 0.0


def _own(model: PlantMap, z: _Float, target: int, row: int) -> float:
    return _at(model, z, target, model.targets[target].equation, row)


def _residual_row(model: PlantMap, z: _Float, target: int, row: int) -> _Float:
    """The full model's residual in each of its bands at ``row`` (``NaN`` where undefined)."""
    low = max(0, row - _pad(model))
    target_model = model.targets[target]
    window = residuals(
        target_model.form, target_model.equation, z[low : row + 1], target, model.horizons
    )
    row_residuals: _Float = window[row - low]
    return row_residuals


def _drop_one_testimony(
    model: PlantMap, z: _Float, candidate: int, row: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Drivers whose drop-one model is inconclusive, and those decisively in band (ADR 0125)."""
    target = model.targets[candidate]
    residual = numpy.abs(_residual_row(model, z, candidate, row))
    scaled = residual / target.equation.bands
    if not numpy.any(numpy.isfinite(scaled)):
        return tuple(link.driver for link in target.links), ()
    deciding = int(numpy.nanargmax(scaled))
    inconclusive: list[int] = []
    in_band: list[int] = []
    for link in target.links:
        vacuous = not link.drop_one.terms
        if vacuous or not link.drop_one.bands[deciding] < residual[deciding]:
            inconclusive.append(link.driver)
        elif _at(model, z, candidate, link.drop_one, row) <= 1.0:
            in_band.append(link.driver)
    return tuple(inconclusive), tuple(in_band)


def _driver_in_band(model: PlantMap, z: _Float, driver: int, candidate: int, row: int) -> bool:
    """Whether a candidate's driver is in band, judged without the candidate (ADR 0126).

    A driver whose own model uses the candidate would carry the candidate's lie into its own
    score, so it is judged by its model without the candidate.
    """
    for link in model.targets[driver].links:
        if link.driver == candidate:
            return not link.drop_one.terms or _at(model, z, driver, link.drop_one, row) <= 1.0
    return _own(model, z, driver, row) <= 1.0


def reconstruct(
    model: PlantMap, values: _Float, column: int, onset: int, end: int
) -> Reconstruction | None:
    """Reconstruct one instrument from its drivers over ``onset..end`` inclusive.

    Returns ``None`` when the signal has no model, or an increment form finds no in-band anchor.
    """
    target = model.targets.get(column)
    if target is None:
        return None
    z = (values - model.mean) / model.spread
    rows = numpy.arange(onset, end + 1)
    equation = target.equation
    low = max(0, onset - _pad(model) - model.anchor_lookback)
    predicted, _first = prediction(equation, z[low : end + 1])
    anchor: int | None = None
    if target.form is Form.LEVEL:
        centre_z = predicted[rows - low]
        band_z = numpy.full(rows.size, equation.bands[0])
        start = onset
    else:
        lookback = max(low, onset - model.anchor_lookback)
        if onset <= lookback or target.free_run is None:
            return None
        before = _scores(model, z, column, equation, lookback, onset - 1)
        calm = numpy.flatnonzero(before <= 1.0)
        if calm.size == 0:
            return None
        anchor = lookback + int(calm[-1])
        steps = numpy.where(numpy.isnan(predicted), 0.0, predicted)
        implied = numpy.cumsum(steps[anchor - low + 1 : end - low + 1])
        centre_z = z[anchor, column] + implied[onset - anchor - 1 :]
        index = numpy.ceil((rows - anchor) / model.free_run_step).astype(numpy.int64) - 1
        known = index < target.free_run.size
        band_z = numpy.full(rows.size, numpy.nan)
        band_z[known] = target.free_run[index[known]]
        start = anchor
    centre = centre_z * model.spread[column] + model.mean[column]
    half = band_z * model.spread[column]
    normal = model.high[column] - model.low[column]
    degraded = tuple(
        driver
        for driver in model.drivers_of(column)
        if driver in model.targets
        and numpy.nanmax(
            _scores(model, z, driver, model.targets[driver].equation, start, end), initial=0.0
        )
        > 1.0
    )
    return Reconstruction(
        column=column,
        form=target.form,
        anchor=anchor,
        rows=rows,
        centre=centre,
        half_width=half,
        too_uncertain=~numpy.isfinite(half) | (half > UNCERTAIN_SHARE * normal),
        degraded_by=degraded,
    )


def _descendants(model: PlantMap, signal: int) -> frozenset[int]:
    seen: set[int] = set()
    stack = list(model.children_of(signal))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(model.children_of(node))
    return frozenset(seen)


def _decisive(model: PlantMap, read: _Float, substituted: _Float, child: int) -> bool:
    """Whether substituting the reconstruction moves the child's residual past its band."""
    target = model.targets[child]
    last = read.shape[0] - 1
    one = residuals(target.form, target.equation, read, child, model.horizons)[last]
    two = residuals(target.form, target.equation, substituted, child, model.horizons)[last]
    moved = numpy.abs(one - two) / target.equation.bands
    return bool(numpy.any(numpy.isfinite(moved))) and float(numpy.nanmax(moved)) > 1.0


def _check(
    model: PlantMap,
    values: _Float,
    z: _Float,
    candidate: int,
    row: int,
    onset: int,
    rules: str = "adr-0125",
) -> InstrumentCheck:
    target = model.targets.get(candidate)
    if target is None:
        return InstrumentCheck(candidate, False, False, (), 0, 0)
    inconclusive, decisively_in_band = _drop_one_testimony(model, z, candidate, row)
    explained_away = len(decisively_in_band) == 1 and not (
        decisively_in_band[0] in model.targets
        and _driver_in_band(model, z, decisively_in_band[0], candidate, row)
    )
    disagrees = _own(model, z, candidate, row) > 1.0 and not explained_away
    drivers_ok = all(
        _driver_in_band(model, z, driver, candidate, row)
        for driver in model.drivers_of(candidate)
        if driver in model.targets
    )
    ancestors = model.ancestors_of(candidate)
    downstream = tuple(
        child for child in model.children_of(candidate) if child not in ancestors | {candidate}
    )
    agree = 0
    rebuilt = reconstruct(model, values, candidate, onset, row) if downstream else None
    if rebuilt is not None:
        low = max(0, row - _pad(model))
        window = z[low : row + 1]
        substituted = window.copy()
        keep = numpy.isfinite(rebuilt.centre) & (rebuilt.rows >= low)
        substituted[rebuilt.rows[keep] - low, candidate] = (
            rebuilt.centre[keep] - model.mean[candidate]
        ) / model.spread[candidate]
        last = row - low
        if rules == "adr-0135":
            downstream = tuple(c for c in downstream if _decisive(model, window, substituted, c))
        agree = sum(
            _own(model, window, child, last) > 1.0 and _own(model, substituted, child, last) <= 1.0
            for child in downstream
        )
    elif rules == "adr-0135":
        downstream = ()
    out_with_reading = sum(_own(model, z, child, row) > 1.0 for child in downstream)
    upstream = True
    if rules == "adr-0135":
        outside_loop = ancestors - _descendants(model, candidate) - {candidate}
        upstream = all(
            _driver_in_band(model, z, a, candidate, row) for a in outside_loop if a in model.targets
        )
    return InstrumentCheck(
        candidate,
        disagrees,
        drivers_ok,
        downstream,
        out_with_reading,
        agree,
        inconclusive,
        decisively_in_band,
        upstream,
    )


def name_instrument(
    model: PlantMap,
    values: _Float,
    row: int,
    column: int,
    onset: int | None = None,
    rules: str = "adr-0125",
) -> Naming:
    """Name the broken links and, if the checks allow, the lying instrument at one event cell.

    Args:
        model: A fitted plant map.
        values: The scored file, rows by signals.
        row: The event's alert row.
        column: The event's alert column.
        onset: Where the event began (its first member's start); the alert row by default.
        rules: `NAMING_RULES`; ADR 0125's by default.

    Raises:
        ValueError: If ``rules`` is not one of `NAMING_RULES`.
    """
    if rules not in NAMING_RULES:
        raise ValueError(f"unknown naming rules {rules!r}")
    onset = row if onset is None else onset
    target = model.targets.get(column)
    if target is None:
        return Naming(row, column, Verdict.NO_MODEL, None, (), (), None)
    z = (values - model.mean) / model.spread
    broken: tuple[int, ...] = ()
    if _own(model, z, column, row) > 1.0:
        broken = tuple(
            link.driver for link in target.links if _at(model, z, column, link.drop_one, row) <= 1.0
        )
    candidates = tuple(dict.fromkeys((column, *broken)))
    checks = tuple(_check(model, values, z, c, row, onset, rules) for c in candidates)
    passing = [check.candidate for check in checks if check.passes]
    instrument: int | None = None
    if len(passing) == 1:
        verdict, instrument = Verdict.NAMED, passing[0]
    elif len(passing) > 1:
        verdict = Verdict.NOT_SEPARABLE
    elif _own(model, z, column, row) > 1.0 and checks[0].follows_reading:
        verdict = Verdict.PLANT_CHANGED
    else:
        verdict = Verdict.UNNAMED
    rebuilt = None if instrument is None else reconstruct(model, values, instrument, onset, row)
    return Naming(row, column, verdict, instrument, broken, checks, rebuilt)
