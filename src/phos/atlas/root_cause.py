"""Rank the signal an alert's departure started from, upstream in the plant map (ADR 0172).

`atlas-v1-consistency` alerts on the signal whose consistency broke. When one sensor is held
false, its value feeds the models downstream of it, and those models break too, so most alerts
sit on signals that are not lying. This module ranks the alerting signal and every signal upstream
of it in the fitted map, so an explanation can quote where the departure started.

A candidate is an **origin** when its own model is out of band and every modelled driver of it is
in band, **inherited** when its own model is out of band and a driver is too, and **in band**
otherwise. Candidates are ordered by that tier, then by their own out-of-band score, then by graph
distance, then by column. Nothing here adds, drops or reorders an alert, and the rank is not a
probability.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.command_physics import champion_train_seed
from phos.atlas.consistency import (
    ConsistencyModel,
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.loop_explainer import (
    LOOP_EXPLAINER_SETTINGS,
    every_sensor_subjects,
    roles_with_every_control_coupling,
)
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import PlantMap
from phos.atlas.plant_map_naming import _own
from phos.atlas.sensor_explainer import (
    HOLD_SHARE,
    LiarSubject,
    _description,
    _matrix,
    _seeds,
    _signal,
    _spec,
)
from phos.synth.injection import HoldReading, TimeWindow
from phos.synth.run import run_plant

__all__ = [
    "ROOT_CAUSE_RESULT_NAME",
    "RootCause",
    "RootCauseTotals",
    "Tier",
    "rank_root_causes",
    "score_root_causes",
    "upstream_of",
]

logger = logging.getLogger(__name__)

ROOT_CAUSE_RESULT_NAME: Final = "lane-e-root-cause"

_Float = NDArray[numpy.float64]


class Tier(IntEnum):
    """Where a candidate's departure sits relative to its own drivers. Lower ranks first."""

    ORIGIN = 0
    INHERITED = 1
    IN_BAND = 2


@dataclass(frozen=True)
class RootCause:
    """One ranked candidate for an alert's root cause.

    Attributes:
        column: The candidate's column in the map.
        signal: Its name.
        tier: `Tier` at the alert row.
        own: Its own model's out-of-band score at the row; 0 when it has no model.
        distance: Links from the candidate down to the alerting signal; 0 for the alert itself.
    """

    column: int
    signal: str
    tier: Tier
    own: float
    distance: int


def upstream_of(model: PlantMap, column: int) -> dict[int, int]:
    """Every ancestor of ``column`` through the map's links, with its shortest distance."""
    found: dict[int, int] = {}
    frontier = [column]
    distance = 0
    while frontier:
        distance += 1
        following: list[int] = []
        for node in frontier:
            for driver in model.drivers_of(node):
                if driver != column and driver not in found:
                    found[driver] = distance
                    following.append(driver)
        frontier = following
    return found


def rank_root_causes(
    model: PlantMap, values: _Float, row: int, column: int
) -> tuple[RootCause, ...]:
    """Rank the alerting signal and its ancestors at ``row``. The first is the quoted root cause.

    Args:
        model: The fitted plant map.
        values: The scored file, rows by signals, in the map's column order.
        row: The alert row.
        column: The alert column.
    """
    z = (values - model.mean) / model.spread
    candidates = {column: 0, **upstream_of(model, column)}
    own = {k: (_own(model, z, k, row) if k in model.targets else 0.0) for k in candidates}

    def in_band(k: int) -> bool:
        return (_own(model, z, k, row) if k in model.targets else 0.0) <= 1.0

    ranked: list[RootCause] = []
    for k, distance in candidates.items():
        if own[k] <= 1.0:
            tier = Tier.IN_BAND
        elif all(in_band(d) for d in model.drivers_of(k) if d in model.targets):
            tier = Tier.ORIGIN
        else:
            tier = Tier.INHERITED
        ranked.append(RootCause(k, model.names[k], tier, own[k], distance))
    ranked.sort(key=lambda item: (item.tier, -item.own, item.distance, item.column))
    return tuple(ranked)


@dataclass(frozen=True)
class RootCauseTotals:
    """Window alerts and how often a rule points at the falsified sensor."""

    cells: int
    on_falsified_column: int
    root_first: int
    root_in_two: int
    other_column_cells: int
    other_column_root_first: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy with the two shares."""
        return {
            "cells": self.cells,
            "alerting_signal_is_falsified": self.on_falsified_column,
            "alerting_signal_share": _share(self.on_falsified_column, self.cells),
            "root_first_is_falsified": self.root_first,
            "root_first_share": _share(self.root_first, self.cells),
            "root_in_first_two": self.root_in_two,
            "other_column_cells": self.other_column_cells,
            "other_column_root_first": self.other_column_root_first,
        }


def score_root_causes(
    split: str, subjects: Sequence[LiarSubject] | None = None
) -> tuple[RootCauseTotals, list[dict[str, object]]]:
    """Every declared sensor held false on ``split``: where alerts sit, and where the rank points.

    The champion and the map are fitted on the champion's training seed, as the explainers are.
    A seed outside the split is refused before a plant is built.
    """
    chosen = every_sensor_subjects() if subjects is None else tuple(subjects)
    seeds = _seeds(split)
    totals = [0, 0, 0, 0, 0, 0]
    per_subject: list[dict[str, object]] = []
    fitted: dict[tuple[str, int, int], tuple[ConsistencyModel, PlantMap, list[str]]] = {}
    for subject in chosen:
        description = _description(subject.plant_id)
        spec = _signal(description, subject.signal)
        key = (subject.plant_id, subject.sample_seconds, subject.n_steps)
        if key not in fitted:
            train = run_plant(subject.plant_id, _spec(champion_train_seed(), subject))
            values, keys = _matrix(train)
            trained = TrainFile(values=values, attack=numpy.zeros(len(values), dtype=numpy.bool_))
            champion = fit([trained], windows_for_period(float(subject.sample_seconds)))
            plant_map = fit_map(
                [trained],
                keys,
                roles_with_every_control_coupling(description),
                float(subject.sample_seconds),
                LOOP_EXPLAINER_SETTINGS,
            )
            fitted[key] = (champion, plant_map, keys)
        champion, plant_map, keys = fitted[key]
        column = keys.index(subject.signal)
        held = spec.low + HOLD_SHARE * (spec.high - spec.low)
        lo, hi = subject.n_steps // 3, 2 * subject.n_steps // 3
        counts = [0, 0, 0, 0, 0, 0]
        for seed in seeds:
            run_spec = _spec(seed, subject)
            run = run_plant(
                subject.plant_id,
                run_spec,
                injection=HoldReading(
                    subject.signal,
                    held,
                    TimeWindow(start=run_spec.instant(lo), end=run_spec.instant(hi)),
                ),
            )
            reported, _keys = _matrix(run)
            clock = numpy.array([step.timestamp.timestamp() for step in run.steps])
            found = events(feature_scores(champion, reported), windows=champion.windows)
            rows, columns, _scores = budget_alerts(found, clock, champion.windows)
            for row, col in zip(rows, columns, strict=True):
                if not lo <= row < hi:
                    continue
                ranked = rank_root_causes(plant_map, reported, row, col)
                first = ranked[0].column == column
                counts[0] += 1
                counts[1] += col == column
                counts[2] += first
                counts[3] += column in {item.column for item in ranked[:2]}
                if col != column:
                    counts[4] += 1
                    counts[5] += first
        per_subject.append(
            {
                "plant_id": subject.plant_id,
                "signal": subject.signal,
                **RootCauseTotals(*counts).as_dict(),
            }
        )
        totals = [a + b for a, b in zip(totals, counts, strict=True)]
    return RootCauseTotals(*totals), per_subject


def _share(count: int, total: int) -> float | None:
    return None if total == 0 else count / total
