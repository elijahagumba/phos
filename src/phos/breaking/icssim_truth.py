"""ICSSim's true cause-and-effect graph, read from its source, for judging only (ADR 0132).

Every edge ``driver -> driven`` is one line of ICSSim's own code at the pinned commit
(`bcfd1844d3f063850c69f2643f6a052bac03d8ec`): the physics in ``src/FactorySimulation.py``
(sha256 ``03c4a3ac…ad5e``), the control programs ``src/PLC1.py`` and ``src/PLC2.py``, and
``_check_manual_input`` in ``src/ics_sim/Device.py``, by which a mode tag forces its actuator.

**This is ground truth, so nothing that learns may read it.** Like ``truth.csv`` (ADR 0017), it
judges the plant model's claims and is never an input to them: no module under ``phos.atlas``
imports this one, which a test checks.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ICSSIM_EDGES", "reachable"]

ICSSIM_EDGES: Final = frozenset(
    {
        # FactorySimulation._logic: the tank fills through the input valve, drains through the
        # output valve, and flows out only while the output valve is open and the tank holds water.
        ("tank_input_valve_status", "tank_level_value"),
        ("tank_output_valve_status", "tank_level_value"),
        ("tank_output_valve_status", "tank_output_flow_value"),
        ("tank_level_value", "tank_output_flow_value"),
        # The bottle fills from the outflow only while it is under the filler.
        ("tank_output_flow_value", "bottle_level_value"),
        ("bottle_distance_to_filler_value", "bottle_level_value"),
        # The belt moves the bottle.
        ("conveyor_belt_engine_status", "bottle_distance_to_filler_value"),
        # PLC1._logic: the input valve on the tank level and its limits, or its mode.
        ("tank_level_value", "tank_input_valve_status"),
        ("tank_level_max", "tank_input_valve_status"),
        ("tank_level_min", "tank_input_valve_status"),
        ("tank_input_valve_mode", "tank_input_valve_status"),
        # PLC1._logic: the output valve on the bottle's level, limit and position, or its mode.
        ("bottle_level_value", "tank_output_valve_status"),
        ("bottle_level_max", "tank_output_valve_status"),
        ("bottle_distance_to_filler_value", "tank_output_valve_status"),
        ("tank_output_valve_mode", "tank_output_valve_status"),
        # PLC2._logic: the belt on the bottle's position, the outflow and the bottle, or its mode.
        ("bottle_distance_to_filler_value", "conveyor_belt_engine_status"),
        ("tank_output_flow_value", "conveyor_belt_engine_status"),
        ("bottle_level_value", "conveyor_belt_engine_status"),
        ("bottle_level_max", "conveyor_belt_engine_status"),
        ("conveyor_belt_engine_mode", "conveyor_belt_engine_status"),
    }
)


def reachable(source: str, edges: frozenset[tuple[str, str]] = ICSSIM_EDGES) -> frozenset[str]:
    """Every signal a directed path of true edges reaches from ``source``, excluding it."""
    children: dict[str, set[str]] = {}
    for driver, driven in edges:
        children.setdefault(driver, set()).add(driven)
    seen: set[str] = set()
    stack = list(children.get(source, ()))
    while stack:
        node = stack.pop()
        if node not in seen and node != source:
            seen.add(node)
            stack.extend(children.get(node, ()))
    return frozenset(seen)
