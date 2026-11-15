"""An islanded generating set carrying however many feeders its spec gives it.

PART R2's third generated process. Its distinguishing feature is that the relationship holding its
signals together is an *identity* rather than a lag or an integral: on every feeder,

    power = sqrt(3) * voltage * current * power factor

and that has to hold at every sample on every feeder, because it is arithmetic rather than
dynamics. An attacker who moves a current reading and leaves the power and the voltage alone has
not made a signal unusual; it has made the three of them contradict each other. That is the
cheapest possible thing for a joint model to catch and the most expensive thing for a
single-signal model to notice, which is exactly why this process is worth generating.

The second feature is that frequency is not a measurement of anything external. The island has no
grid behind it, so the shaft's speed *is* the frequency, and it falls whenever the island draws
more than the machine is making. Take load and everything slows down together.

**The implicit loop is solved exactly, not stepped around.** Bus voltage depends on total current
and total current depends on bus voltage. The first attempt here computed each feeder's current
from the *previous* sample's voltage, which is one sample of lag — and measuring it showed the
identity violated by up to 21% on honest data, because a machine whose excitation is moving
quickly moves its voltage a long way in one sample. An identity that only holds to a fifth is not
an identity, and the whole value of this process is that a detector can trust it.

It needs no approximation. Writing ``A`` for the voltage the excitation alone would give and
``K = sum(P / (sqrt(3) * pf))`` for the load, the two statements

    V = A - drop * I_total        and        I_total = K / V

combine into ``V^2 - A*V + drop*K = 0``, whose positive root is the answer. So the lag lives where
the physics actually puts it — on the field's response to excitation — and the load-dependent sag
is algebraic and instantaneous, which is what it is. The identity then holds to the last bit by
construction.

A negative discriminant means the bus cannot supply the load at any voltage: real voltage
collapse. The template returns the maximum-power-transfer voltage and carries on rather than
raising, because a plant that collapses is one PART R3's validity gate should refuse on the
evidence of a whole run, not one that should crash mid-sample.

**What this is not.** A model of a generating set written from the general shape of one — not a
model of any particular machine, and not validated against one. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator

from phos.synth.command import CommandSource
from phos.synth.plant import (
    BenignEvent,
    Plant,
    PlantDescription,
    PlantStep,
    RunSpec,
    lay_out_events,
)
from phos.synth.plant_spec import PlantSpec, fixed_setpoint, pi_controller
from phos.synth.process import accumulate, clamp, cycle_factor, first_order
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "BUS_VOLTAGE",
    "DISPATCH_SETPOINT",
    "EXCITATION",
    "FEEDER_CURRENT",
    "FEEDER_POWER",
    "FEEDER_SWITCHING",
    "FREQUENCY",
    "FUEL",
    "GENERATION_PROCESS",
    "LOAD_STEP",
    "OUTPUT",
    "POWER_FACTOR",
    "VOLTAGE_SETPOINT",
    "GenerationPlant",
]

GENERATION_PROCESS: Final = "generation-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

FUEL: Final = "fuel"
FREQUENCY: Final = "frequency"
OUTPUT: Final = "output"
EXCITATION: Final = "excitation"
BUS_VOLTAGE: Final = "bus_voltage"
DISPATCH_SETPOINT: Final = "dispatch_setpoint"
VOLTAGE_SETPOINT: Final = "voltage_setpoint"
FEEDER_POWER: Final = "feeder_power"
FEEDER_CURRENT: Final = "feeder_current"
POWER_FACTOR: Final = "power_factor"
"""The role vocabulary this process reads."""

LOAD_STEP: Final = "customer_load_step"
"""A benign event: a customer picks up or sheds load and the machine has to follow."""

FEEDER_SWITCHING: Final = "feeder_switching"
"""A benign event: switching changes the mix of load, so the power factor moves."""

GOVERNOR: Final = "governor"
AVR: Final = "avr"
"""The two regulators. Fixed identifiers; a controller id never reaches the wire."""

OPEN_CIRCUIT_STATE: Final = "_open_circuit_kv"
"""Internal state: the voltage the excitation alone would give, before any load pulls it down.

Internal because no instrument is on it — a real station measures the loaded bus, not the
open-circuit terminal voltage — and it is the field's lagged response, which is the one part of
the electrical answer that is dynamic rather than algebraic."""

ROOT_THREE: Final = math.sqrt(3.0)
"""The three-phase constant in the power identity. Derived, so not a drawn parameter."""


class GenerationPlant(Plant):
    """A machine on an island, with a governor, an AVR and however many feeders.

    See the module docstring for the process, the identity and the one approximation.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the machine and its regulators for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None``. See
                `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile.
            plant_spec: The plant to build. Required: this is a process, not a plant.

        Raises:
            ValueError: If no spec is given.
        """
        if plant_spec is None:
            raise ValueError(
                "GenerationPlant has no default plant: it is a process, not a plant. Draw one "
                "from the power family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        p = plant_spec.parameters
        self._feeders = round(p["feeders"])
        self._rated_mw = p["rated_mw"]
        self._nominal_hz = p["nominal_hz"]
        self._inertia_hz_per_mw_s = p["inertia_hz_per_mw_s"]
        self._fuel_tau_s = p["fuel_tau_s"]
        self._nominal_kv = p["nominal_kv"]
        self._voltage_tau_s = p["voltage_tau_s"]
        self._bus_drop_kv_per_a = p["bus_drop_kv_per_a"]
        self._power_factor = p["power_factor"]
        self._demand_base_mw = p["demand_base_mw"]
        self._demand_daily_fraction = p["demand_daily_fraction"]
        self._shares = tuple(p[f"feeder_share_{index}"] for index in range(self._feeders))

        self._governor = pi_controller(plant_spec, GOVERNOR)
        self._avr = pi_controller(plant_spec, AVR)
        self._governor_setpoint = fixed_setpoint(plant_spec, GOVERNOR)
        self._avr_bias = plant_spec.controller(AVR).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What this set is, as the spec declared it."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start synchronised at nominal frequency and voltage, carrying the opening load."""
        demand = self._demand(0.0, None)
        voltage = self._nominal_kv
        state: dict[str, float] = {
            OPEN_CIRCUIT_STATE: voltage,
            self._tag(FUEL): 100.0 * demand / self._rated_mw,
            self._tag(FREQUENCY): self._nominal_hz,
            self._tag(OUTPUT): demand,
            self._tag(EXCITATION): 50.0,
            self._tag(BUS_VOLTAGE): voltage,
            self._tag(DISPATCH_SETPOINT): demand,
            self._tag(VOLTAGE_SETPOINT): voltage,
        }
        for feeder in range(self._feeders):
            power = demand * self._shares[feeder]
            state[self._tag(FEEDER_POWER, feeder)] = power
            state[self._tag(POWER_FACTOR, feeder)] = self._power_factor
            state[self._tag(FEEDER_CURRENT, feeder)] = _current(power, voltage, self._power_factor)
        return state

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Lay this plant's own kinds of operational event through the run, round-robin."""
        disturbance = self._plant_spec.disturbance
        return lay_out_events(
            rng,
            spec,
            disturbance.plans(),
            first_start_step=disturbance.first_start_step(spec.n_steps),
            gap_steps=disturbance.gap_steps,
        )

    def begin_event(self, event: BenignEvent) -> None:
        """Apply the lasting part of an event: a moved dispatch or voltage setpoint."""
        for key, value in event.parameters.items():
            role = self._plant_spec.role_of(key)
            if role is None or key not in self._state:
                continue
            if role.role in (DISPATCH_SETPOINT, VOLTAGE_SETPOINT):
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run the governor and the AVR, both on what the instruments reported."""
        fuel = self._governor.update(
            measurement=report[self._tag(FREQUENCY)],
            setpoint=self._governor_setpoint,
            dt_seconds=dt_seconds,
            bias=100.0 * report[self._tag(DISPATCH_SETPOINT)] / self._rated_mw,
        )
        excitation = self._avr.update(
            measurement=report[self._tag(BUS_VOLTAGE)],
            setpoint=report[self._tag(VOLTAGE_SETPOINT)],
            dt_seconds=dt_seconds,
            bias=self._avr_bias,
        )
        return {self._tag(FUEL): fuel, self._tag(EXCITATION): excitation}

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the machine one sample: load, then the shaft, then the electrical answer."""
        demand = self._demand(elapsed_hours, active)
        fuel = clamp(actuators[self._tag(FUEL)], 0.0, 100.0)
        excitation = clamp(actuators[self._tag(EXCITATION)], 0.0, 100.0)

        output = first_order(
            state[self._tag(OUTPUT)],
            target=fuel / 100.0 * self._rated_mw,
            dt_seconds=dt_seconds,
            tau_seconds=self._fuel_tau_s,
        )
        frequency = accumulate(
            state[self._tag(FREQUENCY)],
            rate_per_second=(output - demand) * self._inertia_hz_per_mw_s,
            dt_seconds=dt_seconds,
            low=self._nominal_hz * 0.9,
            high=self._nominal_hz * 1.1,
        )

        # The field's response to excitation is the dynamic part; the sag under load is
        # algebraic. See the module docstring for why they are separated.
        open_circuit = first_order(
            state[OPEN_CIRCUIT_STATE],
            target=self._nominal_kv * (0.88 + 0.24 * excitation / 100.0),
            dt_seconds=dt_seconds,
            tau_seconds=self._voltage_tau_s,
        )
        shift = self._power_factor_shift(active)
        factors = [clamp(self._power_factor + shift, 0.6, 1.0) for _ in range(self._feeders)]
        powers = [demand * share for share in self._shares]
        load = sum(
            power * 1000.0 / (ROOT_THREE * factor)
            for power, factor in zip(powers, factors, strict=True)
        )
        voltage = _loaded_voltage(open_circuit, load, self._bus_drop_kv_per_a)

        advanced: dict[str, float] = {OPEN_CIRCUIT_STATE: open_circuit}
        for feeder in range(self._feeders):
            advanced[self._tag(FEEDER_POWER, feeder)] = powers[feeder]
            advanced[self._tag(POWER_FACTOR, feeder)] = factors[feeder]
            advanced[self._tag(FEEDER_CURRENT, feeder)] = _current(
                powers[feeder], voltage, factors[feeder]
            )

        advanced[self._tag(FUEL)] = fuel
        advanced[self._tag(EXCITATION)] = excitation
        advanced[self._tag(OUTPUT)] = output
        advanced[self._tag(FREQUENCY)] = frequency
        advanced[self._tag(BUS_VOLTAGE)] = max(voltage, 0.0)
        advanced[self._tag(DISPATCH_SETPOINT)] = state[self._tag(DISPATCH_SETPOINT)]
        advanced[self._tag(VOLTAGE_SETPOINT)] = state[self._tag(VOLTAGE_SETPOINT)]
        return advanced

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return the two balances this machine owes: the power identity and the shaft.

        The identity — power equals root-three times voltage times current times power factor on
        every feeder — is arithmetic rather than dynamics, so its residual is machine epsilon by
        construction and checking it is checking that `advance` still solves the loop exactly
        rather than stepping around it. That is worth a check precisely because it was got wrong
        once: an earlier version computed current from the previous sample's voltage and violated
        the identity by a fifth.

        The shaft balance is the dynamic one: frequency is the running total of what the machine
        made less what the island drew, scaled by the machine's inertia.

        Args:
            steps: Every sample of the run, in order.
            interval_seconds: The integration step.

        Returns:
            ``{"feeder N identity": residual, "shaft": residual}``.
        """
        residuals: dict[str, float] = {}
        if len(steps) < 2:
            return residuals

        for feeder in range(self._feeders):
            worst = 0.0
            for step in steps:
                values = step.truth.values
                power = values[self._tag(FEEDER_POWER, feeder)]
                if power <= 1e-9:
                    continue
                implied = (
                    ROOT_THREE
                    * values[self._tag(BUS_VOLTAGE)]
                    * values[self._tag(FEEDER_CURRENT, feeder)]
                    * values[self._tag(POWER_FACTOR, feeder)]
                    / 1000.0
                )
                worst = max(worst, abs(implied - power) / power)
            residuals[f"feeder {feeder + 1} identity"] = worst

        unmatched = 0.0
        movement = 0.0
        for step in steps[:-1]:
            values = step.truth.values
            drawn = sum(values[self._tag(FEEDER_POWER, feeder)] for feeder in range(self._feeders))
            imbalance = values[self._tag(OUTPUT)] - drawn
            unmatched += imbalance * interval_seconds
            movement += abs(imbalance) * interval_seconds
        swing = (
            steps[-1].truth.values[self._tag(FREQUENCY)]
            - steps[0].truth.values[self._tag(FREQUENCY)]
        )
        predicted = unmatched * self._inertia_hz_per_mw_s
        # Normalised by all the frequency movement the imbalance could have caused, not by the
        # net swing. A working governor holds frequency, so both the net swing and the net
        # imbalance are near zero, and dividing by either turns a rounding error into a residual
        # of order one. The question the residual should answer is: of the frequency movement
        # this imbalance accounts for, how much is unexplained?
        scale = max(movement * self._inertia_hz_per_mw_s, abs(swing), 1e-9)
        residuals["shaft"] = (predicted - swing) / scale
        return residuals

    def tracking_loops(self) -> tuple[str, ...]:
        """Both regulators. A governor that does not hold frequency is not a generating set."""
        return (GOVERNOR, AVR)

    def _demand(self, elapsed_hours: float, active: BenignEvent | None) -> float:
        """Return what the island is drawing: a daily rhythm, stepped by a customer."""
        swing = cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._demand_base_mw * self._demand_daily_fraction,
            phase_hours=8.0,
        )
        demand = self._demand_base_mw + swing
        if active is not None and active.kind == LOAD_STEP:
            demand += active.parameters.get("load_step_mw", 0.0)
        return clamp(demand, self._rated_mw * 0.05, self._rated_mw)

    def _power_factor_shift(self, active: BenignEvent | None) -> float:
        """Return how far switching has moved the power factor, or zero."""
        if active is None or active.kind != FEEDER_SWITCHING:
            return 0.0
        return active.parameters.get("power_factor_shift", 0.0)

    def _tag(self, role: str, stage: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=0, stage=stage)


def _current(power_mw: float, voltage_kv: float, power_factor: float) -> float:
    """Return feeder current in amps from the three-phase power identity.

    ``P = sqrt(3) * V * I * cos(phi)``, rearranged for current, with megawatts and kilovolts
    cancelling to amps. Guarded against a collapsed bus rather than dividing by zero: a plant
    whose voltage has gone to nothing is a plant the validity gate should refuse, and returning
    an infinity here would turn that into a crash much further downstream.
    """
    denominator = ROOT_THREE * voltage_kv * power_factor
    if denominator <= 1e-9:
        return 0.0
    return power_mw * 1000.0 / denominator


def _loaded_voltage(open_circuit_kv: float, load: float, drop_kv_per_a: float) -> float:
    """Return the bus voltage under load, as the positive root of ``V^2 - A*V + drop*K = 0``.

    Args:
        open_circuit_kv: The voltage the excitation alone would give, ``A``.
        load: ``sum(P / (sqrt(3) * pf))`` over the feeders, in kV·A — the ``K`` of the quadratic.
        drop_kv_per_a: How far the bus sags per amp.

    Returns:
        The loaded voltage. When the discriminant is negative the bus cannot supply this load at
        any voltage — real voltage collapse — and the maximum-power-transfer voltage ``A/2`` is
        returned so the run continues and PART R3's gate can refuse the plant on the evidence of
        the whole run rather than on one sample.
    """
    discriminant = open_circuit_kv * open_circuit_kv - 4.0 * drop_kv_per_a * load
    if discriminant <= 0.0:
        return open_circuit_kv / 2.0
    return (open_circuit_kv + math.sqrt(discriminant)) / 2.0


register_template(GENERATION_PROCESS, GenerationPlant)
