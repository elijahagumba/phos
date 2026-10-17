"""OT packs: combinatorial D2 attacks on the three simulated plants, honestly labelled as ours.

Each pack is an `AttackDatasetConfig` the existing generator can write. Hundreds of labelled
windows come from crossing plant x seed x subtlety x attack kind, packed so windows do not
overlap. Benign operational events (backwash, intake stop, recipe change) are scheduled by the
plant itself, so every pack already interleaves maintenance with the manipulations — that is
the "maintenance window" condition, not a second simulator.

Payloads are regenerated into ``dataset library/OT/generated/`` and are not committed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from phos.library.caveats import SYNTHETIC_LIBRARY_CAVEATS
from phos.synth.attacks.battery import AttackDatasetConfig
from phos.synth.attacks.generate import generate_attack_dataset
from phos.synth.attacks.spec import AttackPlan, AttackType
from phos.synth.catalogue import DatasetConfig
from phos.synth.generate import generate_dataset

__all__ = [
    "LIBRARY_DIRNAME",
    "PROCESS_GAP_HOURS",
    "SAMPLE_INTERVAL_SECONDS",
    "SEEDS",
    "SUBTLETIES",
    "generate_ot_library",
    "lay_out",
    "liar_recipe",
    "ot_catalogue_payload",
    "ot_packs",
    "ot_scenario_count",
    "ot_trains",
    "pack_start",
    "write_ot_catalogue",
]

logger = logging.getLogger(__name__)

LIBRARY_DIRNAME: Final = "dataset library"
SAMPLE_INTERVAL_SECONDS: Final = 30.0
SEEDS: Final = (71001, 71002, 71003)
SUBTLETIES: Final = (0.0, 0.2, 0.4, 0.6, 0.8, 0.9)
_START: Final = datetime(2026, 6, 1, tzinfo=UTC)
_PREFIX_HOURS: Final = 4.0
_PROCESS_GAP_HOURS: Final = 1.25
_COMMAND_GAP_HOURS: Final = 3.0
_TAIL_HOURS: Final = 2.0
_TRAIN_HOURS: Final = 48.0
_TRAIN_SEEDS: Final = {
    "water-treatment": 80001,
    "power-generation": 80002,
    "batch-reactor": 80003,
}
_NUDGE_HOURS: Final = 2.0
_MAX_NUDGES: Final = 12
_COMMAND_TYPES: Final = frozenset(
    {AttackType.MIMIC, AttackType.ROGUE_COMMAND, AttackType.MIMIC_COMMAND}
)


@dataclass(frozen=True)
class AttackRecipe:
    """One attack kind a plant can host, before it is placed on the dial or the clock."""

    attack_type: AttackType
    target: str
    duration_hours: float
    reference: str = ""
    issuer: str = ""
    mimics: str = ""
    note: str = ""

    def to_plan(self, attack_id: str, subtlety: float, start_hours: float) -> AttackPlan:
        """Return a concrete plan at ``subtlety``, opening ``start_hours`` into the run."""
        return AttackPlan(
            attack_id=attack_id,
            type=self.attack_type,
            subtlety=subtlety,
            start_hours=start_hours,
            duration_hours=self.duration_hours,
            target=self.target,
            reference=self.reference,
            issuer=self.issuer,
            mimics=self.mimics,
            note=self.note,
        )


_WATER_PROCESS: Final = (
    AttackRecipe(
        AttackType.BLATANT, "intake_pump_speed_pct", 1.5, note="Intake pump driven off loop."
    ),
    AttackRecipe(
        AttackType.STEALTH_DRIFT, "chlorine_dose_mgpl", 6.0, note="Chlorine dose walked away."
    ),
    AttackRecipe(
        AttackType.CORRELATION_BREAK,
        "raw_inflow_m3ph",
        2.5,
        reference="intake_pump_speed_pct",
        note="Inflow no longer follows pump speed.",
    ),
    AttackRecipe(
        AttackType.LIAR,
        "clearwell_level_m",
        3.0,
        reference="clearwell_level_setpoint_m",
        note="Level reported short so the loop overfills.",
    ),
)
_WATER_COMMAND: Final = (
    AttackRecipe(
        AttackType.MIMIC,
        "clearwell_level_setpoint_m",
        2.5,
        mimics="level_setpoint_change",
        note="Setpoint moved with no write on the wire.",
    ),
    AttackRecipe(
        AttackType.ROGUE_COMMAND,
        "distribution_pressure_setpoint_bar",
        1.5,
        issuer="scada",
        note="Write from the polling-only SCADA node (known graph station, not an unknown master).",
    ),
    AttackRecipe(
        AttackType.MIMIC_COMMAND,
        "chlorine_residual_setpoint_mgpl",
        1.5,
        issuer="hmi",
        mimics="residual_setpoint_change",
        note="Plausible HMI write matching no scheduled operation.",
    ),
)
_POWER_PROCESS: Final = (
    AttackRecipe(
        AttackType.BLATANT, "fuel_valve_pct", 1.5, note="Fuel valve driven off the governor."
    ),
    AttackRecipe(AttackType.STEALTH_DRIFT, "excitation_pct", 6.0, note="Excitation walked away."),
    AttackRecipe(
        AttackType.CORRELATION_BREAK,
        "bus_frequency_hz",
        2.5,
        reference="turbine_speed_rpm",
        note="Frequency no longer shaft speed over sixty.",
    ),
    AttackRecipe(
        AttackType.LIAR,
        "feeder_voltage_kv",
        3.0,
        reference="feeder_voltage_setpoint_kv",
        note="Voltage reported short so the tap changer climbs.",
    ),
)
_POWER_COMMAND: Final = (
    AttackRecipe(
        AttackType.MIMIC,
        "dispatch_setpoint_mw",
        2.5,
        mimics="dispatch_change",
        note="Dispatch moved with no write on the wire.",
    ),
    AttackRecipe(
        AttackType.ROGUE_COMMAND,
        "feeder_voltage_setpoint_kv",
        1.5,
        issuer="scada",
        note="Write from the polling-only SCADA node (known graph station, not an unknown master).",
    ),
    AttackRecipe(
        AttackType.MIMIC_COMMAND,
        "dispatch_setpoint_mw",
        1.5,
        issuer="hmi",
        mimics="dispatch_change",
        note="Plausible HMI dispatch write matching no scheduled change.",
    ),
)
_BATCH_PROCESS: Final = (
    AttackRecipe(
        AttackType.BLATANT, "jacket_valve_pct", 1.5, note="Jacket valve driven off cascade."
    ),
    AttackRecipe(AttackType.STEALTH_DRIFT, "feed_valve_pct", 6.0, note="Feed valve walked away."),
    AttackRecipe(
        AttackType.CORRELATION_BREAK,
        "jacket_flow_m3ph",
        2.5,
        reference="jacket_valve_pct",
        note="Jacket flow no longer follows the valve.",
    ),
    AttackRecipe(
        AttackType.LIAR,
        "reactor_temp_c",
        3.0,
        reference="reactor_temp_setpoint_c",
        note="Temperature reported short so the jacket overheats.",
    ),
)
_BATCH_COMMAND: Final = (
    AttackRecipe(
        AttackType.MIMIC,
        "reactor_temp_setpoint_c",
        2.5,
        mimics="recipe_change",
        note="Recipe-shaped setpoint move on a plant with no control network.",
    ),
)

_PROCESS: Final[dict[str, tuple[AttackRecipe, ...]]] = {
    "water-treatment": _WATER_PROCESS,
    "power-generation": _POWER_PROCESS,
    "batch-reactor": _BATCH_PROCESS,
}
_COMMAND: Final[dict[str, tuple[AttackRecipe, ...]]] = {
    "water-treatment": _WATER_COMMAND,
    "power-generation": _POWER_COMMAND,
    "batch-reactor": _BATCH_COMMAND,
}


def _layout(
    plant_id: str,
    kind: str,
    recipes: Sequence[AttackRecipe],
    seed: int,
    gap_hours: float,
) -> tuple[tuple[AttackPlan, ...], float]:
    """Place every recipe at every subtlety, non-overlapping, and return plans plus duration."""
    cursor = _PREFIX_HOURS
    plans: list[AttackPlan] = []
    short = plant_id.split("-")[0]
    for subtlety in SUBTLETIES:
        band = f"{subtlety:.2f}".replace(".", "p")
        for recipe in recipes:
            attack_id = f"{short}-{kind}-{recipe.attack_type.value.lower()}-{band}-s{seed}"
            plans.append(recipe.to_plan(attack_id, subtlety, cursor))
            cursor += recipe.duration_hours + gap_hours
    return tuple(plans), cursor + _TAIL_HOURS


PROCESS_GAP_HOURS: Final = _PROCESS_GAP_HOURS
"""Hours between consecutive process-pack attacks."""


def lay_out(
    plant_id: str,
    kind: str,
    recipes: Sequence[AttackRecipe],
    seed: int,
    gap_hours: float,
) -> tuple[tuple[AttackPlan, ...], float]:
    """The library's layout, public: every recipe at every subtlety, non-overlapping."""
    return _layout(plant_id, kind, recipes, seed, gap_hours)


def pack_start() -> datetime:
    """When every library pack opens."""
    return _START


def liar_recipe(plant_id: str) -> AttackRecipe:
    """The one ``LIAR`` recipe in a plant's process pack.

    Raises:
        ValueError: If the plant has no process pack, or not exactly one liar in it.
    """
    recipes = [r for r in _PROCESS.get(plant_id, ()) if r.attack_type is AttackType.LIAR]
    if len(recipes) != 1:
        raise ValueError(f"{plant_id!r} has {len(recipes)} liar recipe(s) in its process pack")
    return recipes[0]


def ot_packs() -> tuple[AttackDatasetConfig, ...]:
    """Return every OT attack pack the library generates.

    Three plants, three seeds, a process pack and a command/mimic pack each. Batch has no
    control network, so its command pack is mimic-only.
    """
    packs: list[AttackDatasetConfig] = []
    for plant_id, recipes in _PROCESS.items():
        for seed in SEEDS:
            plans, duration = _layout(plant_id, "process", recipes, seed, _PROCESS_GAP_HOURS)
            packs.append(
                AttackDatasetConfig(
                    name=f"lib-ot-{plant_id}-process-s{seed}",
                    plant_id=plant_id,
                    seed=seed,
                    traffic_seed=seed + 17,
                    start=_START,
                    duration_hours=duration,
                    sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
                    role="attack",
                    note=(
                        f"Library process pack for {plant_id}, seed {seed}. "
                        "Benign events are interleaved by the plant scheduler."
                    ),
                    attacks=plans,
                )
            )
    for plant_id, recipes in _COMMAND.items():
        for seed in SEEDS:
            plans, duration = _layout(plant_id, "command", recipes, seed, _COMMAND_GAP_HOURS)
            packs.append(
                AttackDatasetConfig(
                    name=f"lib-ot-{plant_id}-command-s{seed}",
                    plant_id=plant_id,
                    seed=seed,
                    traffic_seed=seed + 23,
                    start=_START,
                    duration_hours=duration,
                    sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
                    role="attack",
                    note=(
                        f"Library command/mimic pack for {plant_id}, seed {seed}. "
                        "Unknown-master writes live here where the plant has a network."
                    ),
                    attacks=plans,
                )
            )
    return tuple(packs)


def ot_trains() -> tuple[DatasetConfig, ...]:
    """Return one attack-free fitting corpus per plant, different seeds from the packs."""
    return tuple(
        DatasetConfig(
            name=f"lib-ot-{plant_id}-train",
            plant_id=plant_id,
            seed=seed,
            traffic_seed=seed + 5,
            start=_START,
            duration_hours=_TRAIN_HOURS,
            sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
            role="train",
            note=f"Attack-free fitting corpus for library packs of {plant_id}.",
        )
        for plant_id, seed in _TRAIN_SEEDS.items()
    )


def ot_scenario_count(packs: Sequence[AttackDatasetConfig] | None = None) -> int:
    """Return how many labelled attack windows the packs declare."""
    chosen = packs if packs is not None else ot_packs()
    return sum(len(pack.attacks) for pack in chosen)


def ot_catalogue_payload(packs: Sequence[AttackDatasetConfig] | None = None) -> dict[str, object]:
    """Return the committed catalogue document for the OT library."""
    chosen = tuple(packs) if packs is not None else ot_packs()
    return {
        "schema_version": 1,
        "domain": "ATLAS",
        "caveats": list(SYNTHETIC_LIBRARY_CAVEATS),
        "n_packs": len(chosen),
        "n_scenarios": ot_scenario_count(chosen),
        "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
        "seeds": list(SEEDS),
        "subtleties": list(SUBTLETIES),
        "packs": [
            {
                "name": pack.name,
                "plant_id": pack.plant_id,
                "seed": pack.seed,
                "duration_hours": pack.duration_hours,
                "n_attacks": len(pack.attacks),
                "attacks": [
                    {
                        "id": plan.attack_id,
                        "type": plan.type.value,
                        "subtlety": plan.subtlety,
                        "start_hours": plan.start_hours,
                        "duration_hours": plan.duration_hours,
                    }
                    for plan in pack.attacks
                ],
            }
            for pack in chosen
        ],
    }


def write_ot_catalogue(root: Path, packs: Sequence[AttackDatasetConfig] | None = None) -> Path:
    """Write ``OT/catalogue.json`` under the dataset library root and return its path."""
    directory = root / "OT"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "catalogue.json"
    path.write_text(json.dumps(ot_catalogue_payload(packs), indent=2) + "\n", encoding="utf-8")
    return path


def _nudge_command_plans(plans: tuple[AttackPlan, ...], hours: float) -> tuple[AttackPlan, ...]:
    """Shift mimic and command windows later so they miss a colliding operator write."""
    shifted: list[AttackPlan] = []
    for plan in plans:
        if plan.type in _COMMAND_TYPES:
            shifted.append(plan.model_copy(update={"start_hours": plan.start_hours + hours}))
        else:
            shifted.append(plan)
    return tuple(shifted)


def _generate_pack(config: AttackDatasetConfig, output: Path, *, with_capture: bool) -> Path:
    """Generate one pack, nudging command windows if they collide with a genuine write."""
    trial = config
    last_error: ValueError | None = None
    for _attempt in range(_MAX_NUDGES + 1):
        try:
            directory, _manifest = generate_attack_dataset(trial, output, with_capture=with_capture)
            return directory
        except ValueError as error:
            last_error = error
            message = str(error)
            if "inside this attack's window" not in message and "overlap" not in message:
                raise
            logger.warning(
                "%s: %s; nudging command windows by %.1f h", config.name, error, _NUDGE_HOURS
            )
            trial = trial.model_copy(
                update={
                    "attacks": _nudge_command_plans(trial.attacks, _NUDGE_HOURS),
                    "duration_hours": trial.duration_hours + _NUDGE_HOURS,
                }
            )
    raise ValueError(
        f"{config.name}: could not place command windows without colliding after "
        f"{_MAX_NUDGES} nudges: {last_error}"
    )


def generate_ot_library(
    root: Path,
    *,
    with_capture: bool = False,
    packs: Sequence[AttackDatasetConfig] | None = None,
    trains: Sequence[DatasetConfig] | None = None,
) -> list[Path]:
    """Write train corpora, attack packs, and the catalogue. Returns generated directories."""
    ot_root = root / "OT"
    generated = ot_root / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    write_ot_catalogue(root, packs)
    written: list[Path] = []
    for train in trains if trains is not None else ot_trains():
        directory, _manifest = generate_dataset(train, generated, with_capture=False)
        written.append(directory)
        logger.info("wrote train %s -> %s", train.name, directory)
    for pack in packs if packs is not None else ot_packs():
        directory = _generate_pack(pack, generated, with_capture=with_capture)
        written.append(directory)
        logger.info("wrote pack %s -> %s", pack.name, directory)
    return written
