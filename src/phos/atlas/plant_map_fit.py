"""Fitting the plant map: two passes of selection, out-of-block bands, links (ADR 0123 §2-§4).

The design is stated in `phos.atlas.plant_map`; this module is its arithmetic.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import TrainFile
from phos.atlas.plant_map_model import (
    DEFAULT_SETTINGS,
    LOOP_BARS,
    Equation,
    Form,
    Link,
    MapSettings,
    PlantMap,
    TargetModel,
    distinct_samples,
    prediction,
    residuals,
    samples_for,
)
from phos.atlas.plant_map_select import (
    Layout,
    accumulate,
    cv_sse,
    fold_coefficients,
    select_terms,
)
from phos.atlas.signal_roles import SignalRole, SignalRoles

__all__ = ["fit_map"]

logger = logging.getLogger(__name__)

_Float = NDArray[numpy.float64]

# ---------------------------------------------------------------------------- fitting


@dataclass(frozen=True)
class _Segment:
    """Contiguous rows ``[start, end)`` of one training file that share a fold."""

    file: int
    fold: int
    start: int
    end: int


def _segments(
    lengths: Sequence[int], folds: int
) -> tuple[list[_Segment], list[NDArray[numpy.int64]]]:
    total = sum(lengths)
    segments: list[_Segment] = []
    fold_of_rows: list[NDArray[numpy.int64]] = []
    offset = 0
    for index, length in enumerate(lengths):
        fold = (numpy.arange(offset, offset + length) * folds) // max(total, 1)
        fold_of_rows.append(fold)
        edges = numpy.flatnonzero(numpy.diff(fold)) + 1
        for start, end in zip(
            numpy.concatenate(([0], edges)), numpy.concatenate((edges, [length])), strict=True
        ):
            segments.append(_Segment(index, int(fold[start]), int(start), int(end)))
        offset += length
    return segments, fold_of_rows


@dataclass
class _Context:
    z: list[_Float]
    attack: list[NDArray[numpy.bool_]]
    segments: list[_Segment]
    grams: _Float
    layout: Layout
    horizons: tuple[int, ...]
    settings: MapSettings

    def coefficients(self, terms: Sequence[int], y: int) -> list[_Float]:
        """One coefficient vector per fold (fitted without it), then the full fit last."""
        total = self.grams.sum(axis=0)
        ridge, ones = self.settings.ridge, self.layout.ones
        per_fold = [fold_coefficients(total - g, terms, y, ones, ridge) for g in self.grams]
        return [*per_fold, fold_coefficients(total, terms, y, ones, ridge)]

    def pairs(self, terms: Sequence[int]) -> tuple[tuple[int, int], ...]:
        return tuple((int(self.layout.drivers[t]), int(self.layout.lags[t])) for t in terms)

    def out_of_block(
        self,
        form: Form,
        terms: Sequence[int],
        target: int,
        coefs: list[_Float],
        horizons: tuple[int, ...] | None = None,
    ) -> list[_Float]:
        """Each segment's residuals from the model fitted without its fold, rows by bands."""
        horizons = self.horizons if horizons is None else horizons
        pairs = self.pairs(terms)
        width = 1 if form is Form.LEVEL else len(horizons)
        pad = int(self.layout.lags.max(initial=1)) + max(horizons)
        out = []
        for segment in self.segments:
            low = max(0, segment.start - pad)
            z = self.z[segment.file][low : segment.end]
            eq = Equation(pairs, coefs[segment.fold], numpy.ones(width))
            res = residuals(form, eq, z, target, horizons)[segment.start - low :]
            if form is Form.INCREMENT:
                rows = numpy.arange(segment.start, segment.end)[:, None]
                res = numpy.where(
                    rows - numpy.asarray(horizons)[None, :] >= segment.start, res, numpy.nan
                )
            res[self.attack[segment.file][segment.start : segment.end]] = numpy.nan
            out.append(res)
        return out

    def bands(self, residuals: list[_Float], quantile: float) -> _Float:
        stacked = numpy.vstack(residuals)
        bands = numpy.empty(stacked.shape[1])
        for index in range(stacked.shape[1]):
            column = numpy.abs(stacked[:, index])
            column = column[~numpy.isnan(column)]
            bands[index] = numpy.quantile(column, quantile) if column.size else numpy.inf
        return numpy.maximum(bands, 1e-6)


def _free_run(
    context: _Context, terms: Sequence[int], target: int, coefs: list[_Float], period: float
) -> _Float:
    """Free-run band: reconstruction error by elapsed time, from anchors every few minutes."""
    settings = context.settings
    step = samples_for(settings.free_run_step_seconds, period)
    every = samples_for(settings.anchor_every_seconds, period)
    elapsed = numpy.arange(step, samples_for(settings.free_run_max_seconds, period) + 1, step)
    errors: list[list[float]] = [[] for _ in elapsed]
    pairs = context.pairs(terms)
    pad = int(context.layout.lags.max(initial=1))
    for segment in context.segments:
        low = max(0, segment.start - pad)
        z = context.z[segment.file][low : segment.end]
        eq = Equation(pairs, coefs[segment.fold], numpy.ones(1))
        predicted, first = prediction(eq, z)
        implied = numpy.cumsum(numpy.where(numpy.isnan(predicted), 0.0, predicted))
        anchors = numpy.arange(max(segment.start - low, first), segment.end - low, every)
        for index, d in enumerate(elapsed):
            a = anchors[anchors + d < segment.end - low]
            if a.size:
                err = (z[a + d, target] - z[a, target]) - (implied[a + d] - implied[a])
                errors[index].extend(numpy.abs(err).tolist())
    return numpy.asarray(
        [numpy.quantile(e, settings.free_run_quantile) if e else numpy.nan for e in errors]
    )


def _admissible(
    layout: Layout, roles: Sequence[SignalRole | None], target: int
) -> NDArray[numpy.bool_]:
    allowed: NDArray[numpy.bool_] = layout.drivers != target
    if roles[target] is SignalRole.SENSOR:
        setpoints = [i for i, role in enumerate(roles) if role is SignalRole.SETPOINT]
        allowed &= ~numpy.isin(layout.drivers, setpoints)
    return allowed


def _reachable(graph: Mapping[int, set[int]], start: int) -> tuple[int, ...]:
    """Every node a path of edges ``driver -> target`` reaches from ``start``, excluding it."""
    children: dict[int, set[int]] = {}
    for target, drivers in graph.items():
        for driver in drivers:
            children.setdefault(driver, set()).add(target)
    seen: set[int] = set()
    stack = list(children.get(start, ()))
    while stack:
        node = stack.pop()
        if node not in seen and node != start:
            seen.add(node)
            stack.extend(children.get(node, ()))
    return tuple(sorted(seen))


def _level_exclusions(
    roles: SignalRoles,
    names: Sequence[str],
    graph: Mapping[int, set[int]],
    modelled: Sequence[int],
    descendants: Mapping[int, tuple[int, ...]],
    loop_bar: str = "reach",
) -> dict[int, tuple[int, ...]]:
    """The signals barred from each target's level form (ADR 0123 §3, narrowed by ADR 0126).

    A corpus that declares no loop keeps ADR 0123's rule: every preliminary descendant. One that
    does bars a loop's outputs, and everything they reach, from the level form of the reading the
    loop holds; where the loop names no reading, from every signal with a path into its outputs.
    A loop that names a reading but no output leaves that reading under ADR 0123's rule.
    With ``loop_bar="outputs"`` (ADR 0170) a loop bars its declared outputs only.

    Raises:
        ValueError: If ``loop_bar`` is not one of `LOOP_BARS`.
    """
    if loop_bar not in LOOP_BARS:
        raise ValueError(f"unknown loop bar {loop_bar!r}")
    if not roles.loops:
        return {y: descendants[y] for y in modelled}
    index = {name: column for column, name in enumerate(names)}
    barred: dict[int, set[int]] = {y: set() for y in modelled}
    for loop in roles.loops:
        outputs = [index[output] for output in loop.outputs]
        reach = set(outputs)
        if loop_bar == "reach":
            reach |= {x for o in outputs for x in _reachable(graph, o)}
        if loop.reading is None:
            holders = [y for y in modelled if any(o in descendants[y] for o in outputs)]
        else:
            holders = [index[loop.reading]] if index[loop.reading] in barred else []
        for y in holders:
            barred[y] |= reach if outputs else set(descendants[y])
    return {y: tuple(sorted(barred[y] - {y})) for y in modelled}


def fit_map(
    train: Sequence[TrainFile],
    names: Sequence[str],
    roles: SignalRoles,
    period_seconds: float,
    settings: MapSettings = DEFAULT_SETTINGS,
    allowed: Mapping[str, frozenset[str]] | None = None,
) -> PlantMap:
    """Learn the plant map from attack-free training rows.

    Args:
        train: Training files sharing one signal order; attack rows are left out.
        names: One name per column.
        roles: Every column's declared role (`phos.atlas.signal_roles`).
        period_seconds: Seconds between samples; every window converts by ADR 0112's rule.
        settings: ADR 0123's windows and constants by default.
        allowed: Per target name, the only drivers it may use (ADR 0133's graded map). A target
            absent from it gets no model. ``None``, the default, restricts nothing.

    Raises:
        ValueError: If there is no training file, or the role map declares other signals.
    """
    if not train:
        raise ValueError("a plant map needs at least one training file")
    if sorted(names) != sorted(roles.signals):
        raise ValueError("the role map must declare exactly these signals")
    clean = numpy.vstack([f.values[~f.attack] for f in train])
    mean, std = clean.mean(axis=0), clean.std(axis=0)
    spread = numpy.where(std > 0, std, 1.0)
    role_of = tuple(roles.role_of(name) for name in names)
    eligible = [i for i in range(len(names)) if std[i] > 0 and role_of[i] is not None]
    modelled = [i for i in eligible if role_of[i] is not SignalRole.SETPOINT]
    lags = distinct_samples(settings.lag_seconds, period_seconds)
    horizons = distinct_samples(settings.horizon_seconds, period_seconds)
    layout = Layout(
        drivers=numpy.repeat(numpy.asarray(eligible, dtype=numpy.int64), len(lags)),
        lags=numpy.tile(numpy.asarray(lags, dtype=numpy.int64), len(eligible)),
        targets=numpy.asarray(modelled, dtype=numpy.int64),
    )
    z = [(f.values - mean) / spread for f in train]
    segments, fold_of_rows = _segments([f.values.shape[0] for f in train], settings.folds)
    grams = numpy.zeros((settings.folds, layout.width, layout.width))
    fit_step = samples_for(settings.fit_step_seconds, period_seconds)
    for index, f in enumerate(train):
        rows = numpy.arange(max(lags) + 1, f.values.shape[0], fit_step)
        rows = rows[~(f.attack[rows] | f.attack[rows - 1])]
        accumulate(grams, z[index], rows, fold_of_rows[index][rows], layout)
    context = _Context(z, [f.attack for f in train], segments, grams, layout, horizons, settings)

    def admissible(y: int) -> NDArray[numpy.bool_]:
        mask = _admissible(layout, role_of, y)
        if allowed is not None:
            drivers = allowed.get(names[y], frozenset())
            mask &= numpy.isin(layout.drivers, [i for i, n in enumerate(names) if n in drivers])
        return mask

    def select(column: int, allowed: NDArray[numpy.bool_]) -> tuple[int, ...]:
        chosen = select_terms(
            grams,
            layout,
            column,
            allowed,
            settings.max_drivers,
            settings.max_lags_per_driver,
            settings.min_gain,
            settings.ridge,
        )
        return chosen.terms

    first_level = {y: select(layout.level_column(y), admissible(y)) for y in modelled}
    increment = {y: select(layout.increment_column(y), admissible(y)) for y in modelled}
    graph = {
        y: {int(layout.drivers[t]) for t in (*first_level[y], *increment[y])} for y in modelled
    }
    descendants = {y: _reachable(graph, y) for y in modelled}
    barred = _level_exclusions(roles, names, graph, modelled, descendants, settings.loop_bar)
    targets: dict[int, TargetModel] = {}
    for y in modelled:
        allowed_terms = admissible(y) & ~numpy.isin(layout.drivers, barred[y])
        level = select(layout.level_column(y), allowed_terms) if barred[y] else first_level[y]
        model = _target_model(context, y, level, increment[y], period_seconds)
        if model is not None:
            targets[y] = model
    logger.info(
        "plant map: %d of %d signal(s) mapped, %d link(s)",
        len(targets),
        len(names),
        sum(len(m.links) for m in targets.values()),
    )
    return PlantMap(
        names=tuple(names),
        roles=role_of,
        mean=mean,
        spread=spread,
        low=clean.min(axis=0),
        high=clean.max(axis=0),
        period_seconds=period_seconds,
        lags=lags,
        horizons=horizons,
        free_run_step=samples_for(settings.free_run_step_seconds, period_seconds),
        anchor_lookback=samples_for(settings.anchor_lookback_seconds, period_seconds),
        targets=targets,
        preliminary_descendants=descendants,
        level_exclusions=barred,
        settings=settings,
    )


def _target_model(
    context: _Context,
    y: int,
    level_terms: tuple[int, ...],
    increment_terms: tuple[int, ...],
    period: float,
) -> TargetModel | None:
    """Choose the form, then fit the equation, its links, their bands and the free-run band."""
    layout, settings = context.layout, context.settings
    form_h = samples_for(settings.form_horizon_seconds, period)
    options: list[tuple[float, Form, tuple[int, ...], int]] = []
    for form, terms, column in (
        (Form.LEVEL, level_terms, layout.level_column(y)),
        (Form.INCREMENT, increment_terms, layout.increment_column(y)),
    ):
        if not terms:
            continue
        coefs = context.coefficients(terms, column)
        res = context.out_of_block(form, terms, y, coefs, horizons=(form_h,))
        stacked = numpy.concatenate([r[:, 0] for r in res])
        options.append((float(numpy.nanmean(stacked**2)), form, terms, column))
    if not options:
        return None
    _error, form, terms, column = min(options, key=lambda option: (option[0], option[1].value))
    coefs = context.coefficients(terms, column)
    bands = context.bands(context.out_of_block(form, terms, y, coefs), settings.band_quantile)
    equation = Equation(context.pairs(terms), coefs[-1], bands)
    sse = cv_sse(context.grams, terms, column, layout.ones, settings.ridge)
    baseline = cv_sse(context.grams, [], column, layout.ones, settings.ridge)
    links = []
    for driver in dict.fromkeys(int(layout.drivers[t]) for t in terms):
        kept = tuple(t for t in terms if int(layout.drivers[t]) != driver)
        own = [t for t in terms if int(layout.drivers[t]) == driver]
        drop_coefs = context.coefficients(kept, column)
        drop_bands = context.bands(
            context.out_of_block(form, kept, y, drop_coefs), settings.band_quantile
        )
        drop_sse = cv_sse(context.grams, kept, column, layout.ones, settings.ridge)
        links.append(
            Link(
                driver=driver,
                target=y,
                lags=tuple(int(layout.lags[t]) for t in own),
                coefficients=tuple(float(coefs[-1][terms.index(t)]) for t in own),
                error_share=max(0.0, (drop_sse - sse) / drop_sse) if drop_sse > 0 else 0.0,
                drop_one=Equation(context.pairs(kept), drop_coefs[-1], drop_bands),
            )
        )
    free_run = _free_run(context, terms, y, coefs, period) if form is Form.INCREMENT else None
    return TargetModel(y, form, equation, tuple(links), free_run, sse, baseline)
