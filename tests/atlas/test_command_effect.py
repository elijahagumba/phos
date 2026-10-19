"""H1: a write toward a safety limit, against the plant's call, is a command effect."""

from datetime import UTC, datetime, timedelta

from phos.atlas.command_effect import (
    OUTSIDE_OPERATING_MODE,
    SETPOINT_JUMP,
    TOWARD_LIMIT_AGAINST_STATE,
    OperatorWrite,
    called_for_direction,
    command_effect_evidence,
    command_effect_feature_of,
    is_setpoint_jump,
    moves_toward_limit_against_call,
    reading_stays_hidden,
)
from phos.atlas.packet import UNEXPECTED_COMMAND_FUNCTION
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.ontology import Domain, Evidence, EvidenceKind, EvidenceRole, FacetKind
from phos.reasoning import FittedPlattCalibrator
from phos.synth.plants.water import (
    CLEARWELL_LEVEL,
    LEVEL_SETPOINT,
    LEVEL_SETPOINT_OPERATING_HIGH,
    LEVEL_SETPOINT_OPERATING_LOW,
    WATER_DESCRIPTION,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
WEIGHT = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
BAND = {LEVEL_SETPOINT: (LEVEL_SETPOINT_OPERATING_LOW, LEVEL_SETPOINT_OPERATING_HIGH)}
ENTITY = f"ent_water-treatment_{LEVEL_SETPOINT}"


def _evidence(
    setpoint: list[float],
    level: list[float],
    *,
    covered: frozenset[str] = frozenset(),
    enabled: frozenset[str] = frozenset({TOWARD_LIMIT_AGAINST_STATE}),
    active: tuple[str | None, ...] | None = None,
    manual: frozenset[str] = frozenset(),
) -> tuple[Evidence, ...]:
    timestamps = tuple(START + index * timedelta(seconds=120) for index in range(len(setpoint)))
    return command_effect_evidence(
        description=WATER_DESCRIPTION,
        reported={LEVEL_SETPOINT: setpoint, CLEARWELL_LEVEL: level},
        timestamps=timestamps,
        writes=(OperatorWrite(2, LEVEL_SETPOINT, setpoint[2]),),
        operating_bands=BAND,
        covered=covered,
        entity_of={LEVEL_SETPOINT: ENTITY},
        calibrator=WEIGHT,
        learned_from_window=(timestamps[0], timestamps[-1]),
        enabled=enabled,
        active_kinds=active,
        manual_modes=manual,
    )


def test_a_short_clearwell_written_toward_empty_is_against_the_call() -> None:
    facts = _evidence([3.0, 3.0, 0.4, 0.4], [2.9, 2.9, 2.9, 2.9])

    assert len(facts) == 1
    assert facts[0].weight == 0.5
    assert command_effect_feature_of(facts[0]) == TOWARD_LIMIT_AGAINST_STATE
    assert facts[0].facet_kind is FacetKind.COMMAND_EFFECT


def test_a_raise_that_goes_with_the_short_clearwell_is_not_the_fact() -> None:
    assert _evidence([3.0, 3.0, 4.5, 4.5], [2.9, 2.9, 2.9, 2.9]) == ()


def test_a_covering_work_order_withholds_the_fact() -> None:
    facts = _evidence(
        [3.0, 3.0, 0.4, 0.4],
        [2.9, 2.9, 2.9, 2.9],
        covered=frozenset({LEVEL_SETPOINT}),
    )

    assert facts == ()


def test_an_in_band_step_is_not_the_fact() -> None:
    assert not moves_toward_limit_against_call(
        before=3.0,
        after=2.7,
        low=0.0,
        high=6.0,
        operating_low=2.6,
        operating_high=3.8,
        call=called_for_direction(2.5, 3.0, deadband=0.024),
    )


def test_the_fact_supports_unauthorised_and_not_maintenance() -> None:
    fact = _evidence([3.0, 3.0, 0.4, 0.4], [2.9, 2.9, 2.9, 2.9])[0]
    roles = {match.template.template_id: match.role for match in atlas_library().matches(fact, {})}

    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert ENGINEERING_MAINTENANCE_TEMPLATE_ID not in roles
    assert PROCESS_DISTURBANCE_TEMPLATE_ID not in roles
    assert SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID not in roles


def test_a_jump_larger_than_the_operating_band_supports_unauthorised() -> None:
    assert is_setpoint_jump(3.0, 4.5, 2.6, 3.8)
    assert not is_setpoint_jump(3.0, 3.5, 2.6, 3.8)
    facts = _evidence(
        [3.0, 3.0, 4.5, 4.5],
        [2.9, 2.9, 2.9, 2.9],
        enabled=frozenset({SETPOINT_JUMP, OUTSIDE_OPERATING_MODE}),
        active=(None, None, None, None),
    )

    assert len(facts) == 1
    assert command_effect_feature_of(facts[0]) == SETPOINT_JUMP
    assert facts[0].weight == 0.5


def test_a_write_during_backwash_is_outside_the_mode() -> None:
    facts = _evidence(
        [3.0, 3.0, 3.2, 3.2],
        [2.9, 2.9, 2.9, 2.9],
        enabled=frozenset({OUTSIDE_OPERATING_MODE}),
        active=(None, None, "filter_backwash", None),
        manual=frozenset({"filter_backwash"}),
    )

    assert len(facts) == 1
    assert command_effect_feature_of(facts[0]) == OUTSIDE_OPERATING_MODE


def test_a_moved_actuator_and_a_held_reading_is_a_hide() -> None:
    assert reading_stays_hidden(
        actuator_before=10.0,
        actuator_after=0.0,
        reading_before=2.9,
        reading_after=2.9,
        actuator_span=100.0,
        reading_deadband=0.024,
    )
    assert not reading_stays_hidden(
        actuator_before=10.0,
        actuator_after=90.0,
        reading_before=2.9,
        reading_after=3.2,
        actuator_span=100.0,
        reading_deadband=0.024,
    )


def test_a_known_link_function_change_is_not_a_command_effect() -> None:
    fact = Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id="obs_known_link",
        entity_ids=["ent_hmi", "ent_plc"],
        timestamp=START,
        domain=Domain.ATLAS,
        weight=0.5,
        summary=f"graph:{UNEXPECTED_COMMAND_FUNCTION}: hmi wrote a new function",
        facet_kind=FacetKind.GRAPH_FINDING,
        facet=UNEXPECTED_COMMAND_FUNCTION,
    )

    assert command_effect_feature_of(fact) is None
    roles = {match.template.template_id: match.role for match in atlas_library().matches(fact, {})}
    assert roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
