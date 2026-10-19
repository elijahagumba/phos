"""Name the lying sensor on the champion's alerts, and leave the alerts alone (ADR 0161).

The plant map is an explainer. `atlas-v1-consistency` decides which cells are alerts, with its
frozen windows scaled by the sample period. This module fits a separate map, under
`lane-d-plant-map-explainer` settings, and asks `name_instrument` at those cells. It does not
add, drop, or reorder an alert. It does not claim the map detects anything the champion missed,
and a synthetic pass is not a result on a real plant (ADR 0143).

Roles come from the plant's signal table: the role is the declared `SignalKind`, and the quote is
the signal's label. Control loops come from `CONTROL` couplings that name one sensor, one
setpoint and one actuator. A coupling that names several sensors is not turned into a loop.

The held reading is a constant at 90% of the signal's span, over the middle third of the run.
The true state keeps moving underneath. Reconstruction error is the absolute gap between the
map's centre and that true value, divided by the signal's span.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.command_physics import champion_train_seed
from phos.atlas.consistency import (
    RESULT_NAME,
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, MapSettings
from phos.atlas.plant_map_model import RESULT_NAME as MAP_RESULT_NAME
from phos.atlas.plant_map_naming import Naming, Verdict, name_instrument
from phos.atlas.signal_roles import ControlLoop, RoleDeclaration, SignalRole, SignalRoles
from phos.eval.build_declaration import (
    BUILD_DEVELOPMENT_SEEDS,
    BUILD_HELD_BACK_SEEDS,
    SCORECARD,
)
from phos.synth.injection import HoldReading, TimeWindow
from phos.synth.plant import CouplingKind, PlantDescription, RunSpec, SignalKind, SignalSpec
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION
from phos.synth.plants.water import WATER_DESCRIPTION
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "EXPLAINER_RESULT_NAME",
    "EXPLAINER_SETTINGS",
    "FROZEN_SUBJECTS",
    "HOLD_SHARE",
    "SURVEY_SUBJECTS",
    "LiarSubject",
    "SubjectResult",
    "bar_met",
    "naming_scorecard",
    "roles_from_plant",
    "score_naming",
    "score_subject",
]

logger = logging.getLogger(__name__)

EXPLAINER_RESULT_NAME: Final = "lane-d-plant-map-explainer"
"""Not `atlas-plant-map-v1`. These windows were set for the synthetic sample periods."""

EXPLAINER_SETTINGS: Final = MapSettings(
    lag_seconds=(60, 120, 300, 600),
    horizon_seconds=(120, 600),
    form_horizon_seconds=600,
    fit_step_seconds=60,
    anchor_every_seconds=600,
    free_run_step_seconds=120,
    free_run_max_seconds=7200,
    anchor_lookback_seconds=7200,
    naming_rules="adr-0135",
)
"""Shorter windows than `DEFAULT_SETTINGS`, and ADR 0135's naming rules.

ADR 0125's rules, which remain the default, named water's filtered turbidity on 0 of 20
development seeds. ADR 0135's rules named it on 20 of 20. The default settings object is not
modified.
"""

HOLD_SHARE: Final = 0.9
"""Where the falsified reading is held, as a fraction of the way from low to high."""

_START: Final = datetime(2026, 10, 1, tzinfo=UTC)
_WITHIN: Final = 0.10
_NAMED_RIGHT_BAR: Final = 0.70


@dataclass(frozen=True)
class LiarSubject:
    """One sensor held false, on one plant.

    Attributes:
        plant_id: Which synthetic plant.
        sample_seconds: The run's sample interval.
        n_steps: How many samples. Long enough for the explainer's lags.
        signal: The falsified column, a declared sensor.
        on_the_bar: Whether this subject is one of the three the bar is judged on.
    """

    plant_id: str
    sample_seconds: int
    n_steps: int
    signal: str
    on_the_bar: bool


FROZEN_SUBJECTS: Final[tuple[LiarSubject, ...]] = (
    LiarSubject("water-treatment", 30, 900, "filtered_turbidity_ntu", True),
    LiarSubject("power-generation", 10, 1200, "transformer_oil_temp_c", True),
    LiarSubject("batch-reactor", 60, 700, "reactor_temp_c", True),
)
"""One sensor per plant, frozen on development before any held-back look."""

SURVEY_SUBJECTS: Final[tuple[LiarSubject, ...]] = (
    LiarSubject("water-treatment", 30, 900, "chlorine_residual_mgpl", False),
    LiarSubject("water-treatment", 30, 900, "distribution_pressure_bar", False),
    LiarSubject("power-generation", 10, 1200, "feeder_voltage_kv", False),
    LiarSubject("power-generation", 10, 1200, "exhaust_temp_c", False),
    LiarSubject("batch-reactor", 60, 700, "jacket_temp_c", False),
    LiarSubject("batch-reactor", 60, 700, "reactor_pressure_barg", False),
)
"""Other sensors measured on the same rule, so a pass on the frozen three is not the only row."""


@dataclass(frozen=True)
class SubjectResult:
    """How the explainer did on one subject across a split."""

    plant_id: str
    signal: str
    on_the_bar: bool
    scored: int
    caught: int
    named_right: int
    named_wrong: int
    reconstruction_max: float | None
    reconstruction_within_tenth: int
    reconstruction_cells: int
    alerts_unchanged: bool
    seeds_not_named_right: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "plant_id": self.plant_id,
            "signal": self.signal,
            "on_the_bar": self.on_the_bar,
            "scored": self.scored,
            "caught": self.caught,
            "named_right": self.named_right,
            "named_wrong": self.named_wrong,
            "naming_right": _rate(self.named_right, self.caught),
            "naming_wrong": _rate(self.named_wrong, self.caught),
            "reconstruction_max": self.reconstruction_max,
            "reconstruction_within_tenth": self.reconstruction_within_tenth,
            "reconstruction_cells": self.reconstruction_cells,
            "alerts_unchanged": self.alerts_unchanged,
            "seeds_not_named_right": list(self.seeds_not_named_right),
            "champion_result_name": RESULT_NAME,
            "explainer_result_name": EXPLAINER_RESULT_NAME,
        }


def roles_from_plant(description: PlantDescription) -> SignalRoles:
    """Roles and loops read from the plant's own signal table and couplings.

    The quote is the signal's label. The role is its declared kind. Nothing is inferred from
    the key's spelling.
    """
    kind_of = {
        SignalKind.SENSOR: SignalRole.SENSOR,
        SignalKind.ACTUATOR: SignalRole.ACTUATOR,
        SignalKind.SETPOINT: SignalRole.SETPOINT,
    }
    declarations = tuple(
        RoleDeclaration(
            signal=spec.key,
            role=kind_of[spec.kind],
            cited=f"{description.plant_id} signal table",
            quote=spec.label,
        )
        for spec in description.signals
    )
    signal_kind = {spec.key: spec.kind for spec in description.signals}
    loops: list[ControlLoop] = []
    for coupling in description.couplings:
        if coupling.kind is not CouplingKind.CONTROL:
            continue
        setpoints = [
            driver for driver in coupling.drivers if signal_kind[driver] is SignalKind.SETPOINT
        ]
        sensors = [
            driver for driver in coupling.drivers if signal_kind[driver] is SignalKind.SENSOR
        ]
        if signal_kind[coupling.driven] is not SignalKind.ACTUATOR:
            continue
        if len(setpoints) != 1 or len(sensors) != 1:
            continue
        loops.append(
            ControlLoop(
                name=coupling.driven,
                cited=f"{description.plant_id} couplings",
                statement=coupling.relation,
                reading=sensors[0],
                outputs=(coupling.driven,),
                setpoint=setpoints[0],
            )
        )
    return SignalRoles(
        declarations,
        [spec.key for spec in description.signals],
        source=description.label,
        loops=loops,
    )


def score_subject(
    subject: LiarSubject,
    *,
    split: str,
    seeds: Sequence[int] | None = None,
    settings: MapSettings = EXPLAINER_SETTINGS,
    roles_for: Callable[[PlantDescription], SignalRoles] | None = None,
) -> SubjectResult:
    """Score one subject on ``split``. The champion is fit on seed 97001.

    ``seeds`` restricts the score to a subset of that split. A seed from another split is
    refused before any plant is built. ``settings`` and ``roles_for`` default to this module's
    explainer; a later explainer (ADR 0170) passes its own without changing this one.

    Raises:
        ValueError: If ``split`` is not a build split, or a requested seed is outside it.
    """
    allowed = _seeds(split)
    chosen = allowed if seeds is None else tuple(seeds)
    outside = [seed for seed in chosen if seed not in allowed]
    if outside:
        raise ValueError(f"seeds {outside} are not in the {split} split")
    description = _description(subject.plant_id)
    spec = _signal(description, subject.signal)
    if spec.kind is not SignalKind.SENSOR:
        raise ValueError(f"{subject.signal} is a {spec.kind.value}, not a sensor")
    train = run_plant(subject.plant_id, _spec(champion_train_seed(), subject))
    values, keys = _matrix(train)
    trained = TrainFile(values=values, attack=numpy.zeros(subject.n_steps, dtype=numpy.bool_))
    champion = fit([trained], windows_for_period(float(subject.sample_seconds)))
    roles = roles_from_plant(description) if roles_for is None else roles_for(description)
    plant_map = fit_map(
        [trained],
        keys,
        roles,
        float(subject.sample_seconds),
        settings,
    )
    column = keys.index(subject.signal)
    span = spec.high - spec.low
    held = spec.low + HOLD_SHARE * span
    caught = named_right = named_wrong = 0
    within = cells = 0
    worst: float | None = None
    unchanged = True
    missed: list[int] = []
    lo, hi = subject.n_steps // 3, 2 * subject.n_steps // 3
    for seed in chosen:
        run_spec = _spec(seed, subject)
        alerts_run = run_plant(
            subject.plant_id,
            run_spec,
            injection=HoldReading(
                subject.signal,
                held,
                TimeWindow(start=run_spec.instant(lo), end=run_spec.instant(hi)),
            ),
        )
        reported, _keys = _matrix(alerts_run)
        clock = numpy.array(
            [step.timestamp.timestamp() for step in alerts_run.steps], dtype=numpy.float64
        )
        found = events(feature_scores(champion, reported), windows=champion.windows)
        rows, columns, _scores = budget_alerts(found, clock, champion.windows)
        again_rows, again_columns, _again_scores = budget_alerts(found, clock, champion.windows)
        if rows != again_rows or columns != again_columns:
            unchanged = False
        window_cells = [
            (row, col)
            for row, col in zip(rows, columns, strict=True)
            if lo <= row < hi and col == column
        ]
        if not window_cells:
            continue
        caught += 1
        truth = [step.truth.values[subject.signal] for step in alerts_run.steps]
        right = True
        wrong = False
        for row, col in window_cells:
            naming = name_instrument(plant_map, reported, row, col, rules=settings.naming_rules)
            if naming.verdict is Verdict.NAMED and naming.instrument == column:
                error = _reconstruction_error(naming, row, truth[row], span)
                if error is None:
                    right = False
                else:
                    cells += 1
                    worst = error if worst is None else max(worst, error)
                    if error <= _WITHIN:
                        within += 1
                    else:
                        right = False
            else:
                right = False
                if naming.verdict is Verdict.NAMED:
                    wrong = True
        if right:
            named_right += 1
        else:
            missed.append(seed)
        if wrong:
            named_wrong += 1
    return SubjectResult(
        plant_id=subject.plant_id,
        signal=subject.signal,
        on_the_bar=subject.on_the_bar,
        scored=len(chosen),
        caught=caught,
        named_right=named_right,
        named_wrong=named_wrong,
        reconstruction_max=worst,
        reconstruction_within_tenth=within,
        reconstruction_cells=cells,
        alerts_unchanged=unchanged,
        seeds_not_named_right=tuple(missed),
    )


def score_naming(
    split: str, *, survey: bool = True, seeds: Sequence[int] | None = None
) -> tuple[SubjectResult, ...]:
    """Score the frozen subjects, and the survey subjects when ``survey`` is set."""
    subjects = FROZEN_SUBJECTS + SURVEY_SUBJECTS if survey else FROZEN_SUBJECTS
    return tuple(score_subject(subject, split=split, seeds=seeds) for subject in subjects)


def naming_scorecard(results: Sequence[SubjectResult]) -> dict[str, float | None]:
    """Fill the naming keys. Other scorecard keys stay ``None``.

    ``naming_right`` is the lowest of the three frozen rates, and ``naming_wrong`` the highest.
    ``reconstruction_error`` is the worst reconstructed gap, as a fraction of span.
    ``falsified_sensor_passes`` is the fraction of those three that meet the bar. A plant with
    no caught run leaves the rates ``None`` rather than a zero.
    """
    numbers: dict[str, float | None] = dict.fromkeys(SCORECARD)
    frozen = [item for item in results if item.on_the_bar]
    if len(frozen) != len(FROZEN_SUBJECTS):
        return numbers
    rates = [_rate(item.named_right, item.caught) for item in frozen]
    wrongs = [_rate(item.named_wrong, item.caught) for item in frozen]
    present = [rate for rate in rates if rate is not None]
    present_wrong = [rate for rate in wrongs if rate is not None]
    if len(present) == len(frozen):
        numbers["naming_right"] = min(present)
    if len(present_wrong) == len(frozen):
        numbers["naming_wrong"] = max(present_wrong)
    errors = [item.reconstruction_max for item in frozen]
    present_errors = [error for error in errors if error is not None]
    if len(present_errors) == len(frozen):
        numbers["reconstruction_error"] = max(present_errors)
    numbers["falsified_sensor_passes"] = _passes(frozen) / len(frozen)
    return numbers


def _passes(frozen: Sequence[SubjectResult]) -> int:
    """How many frozen subjects meet the naming bar on their own."""
    passed = 0
    for item in frozen:
        rate = _rate(item.named_right, item.caught)
        if rate is None or rate < _NAMED_RIGHT_BAR:
            continue
        if item.reconstruction_max is None or item.reconstruction_max > _WITHIN:
            continue
        if not item.alerts_unchanged:
            continue
        passed += 1
    return passed


def bar_met(results: Sequence[SubjectResult]) -> bool:
    """The three frozen plants each name at least 70% of caught runs, within 10% of span.

    A plant with no caught run has not met the bar. Survey subjects are not in this judgement.
    """
    frozen = [item for item in results if item.on_the_bar]
    if len(frozen) != len(FROZEN_SUBJECTS):
        return False
    for item in frozen:
        rate = _rate(item.named_right, item.caught)
        if rate is None or rate < _NAMED_RIGHT_BAR:
            return False
        if item.reconstruction_max is None or item.reconstruction_max > _WITHIN:
            return False
        if not item.alerts_unchanged:
            return False
    return True


def _reconstruction_error(naming: Naming, row: int, truth: float, span: float) -> float | None:
    """Return ``|centre - truth| / span`` at ``row``, or ``None`` when the row was not rebuilt."""
    reconstruction = naming.reconstruction
    if reconstruction is None or span <= 0:
        return None
    rebuilt = [int(item) for item in reconstruction.rows]
    if row not in rebuilt:
        return None
    centre = float(reconstruction.centre[rebuilt.index(row)])
    if not numpy.isfinite(centre):
        return None
    return abs(centre - truth) / span


def _description(plant_id: str) -> PlantDescription:
    """The declaration for a plant this explainer knows."""
    descriptions = {
        WATER_DESCRIPTION.plant_id: WATER_DESCRIPTION,
        POWER_DESCRIPTION.plant_id: POWER_DESCRIPTION,
        BATCH_DESCRIPTION.plant_id: BATCH_DESCRIPTION,
    }
    try:
        return descriptions[plant_id]
    except KeyError as exc:
        raise KeyError(f"no plant {plant_id!r}") from exc


def _signal(description: PlantDescription, key: str) -> SignalSpec:
    """The declared spec, or a loud miss."""
    for spec in description.signals:
        if spec.key == key:
            return spec
    raise KeyError(f"{description.plant_id} has no signal {key!r}")


def _spec(seed: int, subject: LiarSubject) -> RunSpec:
    """One run of ``subject.n_steps`` from a fixed start."""
    interval = timedelta(seconds=subject.sample_seconds)
    return RunSpec(
        seed=seed,
        start=_START,
        duration=interval * subject.n_steps,
        sample_interval=interval,
    )


def _matrix(run: PlantRun) -> tuple[NDArray[numpy.float64], list[str]]:
    """Reported values in declaration order, and the column names."""
    keys = [spec.key for spec in run.description.signals]
    rows = [[step.report.values[key] for key in keys] for step in run.steps]
    return numpy.asarray(rows, dtype=numpy.float64), keys


def _seeds(split: str) -> tuple[int, ...]:
    """Seeds a split may score. Anything else is refused before a plant is built."""
    if split == "development":
        return BUILD_DEVELOPMENT_SEEDS
    if split == "held-back":
        return BUILD_HELD_BACK_SEEDS
    raise ValueError(f"split must be 'development' or 'held-back', got {split!r}")


def _rate(count: int, total: int) -> float | None:
    """``count / total``, or ``None`` when there is nothing to divide."""
    if total == 0:
        return None
    return count / total


def explainer_is_not_the_default() -> bool:
    """The lane settings are a different object from the frozen map defaults."""
    return _names_differ(EXPLAINER_RESULT_NAME, MAP_RESULT_NAME) and (
        EXPLAINER_SETTINGS is not DEFAULT_SETTINGS
        and DEFAULT_SETTINGS.naming_rules == "adr-0125"
        and EXPLAINER_SETTINGS.naming_rules == "adr-0135"
    )


def _names_differ(left: str, right: str) -> bool:
    """Whether two result names differ.

    Split out so the two literals are not compared at the call site, which mypy treats as an
    overlap it already knows.
    """
    return left != right
