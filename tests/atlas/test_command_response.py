"""A declared command whose actuator did not move becomes one consistency fact (ADR 0160)."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.command_response import (
    HORIZON_STEPS,
    CommandResponsePair,
    declared_pairs,
    response_mismatches,
)
from phos.atlas.consistency_evidence import (
    COMMAND_TO_RESPONSE_MISMATCH,
    ConsistencyFact,
    consistency_feature_of,
)
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    CommandBehaviourPattern,
    CommandResponsePattern,
    SubsystemBreadthPattern,
    atlas_templates,
    prior_at_rank,
)
from phos.ontology import EvidenceKind, EvidenceRole, FacetKind
from phos.reasoning import FittedPlattCalibrator, is_out_of_band
from phos.reasoning.analyst_settling import describe_pattern
from phos.synth.plant import SignalKind, SignalSpec
from phos.synth.plants.batch import BATCH_DESCRIPTION, JACKET_VALVE, TEMP_SETPOINT
from phos.synth.plants.power import (
    DISPATCH_SETPOINT,
    EXCITATION,
    FUEL_VALVE,
    POWER_DESCRIPTION,
    TAP_POSITION,
    VOLTAGE_SETPOINT,
)
from phos.synth.plants.water import (
    COAGULANT_DOSE,
    INTAKE_SPEED,
    LEVEL_SETPOINT,
    WATER_DESCRIPTION,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
WEIGHT = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
WINDOW = (START, START)


def _signal(key: str, kind: SignalKind, high: float = 100.0) -> SignalSpec:
    """One signal with a span of ``[0, high]``."""
    return SignalSpec(
        key=key,
        label=key,
        unit="u",
        kind=kind,
        physical_unit="loop",
        low=0.0,
        high=high,
        noise_stddev=0.0,
    )


def _flat(value: float, n: int = 30) -> list[float]:
    """A constant series."""
    return [value] * n


def _facts(
    *,
    actuator: list[float],
    setpoint: list[float] | None = None,
    writes: tuple[tuple[int, str], ...] = ((5, "setpoint"),),
    horizon: int = HORIZON_STEPS,
) -> tuple[ConsistencyFact, ...]:
    """Promote mismatches for one setpoint and one actuator."""
    n = len(actuator)
    command = _flat(0.0, n) if setpoint is None else setpoint
    bundle = response_mismatches(
        pairs=(CommandResponsePair("setpoint", "actuator", "measurement"),),
        signals={
            "setpoint": _signal("setpoint", SignalKind.SETPOINT),
            "actuator": _signal("actuator", SignalKind.ACTUATOR),
            "measurement": _signal("measurement", SignalKind.SENSOR),
        },
        reported={"setpoint": command, "actuator": actuator, "measurement": _flat(1.0, n)},
        writes=writes,
        timestamps=[START + timedelta(seconds=index) for index in range(n)],
        entity_of={"actuator": "ent_actuator"},
        calibrator=WEIGHT,
        learned_from_window=WINDOW,
        horizon_steps=horizon,
    )
    return bundle.facts


def test_declared_pairs_follow_control_couplings_with_one_setpoint() -> None:
    """The pair is the plant's coupling, not a pairing searched from the series."""
    water = {pair.command: pair for pair in declared_pairs(WATER_DESCRIPTION)}
    power = {pair.command: pair for pair in declared_pairs(POWER_DESCRIPTION)}
    batch = {pair.command: pair for pair in declared_pairs(BATCH_DESCRIPTION)}

    assert water[LEVEL_SETPOINT] == CommandResponsePair(
        LEVEL_SETPOINT, INTAKE_SPEED, "clearwell_level_m"
    )
    assert COAGULANT_DOSE not in {pair.actuator for pair in water.values()}
    assert power[VOLTAGE_SETPOINT].actuator == TAP_POSITION
    assert power[DISPATCH_SETPOINT].actuator == FUEL_VALVE
    assert EXCITATION not in {pair.actuator for pair in power.values()}
    jacket = batch[TEMP_SETPOINT]
    assert jacket.actuator == JACKET_VALVE
    assert jacket.response == JACKET_VALVE


def test_a_still_actuator_after_a_real_write_is_one_out_of_band_fact() -> None:
    """Travel under 5% of span, after a step of at least that share, is the mismatch."""
    setpoint = _flat(0.0)
    setpoint[5] = 50.0
    for index in range(6, len(setpoint)):
        setpoint[index] = 50.0
    facts = _facts(actuator=_flat(10.0), setpoint=setpoint)

    assert len(facts) == 1
    fact = facts[0]
    assert fact.evidence.facet_kind is FacetKind.CONSISTENCY
    assert consistency_feature_of(fact.evidence) == COMMAND_TO_RESPONSE_MISMATCH
    assert is_out_of_band(fact.deviation, fact.observation)
    assert fact.observation.value == 0.0


def test_an_actuator_that_moved_is_not_a_fact() -> None:
    """Travel at the threshold is an answer, not a mismatch."""
    actuator = _flat(10.0)
    actuator[5 + HORIZON_STEPS] = 15.0
    assert _facts(actuator=actuator, setpoint=_step()) == ()


def test_a_tiny_write_a_late_window_and_the_first_sample_are_not_facts() -> None:
    """The check refuses a step under the share, a window off the series, and index 0."""
    tiny = _flat(0.0)
    tiny[5] = 1.0
    assert _facts(actuator=_flat(10.0), setpoint=tiny) == ()
    assert _facts(actuator=_flat(10.0), setpoint=_step(), writes=((15, "setpoint"),)) == ()
    assert _facts(actuator=_flat(10.0), setpoint=_step(), writes=((0, "setpoint"),)) == ()


def test_shares_and_the_horizon_are_refused_when_they_are_not_a_check() -> None:
    """A share outside (0, 1) or a non-positive horizon is not a threshold."""
    with pytest.raises(ValueError, match="min_command_share"):
        response_mismatches(
            pairs=(),
            signals={},
            reported={},
            writes=(),
            timestamps=[],
            entity_of={},
            calibrator=WEIGHT,
            learned_from_window=WINDOW,
            min_command_share=0.0,
        )
    with pytest.raises(ValueError, match="horizon_steps"):
        response_mismatches(
            pairs=(),
            signals={},
            reported={},
            writes=(),
            timestamps=[],
            entity_of={},
            calibrator=WEIGHT,
            learned_from_window=WINDOW,
            horizon_steps=0,
        )


def test_the_fact_supports_a_sensor_fault_and_contradicts_maintenance_and_a_real_upset() -> None:
    """Known-link matchers are untouched: unauthorised control stays silent on this fact."""
    facts = _facts(actuator=_flat(10.0), setpoint=_step())
    evidence = facts[0].evidence
    roles = {
        template.template_id: template.role_for(evidence, {}) for template in atlas_templates()
    }

    assert roles[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert roles[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is None


def test_a_grouped_departure_is_not_the_same_fact_as_a_command_the_actuator_ignored() -> None:
    """Both directions. A breadth band must not be read as this mismatch."""
    broad = SubsystemBreadthPattern(
        kinds=(EvidenceKind.DEVIATION,), min_signals=3, subsystem_events_only=True
    )
    response = CommandResponsePattern(kinds=(EvidenceKind.DEVIATION,))

    assert not broad.overlaps(response)
    assert not response.overlaps(broad)
    assert describe_pattern(response) == "a declared command whose actuator did not move"


def test_command_behaviour_and_command_response_are_disjoint_and_priors_are_unchanged() -> None:
    """One fact, one facet. The prior ladder is the one ADR 0071 already pinned."""
    response = CommandResponsePattern(kinds=(EvidenceKind.DEVIATION,))
    behaviour = CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,))
    assert not response.overlaps(behaviour)
    assert not behaviour.overlaps(response)
    by_id = {template.template_id: template for template in atlas_templates()}
    assert by_id[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID].prior == prior_at_rank(2)
    assert by_id[ENGINEERING_MAINTENANCE_TEMPLATE_ID].prior == prior_at_rank(1)
    assert by_id[UNAUTHORISED_CONTROL_TEMPLATE_ID].prior == prior_at_rank(0)


def _step() -> list[float]:
    """A setpoint that steps from 0 to 50 at sample 5 and stays there."""
    series = _flat(0.0)
    for index in range(5, len(series)):
        series[index] = 50.0
    return series
