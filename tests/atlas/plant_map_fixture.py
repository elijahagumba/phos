"""A small tank for the plant-map tests: ADR 0123's water-liar mechanism in five signals.

``level`` integrates ``inflow`` minus ``outflow``. A PI loop moves ``valve`` to hold the *reported*
level at ``target``, and ``inflow`` follows ``valve`` one sample later. ``quality`` follows the
true level, the way chlorine residual follows the clearwell's volume. A liar reports the level a
fixed deficit under ``target`` whatever it truly reads, as the synthetic library's liar does
(`phos.synth.attacks.library`); the loop then overfills, and only the flows disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from numpy.typing import NDArray

from phos.atlas.signal_roles import ControlLoop, RoleDeclaration, SignalRole, SignalRoles

NAMES = ("level", "inflow", "outflow", "valve", "target", "quality")
LEVEL, INFLOW, OUTFLOW, VALVE, TARGET, QUALITY = range(6)
ROLE_OF = {
    "level": SignalRole.SENSOR,
    "inflow": SignalRole.SENSOR,
    "outflow": SignalRole.SENSOR,
    "valve": SignalRole.ACTUATOR,
    "target": SignalRole.SETPOINT,
    "quality": SignalRole.SENSOR,
}


#: The tank's one loop, as its own docstring states it (ADR 0126).
LEVEL_LOOP = ControlLoop(
    name="tank level",
    cited="plant_map_fixture module docstring",
    statement="A PI loop moves valve to hold the reported level at target",
    reading="level",
    outputs=("valve",),
    setpoint="target",
)


def roles(
    names: tuple[str, ...] = NAMES,
    unroled: frozenset[str] = frozenset(),
    loops: tuple[ControlLoop, ...] = (LEVEL_LOOP,),
) -> SignalRoles:
    """The fixture's roles and its declared loop, with any named signals declared without one."""
    declarations = [
        RoleDeclaration(signal=name, role=None, cited="fixture", reason="not described")
        if name in unroled
        else RoleDeclaration(signal=name, role=ROLE_OF[name], cited="fixture", quote=name)
        for name in names
    ]
    usable = tuple(
        loop
        for loop in loops
        if not {loop.reading, *loop.outputs, loop.setpoint} & (unroled | (set(NAMES) - set(names)))
    )
    return SignalRoles(declarations, names, source="plant_map_fixture", loops=usable)


@dataclass(frozen=True)
class Run:
    """A simulated run: what the control system reports, and the true level."""

    reported: NDArray[numpy.float64]
    true_level: NDArray[numpy.float64]


def simulate(
    rows: int,
    seed: int,
    liar: tuple[int, int, float] | None = None,
    forced_valve: tuple[int, int, float] | None = None,
    inflow_liar: tuple[int, int, float] | None = None,
) -> Run:
    """Run the tank.

    Args:
        rows: Samples to simulate.
        seed: Random seed.
        liar: ``(start, end, deficit)``: in that window the level is reported ``deficit`` under
            ``target``, whatever it truly reads.
        forced_valve: ``(start, end, position)``: the valve is held there, readings stay true.
        inflow_liar: ``(start, end, value)``: in that window the inflow meter reports ``value``
            whatever flows; the level, and everything else, reads true.
    """
    rng = numpy.random.default_rng(seed)
    out = numpy.zeros((rows, len(NAMES)))
    level, valve, quality, integral = 5.0, 50.0, 2.5, 0.0
    previous_valve = valve
    target = 5.0
    demand = 40.0
    true_level = numpy.zeros(rows)
    for t in range(rows):
        if t % 1500 == 0:
            target = 5.0 + rng.choice([-0.5, 0.0, 0.5])
        demand = 40.0 + 0.97 * (demand - 40.0) + rng.normal(0.0, 1.5)
        reported = level
        if liar is not None and liar[0] <= t < liar[1]:
            reported = target - liar[2]
        error = target - reported
        integral = numpy.clip(integral + 0.02 * error, -40.0, 40.0)
        valve = float(numpy.clip(50.0 + 8.0 * error + integral, 0.0, 100.0))
        if forced_valve is not None and forced_valve[0] <= t < forced_valve[1]:
            valve = forced_valve[2]
        inflow = 0.8 * previous_valve + rng.normal(0.0, 0.3)
        previous_valve = valve
        outflow = demand
        quality = 0.9 * quality + 0.1 * (0.5 * level) + rng.normal(0.0, 0.01)
        reported_inflow = inflow
        if inflow_liar is not None and inflow_liar[0] <= t < inflow_liar[1]:
            reported_inflow = inflow_liar[2] + rng.normal(0.0, 0.3)
        out[t] = (
            reported + rng.normal(0.0, 0.01),
            reported_inflow,
            outflow,
            valve,
            target,
            quality,
        )
        true_level[t] = level
        level = level + 0.002 * (inflow - outflow) + rng.normal(0.0, 0.002)
    return Run(reported=out, true_level=true_level)
