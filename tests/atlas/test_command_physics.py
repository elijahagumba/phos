"""Commands against physics separate a pair neither path separates alone (ADR 0160)."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.command_physics import (
    GAINED_PAIR,
    SCORED_LOOPS,
    champion_train_seed,
    gained_pairs,
    score_seed,
    separated_pairs,
)
from phos.atlas.command_response import CommandResponsePair, response_mismatches
from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
)
from phos.eval.build_declaration import BUILD_DEVELOPMENT_SEEDS, BUILD_HELD_BACK_SEEDS
from phos.ontology import Domain, Entity, EntityType, Evidence, EvidenceKind, FacetKind
from phos.reasoning import FittedPlattCalibrator
from phos.synth.plant import SignalKind, SignalSpec
from phos.synth.plants.power import TAP_POSITION

START = datetime(2026, 10, 1, tzinfo=UTC)


def _entity(name: str) -> Entity:
    """One entity whose id is its name."""
    return Entity(id=f"ent_{name}", type=EntityType.PLC, domain=Domain.ATLAS, name=name)


def _cross(name: str) -> Evidence:
    """A cross-signal fact on ``name``. It does not contradict maintenance."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=f"dev_{name}",
        entity_ids=[f"ent_{name}"],
        timestamp=START,
        domain=Domain.ATLAS,
        weight=0.5,
        summary="the reading disagrees with the rest of the plant",
        facet_kind=FacetKind.CONSISTENCY,
        facet=CROSS_SIGNAL_MISMATCH,
    )


def _mismatch() -> Evidence:
    """A command the actuator ignored, promoted through the same door as a scored run."""
    actuator = [10.0] * 30
    setpoint = [0.0] * 5 + [50.0] * 25
    bundle = response_mismatches(
        pairs=(CommandResponsePair("setpoint", "actuator", "measurement"),),
        signals={
            "setpoint": SignalSpec(
                key="setpoint",
                label="setpoint",
                unit="u",
                kind=SignalKind.SETPOINT,
                physical_unit="loop",
                low=0.0,
                high=100.0,
                noise_stddev=0.0,
            ),
            "actuator": SignalSpec(
                key="actuator",
                label="actuator",
                unit="u",
                kind=SignalKind.ACTUATOR,
                physical_unit="loop",
                low=0.0,
                high=100.0,
                noise_stddev=0.0,
            ),
        },
        reported={"setpoint": setpoint, "actuator": actuator},
        writes=((5, "setpoint"),),
        timestamps=[START + timedelta(seconds=index) for index in range(30)],
        entity_of={"actuator": "ent_actuator"},
        calibrator=FittedPlattCalibrator(coefficient=0.0, intercept=0.0),
        learned_from_window=(START, START),
    )
    return bundle.facts[0].evidence


def test_cross_signal_does_not_separate_maintenance_from_a_sensor_fault() -> None:
    """The gained pair is the one the command-to-response fact adds."""
    cross = _cross("flow")
    mismatch = _mismatch()
    entities = (_entity("flow"), _entity("actuator"))
    physics = separated_pairs((cross,), entities)
    gained = gained_pairs((), (cross,), (cross, mismatch), entities)

    assert (ENGINEERING_MAINTENANCE_TEMPLATE_ID, SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID) not in physics
    assert GAINED_PAIR in gained
    assert (
        PROCESS_DISTURBANCE_TEMPLATE_ID,
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    ) in physics


def test_a_seed_outside_its_split_is_refused_before_a_plant_is_built() -> None:
    """Held-back seeds are not opened from the development entry, and the reverse holds."""
    with pytest.raises(ValueError, match="97101"):
        score_seed(97101, split="development")
    with pytest.raises(ValueError, match="97001"):
        score_seed(97001, split="held-back")
    with pytest.raises(ValueError, match="94001"):
        score_seed(94001, split="development")


def test_the_champion_trains_on_the_first_development_seed() -> None:
    """Held-back scoring must not fit on a held-back seed."""
    assert champion_train_seed() == 97001
    assert champion_train_seed() == BUILD_DEVELOPMENT_SEEDS[0]
    assert champion_train_seed() not in BUILD_HELD_BACK_SEEDS


def test_power_is_scored_on_the_tap_changer() -> None:
    """The fuel valve is a declared pair and not the loop this measurement writes."""
    power = next(loop for loop in SCORED_LOOPS if loop.plant_id == "power-generation")
    assert power.actuator == TAP_POSITION
    assert power.command == "feeder_voltage_setpoint_kv"


def test_seed_97001_gains_the_pair_on_water_and_power_and_skips_batch() -> None:
    """One development seed, both networked plants, follow runs clean."""
    result = score_seed(97001, split="development")
    by_plant = {plant.plant_id: plant for plant in result.plants}

    assert by_plant["batch-reactor"].skipped
    for plant_id in ("water-treatment", "power-generation"):
        plant = by_plant[plant_id]
        assert plant.follow_mismatch_count == 0, plant
        assert plant.stuck_mismatch_count >= 1, plant
        assert GAINED_PAIR in plant.gained_pairs, plant
        assert plant.command_pairs == ()
    assert result.passed
