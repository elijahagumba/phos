"""Synthetic harness for self-closing maintenance alerts (ADR 0151).

Each development seed 97001-97020 lays a maintenance calendar with
`plan_maintenance`, writes it as an SAP PM export, and reads that export back through
`load_work_order_export`. Maintenance alerts carry the job log's citation. Attack alerts,
including a `MIMIC` placed on the same instant as a real job, carry none.

The product rule is `close_maintenance_alerts`. The rival is `close_on_overlap`. The same
events are also injected, at the same magnitude, into a one-second trace and scored with
`atlas-v1-consistency` at the frozen one-second windows.

Nothing here appends ``eval_runs/log.jsonl``. Seeds outside `BUILD_DEVELOPMENT_SEEDS` are
refused before a calendar is drawn. Hypothesis confidence is not computed.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Final

import numpy
from numpy.random import Generator, SeedSequence
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from phos.atlas.cmms import SAP_PM_SCHEMA, WorkOrderRecord, load_work_order_export
from phos.atlas.consistency import (
    RESULT_NAME,
    SHIFT_SECONDS,
    ScoredFile,
    TrainFile,
    detect,
)
from phos.atlas.consistency_windows import FROZEN_WINDOWS, windows_for_period
from phos.atlas.maintenance_closure import (
    JobCitation,
    OpenAlert,
    close_maintenance_alerts,
    close_on_overlap,
)
from phos.eval.build_declaration import BUILD_DEVELOPMENT_SEEDS, BUILD_HELD_BACK_SEEDS, SCORECARD
from phos.synth.attacks.spec import AttackType
from phos.synth.maintenance import (
    MaintenanceCalendar,
    MaintenancePractice,
    plan_maintenance,
    write_sap_pm_export,
)
from phos.synth.plant import RunSpec

__all__ = [
    "ASSETS",
    "EFFECT_SECONDS",
    "FEATURE_OF",
    "HARNESS_CAVEAT",
    "HARNESS_PRACTICE",
    "MAINTENANCE_CLOSURE_BAR",
    "RANDOM_ATTACK_KINDS",
    "REGRESSION_ROLE",
    "RESULT_NAME",
    "RUN_HOURS",
    "SAMPLE_SECONDS",
    "ClosureReport",
    "ConsistencyReport",
    "ConsistencySeed",
    "SeedScore",
    "UndeclaredSeedError",
    "alert_count_phrase",
    "build_held_back_seed",
    "build_seed",
    "score_consistency",
    "score_development_closures",
    "score_held_back_closures_once",
    "score_held_back_consistency_once",
    "synthetic_scorecard",
]

logger = logging.getLogger(__name__)

HARNESS_CAVEAT: Final = (
    "Synthetic maintenance closure on seeds 97001-97020 is a diagnosis. It is not a detection "
    "claim and it is not evidence about a real plant. A Kelmarsh false-alarm count, when one "
    "is reported beside this, is not evidence the plant map detects attacks. Hypothesis "
    "confidence is not reported."
)

MAINTENANCE_CLOSURE_BAR: Final = 0.70
"""A5 / W4 pass mark: share of maintenance-caused alerts that close with a cited work order."""

ASSETS: Final[tuple[str, ...]] = ("P-101", "P-102", "V-201")
FEATURE_OF: Final[Mapping[str, str]] = {
    "P-101": "flow",
    "P-102": "speed",
    "V-201": "position",
}
"""One signal per asset. The SAP export does not name it; the job log does."""

RUN_START: Final = datetime(2026, 1, 1, tzinfo=UTC)
RUN_HOURS: Final = 6.0
RUN: Final = timedelta(hours=RUN_HOURS)
SAMPLE_SECONDS: Final = 1.0
TRAIN_SECONDS: Final = 3600
EFFECT_SECONDS: Final = 30
"""How long a job or an attack moves its signal in the consistency trace. Same length, same step."""

STEP: Final = 20.0
"""Added to the signal for EFFECT_SECONDS. Maintenance and attacks use the same step."""

HARNESS_PRACTICE: Final = MaintenancePractice(
    routine_interval=timedelta(hours=2),
    routine_duration=timedelta(minutes=20),
    reactive_per_year=12.0,
    reactive_duration=timedelta(minutes=15),
    shutdown_interval=None,
    idle_share=0.15,
)
"""Compressed routine interval so a six-hour run contains several jobs.

``idle_share`` is the shipped `MaintenancePractice` default. It is what leaves a maintenance
alert open: the export loader drops orders that do not sanction, so their citations do not
resolve. It was not chosen by looking at a score.
"""

RANDOM_ATTACK_KINDS: Final[tuple[AttackType, ...]] = (
    AttackType.MIMIC,
    AttackType.BLATANT,
    AttackType.STEALTH_DRIFT,
)
REGRESSION_ROLE: Final = "mimic-inside-window"
"""One MIMIC placed, after the calendar exists, on a real job's instant. It carries no citation."""

_RIVAL_NAME: Final = "close_on_overlap"
_Float64 = NDArray[numpy.float64]


class UndeclaredSeedError(ValueError):
    """Raised when a harness call is asked for a seed outside 97001-97020."""


class Cause(str, Enum):
    """Ground truth for scoring. The closer never receives this."""

    MAINTENANCE = "maintenance"
    ATTACK = "attack"


class Effect(BaseModel):
    """A thirty-second step in the consistency trace. Scoring labels only; not a closure input."""

    model_config = ConfigDict(frozen=True)

    feature: str
    start: datetime
    end: datetime
    cause: Cause
    kind: str


class LabelledAlert(BaseModel):
    """An alert plus the ground truth used after the closer has decided."""

    model_config = ConfigDict(frozen=True)

    alert: OpenAlert
    cause: Cause
    kind: str
    role: str


class SeedBundle(BaseModel):
    """One seed's alerts, the export the closer sees, and the trace effects."""

    model_config = ConfigDict(frozen=True)

    seed: int
    alerts: tuple[LabelledAlert, ...]
    records: tuple[WorkOrderRecord, ...]
    effects: tuple[Effect, ...]
    orders: int
    sanctioning_orders: int


class SeedScore(BaseModel):
    """Closure counts for one seed.

    Rates are left to the aggregate, so one small seed is not reported as the bar.
    """

    model_config = ConfigDict(frozen=True)

    seed: int
    maintenance_alerts: int
    maintenance_closed: int
    attack_alerts: int
    attack_closed: int
    mimic_alerts: int
    mimic_closed: int
    rival_attack_closed: int
    rival_maintenance_closed: int
    chance_attack_closed: int
    orders: int
    sanctioning_orders: int
    regression_mimic_closed: bool
    regression_mimic_closed_by_rival: bool
    cited_order_ids: tuple[str, ...]


class ClosureReport(BaseModel):
    """The development-seed closure measurement. Counts are the claim; the rate is their ratio."""

    model_config = ConfigDict(frozen=True)

    seeds: tuple[int, ...]
    maintenance_alerts: int
    maintenance_closed: int
    maintenance_closure_rate: float
    attack_alerts: int
    attack_closed: int
    mimic_alerts: int
    mimic_closed: int
    bar: float
    maintenance_bar_met: bool
    no_attack_closed: bool
    rival_name: str
    rival_maintenance_closed: int
    rival_attack_closed: int
    rival_maintenance_closure_rate: float
    rival_attack_closure_rate: float
    margin_over_best_simple_rival: float
    chance_attack_closed: int
    chance_attack_closure_rate: float
    margin_over_chance: float
    per_seed: tuple[SeedScore, ...]
    caveat: str


class ConsistencySeed(BaseModel):
    """`atlas-v1-consistency` on one seed's trace."""

    model_config = ConfigDict(frozen=True)

    seed: int
    detector: str
    attack_effects: int
    attacks_caught: int
    attacks_caught_on_target: int
    alerts: int
    attack_alerts: int
    maintenance_alerts: int
    unexplained_alerts: int
    false_alerts_per_shift: float
    shifts: float


class ConsistencyReport(BaseModel):
    """The champion detector on the same seeds and the same events."""

    model_config = ConfigDict(frozen=True)

    detector: str
    seeds: tuple[int, ...]
    attacks: int
    attacks_caught: int
    attacks_caught_on_target: int
    catches_within_budget: float
    catches_on_target: float
    alerts: int
    unexplained_alerts: int
    false_alerts_per_shift: float
    shifts: float
    per_seed: tuple[ConsistencySeed, ...]
    caveat: str


def require_development_seed(seed: int) -> None:
    """Refuse any seed the October build did not declare for iteration.

    Args:
        seed: The seed the caller asked to run.

    Raises:
        UndeclaredSeedError: If ``seed`` is not in `BUILD_DEVELOPMENT_SEEDS`. Held-back
            97101-97120, T1's 94001-94020, and every used set fail this check. Nothing is
            generated first.
    """
    if seed not in BUILD_DEVELOPMENT_SEEDS:
        raise UndeclaredSeedError(
            f"seed {seed} is outside BUILD_DEVELOPMENT_SEEDS (97001-97020). Held-back seeds "
            "97101-97120, T1's 94001-94020, and the arena, red-team, confirm, and ICSSim seed "
            "sets are not run."
        )


def _rng(seed: int, stream: int) -> Generator:
    """A generator for one named stream of one development seed."""
    return numpy.random.default_rng(SeedSequence([seed, stream]))


def _effect(feature: str, start: datetime, cause: Cause, kind: str) -> Effect:
    """A step that begins at ``start`` and lasts `EFFECT_SECONDS`, clipped to the run."""
    run_end = RUN_START + RUN
    end = min(start + timedelta(seconds=EFFECT_SECONDS), run_end)
    return Effect(feature=feature, start=start, end=end, cause=cause, kind=kind)


def build_seed(seed: int) -> SeedBundle:
    """Draw one seed's calendar, export, alerts, and trace effects.

    The calendar is drawn from `HARNESS_PRACTICE` alone. Random attacks are placed without
    reading it. The regression `MIMIC` is placed afterwards, on the earliest sanctioning
    order's start when one exists, and it carries no citation. The calendar is not redrawn.

    Args:
        seed: A build development seed, 97001-97020.

    Returns:
        The alerts the closer will see, the sanctioning export rows, and the trace effects.

    Raises:
        UndeclaredSeedError: If ``seed`` is not a development seed.
        RuntimeError: If the SAP round trip does not preserve the sanctioning order ids or times.
    """
    require_development_seed(seed)
    return _build(seed)


def build_held_back_seed(seed: int) -> SeedBundle:
    """Draw one held-back seed exactly as `build_seed` draws a development one (ADR 0164).

    Only `scripts/lane_b_heldback.py` calls this, after it has checked the committed
    declaration. Nothing may be tuned on what it returns.

    Raises:
        UndeclaredSeedError: If ``seed`` is not in 97101-97120.
    """
    if seed not in BUILD_HELD_BACK_SEEDS:
        raise UndeclaredSeedError(f"seed {seed} is not a build held-back seed (97101-97120)")
    return _build(seed)


def _build(seed: int) -> SeedBundle:
    """The seed's calendar, export, alerts, and effects. Callers gate the seed first."""
    spec = RunSpec(
        seed=seed,
        start=RUN_START,
        duration=RUN,
        sample_interval=timedelta(seconds=SAMPLE_SECONDS),
    )
    calendar = plan_maintenance(_rng(seed, 1), spec, ASSETS, HARNESS_PRACTICE)
    records = _load_export(calendar)
    _check_round_trip(calendar, records)

    alerts: list[LabelledAlert] = []
    effects: list[Effect] = []
    reloaded = {record.order_id: record for record in records}
    for order in calendar.orders:
        feature = FEATURE_OF[order.asset_id]
        stamp = reloaded[order.order_id].start if order.order_id in reloaded else order.start
        if order.sanctioning and stamp != order.start:
            raise RuntimeError(
                f"seed {seed} order {order.order_id} moved from {order.start} to {stamp} "
                "on the SAP round trip"
            )
        alerts.append(
            LabelledAlert(
                alert=OpenAlert(
                    alert_id=f"{seed}-job-{order.order_id}",
                    asset_id=order.asset_id,
                    feature=feature,
                    timestamp=stamp,
                    citations=(JobCitation(order_id=order.order_id, feature=feature),),
                ),
                cause=Cause.MAINTENANCE,
                kind=order.kind.value,
                role="job",
            )
        )
        effects.append(_effect(feature, stamp, Cause.MAINTENANCE, order.kind.value))

    attack_rng = _rng(seed, 2)
    span = int(RUN.total_seconds()) - EFFECT_SECONDS
    for index, kind in enumerate(RANDOM_ATTACK_KINDS):
        asset = ASSETS[int(attack_rng.integers(0, len(ASSETS)))]
        offset = int(attack_rng.integers(0, span + 1))
        stamp = RUN_START + timedelta(seconds=offset)
        feature = FEATURE_OF[asset]
        alerts.append(
            LabelledAlert(
                alert=OpenAlert(
                    alert_id=f"{seed}-attack-{index}-{kind.value}",
                    asset_id=asset,
                    feature=feature,
                    timestamp=stamp,
                    citations=(),
                ),
                cause=Cause.ATTACK,
                kind=kind.value,
                role="attack",
            )
        )
        effects.append(_effect(feature, stamp, Cause.ATTACK, kind.value))

    host = min(records, key=lambda record: (record.start, record.order_id)) if records else None
    if host is None:
        asset = ASSETS[int(attack_rng.integers(0, len(ASSETS)))]
        offset = int(attack_rng.integers(0, span + 1))
        stamp = RUN_START + timedelta(seconds=offset)
        feature = FEATURE_OF[asset]
    else:
        asset = host.asset_id
        feature = FEATURE_OF[asset]
        stamp = host.start
    alerts.append(
        LabelledAlert(
            alert=OpenAlert(
                alert_id=f"{seed}-{REGRESSION_ROLE}",
                asset_id=asset,
                feature=feature,
                timestamp=stamp,
                citations=(),
            ),
            cause=Cause.ATTACK,
            kind=AttackType.MIMIC.value,
            role=REGRESSION_ROLE,
        )
    )
    effects.append(_effect(feature, stamp, Cause.ATTACK, AttackType.MIMIC.value))

    sanctioning = sum(1 for order in calendar.orders if order.sanctioning)
    logger.info(
        "seed %d: %d orders, %d sanctioning, %d alerts",
        seed,
        len(calendar.orders),
        sanctioning,
        len(alerts),
    )
    return SeedBundle(
        seed=seed,
        alerts=tuple(alerts),
        records=records,
        effects=tuple(effects),
        orders=len(calendar.orders),
        sanctioning_orders=sanctioning,
    )


def _load_export(calendar: MaintenanceCalendar) -> tuple[WorkOrderRecord, ...]:
    """Write the calendar as SAP PM and read it back with the real loader."""
    with tempfile.TemporaryDirectory(prefix="phos-maint-") as directory:
        path = Path(directory) / "sap.csv"
        write_sap_pm_export(calendar, path)
        return load_work_order_export(path, SAP_PM_SCHEMA, ASSETS)


def _check_round_trip(calendar: MaintenanceCalendar, records: tuple[WorkOrderRecord, ...]) -> None:
    """The loader must keep every sanctioning order and only those."""
    loaded = {record.order_id for record in records}
    sanctioned = {order.order_id for order in calendar.orders if order.sanctioning}
    if loaded != sanctioned:
        raise RuntimeError(
            "SAP round trip did not preserve sanctioning orders: "
            f"loaded {sorted(loaded)} calendar {sorted(sanctioned)}"
        )


def _score_seed(bundle: SeedBundle) -> SeedScore:
    """Run the product rule, the overlap rival, and one citation permutation."""
    alerts = [item.alert for item in bundle.alerts]
    champion = close_maintenance_alerts(alerts, bundle.records)
    rival = close_on_overlap(alerts, bundle.records)
    chance = close_maintenance_alerts(_permute_citations(bundle), bundle.records)
    by_champion = {decision.alert_id: decision for decision in champion}
    by_rival = {decision.alert_id: decision for decision in rival}
    by_chance = {decision.alert_id: decision for decision in chance}

    maintenance = [item for item in bundle.alerts if item.cause is Cause.MAINTENANCE]
    attacks = [item for item in bundle.alerts if item.cause is Cause.ATTACK]
    mimics = [item for item in attacks if item.kind == AttackType.MIMIC.value]
    regression = next(item for item in bundle.alerts if item.role == REGRESSION_ROLE)
    cited_ids: list[str] = []
    for decision in champion:
        if decision.closed and decision.order_id is not None:
            cited_ids.append(decision.order_id)
    cited = tuple(sorted(cited_ids))
    return SeedScore(
        seed=bundle.seed,
        maintenance_alerts=len(maintenance),
        maintenance_closed=sum(
            1 for item in maintenance if by_champion[item.alert.alert_id].closed
        ),
        attack_alerts=len(attacks),
        attack_closed=sum(1 for item in attacks if by_champion[item.alert.alert_id].closed),
        mimic_alerts=len(mimics),
        mimic_closed=sum(1 for item in mimics if by_champion[item.alert.alert_id].closed),
        rival_attack_closed=sum(1 for item in attacks if by_rival[item.alert.alert_id].closed),
        rival_maintenance_closed=sum(
            1 for item in maintenance if by_rival[item.alert.alert_id].closed
        ),
        chance_attack_closed=sum(1 for item in attacks if by_chance[item.alert.alert_id].closed),
        orders=bundle.orders,
        sanctioning_orders=bundle.sanctioning_orders,
        regression_mimic_closed=by_champion[regression.alert.alert_id].closed,
        regression_mimic_closed_by_rival=by_rival[regression.alert.alert_id].closed,
        cited_order_ids=cited,
    )


def _permute_citations(bundle: SeedBundle) -> list[OpenAlert]:
    """Move each alert's citations onto another alert, as a chance null for the same closer."""
    alerts = [item.alert for item in bundle.alerts]
    order = _rng(bundle.seed, 4).permutation(len(alerts)).tolist()
    shuffled: list[OpenAlert] = []
    for index, alert in enumerate(alerts):
        donor = alerts[int(order[index])]
        shuffled.append(alert.model_copy(update={"citations": donor.citations}))
    return shuffled


def _rate(closed: int, total: int, what: str) -> float:
    """A ratio. An empty denominator is a broken harness, not a rate of one."""
    if total <= 0:
        raise ValueError(f"no {what} alerts to score")
    return closed / total


def score_development_closures(
    seeds: Sequence[int] = BUILD_DEVELOPMENT_SEEDS,
) -> ClosureReport:
    """Score the closure rule on the given development seeds.

    Args:
        seeds: Defaults to 97001-97020. Any other seed is refused.

    Returns:
        Counts, the two margins, and the per-seed rows.
    """
    return _closures(seeds, build_seed)


def score_held_back_closures_once() -> ClosureReport:
    """The closure rule on 97101-97120. Called only by the declared command (ADR 0164)."""
    return _closures(BUILD_HELD_BACK_SEEDS, build_held_back_seed)


def _closures(seeds: Sequence[int], builder: Callable[[int], SeedBundle]) -> ClosureReport:
    """Score the closure rule on ``seeds``, each drawn by ``builder``."""
    per_seed = tuple(_score_seed(builder(seed)) for seed in seeds)
    maintenance_alerts = sum(row.maintenance_alerts for row in per_seed)
    maintenance_closed = sum(row.maintenance_closed for row in per_seed)
    attack_alerts = sum(row.attack_alerts for row in per_seed)
    attack_closed = sum(row.attack_closed for row in per_seed)
    mimic_alerts = sum(row.mimic_alerts for row in per_seed)
    mimic_closed = sum(row.mimic_closed for row in per_seed)
    rival_maintenance = sum(row.rival_maintenance_closed for row in per_seed)
    rival_attacks = sum(row.rival_attack_closed for row in per_seed)
    chance_attacks = sum(row.chance_attack_closed for row in per_seed)
    maintenance_rate = _rate(maintenance_closed, maintenance_alerts, "maintenance")
    attack_rate = _rate(attack_closed, attack_alerts, "attack")
    rival_attack_rate = _rate(rival_attacks, attack_alerts, "attack")
    chance_rate = _rate(chance_attacks, attack_alerts, "attack")
    return ClosureReport(
        seeds=tuple(seeds),
        maintenance_alerts=maintenance_alerts,
        maintenance_closed=maintenance_closed,
        maintenance_closure_rate=maintenance_rate,
        attack_alerts=attack_alerts,
        attack_closed=attack_closed,
        mimic_alerts=mimic_alerts,
        mimic_closed=mimic_closed,
        bar=MAINTENANCE_CLOSURE_BAR,
        maintenance_bar_met=maintenance_rate >= MAINTENANCE_CLOSURE_BAR,
        no_attack_closed=attack_closed == 0 and mimic_closed == 0,
        rival_name=_RIVAL_NAME,
        rival_maintenance_closed=rival_maintenance,
        rival_attack_closed=rival_attacks,
        rival_maintenance_closure_rate=_rate(rival_maintenance, maintenance_alerts, "maintenance"),
        rival_attack_closure_rate=rival_attack_rate,
        margin_over_best_simple_rival=rival_attack_rate - attack_rate,
        chance_attack_closed=chance_attacks,
        chance_attack_closure_rate=chance_rate,
        margin_over_chance=chance_rate - attack_rate,
        per_seed=per_seed,
        caveat=HARNESS_CAVEAT,
    )


def score_consistency(seeds: Sequence[int] = BUILD_DEVELOPMENT_SEEDS) -> ConsistencyReport:
    """Score `atlas-v1-consistency` on the same seeds and the same events.

    Training is one quiet hour. The test trace is the six-hour run. Jobs and attacks are the
    same thirty-second step, so magnitude does not separate `MIMIC` from maintenance. Windows
    are `windows_for_period(1)`, which is the frozen HAI window set.

    Args:
        seeds: Defaults to 97001-97020.

    Returns:
        Catches within the detector's own shift budget, and unexplained alerts per shift.
    """
    return _consistency(seeds, build_seed)


def score_held_back_consistency_once() -> ConsistencyReport:
    """The champion on 97101-97120's events. Called only by the declared command (ADR 0164)."""
    return _consistency(BUILD_HELD_BACK_SEEDS, build_held_back_seed)


def _consistency(seeds: Sequence[int], builder: Callable[[int], SeedBundle]) -> ConsistencyReport:
    """Score the champion on ``seeds``, each drawn by ``builder``."""
    if windows_for_period(SAMPLE_SECONDS) != FROZEN_WINDOWS:
        raise RuntimeError("one-second windows are no longer the frozen consistency windows")
    per_seed = tuple(_consistency_seed(seed, builder) for seed in seeds)
    attacks = sum(row.attack_effects for row in per_seed)
    caught = sum(row.attacks_caught for row in per_seed)
    caught_target = sum(row.attacks_caught_on_target for row in per_seed)
    alerts = sum(row.alerts for row in per_seed)
    unexplained = sum(row.unexplained_alerts for row in per_seed)
    shifts = sum(row.shifts for row in per_seed)
    return ConsistencyReport(
        detector=RESULT_NAME,
        seeds=tuple(seeds),
        attacks=attacks,
        attacks_caught=caught,
        attacks_caught_on_target=caught_target,
        catches_within_budget=_rate(caught, attacks, "attack-effect"),
        catches_on_target=_rate(caught_target, attacks, "attack-effect"),
        alerts=alerts,
        unexplained_alerts=unexplained,
        false_alerts_per_shift=(unexplained / shifts) if shifts else 0.0,
        shifts=shifts,
        per_seed=per_seed,
        caveat=HARNESS_CAVEAT,
    )


def _consistency_seed(
    seed: int, builder: Callable[[int], SeedBundle] = build_seed
) -> ConsistencySeed:
    """Fit and score one seed. Labels are applied after `detect` returns."""
    bundle = builder(seed)
    n_signals = len(ASSETS)
    features = [FEATURE_OF[asset] for asset in ASSETS]
    train_values = _quiet(_rng(seed, 3), TRAIN_SECONDS, n_signals)
    test_n = int(RUN.total_seconds())
    test_values = _quiet(_rng(seed, 5), test_n, n_signals)
    _inject(test_values, bundle, features)
    origin = RUN_START.timestamp()
    train = TrainFile(
        values=train_values,
        attack=numpy.zeros(TRAIN_SECONDS, dtype=numpy.bool_),
    )
    test = ScoredFile(
        time=origin + numpy.arange(test_n, dtype=numpy.float64),
        values=test_values,
    )
    windows = windows_for_period(SAMPLE_SECONDS)
    rows, columns, _scores = detect([train], [test], windows)[0]
    alert_times = [RUN_START + timedelta(seconds=int(row)) for row in rows]
    alert_features = [features[int(column)] for column in columns]
    attack_effects = [effect for effect in bundle.effects if effect.cause is Cause.ATTACK]
    maintenance_effects = [effect for effect in bundle.effects if effect.cause is Cause.MAINTENANCE]

    def _inside(when: datetime, effect: Effect) -> bool:
        return effect.start <= when < effect.end

    attack_alerts = 0
    maintenance_alerts = 0
    unexplained = 0
    for when in alert_times:
        if any(_inside(when, effect) for effect in attack_effects):
            attack_alerts += 1
        elif any(_inside(when, effect) for effect in maintenance_effects):
            maintenance_alerts += 1
        else:
            unexplained += 1

    caught = 0
    caught_target = 0
    for effect in attack_effects:
        hits = [index for index, when in enumerate(alert_times) if _inside(when, effect)]
        if hits:
            caught += 1
            if any(alert_features[index] == effect.feature for index in hits):
                caught_target += 1

    shifts = test_n / SHIFT_SECONDS
    return ConsistencySeed(
        seed=seed,
        detector=RESULT_NAME,
        attack_effects=len(attack_effects),
        attacks_caught=caught,
        attacks_caught_on_target=caught_target,
        alerts=len(rows),
        attack_alerts=attack_alerts,
        maintenance_alerts=maintenance_alerts,
        unexplained_alerts=unexplained,
        false_alerts_per_shift=(unexplained / shifts) if shifts else 0.0,
        shifts=shifts,
    )


def _quiet(rng: Generator, n: int, n_signals: int) -> _Float64:
    """A smooth shared rhythm plus a little noise. Spread is positive on every column."""
    t = numpy.arange(n, dtype=numpy.float64)
    shared = numpy.sin(2.0 * numpy.pi * t / 1800.0)
    values = numpy.zeros((n, n_signals), dtype=numpy.float64)
    for index in range(n_signals):
        wave = numpy.sin(2.0 * numpy.pi * t / (900.0 + 100.0 * index))
        noise = rng.normal(0.0, 0.05, size=n)
        values[:, index] = 10.0 + shared + 0.3 * wave + noise
    return values


def _inject(values: _Float64, bundle: SeedBundle, features: Sequence[str]) -> None:
    """Apply each effect once. Overlapping effects do not stack."""
    n = values.shape[0]
    bumped = numpy.zeros(values.shape, dtype=numpy.bool_)
    column_of = {feature: index for index, feature in enumerate(features)}
    for effect in bundle.effects:
        start_row = int((effect.start - RUN_START).total_seconds())
        end_row = int((effect.end - RUN_START).total_seconds())
        column = column_of[effect.feature]
        for row in range(max(0, start_row), min(n, end_row)):
            if not bumped[row, column]:
                values[row, column] += STEP
                bumped[row, column] = True


def synthetic_scorecard(
    closure: ClosureReport,
    consistency: ConsistencyReport,
    runtime_seconds: float,
) -> dict[str, object]:
    """Fill `SCORECARD` for this lane's synthetic runs.

    Cells this lane does not measure stay ``measured: false`` with a reason. No cell is a
    hypothesis confidence.

    Args:
        closure: The citation-closure report.
        consistency: The champion detector on the same seeds.
        runtime_seconds: Wall time for both measurements together.

    Returns:
        A dict whose keys are exactly `SCORECARD`, in that order.
    """
    not_this_lane = {"measured": False, "reason": "not this lane"}
    card: dict[str, object] = {
        "catches_within_budget": {
            "measured": True,
            "detector": consistency.detector,
            "value": consistency.catches_within_budget,
            "caught": consistency.attacks_caught,
            "attacks": consistency.attacks,
            "caught_on_target_signal": consistency.attacks_caught_on_target,
            "definition": (
                "Share of attack steps on the synthetic trace that contain a budgeted "
                f"{RESULT_NAME} alert. Maintenance and attacks use the same 30-second step."
            ),
        },
        "margin_over_best_simple_rival": {
            "measured": True,
            "value": closure.margin_over_best_simple_rival,
            "rival": closure.rival_name,
            "champion_attack_closure_rate": closure.attack_closed / closure.attack_alerts,
            "rival_attack_closure_rate": closure.rival_attack_closure_rate,
            "definition": (
                "Rival attack-closure rate minus the citation rule's attack-closure rate, "
                "on the same alerts. The rival closes on window overlap."
            ),
        },
        "margin_over_chance": {
            "measured": True,
            "value": closure.margin_over_chance,
            "chance_attack_closure_rate": closure.chance_attack_closure_rate,
            "chance_attack_closed": closure.chance_attack_closed,
            "definition": (
                "One permutation per seed moves citations between alerts and the same closer "
                "runs again. Margin is that null's attack-closure rate minus the real one's."
            ),
        },
        "falsified_sensor_passes": not_this_lane,
        "naming_right": not_this_lane,
        "naming_wrong": not_this_lane,
        "reconstruction_error": not_this_lane,
        "maintenance_closures": {
            "measured": True,
            "value": closure.maintenance_closure_rate,
            "closed": closure.maintenance_closed,
            "maintenance_alerts": closure.maintenance_alerts,
            "attack_closed": closure.attack_closed,
            "attack_alerts": closure.attack_alerts,
            "mimic_closed": closure.mimic_closed,
            "mimic_alerts": closure.mimic_alerts,
            "bar": closure.bar,
            "maintenance_bar_met": closure.maintenance_bar_met,
            "no_attack_closed": closure.no_attack_closed,
            "definition": (
                "Share of maintenance-caused alerts that closed with a cited sanctioning work "
                "order. The attack count includes MIMIC, and the in-window MIMIC."
            ),
        },
        "calibration": {
            "measured": False,
            "reason": "W5 is another lane. Hypothesis confidence is not computed or shown.",
        },
        "false_alerts_per_shift": {
            "measured": True,
            "value": consistency.false_alerts_per_shift,
            "unexplained_alerts": consistency.unexplained_alerts,
            "shifts": consistency.shifts,
            "detector": consistency.detector,
            "definition": (
                "Budgeted consistency alerts on the synthetic trace whose time falls in neither "
                "an attack step nor a maintenance step, divided by scored time "
                "over an 8-hour shift."
            ),
        },
        "runtime": {
            "measured": True,
            "value": runtime_seconds,
            "unit": "seconds",
            "definition": "Wall time to score closure and consistency on the seeds in this report.",
        },
    }
    if tuple(card) != SCORECARD:
        raise RuntimeError(f"scorecard keys {tuple(card)} are not {SCORECARD}")
    return card


def alert_count_phrase(count: int) -> str:
    """Return a count of attack alerts, singular when the count is one."""
    noun = "alert" if count == 1 else "alerts"
    return f"{count} attack {noun}"


def render_closure_markdown(closure: ClosureReport, consistency: ConsistencyReport) -> str:
    """Plain-English summary of one synthetic measurement. No confidence is printed."""
    lines = [
        "# Maintenance closure on seeds 97001-97020",
        "",
        HARNESS_CAVEAT,
        "",
        "## Closure",
        "",
        (
            f"Maintenance alerts closed with a cited work order: "
            f"{closure.maintenance_closed} of {closure.maintenance_alerts} "
            f"({closure.maintenance_closure_rate:.4f}). "
            f"The bar is {closure.bar:.0%}."
        ),
        (
            f"Attack alerts closed: {closure.attack_closed} of {closure.attack_alerts}. "
            f"MIMIC alerts closed: {closure.mimic_closed} of {closure.mimic_alerts}."
        ),
        (
            f"Maintenance bar met: {closure.maintenance_bar_met}. "
            f"No attack closed: {closure.no_attack_closed}."
        ),
        (
            f"Overlap rival `{closure.rival_name}` closed "
            f"{closure.rival_attack_closed} of {closure.attack_alerts} attack alerts "
            f"({closure.rival_attack_closure_rate:.4f}). "
            f"Margin over that rival, in attack-closure rate: "
            f"{closure.margin_over_best_simple_rival:.4f}."
        ),
        (
            f"Citation-permutation null closed "
            f"{alert_count_phrase(closure.chance_attack_closed)} "
            f"({closure.chance_attack_closure_rate:.4f}). "
            f"Margin over that chance: {closure.margin_over_chance:.4f}."
        ),
        "",
        "## atlas-v1-consistency on the same events",
        "",
        (
            f"Detector `{consistency.detector}`. "
            f"Attack steps with a budgeted alert: {consistency.attacks_caught} of "
            f"{consistency.attacks} ({consistency.catches_within_budget:.4f}). "
            f"Of those, {consistency.attacks_caught_on_target} were on the attacked signal."
        ),
        (
            f"Unexplained budgeted alerts: {consistency.unexplained_alerts} over "
            f"{consistency.shifts:.4f} shifts, "
            f"{consistency.false_alerts_per_shift:.4f} per shift."
        ),
        "",
        "A catch on this trace is a diagnosis. The step used for a job and the step used for an "
        "attack are the same size, so the detector is not being asked to tell them apart.",
        "",
    ]
    return "\n".join(lines)
