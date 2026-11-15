"""The `power` family: how a seed becomes one islanded generating set.

PART R2. `phos.synth.plants.generation` holds the physics and the power identity; this module
holds what may vary.

**Load is drawn relative to the machine, never in absolute megawatts.** ``demand_base_mw`` is the
rated output times a drawn ``load_factor``, for the same reason the pumps and heaters in the other
families are sized for their duty: a 40 MW load is nothing to one machine and impossible for the
next, so the meaningful quantity is the ratio. The feeders' shares are drawn and then normalised
so they sum to one, which keeps the load split random without letting it stop adding up.
"""

import math
from collections.abc import Mapping
from typing import Final

from phos.synth.families import BoundScale, ParameterBound, PlantFamily, bounded, register_family
from phos.synth.plant import Coupling, CouplingKind, PhysicalUnit, SignalKind, SignalSpec
from phos.synth.plant_spec import (
    Component,
    ComponentKind,
    Connection,
    ControllerKind,
    ControllerSpec,
    DisturbanceSpec,
    EventPlanSpec,
    PlantSpec,
)
from phos.synth.plants.generation import (
    AVR,
    BUS_VOLTAGE,
    DISPATCH_SETPOINT,
    EXCITATION,
    FEEDER_CURRENT,
    FEEDER_POWER,
    FEEDER_SWITCHING,
    FREQUENCY,
    FUEL,
    GENERATION_PROCESS,
    GOVERNOR,
    LOAD_STEP,
    OUTPUT,
    POWER_FACTOR,
    VOLTAGE_SETPOINT,
)
from phos.synth.plants.spec_build import (
    RolePosition,
    draw_naming_scheme,
    modbus_network,
    operator_authority,
    render_tags,
    roles_from_tags,
)
from phos.synth.randomise import StreamDraw

__all__ = ["POWER_BOUNDS", "PowerFamily"]

_PREFIXES: Final = ("", "GEN", "STN", "G1", "PWR")
_TURBINE: Final = "turbine"
_GENERATOR: Final = "generator"
_DISPATCH_CHANGE: Final = "dispatch_change"
_VOLTAGE_SETPOINT_CHANGE: Final = "voltage_setpoint_change"

POWER_BOUNDS: Final = (
    ParameterBound(
        "feeders",
        1,
        4,
        BoundScale.INTEGER,
        "",
        "How many outgoing circuits leave the site. Each one is metered separately, and each one "
        "has to satisfy the power identity on its own.",
    ),
    ParameterBound(
        "rated_mw",
        3.0,
        200.0,
        BoundScale.LOG,
        "MW",
        "What the machine is rated at. A small standby set and a mid-size industrial station are "
        "nearly two orders of magnitude apart, which is why this is drawn in the log.",
    ),
    ParameterBound.among(
        "nominal_hz",
        (50.0, 60.0),
        "Hz",
        "The frequency the island runs at. Discrete, because 55 Hz is not a cautious middle — it "
        "is a plant that does not exist.",
    ),
    ParameterBound(
        "load_factor",
        0.30,
        0.85,
        BoundScale.LINEAR,
        "",
        "Mean island load as a fraction of rated output. Below this the machine is barely loaded "
        "and above it there is no headroom for a customer to pick up.",
    ),
    ParameterBound(
        "demand_daily_fraction",
        0.04,
        0.35,
        BoundScale.LINEAR,
        "",
        "How far the island's draw swings over a day, as a fraction of its mean.",
    ),
    ParameterBound(
        "inertia_hz_per_mw_s",
        0.004,
        0.06,
        BoundScale.LOG,
        "Hz/MW/s",
        "How far the frequency falls per megawatt of unmatched load per second. This is the "
        "machine's rotating inertia, and it is the whole reason frequency moves at all: a heavy "
        "machine rides through a load step that a light one notices immediately.",
    ),
    ParameterBound(
        "fuel_tau_s",
        1.0,
        10.0,
        BoundScale.LOG,
        "s",
        "How long the machine takes to turn a fuel change into output. Seconds, not tens of "
        "seconds: a gas turbine's fuel system is fast, and it has to be, because frequency on an "
        "islanded machine is an integral and there is nothing else holding it up.",
    ),
    ParameterBound(
        "nominal_kv",
        3.3,
        33.0,
        BoundScale.LOG,
        "kV",
        "Bus voltage the machine is designed around, and what the AVR holds it at.",
    ),
    ParameterBound(
        "voltage_tau_s",
        1.0,
        20.0,
        BoundScale.LOG,
        "s",
        "How long bus voltage takes to follow a change in excitation.",
    ),
    ParameterBound(
        "bus_drop_fraction",
        0.01,
        0.10,
        BoundScale.LINEAR,
        "",
        "How far the bus sags at full load, as a fraction of nominal voltage — the machine's own "
        "impedance in per-unit, which is how a machine's reactance is actually quoted. The "
        "kV-per-amp figure the physics reads is derived from it. Drawn in kV/A directly, the same "
        "number was a rounding error on a small machine at high voltage and a 26% collapse on a "
        "large one at low voltage, because an amp means nothing without knowing the machine. This "
        "is what couples the feeders to each other: load on one pulls the voltage every other "
        "feeder is measured against.",
    ),
    ParameterBound(
        "power_factor",
        0.78,
        0.99,
        BoundScale.LINEAR,
        "",
        "Mean power factor of the load. It appears directly in the power identity, so a detector "
        "that ignores it will find the identity broken on every honest sample.",
    ),
    ParameterBound(
        "governor_droop_fraction",
        0.01,
        0.05,
        BoundScale.LINEAR,
        "",
        "How far the frequency is allowed to fall, as a fraction of nominal, while the governor "
        "picks up the largest load step a customer makes. This is a governor's droop, which is "
        "what a real one is actually specified by, and the gain in percent per hertz is derived "
        "from it together with the machine's rating, its inertia and the step it has to reject. "
        "Drawn as a gain directly, the governor was unstable on seventeen draws in twenty — "
        "frequency is an *integral* of unmatched power, so a gain that suits a 6 MW set makes a "
        "170 MW one hunt, and no gain at all works if the loop is tuned to a timescale over "
        "which the frequency has already left the building.",
    ),
    ParameterBound(
        "governor_integral_multiple",
        2.0,
        8.0,
        BoundScale.LINEAR,
        "",
        "How much slower the governor's integral action is than its proportional action. Above "
        "one because an integral faster than the loop it is correcting winds up and oscillates, "
        "which is the second half of what made the independently drawn tuning unstable.",
    ),
    ParameterBound(
        "avr_loop_gain",
        1.0,
        8.0,
        BoundScale.LOG,
        "",
        "Dimensionless loop gain of the automatic voltage regulator — how hard it pushes, "
        "relative to how much the bus voltage actually moves per percent of excitation. The gain "
        "in percent per kilovolt is derived from it and the machine's nominal voltage.",
    ),
    ParameterBound(
        "avr_integral_multiple",
        1.0,
        5.0,
        BoundScale.LINEAR,
        "",
        "How much slower the AVR's integral action is than the field's own time constant.",
    ),
    ParameterBound(
        "avr_bias_pct",
        30.0,
        70.0,
        BoundScale.LINEAR,
        "%",
        "Excitation the AVR starts from before its own terms.",
    ),
    ParameterBound(
        "frequency_noise_hz",
        0.002,
        0.08,
        BoundScale.LOG,
        "Hz",
        "Measurement noise on the frequency transducer.",
    ),
    ParameterBound(
        "voltage_noise_fraction",
        0.0005,
        0.01,
        BoundScale.LOG,
        "",
        "Measurement noise on bus and feeder voltage, as a fraction of nominal.",
    ),
    ParameterBound(
        "power_noise_fraction",
        0.001,
        0.02,
        BoundScale.LOG,
        "",
        "Measurement noise on the power and current meters, as a fraction of rated output.",
    ),
    ParameterBound(
        "power_factor_noise",
        0.001,
        0.02,
        BoundScale.LOG,
        "",
        "Measurement noise on the power-factor meters.",
    ),
    ParameterBound(
        "scan_period_s",
        1,
        10,
        BoundScale.INTEGER,
        "s",
        "How often the station is polled, which in this engine is also how often its regulators "
        "run. Much faster than the other families, and it has to be: an islanded machine's "
        "frequency is an integral, so a governor updated every half minute has no chance of "
        "holding it. A real turbine governor is a local controller running far faster than this "
        "and faster than anything this engine represents.",
    ),
    ParameterBound(
        "event_gap_low_steps",
        60,
        600,
        BoundScale.INTEGER,
        "samples",
        "Shortest quiet stretch between two benign events.",
    ),
    ParameterBound(
        "event_gap_span_steps",
        300,
        3000,
        BoundScale.INTEGER,
        "samples",
        "How much longer the longest quiet stretch may be than the shortest.",
    ),
    ParameterBound(
        "load_step_headroom",
        0.2,
        0.9,
        BoundScale.LINEAR,
        "",
        "How much of the machine's spare capacity the largest customer load step takes up. The "
        "step as a fraction of rated output is derived from it and the load factor. Drawn as a "
        "fraction of rating directly, a quarter-rating step on a machine already at 85% drove "
        "the demand past what the set can make, and the fuel valve sat at its stop for most of "
        "the run — a plant with no governor behaviour in it at all.",
    ),
    ParameterBound(
        "load_step_steps",
        30,
        600,
        BoundScale.INTEGER,
        "samples",
        "How long a customer's load step lasts.",
    ),
    ParameterBound(
        "power_factor_shift",
        0.02,
        0.12,
        BoundScale.LINEAR,
        "",
        "How far switching moves the power factor while it lasts.",
    ),
    ParameterBound(
        "switching_steps",
        30,
        600,
        BoundScale.INTEGER,
        "samples",
        "How long a feeder-switching event lasts.",
    ),
)
"""Everything the `power` family varies, rendered into ``docs/sim/README.md``."""


class PowerFamily(PlantFamily):
    """Islanded generating sets: the same machine at different sizes, inertias and tunings."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "power"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Islanded generating set"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return GENERATION_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "power generation"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not an engineer."""
        return (
            "A generating set supplying an island with no grid behind it. A governor holds the "
            "frequency by varying fuel and an automatic voltage regulator holds the bus voltage "
            "by varying excitation. Because there is no grid, taking load slows the whole island "
            "down, and on every outgoing circuit the power, the voltage and the current have to "
            "multiply out."
        )

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return POWER_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one generating set.

        Args:
            master_seed: Seeds every draw below.

        Returns:
            The drawn plant, as a valid spec.
        """
        streams = self.streams(master_seed)
        limits = self.bounds_by_name()
        structure = streams.draw("structure")
        sizing = streams.draw("sizing")
        tuning = streams.draw("tuning")
        instruments = streams.draw("instruments")
        naming = streams.draw("naming")
        events = streams.draw("disturbance")

        feeders = round(bounded(structure, limits, "feeders"))
        shares = _shares(structure, feeders)
        parameters = _parameters(sizing, tuning, instruments, limits, feeders, shares)
        scheme = draw_naming_scheme(naming, _PREFIXES)
        tags = render_tags(scheme, _positions(feeders))

        return PlantSpec(
            plant_id=f"generation-{master_seed}",
            label=f"Islanded generating set, {feeders} feeder(s)",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families from the {self.family_id} family at master seed "
                f"{master_seed}. A model of an islanded generating set built from shaft inertia, "
                "a first-order fuel response, the three-phase power identity on each feeder and "
                "PI governor and AVR control. Not a model of any particular machine and not "
                "validated against one."
            ),
            process=self.process,
            parameters=parameters,
            units=_units(feeders),
            signals=_signals(parameters, feeders, tags),
            components=_components(feeders, tags),
            connections=_connections(feeders),
            controllers=_controllers(parameters, tags),
            couplings=_couplings(feeders, tags),
            control_network=modbus_network(
                poll_interval_seconds=parameters["scan_period_s"],
                subnet="10.6",
                per_plc=_register_plan(feeders, tags),
            ),
            write_authority=operator_authority(tags, (DISPATCH_SETPOINT, VOLTAGE_SETPOINT)),
            disturbance=_disturbance(events, limits, parameters, tags),
            roles=roles_from_tags(tags),
        )


def _shares(draw: StreamDraw, feeders: int) -> tuple[float, ...]:
    """Draw how the island's load splits across its feeders, normalised to sum to one.

    Normalising rather than drawing the last share as the remainder keeps every feeder drawn the
    same way, so no feeder is systematically the odd one out across seeds.
    """
    raw = [draw.uniform(f"feeder_weight_{index}", 0.5, 2.0) for index in range(feeders)]
    total = sum(raw)
    return tuple(weight / total for weight in raw)


def _parameters(
    sizing: StreamDraw,
    tuning: StreamDraw,
    instruments: StreamDraw,
    limits: Mapping[str, ParameterBound],
    feeders: int,
    shares: tuple[float, ...],
) -> dict[str, float]:
    """Draw the machine, its tuning and its instruments."""
    rated = bounded(sizing, limits, "rated_mw")
    load_factor = bounded(sizing, limits, "load_factor")
    nominal_hz = bounded(sizing, limits, "nominal_hz")
    inertia = bounded(sizing, limits, "inertia_hz_per_mw_s")
    fuel_tau = bounded(sizing, limits, "fuel_tau_s")
    nominal_kv = bounded(sizing, limits, "nominal_kv")
    power_factor_at = bounded(sizing, limits, "power_factor")
    voltage_tau = bounded(sizing, limits, "voltage_tau_s")
    scan_period = bounded(instruments, limits, "scan_period_s")
    step_headroom = bounded(sizing, limits, "load_step_headroom")
    # The step has to fit in what the machine has spare above its mean load, with a little
    # left over so the governor is never asked for more than the set can make.
    largest_load_step = min(0.25, max(0.95 - load_factor, 0.02) * step_headroom)
    sag_fraction = bounded(sizing, limits, "bus_drop_fraction")
    power_factor = power_factor_at
    # Current at rated output and nominal voltage, from the same identity the physics uses. The
    # machine's impedance is drawn as a per-unit sag and converted here, because a kV-per-amp
    # figure is meaningless without knowing how many amps the machine actually draws.
    full_current = rated * 1000.0 / (math.sqrt(3.0) * nominal_kv * power_factor)

    # Both regulators are tuned relative to the machine they are regulating, because a gain in
    # percent per hertz means nothing without knowing how much a percent of fuel moves the
    # frequency of *this* machine.
    #
    # The shaft is an integrator: df/dt = (output - demand) * inertia, and output follows fuel at
    # rated/100 MW per percent. So a percent of fuel moves the frequency at `shaft_gain` hertz
    # per second. Closing that loop no faster than a multiple of the fuel system's own lag, with
    # the integral slower again, is what keeps it stable on a 6 MW set and a 170 MW one alike.
    shaft_gain = rated / 100.0 * inertia
    droop = bounded(tuning, limits, "governor_droop_fraction")
    governor_integral_multiple = bounded(tuning, limits, "governor_integral_multiple")
    # How fast the governor must close the loop, from the job it has to do rather than from a
    # multiple of anything. A load step of `step` times rated output drives the frequency at
    # `step * rated * inertia` hertz per second; the governor must arrest that inside the droop
    # it is specified to hold, so its closed-loop time constant is the droop divided by that
    # rate. Then floored, because a loop cannot be faster than the rate it is updated at nor
    # faster than the fuel system it drives: a station polled every ten seconds cannot hold a
    # one-second lag however hard it pushes, and a tuning that ignores that is not aggressive,
    # it is bang-bang.
    worst_step_mw = rated * largest_load_step
    required_s = nominal_hz * droop / max(worst_step_mw * inertia, 1e-9)
    governor_closed_loop_s = max(required_s, 2.0 * fuel_tau, 2.0 * scan_period)
    # The bus is first-order rather than integrating: excitation spans 0.88 to 1.12 of nominal
    # voltage across its whole travel, so a percent of excitation is worth this many kilovolts.
    voltage_gain_kv_per_pct = 0.24 * nominal_kv / 100.0
    avr_loop_gain = bounded(tuning, limits, "avr_loop_gain")
    avr_integral_multiple = bounded(tuning, limits, "avr_integral_multiple")
    avr_timescale_s = max(voltage_tau, scan_period)
    parameters = {
        "feeders": float(feeders),
        "rated_mw": rated,
        "nominal_hz": nominal_hz,
        "load_factor": load_factor,
        "demand_base_mw": rated * load_factor,
        "demand_daily_fraction": bounded(sizing, limits, "demand_daily_fraction"),
        "inertia_hz_per_mw_s": inertia,
        "fuel_tau_s": fuel_tau,
        "nominal_kv": nominal_kv,
        "voltage_tau_s": voltage_tau,
        "bus_drop_fraction": sag_fraction,
        "bus_drop_kv_per_a": nominal_kv * sag_fraction / full_current,
        "full_load_current_a": full_current,
        "power_factor": power_factor,
        "load_step_headroom": step_headroom,
        "load_step_fraction": largest_load_step,
        "governor_droop_fraction": droop,
        "governor_closed_loop_s": governor_closed_loop_s,
        "governor_gain": 1.0 / (shaft_gain * governor_closed_loop_s),
        "governor_integral_multiple": governor_integral_multiple,
        "governor_integral_s": governor_closed_loop_s * governor_integral_multiple,
        "avr_loop_gain": avr_loop_gain,
        "avr_gain": avr_loop_gain / voltage_gain_kv_per_pct / avr_integral_multiple,
        "avr_integral_multiple": avr_integral_multiple,
        "avr_timescale_s": avr_timescale_s,
        "avr_integral_s": avr_timescale_s * avr_integral_multiple,
        "avr_bias_pct": bounded(tuning, limits, "avr_bias_pct"),
        "frequency_noise_hz": bounded(instruments, limits, "frequency_noise_hz"),
        "voltage_noise_fraction": bounded(instruments, limits, "voltage_noise_fraction"),
        "power_noise_fraction": bounded(instruments, limits, "power_noise_fraction"),
        "power_factor_noise": bounded(instruments, limits, "power_factor_noise"),
        "scan_period_s": scan_period,
    }
    for index, share in enumerate(shares):
        parameters[f"feeder_share_{index}"] = share
    return parameters


def _positions(feeders: int) -> tuple[tuple[RolePosition, str], ...]:
    """Return every role position this plant has, with the unit its signal carries."""
    positions: list[tuple[RolePosition, str]] = [
        ((FUEL, 0, 0), "pct"),
        ((FREQUENCY, 0, 0), "Hz"),
        ((OUTPUT, 0, 0), "MW"),
        ((EXCITATION, 0, 0), "pct"),
        ((BUS_VOLTAGE, 0, 0), "kV"),
        ((DISPATCH_SETPOINT, 0, 0), "MW"),
        ((VOLTAGE_SETPOINT, 0, 0), "kV"),
    ]
    for feeder in range(feeders):
        positions.append(((FEEDER_POWER, 0, feeder), "MW"))
        positions.append(((FEEDER_CURRENT, 0, feeder), "A"))
        positions.append(((POWER_FACTOR, 0, feeder), ""))
    return tuple(positions)


def _units(feeders: int) -> tuple[PhysicalUnit, ...]:
    """Return the turbine, the generator and one unit per outgoing feeder."""
    units = [
        PhysicalUnit(unit_id=_TURBINE, label="Prime mover and fuel system"),
        PhysicalUnit(unit_id=_GENERATOR, label="Generator, excitation and bus"),
    ]
    units.extend(
        PhysicalUnit(unit_id=feeder_unit(feeder), label=f"Outgoing feeder {feeder + 1}")
        for feeder in range(feeders)
    )
    return tuple(units)


def feeder_unit(feeder: int) -> str:
    """Return the physical unit identifier one feeder's metering sits on."""
    return f"feeder{feeder + 1}"


def _signals(
    parameters: Mapping[str, float], feeders: int, tags: Mapping[RolePosition, str]
) -> tuple[SignalSpec, ...]:
    """Return the instruments, with the spans and noise this plant was drawn with."""
    rated = parameters["rated_mw"]
    nominal_kv = parameters["nominal_kv"]
    nominal_hz = parameters["nominal_hz"]
    voltage_noise = parameters["voltage_noise_fraction"] * nominal_kv
    power_noise = parameters["power_noise_fraction"] * rated
    full_current = parameters["full_load_current_a"]

    signals = [
        SignalSpec(
            key=tags[(FUEL, 0, 0)],
            label="Fuel valve position",
            unit="%",
            kind=SignalKind.ACTUATOR,
            physical_unit=_TURBINE,
            low=0.0,
            high=100.0,
            noise_stddev=parameters["power_noise_fraction"] * 10.0,
        ),
        SignalSpec(
            key=tags[(OUTPUT, 0, 0)],
            label="Generator output",
            unit="MW",
            kind=SignalKind.SENSOR,
            physical_unit=_GENERATOR,
            low=0.0,
            high=rated * 1.15,
            noise_stddev=power_noise,
            drift_amplitude=power_noise * 0.4,
        ),
        SignalSpec(
            key=tags[(FREQUENCY, 0, 0)],
            label="Bus frequency",
            unit="Hz",
            kind=SignalKind.SENSOR,
            physical_unit=_GENERATOR,
            low=nominal_hz * 0.88,
            high=nominal_hz * 1.12,
            noise_stddev=parameters["frequency_noise_hz"],
            drift_amplitude=parameters["frequency_noise_hz"] * 0.3,
        ),
        SignalSpec(
            key=tags[(EXCITATION, 0, 0)],
            label="Excitation",
            unit="%",
            kind=SignalKind.ACTUATOR,
            physical_unit=_GENERATOR,
            low=0.0,
            high=100.0,
            noise_stddev=parameters["power_noise_fraction"] * 10.0,
        ),
        SignalSpec(
            key=tags[(BUS_VOLTAGE, 0, 0)],
            label="Bus voltage",
            unit="kV",
            kind=SignalKind.SENSOR,
            physical_unit=_GENERATOR,
            low=0.0,
            high=nominal_kv * 1.3,
            noise_stddev=voltage_noise,
            drift_amplitude=voltage_noise * 0.4,
        ),
        SignalSpec(
            key=tags[(DISPATCH_SETPOINT, 0, 0)],
            label="Dispatch setpoint",
            unit="MW",
            kind=SignalKind.SETPOINT,
            physical_unit=_GENERATOR,
            low=0.0,
            high=rated,
            noise_stddev=0.0,
        ),
        SignalSpec(
            key=tags[(VOLTAGE_SETPOINT, 0, 0)],
            label="Bus voltage setpoint",
            unit="kV",
            kind=SignalKind.SETPOINT,
            physical_unit=_GENERATOR,
            low=0.0,
            high=nominal_kv * 1.3,
            noise_stddev=0.0,
        ),
    ]
    for feeder in range(feeders):
        unit = feeder_unit(feeder)
        signals.append(
            SignalSpec(
                key=tags[(FEEDER_POWER, 0, feeder)],
                label=f"Feeder {feeder + 1} power",
                unit="MW",
                kind=SignalKind.SENSOR,
                physical_unit=unit,
                low=0.0,
                high=rated * 1.15,
                noise_stddev=power_noise,
                drift_amplitude=power_noise * 0.4,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(FEEDER_CURRENT, 0, feeder)],
                label=f"Feeder {feeder + 1} current",
                unit="A",
                kind=SignalKind.SENSOR,
                physical_unit=unit,
                low=0.0,
                high=full_current * 1.3,
                noise_stddev=parameters["power_noise_fraction"] * full_current,
                drift_amplitude=parameters["power_noise_fraction"] * full_current * 0.4,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(POWER_FACTOR, 0, feeder)],
                label=f"Feeder {feeder + 1} power factor",
                unit="ratio",
                kind=SignalKind.SENSOR,
                physical_unit=unit,
                low=0.0,
                high=1.0,
                noise_stddev=parameters["power_factor_noise"],
                drift_amplitude=parameters["power_factor_noise"] * 0.4,
            )
        )
    return tuple(signals)


def _components(feeders: int, tags: Mapping[RolePosition, str]) -> tuple[Component, ...]:
    """Return what the station is made of, with every signal owned exactly once."""
    components = [
        Component(
            component_id="fuel_valve",
            kind=ComponentKind.VALVE,
            label="Fuel control valve",
            physical_unit=_TURBINE,
            signals=(tags[(FUEL, 0, 0)],),
            description="How much fuel the machine is given. The only handle it has on power.",
        ),
        Component(
            component_id="prime_mover",
            kind=ComponentKind.TURBINE,
            label="Prime mover",
            physical_unit=_TURBINE,
            description="Burns the fuel and turns the shaft.",
        ),
        Component(
            component_id="generator",
            kind=ComponentKind.GENERATOR,
            label="Synchronous generator",
            physical_unit=_GENERATOR,
            signals=(tags[(OUTPUT, 0, 0)], tags[(FREQUENCY, 0, 0)]),
            description=(
                "Turns shaft power into electrical power. With no grid behind the island, the "
                "frequency is this machine's own shaft speed: draw more than it makes and "
                "everything slows down together."
            ),
        ),
        Component(
            component_id="exciter",
            kind=ComponentKind.OTHER,
            label="Excitation system",
            physical_unit=_GENERATOR,
            signals=(tags[(EXCITATION, 0, 0)],),
            description="Feeds the field winding. More excitation, higher voltage.",
        ),
        Component(
            component_id="station_bus",
            kind=ComponentKind.BUS,
            label="Station bus",
            physical_unit=_GENERATOR,
            signals=(tags[(BUS_VOLTAGE, 0, 0)],),
            description=(
                "Where every feeder connects. Its voltage sags as total current rises, which is "
                "what couples the feeders to one another."
            ),
        ),
        Component(
            component_id="dispatch",
            kind=ComponentKind.CONTROLLER,
            label="Dispatch instruction",
            physical_unit=_GENERATOR,
            signals=(tags[(DISPATCH_SETPOINT, 0, 0)],),
            description="How much the operator has told the set to make.",
        ),
        Component(
            component_id="voltage_target",
            kind=ComponentKind.CONTROLLER,
            label="Voltage target",
            physical_unit=_GENERATOR,
            signals=(tags[(VOLTAGE_SETPOINT, 0, 0)],),
            description="The bus voltage the regulator is holding to.",
        ),
    ]
    for feeder in range(feeders):
        components.append(
            Component(
                component_id=f"feeder_{feeder}",
                kind=ComponentKind.FEEDER,
                label=f"Outgoing feeder {feeder + 1}",
                physical_unit=feeder_unit(feeder),
                signals=(
                    tags[(FEEDER_POWER, 0, feeder)],
                    tags[(FEEDER_CURRENT, 0, feeder)],
                    tags[(POWER_FACTOR, 0, feeder)],
                ),
                description=(
                    "A circuit leaving the site, with its metering. Its power, its voltage and "
                    "its current have to multiply out — that is arithmetic, not a trend."
                ),
            )
        )
        components.append(
            Component(
                component_id=f"customers_{feeder}",
                kind=ComponentKind.LOAD,
                label=f"Feeder {feeder + 1} customers",
                physical_unit=feeder_unit(feeder),
                description="Whoever is on this circuit. Nothing here decides what they draw.",
            )
        )
    return tuple(components)


def _connections(feeders: int) -> tuple[Connection, ...]:
    """Return which way the energy goes, and which instruction drives what."""
    connections = [
        Connection(
            source="fuel_valve", target="prime_mover", medium="fuel", label="fuel to the burner"
        ),
        Connection(
            source="prime_mover", target="generator", medium="shaft", label="shaft power to rotor"
        ),
        Connection(
            source="exciter", target="generator", medium="electrical", label="field current"
        ),
        Connection(
            source="generator",
            target="station_bus",
            medium="electrical",
            label="machine terminals to the bus",
        ),
        Connection(
            source="dispatch",
            target="fuel_valve",
            medium="signal",
            label="dispatch paces the governor's feedforward",
        ),
        Connection(
            source="voltage_target",
            target="exciter",
            medium="signal",
            label="voltage target drives the regulator",
        ),
    ]
    for feeder in range(feeders):
        connections.append(
            Connection(
                source="station_bus",
                target=f"feeder_{feeder}",
                medium="electrical",
                label="bus to the outgoing feeder",
            )
        )
        connections.append(
            Connection(
                source=f"feeder_{feeder}",
                target=f"customers_{feeder}",
                medium="electrical",
                label="feeder to its customers",
            )
        )
    return tuple(connections)


def _controllers(
    parameters: Mapping[str, float], tags: Mapping[RolePosition, str]
) -> tuple[ControllerSpec, ...]:
    """Return the governor and the AVR, on the tuning this plant was drawn with."""
    return (
        ControllerSpec(
            controller_id=GOVERNOR,
            kind=ControllerKind.PI,
            measurement=tags[(FREQUENCY, 0, 0)],
            setpoint_value=parameters["nominal_hz"],
            output=tags[(FUEL, 0, 0)],
            gain=parameters["governor_gain"],
            integral_time_seconds=parameters["governor_integral_s"],
            low=0.0,
            high=100.0,
            description=(
                "Holds the island at nominal frequency by moving the fuel valve. Its feedforward "
                "is paced from the dispatch setpoint by the template, so it is not a constant "
                "and is not declared here."
            ),
        ),
        ControllerSpec(
            controller_id=AVR,
            kind=ControllerKind.PI,
            measurement=tags[(BUS_VOLTAGE, 0, 0)],
            setpoint=tags[(VOLTAGE_SETPOINT, 0, 0)],
            output=tags[(EXCITATION, 0, 0)],
            gain=parameters["avr_gain"],
            integral_time_seconds=parameters["avr_integral_s"],
            low=0.0,
            high=100.0,
            bias=parameters["avr_bias_pct"],
            description="Holds the bus at its target voltage by varying excitation.",
        ),
    )


def _couplings(feeders: int, tags: Mapping[RolePosition, str]) -> tuple[Coupling, ...]:
    """Return the plant's claim about what makes its signals related."""
    couplings = [
        Coupling(
            driven=tags[(OUTPUT, 0, 0)],
            drivers=(tags[(FUEL, 0, 0)],),
            kind=CouplingKind.LAG,
            relation="output follows the fuel valve with a first-order lag",
        ),
        Coupling(
            driven=tags[(FREQUENCY, 0, 0)],
            drivers=(tags[(OUTPUT, 0, 0)], *(tags[(FEEDER_POWER, 0, f)] for f in range(feeders))),
            kind=CouplingKind.INTEGRATION,
            relation=(
                "frequency is the running total of output less what the feeders are drawing, "
                "scaled by the machine's inertia"
            ),
        ),
        Coupling(
            driven=tags[(FUEL, 0, 0)],
            drivers=(tags[(FREQUENCY, 0, 0)], tags[(DISPATCH_SETPOINT, 0, 0)]),
            kind=CouplingKind.CONTROL,
            relation="the governor holds frequency at nominal, paced by dispatch",
        ),
        Coupling(
            driven=tags[(BUS_VOLTAGE, 0, 0)],
            drivers=(
                tags[(EXCITATION, 0, 0)],
                *(tags[(FEEDER_CURRENT, 0, f)] for f in range(feeders)),
            ),
            kind=CouplingKind.LAG,
            relation="bus voltage rises with excitation and sags with total current drawn",
        ),
        Coupling(
            driven=tags[(EXCITATION, 0, 0)],
            drivers=(tags[(BUS_VOLTAGE, 0, 0)], tags[(VOLTAGE_SETPOINT, 0, 0)]),
            kind=CouplingKind.CONTROL,
            relation="the regulator holds bus voltage at its setpoint",
        ),
    ]
    for feeder in range(feeders):
        couplings.append(
            Coupling(
                driven=tags[(FEEDER_CURRENT, 0, feeder)],
                drivers=(
                    tags[(FEEDER_POWER, 0, feeder)],
                    tags[(BUS_VOLTAGE, 0, 0)],
                    tags[(POWER_FACTOR, 0, feeder)],
                ),
                kind=CouplingKind.ALGEBRAIC,
                relation=(
                    "current is power divided by root-three times voltage times power factor; an "
                    "identity, not a trend"
                ),
            )
        )
    return tuple(couplings)


def _register_plan(
    feeders: int, tags: Mapping[RolePosition, str]
) -> tuple[tuple[list[str], list[str]], ...]:
    """Return what the station PLC exposes read-only, and what an operator may write."""
    readable = [
        tags[(FUEL, 0, 0)],
        tags[(OUTPUT, 0, 0)],
        tags[(FREQUENCY, 0, 0)],
        tags[(EXCITATION, 0, 0)],
        tags[(BUS_VOLTAGE, 0, 0)],
    ]
    for feeder in range(feeders):
        readable.append(tags[(FEEDER_POWER, 0, feeder)])
        readable.append(tags[(FEEDER_CURRENT, 0, feeder)])
        readable.append(tags[(POWER_FACTOR, 0, feeder)])
    writable = [tags[(DISPATCH_SETPOINT, 0, 0)], tags[(VOLTAGE_SETPOINT, 0, 0)]]
    return ((readable, writable),)


def _disturbance(
    draw: StreamDraw,
    limits: Mapping[str, ParameterBound],
    parameters: Mapping[str, float],
    tags: Mapping[RolePosition, str],
) -> DisturbanceSpec:
    """Draw what normally happens to this station, and how far apart."""
    gap_low = round(bounded(draw, limits, "event_gap_low_steps"))
    gap_high = gap_low + round(bounded(draw, limits, "event_gap_span_steps"))
    step = parameters["load_step_fraction"] * parameters["rated_mw"]
    step_steps = round(bounded(draw, limits, "load_step_steps"))
    shift = bounded(draw, limits, "power_factor_shift")
    switching_steps = round(bounded(draw, limits, "switching_steps"))
    dispatch = tags[(DISPATCH_SETPOINT, 0, 0)]
    voltage = tags[(VOLTAGE_SETPOINT, 0, 0)]
    base = parameters["demand_base_mw"]
    nominal_kv = parameters["nominal_kv"]

    return DisturbanceSpec(
        event_plans=(
            EventPlanSpec(
                kind=LOAD_STEP,
                label="Industrial customer picks up or sheds load",
                duration_steps=step_steps,
                parameter_ranges={"load_step_mw": (-step, step)},
                detail="customer load stepped by:",
            ),
            EventPlanSpec(
                kind=_DISPATCH_CHANGE,
                label="Operator changes the dispatch setpoint",
                duration_steps=0,
                writes=(dispatch,),
                parameter_ranges={dispatch: (base * 0.85, base * 1.15)},
                detail="new dispatch setpoint:",
            ),
            EventPlanSpec(
                kind=FEEDER_SWITCHING,
                label="Switching changes the load mix, so the power factor moves",
                duration_steps=switching_steps,
                parameter_ranges={"power_factor_shift": (-shift, shift)},
                detail="power factor shifted by:",
            ),
            EventPlanSpec(
                kind=_VOLTAGE_SETPOINT_CHANGE,
                label="Operator changes the bus voltage setpoint",
                duration_steps=0,
                writes=(voltage,),
                parameter_ranges={voltage: (nominal_kv * 0.97, nominal_kv * 1.03)},
                detail="new bus voltage setpoint:",
            ),
        ),
        first_start_floor=60,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_family(PowerFamily())
