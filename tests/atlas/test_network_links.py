"""Grade C (ADR 0130): control relations a controller's own traffic shows."""

from phos.atlas.network_links import Exchange, network_claims, score_claims
from phos.atlas.signal_roles import ControlLoop, RoleDeclaration, SignalRole, SignalRoles

ROLE_OF = {
    "level": SignalRole.SENSOR,
    "flow": SignalRole.SENSOR,
    "valve": SignalRole.ACTUATOR,
    "pump": SignalRole.ACTUATOR,
    "belt": SignalRole.ACTUATOR,
    "limit": SignalRole.SETPOINT,
}
LOOPS = (
    ControlLoop(name="pump", cited="c", statement="s", reading="level", outputs=("pump",)),
    ControlLoop(
        name="belt", cited="c", statement="s", reading="flow", outputs=("belt",), setpoint="limit"
    ),
)
ROLES = SignalRoles(
    [RoleDeclaration(signal=k, role=v, cited="c", quote=k) for k, v in ROLE_OF.items()],
    tuple(ROLE_OF),
    source="fixture",
    loops=LOOPS,
)
HOSTED = {
    "level": "plc1",
    "valve": "plc1",
    "flow": "plc2",
    "pump": "plc2",
    "belt": "plc2",
    "limit": "plc1",
}


def _traffic(*extra: Exchange) -> list[Exchange]:
    # plc2 reads plc1's level and limit; the operator polls everything; plc2 serves its own.
    base = [
        Exchange("plc2", "plc1", "read", "level"),
        Exchange("plc2", "plc1", "read", "limit"),
        Exchange("plc1", "plc2", "read", "flow"),
        *(Exchange("operator", server, "read", point) for point, server in HOSTED.items()),
    ]
    return [*base, *extra]


def test_a_controller_s_read_claims_its_actuators() -> None:
    claims = {(c.controller, c.point): c for c in network_claims(_traffic(), ROLES)}
    assert set(claims) == {("plc2", "level"), ("plc2", "limit"), ("plc1", "flow")}
    assert claims[("plc2", "level")].actuators == ("belt", "pump")
    assert claims[("plc1", "flow")].actuators == ("valve",)


def test_a_console_that_only_reads_makes_no_claim() -> None:
    claims = network_claims(_traffic(), ROLES)
    assert all(c.controller != "operator" for c in claims)


def test_a_statistical_link_narrows_a_claim_only_when_one_actuator_agrees() -> None:
    claims = {
        (c.controller, c.point): c
        for c in network_claims(_traffic(), ROLES, {"level": ["pump"], "limit": ["belt", "pump"]})
    }
    assert claims[("plc2", "level")].narrowed == "pump"
    assert claims[("plc2", "limit")].narrowed is None


def test_claims_are_judged_against_the_declared_loops() -> None:
    claims = network_claims(_traffic(), ROLES, {"level": ["pump"]})
    score = score_claims(claims, ROLES, HOSTED)
    # level -> {belt, pump} holds (pump); limit -> {belt, pump} holds (the belt loop's setpoint);
    # flow -> {valve} holds for no loop.
    assert (score["claims"], score["true"]) == (3, 2)
    assert (score["narrowed"], score["narrowed_true"]) == (1, 1)
    # Only the pump loop crosses controllers (level on plc1, pump on plc2); it is found.
    assert (score["loops_visible_on_the_network"], score["visible_loops_found"]) == (1, 1)
