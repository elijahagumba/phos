"""Commands against physics on the synthetic plants (ADR 0160).

The question is whether a command-to-response fact separates a pair of explanations that neither
the command path nor the cross-signal path separates on its own. It is a diagnosis on plants this
repository builds. It is not a claim about a real factory, and it is not a re-score of HAI or
BATADAL.

**Three bundles, one story.** For a stuck actuator and for the same command with the actuator
free to follow:

- The command bundle is empty. The write comes from the plant's declared operator. An empty
  baseline must not be read as an unknown master, and this measurement does not retune the
  known-link matchers. Silence does not separate a pair.
- The physics bundle is `CROSS_SIGNAL_MISMATCH` from `atlas-v1-consistency`, fit on the quiet
  development seed and scored on the same run.
- The joint bundle is the physics facts plus `COMMAND_TO_RESPONSE_MISMATCH`.

A pair is separated when one evidence id supports one contentful explanation and contradicts the
other. A gained pair is separated by the joint bundle and by neither of the other two. A networked
plant passes when the stuck run gains at least one pair and the follow run emits no mismatch.
Batch has no control network, so it is recorded and not scored. A seed passes when every networked
plant passes.

The champion's alerts are counted on the same stuck run. They are the comparison. They are not
edited, and they are not the separation bar.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.command_response import (
    HORIZON_STEPS,
    declared_pairs,
    response_mismatches,
)
from phos.atlas.consistency import (
    RESULT_NAME,
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_evidence import (
    CROSS_SIGNAL_MISMATCH,
    consistency_feature_of,
    promote_consistency,
)
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.eval.build_declaration import BUILD_DEVELOPMENT_SEEDS, BUILD_HELD_BACK_SEEDS, SCORECARD
from phos.ontology import Domain, Entity, EntityType, Evidence, InMemoryEvidenceStore
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    FittedPlattCalibrator,
    ReasoningConfig,
    ReasoningEngine,
)
from phos.synth.command import PlannedCommandSource, PlannedWrite
from phos.synth.injection import HoldActuator, TimeWindow
from phos.synth.plant import CommandKind, PlantDescription, RunSpec
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION, TAP_POSITION, VOLTAGE_SETPOINT
from phos.synth.plants.water import INTAKE_SPEED, LEVEL_SETPOINT, WATER_DESCRIPTION
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "CHAMPION_RESULT_NAME",
    "GAINED_PAIR",
    "N_STEPS",
    "WRITE_AT",
    "PlantPhysics",
    "ScoredLoop",
    "SeedPhysics",
    "bar_met",
    "champion_train_seed",
    "gained_pairs",
    "score_seed",
    "score_split",
    "scorecard_numbers",
    "separated_pairs",
]

logger = logging.getLogger(__name__)

CHAMPION_RESULT_NAME: Final = RESULT_NAME
"""The frozen consistency detector these runs are scored against. Its code is not retuned."""

N_STEPS: Final = 40
"""Samples in every run. Short enough to score, long enough for the horizon."""

WRITE_AT: Final = 8
"""Sample at which the declared operator writes. The horizon then fits inside the run."""

GAINED_PAIR: Final = (ENGINEERING_MAINTENANCE_TEMPLATE_ID, SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID)
"""Maintenance finished nothing; the device did not answer. That is the pair to separate."""

_START: Final = datetime(2026, 10, 1, tzinfo=UTC)
_CONTENTFUL: Final = (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
_WEIGHT: Final = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
"""A constant one half. Separation reads evidence lists, not this weight, and it is not surfaced."""

_A3_BLOCK: Final = (
    "HAI and BATADAL are validation corpora and gate look 1 is spent (ADR 0143). "
    "They were not opened. A3 is not re-scored here."
)


@dataclass(frozen=True)
class ScoredLoop:
    """The one declared loop a networked plant is scored on.

    Attributes:
        plant_id: Which synthetic plant.
        sample_seconds: The run's sample interval.
        command: The setpoint the operator writes.
        write_value: The engineering value written, inside the signal's span.
        actuator: The coupling's driven signal, the one a stuck run holds.
    """

    plant_id: str
    sample_seconds: int
    command: str
    write_value: float
    actuator: str


SCORED_LOOPS: Final[tuple[ScoredLoop, ...]] = (
    ScoredLoop("water-treatment", 30, LEVEL_SETPOINT, 4.8, INTAKE_SPEED),
    ScoredLoop("power-generation", 10, VOLTAGE_SETPOINT, 12.5, TAP_POSITION),
)
"""Water's level loop and power's tap changer. The fuel valve is declared and not scored.

A dispatch step does not move that valve by 5% of its span inside the horizon. Scoring it would
call a slow governor a failed actuator. The tap changer does move, and that is the power loop.
"""


@dataclass(frozen=True)
class PlantPhysics:
    """One plant on one seed: the three bundles, the champion's alerts, and the follow run."""

    plant_id: str
    skipped: bool
    skip_reason: str
    follow_mismatch_count: int
    stuck_mismatch_count: int
    follow_travel: float | None
    stuck_travel: float | None
    gained_pairs: tuple[tuple[str, str], ...]
    command_pairs: tuple[tuple[str, str], ...]
    physics_pairs: tuple[tuple[str, str], ...]
    joint_pairs: tuple[tuple[str, str], ...]
    champion_alert_rows: tuple[int, ...]
    champion_alert_in_window: bool | None
    champion_follow_alert_rows: tuple[int, ...]
    champion_follow_alert_in_window: bool | None
    false_alerts_per_shift: float | None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "plant_id": self.plant_id,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "follow_mismatch_count": self.follow_mismatch_count,
            "stuck_mismatch_count": self.stuck_mismatch_count,
            "follow_travel": self.follow_travel,
            "stuck_travel": self.stuck_travel,
            "gained_pairs": [list(pair) for pair in self.gained_pairs],
            "command_pairs": [list(pair) for pair in self.command_pairs],
            "physics_pairs": [list(pair) for pair in self.physics_pairs],
            "joint_pairs": [list(pair) for pair in self.joint_pairs],
            "champion_alert_rows": list(self.champion_alert_rows),
            "champion_alert_in_window": self.champion_alert_in_window,
            "champion_follow_alert_rows": list(self.champion_follow_alert_rows),
            "champion_follow_alert_in_window": self.champion_follow_alert_in_window,
            "false_alerts_per_shift": self.false_alerts_per_shift,
            "champion_result_name": CHAMPION_RESULT_NAME,
        }


@dataclass(frozen=True)
class SeedPhysics:
    """Every plant on one seed, and whether the separation bar passed for that seed."""

    seed: int
    split: str
    plants: tuple[PlantPhysics, ...]
    passed: bool

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "seed": self.seed,
            "split": self.split,
            "passed": self.passed,
            "plants": [plant.as_dict() for plant in self.plants],
        }


def champion_train_seed() -> int:
    """Return the only seed the champion is fit on: the first development seed.

    A held-back score still trains here. A held-back seed is never a training seed.
    """
    return BUILD_DEVELOPMENT_SEEDS[0]


def separated_pairs(
    evidence: Sequence[Evidence], entities: Sequence[Entity]
) -> tuple[tuple[str, str], ...]:
    """Return contentful explanation pairs one evidence id supports and another contradicts.

    ``insufficient_evidence`` is not a member of any pair. The rank order is not consulted:
    separation is a fact about the evidence lists, not about which template sorts first.

    Args:
        evidence: Facts to weigh, in order.
        entities: Entities those facts may name. Patterns here do not constrain type; the store
            still holds them so a later constraint would resolve rather than guess.

    Returns:
        Pairs of template ids, sorted, each pair sorted internally.
    """
    store = InMemoryEvidenceStore()
    for entity in entities:
        store.add_entity(entity)
    engine = ReasoningEngine(
        atlas_library(),
        store,
        ReasoningConfig(correlation_window=timedelta(hours=2)),
    )
    if evidence:
        engine.ingest(evidence)
    support: dict[str, set[str]] = {template_id: set() for template_id in _CONTENTFUL}
    contradict: dict[str, set[str]] = {template_id: set() for template_id in _CONTENTFUL}
    for hypothesis in engine.hypotheses(Domain.ATLAS):
        if hypothesis.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
            continue
        if hypothesis.template_id not in support:
            continue
        support[hypothesis.template_id].update(hypothesis.supporting)
        contradict[hypothesis.template_id].update(hypothesis.contradictory)
    found: list[tuple[str, str]] = []
    ordered = tuple(sorted(_CONTENTFUL))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            shared = (support[left] & contradict[right]) or (support[right] & contradict[left])
            if shared:
                found.append((left, right))
    return tuple(found)


def gained_pairs(
    command: Sequence[Evidence],
    physics: Sequence[Evidence],
    joint: Sequence[Evidence],
    entities: Sequence[Entity],
) -> tuple[tuple[str, str], ...]:
    """Return pairs the joint bundle separates and neither path separates alone."""
    alone = set(separated_pairs(command, entities)) | set(separated_pairs(physics, entities))
    return tuple(pair for pair in separated_pairs(joint, entities) if pair not in alone)


def score_seed(seed: int, *, split: str) -> SeedPhysics:
    """Score one seed on the named split. A seed from the other split is refused.

    Args:
        seed: A build seed. Development is 97001-97020. Held-back is 97101-97120.
        split: ``"development"`` or ``"held-back"``.

    Returns:
        The seed's plants and whether every networked plant gained a pair with a clean follow run.

    Raises:
        ValueError: If ``seed`` is not in ``split``, or ``split`` is not one of those two names.
    """
    _require_seed(seed, split)
    plants = (*(_score_loop(loop, seed) for loop in SCORED_LOOPS), _skipped_batch())
    return SeedPhysics(seed=seed, split=split, plants=plants, passed=_passed(plants))


def score_split(split: str) -> tuple[SeedPhysics, ...]:
    """Score every seed of ``split``, in order.

    Raises:
        ValueError: If ``split`` is not ``"development"`` or ``"held-back"``.
    """
    return tuple(score_seed(seed, split=split) for seed in _seeds(split))


def bar_met(results: Sequence[SeedPhysics]) -> bool:
    """Return whether a majority of the seeds passed.

    Majority is strict: more than half. For the declared twenty seeds that is at least eleven.
    An empty result has not met the bar.
    """
    if not results:
        return False
    passed = sum(1 for item in results if item.passed)
    return passed * 2 > len(results)


def scorecard_numbers(results: Sequence[SeedPhysics]) -> dict[str, float | None]:
    """Fill the scorecard keys this measurement owns. The rest stay ``None``.

    ``catches_within_budget`` is the fraction of stuck networked runs whose champion alert falls
    in the command window. It is the comparison with `atlas-v1-consistency`, not the separation
    bar, and it is not by itself a catch: the same count on the follow run is
    ``champion_follow_alerts_in_window``. ``false_alerts_per_shift`` is the mean, over those runs,
    of command-to-response mismatches on the follow run, scaled to an eight-hour shift. Unmeasured
    keys stay ``None`` rather than a zero that would read as a result.
    """
    scored = [plant for item in results for plant in item.plants if not plant.skipped]
    catches: float | None = None
    false_alerts: float | None = None
    if scored:
        hits = sum(1 for plant in scored if plant.champion_alert_in_window)
        catches = hits / len(scored)
        false_alerts = sum(
            0.0 if plant.false_alerts_per_shift is None else plant.false_alerts_per_shift
            for plant in scored
        ) / len(scored)
    numbers: dict[str, float | None] = dict.fromkeys(SCORECARD)
    numbers["catches_within_budget"] = catches
    numbers["false_alerts_per_shift"] = false_alerts
    return numbers


def diagnosis(results: Sequence[SeedPhysics]) -> dict[str, object]:
    """Return the separation counts and the reason A3 was not scored."""
    return {
        "a3_scored": False,
        "a3_block": _A3_BLOCK,
        "a4_seeds_passed": sum(1 for item in results if item.passed),
        "a4_seeds_scored": len(results),
        "a4_bar_met": bar_met(results),
        "gained_pair": list(GAINED_PAIR),
        "champion_result_name": CHAMPION_RESULT_NAME,
        "champion_train_seed": champion_train_seed(),
        "champion_follow_alerts_in_window": _follow_alert_rate(results),
    }


def _follow_alert_rate(results: Sequence[SeedPhysics]) -> float | None:
    """Share of networked follow runs with a champion alert inside the command window."""
    scored = [plant for item in results for plant in item.plants if not plant.skipped]
    if not scored:
        return None
    hits = sum(1 for plant in scored if plant.champion_follow_alert_in_window)
    return hits / len(scored)


def _passed(plants: Sequence[PlantPhysics]) -> bool:
    """A seed passes when every networked plant gains a pair and its follow run is clean."""
    scored = [plant for plant in plants if not plant.skipped]
    if not scored:
        return False
    return all(plant.gained_pairs and plant.follow_mismatch_count == 0 for plant in scored)


def _score_loop(loop: ScoredLoop, seed: int) -> PlantPhysics:
    """Run one declared loop: quiet train, follow, stuck, then the three bundles."""
    description = _description(loop.plant_id)
    train = run_plant(loop.plant_id, _spec(champion_train_seed(), loop.sample_seconds))
    follow = run_plant(
        loop.plant_id,
        _spec(seed, loop.sample_seconds),
        commands=_source(description, loop),
    )
    held = follow.steps[WRITE_AT - 1].report.values[loop.actuator]
    stuck = run_plant(
        loop.plant_id,
        _spec(seed, loop.sample_seconds),
        injection=HoldActuator(
            actuator=loop.actuator,
            value=held,
            window=TimeWindow(
                start=_spec(seed, loop.sample_seconds).instant(WRITE_AT),
                end=_spec(seed, loop.sample_seconds).instant(N_STEPS),
            ),
        ),
        commands=_source(description, loop),
    )
    entities = _entities(description)
    entity_of = {entity.name: entity.id for entity in entities}
    follow_facts = _mismatches(description, follow, entity_of, train)
    stuck_facts = _mismatches(description, stuck, entity_of, train)
    physics = _physics(description, train, stuck, entity_of)
    joint = physics + stuck_facts
    command: tuple[Evidence, ...] = ()
    gained = gained_pairs(command, physics, joint, entities)
    rows = _champion_rows(train, stuck, loop.sample_seconds)
    follow_rows = _champion_rows(train, follow, loop.sample_seconds)
    in_window = any(WRITE_AT <= row < WRITE_AT + HORIZON_STEPS for row in rows)
    follow_in_window = any(WRITE_AT <= row < WRITE_AT + HORIZON_STEPS for row in follow_rows)
    hours = N_STEPS * loop.sample_seconds / 3600.0
    return PlantPhysics(
        plant_id=loop.plant_id,
        skipped=False,
        skip_reason="",
        follow_mismatch_count=len(follow_facts),
        stuck_mismatch_count=len(stuck_facts),
        follow_travel=_travel(follow, loop.actuator),
        stuck_travel=_travel(stuck, loop.actuator),
        gained_pairs=gained,
        command_pairs=separated_pairs(command, entities),
        physics_pairs=separated_pairs(physics, entities),
        joint_pairs=separated_pairs(joint, entities),
        champion_alert_rows=tuple(rows),
        champion_alert_in_window=in_window,
        champion_follow_alert_rows=tuple(follow_rows),
        champion_follow_alert_in_window=follow_in_window,
        false_alerts_per_shift=len(follow_facts) / hours * 8.0,
    )


def _skipped_batch() -> PlantPhysics:
    """Batch has telemetry and no wire. There is no command to put against the physics."""
    return PlantPhysics(
        plant_id=BATCH_DESCRIPTION.plant_id,
        skipped=True,
        skip_reason=(
            "batch-reactor declares no control network, so there is no wire command to put "
            "against the physics"
        ),
        follow_mismatch_count=0,
        stuck_mismatch_count=0,
        follow_travel=None,
        stuck_travel=None,
        gained_pairs=(),
        command_pairs=(),
        physics_pairs=(),
        joint_pairs=(),
        champion_alert_rows=(),
        champion_alert_in_window=None,
        champion_follow_alert_rows=(),
        champion_follow_alert_in_window=None,
        false_alerts_per_shift=None,
    )


def _description(plant_id: str) -> PlantDescription:
    """Return the declaration for a scored plant."""
    descriptions = {
        WATER_DESCRIPTION.plant_id: WATER_DESCRIPTION,
        POWER_DESCRIPTION.plant_id: POWER_DESCRIPTION,
    }
    try:
        return descriptions[plant_id]
    except KeyError as exc:
        raise KeyError(f"no scored plant {plant_id!r}") from exc


def _spec(seed: int, sample_seconds: int) -> RunSpec:
    """A run of `N_STEPS` samples from a fixed start."""
    interval = timedelta(seconds=sample_seconds)
    return RunSpec(
        seed=seed,
        start=_START,
        duration=interval * N_STEPS,
        sample_interval=interval,
    )


def _source(description: PlantDescription, loop: ScoredLoop) -> PlannedCommandSource:
    """One write from the plant's declared operator. Not an unknown master."""
    network = description.control_network
    if network is None:
        raise ValueError(f"plant {description.plant_id!r} has no control network")
    write = PlannedWrite(
        issuer=network.operator,
        signal=loop.command,
        value=loop.write_value,
        reason="lane-d command against physics",
    )
    return PlannedCommandSource({WRITE_AT: (write,)})


def _entities(description: PlantDescription) -> tuple[Entity, ...]:
    """One PLC entity per declared signal, id stable for the plant and the signal."""
    return tuple(
        Entity(
            id=f"ent_{description.plant_id}_{spec.key}",
            type=EntityType.PLC,
            domain=Domain.ATLAS,
            name=spec.key,
        )
        for spec in description.signals
    )


def _mismatches(
    description: PlantDescription,
    run: PlantRun,
    entity_of: Mapping[str, str],
    train: PlantRun,
) -> tuple[Evidence, ...]:
    """Command-to-response facts for the writes on ``run``'s wire."""
    reported = {spec.key: run.reported(spec.key) for spec in description.signals}
    bundle = response_mismatches(
        pairs=declared_pairs(description),
        signals={spec.key: spec for spec in description.signals},
        reported=reported,
        writes=_wire_writes(run),
        timestamps=[step.timestamp for step in run.steps],
        entity_of=entity_of,
        calibrator=_WEIGHT,
        learned_from_window=(train.steps[0].timestamp, train.steps[-1].timestamp),
    )
    return tuple(fact.evidence for fact in bundle.facts)


def _wire_writes(run: PlantRun) -> tuple[tuple[int, str], ...]:
    """Decode write intents through the declared register map. Reads are not writes."""
    network = run.description.control_network
    if network is None:
        return ()
    by_address: dict[tuple[str, int], str] = {}
    for block in network.blocks:
        for offset, signal in enumerate(block.signals):
            by_address[(block.node_id, block.start_address + offset)] = signal
    found: list[tuple[int, str]] = []
    for step in run.steps:
        for intent in step.commands:
            if intent.kind is not CommandKind.WRITE:
                continue
            for offset in range(intent.quantity):
                decoded = by_address.get((intent.target, intent.address + offset))
                if decoded is not None:
                    found.append((step.index, decoded))
    return tuple(found)


def _physics(
    description: PlantDescription,
    train: PlantRun,
    stuck: PlantRun,
    entity_of: Mapping[str, str],
) -> tuple[Evidence, ...]:
    """Cross-signal facts from the champion on the stuck run. Not command-to-response."""
    model = fit(
        [
            TrainFile(
                values=_matrix(train),
                attack=numpy.zeros(len(train.steps), dtype=numpy.bool_),
            )
        ],
        windows_for_period(train.spec.interval_seconds),
    )
    bundle = promote_consistency(
        model,
        _matrix(stuck),
        [step.timestamp for step in stuck.steps],
        [spec.key for spec in description.signals],
        entity_of,
        _WEIGHT,
        (train.steps[0].timestamp, train.steps[-1].timestamp),
    )
    return tuple(
        fact.evidence
        for fact in bundle.facts
        if consistency_feature_of(fact.evidence) == CROSS_SIGNAL_MISMATCH
    )


def _champion_rows(train: PlantRun, stuck: PlantRun, sample_seconds: int) -> list[int]:
    """Budgeted alert rows from `atlas-v1-consistency` on the stuck run."""
    windows = windows_for_period(float(sample_seconds))
    model = fit(
        [
            TrainFile(
                values=_matrix(train),
                attack=numpy.zeros(len(train.steps), dtype=numpy.bool_),
            )
        ],
        windows,
    )
    time = numpy.array([step.timestamp.timestamp() for step in stuck.steps], dtype=numpy.float64)
    rows, _columns, _scores = budget_alerts(
        events(feature_scores(model, _matrix(stuck)), windows=model.windows),
        time,
        model.windows,
    )
    return rows


def _matrix(run: PlantRun) -> NDArray[numpy.float64]:
    """Reported values, rows by samples and columns in declaration order."""
    keys = [spec.key for spec in run.description.signals]
    rows = [[step.report.values[key] for key in keys] for step in run.steps]
    return numpy.asarray(rows, dtype=numpy.float64)


def _travel(run: PlantRun, actuator: str) -> float:
    """Actuator travel from the write sample to the horizon sample."""
    series = run.reported(actuator)
    return abs(series[WRITE_AT + HORIZON_STEPS] - series[WRITE_AT])


def _seeds(split: str) -> tuple[int, ...]:
    """The seeds a split may score."""
    if split == "development":
        return BUILD_DEVELOPMENT_SEEDS
    if split == "held-back":
        return BUILD_HELD_BACK_SEEDS
    raise ValueError(f"split must be 'development' or 'held-back', got {split!r}")


def _require_seed(seed: int, split: str) -> None:
    """Refuse a seed that is not in the named split, before any plant is built."""
    allowed = _seeds(split)
    if seed not in allowed:
        raise ValueError(
            f"seed {seed} is not in the {split} split; this measurement does not open it"
        )
