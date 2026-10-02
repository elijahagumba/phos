"""The twelve U3 diagnostic scenarios as seeded, constructible configurations.

Each scenario is a plant, a seed, a realism profile, a command source, and a capture/maintenance
choice. Ground truth is declared here. Atlas never reads this module: the generator still does not
import a detector, and scenario ground truth never becomes an engine input.

**The batch reactor cannot host command, communication-failure, unauthorised-command or attacker
scenarios.** It declares no control network. Those kinds refuse it rather than inventing a bus.

**Attacker-during-maintenance is built by giving the adversary an independently planned calendar**
and letting it pick a sanctioned window. The calendar is never moved to cover the attack.

SYNTHETIC-DERIVED. Not a detection claim. Not a row in ``eval_runs/log.jsonl``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Final

import numpy

from phos.synth.catalogue_scenarios import scenarios_for
from phos.synth.command import CommandSource, NoCommands, PlannedCommandSource, PlannedWrite
from phos.synth.maintenance import (
    MaintenanceCalendar,
    MaintenancePractice,
    WorkOrder,
    plan_maintenance,
)
from phos.synth.plant import SYNTHETIC_DERIVED, RunSpec
from phos.synth.plants.water import LEVEL_SETPOINT
from phos.synth.realism import RealismProfile
from phos.synth.run import PlantRun, build_plant, run_plant
from phos.synth.scenarios import GoalSeekingSource

__all__ = [
    "COMMAND_PLANTS",
    "HOSTS",
    "NO_NETWORK_REFUSAL",
    "DiagnosticKind",
    "DiagnosticScenario",
    "construct",
    "kinds",
    "run_scenario",
]

NO_NETWORK_REFUSAL: Final = (
    "batch-reactor declares no control network; inventing one would be fiction (ADR 0015)"
)
COMMAND_PLANTS: Final = ("water-treatment", "power-generation")
HOSTS: Final = ("water-treatment", "power-generation", "batch-reactor")
_START: Final = datetime(2026, 3, 1, tzinfo=UTC)
_ASSETS: Final = ("intake", "dosing", "filtration", "clearwell", "distribution")


class DiagnosticKind(str, Enum):
    """The twelve Gate-1 scenarios. Names are the plan's names, underscored."""

    ORDINARY_OPERATION = "ordinary_operation"
    MAINTENANCE = "maintenance"
    STARTUP_AND_SHUTDOWN = "startup_and_shutdown"
    PROCESS_DISTURBANCES = "process_disturbances"
    SENSOR_FAILURES = "sensor_failures"
    COMMUNICATION_FAILURES = "communication_failures"
    LEGITIMATE_OPERATOR = "legitimate_operator_interventions"
    UNAUTHORISED_COMMANDS = "unauthorised_commands"
    ATTACKER_ACTIVITY = "attacker_activity"
    ATTACKER_DURING_MAINTENANCE = "attacker_activity_during_a_genuine_maintenance_window"
    CONFLICTING_OBSERVATIONS = "conflicting_observations"
    INCOMPLETE_OBSERVATIONS = "deliberately_incomplete_observations"


@dataclass(frozen=True)
class DiagnosticScenario:
    """One seeded configuration, with ground truth declared where Atlas cannot see it.

    Attributes:
        kind: Which of the twelve.
        plant_id: Host plant.
        spec: The run.
        realism: Ordinary trouble. Quiet unless the kind is the trouble.
        commands: Who writes, or ``None`` for the plant's default echo path.
        with_capture: Whether a capture should be written. Incomplete observations set this false.
        calendar: An independently planned maintenance register, or ``None``.
        ground_truth: Declarative statements about what is true. Never an Atlas input.
        label: Always SYNTHETIC-DERIVED.
        refused_on: Plants that cannot host this kind, with the reason.
    """

    kind: DiagnosticKind
    plant_id: str
    spec: RunSpec
    realism: RealismProfile
    commands: CommandSource | None
    with_capture: bool
    calendar: MaintenanceCalendar | None
    ground_truth: tuple[str, ...]
    label: str = SYNTHETIC_DERIVED
    refused_on: tuple[str, ...] = ()


def kinds() -> tuple[DiagnosticKind, ...]:
    """Return the twelve kinds in plan order."""
    return tuple(DiagnosticKind)


def _spec(seed: int, hours: float = 2.0, interval: float = 30.0) -> RunSpec:
    """Return a short seeded run. Fit-history for Atlas is enforced elsewhere, not here."""
    return RunSpec(
        seed=seed,
        start=_START,
        duration=timedelta(hours=hours),
        sample_interval=timedelta(seconds=interval),
    )


def _needs_network(kind: DiagnosticKind) -> bool:
    """Return whether the kind is meaningless on a plant with no control network."""
    return kind in {
        DiagnosticKind.COMMUNICATION_FAILURES,
        DiagnosticKind.LEGITIMATE_OPERATOR,
        DiagnosticKind.UNAUTHORISED_COMMANDS,
        DiagnosticKind.ATTACKER_ACTIVITY,
        DiagnosticKind.ATTACKER_DURING_MAINTENANCE,
    }


def _water_operator(issuer: str, reason: str, spec: RunSpec) -> PlannedCommandSource:
    """Return one setpoint write halfway through the run."""
    step = spec.n_steps // 2
    return PlannedCommandSource(
        {step: (PlannedWrite(issuer=issuer, signal=LEVEL_SETPOINT, value=3.6, reason=reason),)}
    )


def _span(plant_id: str, spec: RunSpec, signal: str) -> tuple[float, float]:
    """Return ``(low, high)`` for ``signal`` from the plant's declaration."""
    declared = build_plant(plant_id, spec).description.signal(signal)
    return declared.low, declared.high


def _attacker(plant_id: str, spec: RunSpec) -> CommandSource:
    """Return the impatient catalogue adversary for ``plant_id``, trimmed to the run."""
    available = scenarios_for(plant_id)
    if not available:
        return NoCommands()
    chosen = next(
        (item for item in available if item.scenario_id.endswith("impatient")),
        available[0],
    )
    low, high = _span(plant_id, spec, chosen.goal.signal)
    first = min(chosen.first_step, max(spec.n_steps - 2, 0))
    shifted = chosen.model_copy(update={"first_step": first})
    return GoalSeekingSource(shifted, low=low, high=high)


def _calendar(spec: RunSpec, seed: int) -> MaintenanceCalendar:
    """Plan maintenance independently of any adversary."""
    return plan_maintenance(
        numpy.random.default_rng(seed),
        spec,
        _ASSETS,
        MaintenancePractice(routine_interval=timedelta(hours=4), reactive_per_year=800.0),
    )


def _first_step_inside(spec: RunSpec, order: WorkOrder) -> int | None:
    """Return the first sample at or after ``order.start`` that still sits inside the window."""
    elapsed = (order.start - spec.start) / spec.sample_interval
    first = max(math.ceil(elapsed), 0)
    if first >= spec.n_steps:
        return None
    instant = spec.start + first * spec.sample_interval
    if not (order.start <= instant <= order.end):
        return None
    return first


def _adversary_picks_a_window(
    plant_id: str, spec: RunSpec, calendar: MaintenanceCalendar
) -> CommandSource:
    """Give the adversary the calendar; it chooses a sanctioned window. Calendar is not moved."""
    available = scenarios_for(plant_id)
    if not available:
        return NoCommands()
    chosen = next(
        (item for item in available if item.scenario_id.endswith("impatient")),
        available[0],
    )
    low, high = _span(plant_id, spec, chosen.goal.signal)
    for order in calendar.sanctioning():
        if order.asset_id != chosen.asset_id:
            continue
        first = _first_step_inside(spec, order)
        if first is None:
            continue
        shifted = chosen.model_copy(update={"first_step": first})
        return GoalSeekingSource(shifted, low=low, high=high)
    return NoCommands()


def construct(
    kind: DiagnosticKind, seed: int, plant_id: str = "water-treatment"
) -> DiagnosticScenario:
    """Build one seeded scenario. Refuses a plant that cannot host the kind.

    Raises:
        ValueError: If ``plant_id`` cannot host ``kind``. The message is the recorded refusal.
    """
    if _needs_network(kind) and plant_id == "batch-reactor":
        raise ValueError(NO_NETWORK_REFUSAL)

    spec = _spec(seed)
    quiet = RealismProfile()
    refused = (NO_NETWORK_REFUSAL,) if _needs_network(kind) else ()

    if kind is DiagnosticKind.ORDINARY_OPERATION:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            quiet,
            NoCommands(),
            True,
            None,
            ("ordinary operation: quiet profile, no commanded writes",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.MAINTENANCE:
        calendar = _calendar(spec, seed)
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            quiet,
            NoCommands(),
            True,
            calendar,
            (
                "maintenance register planned without seeing any adversary",
                f"orders={len(calendar.orders)}",
            ),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.STARTUP_AND_SHUTDOWN:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(startup_transitions=1),
            None,
            True,
            None,
            ("startup or shutdown transition placed by the realism planner",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.PROCESS_DISTURBANCES:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(grade_changes=1),
            None,
            True,
            None,
            ("grade change plus the plant's own BenignEvent schedule",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.SENSOR_FAILURES:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(sensor_faults=2),
            None,
            True,
            None,
            ("instrument faults applied as the instrument's own reading",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.COMMUNICATION_FAILURES:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(comms_dropouts=1),
            None,
            True,
            None,
            ("comms dropouts planned; generate.py hands them to the capture",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.LEGITIMATE_OPERATOR:
        source: CommandSource = (
            _water_operator("hmi", "operator accepted a new clearwell target", spec)
            if plant_id == "water-treatment"
            else NoCommands()
        )
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(operator_interventions=1),
            source,
            True,
            None,
            ("authorised HMI write plus an operator-intervention phenomenon",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.UNAUTHORISED_COMMANDS:
        source = (
            _water_operator("scada", "scada is not granted this setpoint", spec)
            if plant_id == "water-treatment"
            else NoCommands()
        )
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            quiet,
            source,
            True,
            None,
            ("scada writing a setpoint granted only to hmi: unauthorised, known station",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.ATTACKER_ACTIVITY:
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            quiet,
            _attacker(plant_id, spec),
            True,
            None,
            ("catalogue adversary; provenance is the catalogue's, not a detection claim",),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.ATTACKER_DURING_MAINTENANCE:
        calendar = _calendar(spec, seed)
        source = _adversary_picks_a_window(plant_id, spec, calendar)
        overlap = not isinstance(source, NoCommands)
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            quiet,
            source,
            True,
            calendar,
            (
                "adversary was given the calendar and chose a sanctioned window",
                "calendar was not moved to cover the attack",
                f"overlap_on_this_seed={overlap}",
            ),
            SYNTHETIC_DERIVED,
            refused,
        )
    if kind is DiagnosticKind.CONFLICTING_OBSERVATIONS:
        source = (
            _water_operator("hmi", "genuine operator move", spec)
            if plant_id == "water-treatment"
            else NoCommands()
        )
        return DiagnosticScenario(
            kind,
            plant_id,
            spec,
            RealismProfile(sensor_faults=1),
            source,
            True,
            None,
            (
                "two true stories at once: an instrument fault AND a genuine authorised write",
                "Atlas is not told which is which",
            ),
            SYNTHETIC_DERIVED,
            refused,
        )
    return DiagnosticScenario(
        kind,
        plant_id,
        spec,
        quiet,
        NoCommands(),
        False,
        None,
        ("capture withheld; telemetry-only is one lever of incomplete observations",),
        SYNTHETIC_DERIVED,
        refused,
    )


def run_scenario(scenario: DiagnosticScenario) -> PlantRun:
    """Simulate the scenario. Capture writing is the caller's job; this returns the run."""
    return run_plant(
        scenario.plant_id,
        scenario.spec,
        commands=scenario.commands,
        realism=scenario.realism,
    )
