"""Heated vessels in series, each fighting the stream running through it and the room around it.

PART R2's second generated process, and the one that carries a different kind of coupling from
`level_flow`. A tank's level is an integral of two flows and nothing else. A vessel's temperature
is an integral of *three* competing terms — the heat its heater puts in, the heat the stream
through it carries away, and the heat it loses to the room — and the balance between them shifts
with the throughput and with the weather. A reading that is plausible on a cold morning at low
throughput is impossible on a warm afternoon at high throughput, and no single-signal model can
tell the difference.

**The process.** Fluid passes through a chain of heated vessels. Each has a temperature
transmitter, a heater whose duty is set by its own PI loop, and a residence time set by how much
is in it and how fast the stream is moving. Each vessel's inlet is the one above it's outlet, so
a disturbance at the front of the chain arrives at the back late and smeared. Trains may run side
by side.

**The energy balance, and why it is written the way it is.** The honest statement is

    C dT/dt = flow * cp * (inlet - T) + heater - UA * (T - ambient)

with ``C`` the vessel's heat capacity. Stepped explicitly, the flow term has a gain above two per
sample whenever the residence time is shorter than half the sample interval — a vessel that
empties faster than we look at it — and the temperature oscillates and diverges. That is a
numerical artefact and not a plant. So the flow term is integrated as the exponential approach it
actually is, with the residence time as its time constant, and the heater and the ambient loss are
added explicitly, because both are small against ``C`` over one sample. `phos.synth.plants.batch`
takes the same care over its vessel wall for the same reason.

**What the spec decides and this module obeys.** How many trains and how many vessels in each;
how much is in every vessel and what its contents' heat capacity is; how big every heater is; how
well insulated the vessels are; the throughput and its daily swing; the weather; every loop's
tuning; the instruments and their error; the scan period; and every tag name. Found by role, never
by name.

**What this is not.** A model of a heated process written from the general shape of one — not a
model of any particular plant, and not validated against one. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

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
from phos.synth.plant_spec import PlantSpec, pi_controller
from phos.synth.process import PiController, clamp, cycle_factor, first_order
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "AMBIENT",
    "COLD_FEED",
    "DUTY",
    "FLOW",
    "TEMPERATURE",
    "TEMPERATURE_SETPOINT",
    "THERMAL_PROCESS",
    "THROUGHPUT_CHANGE",
    "ThermalPlant",
    "duty_loop_id",
]

THERMAL_PROCESS: Final = "thermal-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

TEMPERATURE: Final = "temperature"
TEMPERATURE_SETPOINT: Final = "temperature_setpoint"
DUTY: Final = "duty"
FLOW: Final = "flow"
AMBIENT: Final = "ambient"
"""The role vocabulary this process reads."""

COLD_FEED: Final = "cold_feed_excursion"
"""A benign event: what arrives at the front of the chain turns colder for a while."""

THROUGHPUT_CHANGE: Final = "throughput_change"
"""A benign event: the stream through a train is stepped up or down."""

_SETPOINT_CHANGE: Final = "temperature_setpoint_change"
"""A benign event: an operator moves a vessel's target temperature."""


def duty_loop_id(train: int, stage: int) -> str:
    """Return the controller identifier of one vessel's temperature loop.

    Internal: a controller identifier never reaches the telemetry, the capture or a detector, so
    fixing it costs nothing that tag-name randomisation buys and lets the template ask for its
    own loops by name.
    """
    return f"temperature_t{train}_s{stage}"


class ThermalPlant(Plant):
    """A chain of heated vessels, sized, insulated and tuned by its spec.

    See the module docstring for the process and the energy balance.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the chain and its loops for one run.

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
                "ThermalPlant has no default plant: it is a process, not a plant. Draw one from "
                "the thermal family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        p = plant_spec.parameters
        self._trains = round(p["trains"])
        self._stages = round(p["stages"])
        self._holdup_kg = p["holdup_kg"]
        self._heat_capacity = p["heat_capacity_kj_per_kg_k"]
        self._rated_kw = p["heater_rated_kw"]
        self._ua_kw_per_k = p["ua_ambient_kw_per_k"]
        self._feed_temp_c = p["feed_temp_c"]
        self._ambient_base_c = p["ambient_base_c"]
        self._ambient_daily_c = p["ambient_daily_c"]
        self._flow_base_kgph = p["flow_base_kgph"]
        self._flow_daily_fraction = p["flow_daily_fraction"]
        self._temp_setpoint_c = p["temperature_setpoint_c"]
        self._temp_high_c = p["temperature_span_c"]

        self._ambient_tag = plant_spec.tags_with_role(AMBIENT)[0]
        self._loops: dict[tuple[int, int], PiController] = {}
        self._biases: dict[tuple[int, int], float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                loop = duty_loop_id(train, stage)
                self._loops[(train, stage)] = pi_controller(plant_spec, loop)
                self._biases[(train, stage)] = plant_spec.controller(loop).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What this chain is, as the spec declared it."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start every vessel at its target, with the duty that holds it there.

        Starting settled rather than cold is deliberate: a run that opens with every heater at
        full duty spends its first hour in a warm-up nothing else in the corpus resembles, and a
        model fitted on it learns the warm-up.
        """
        ambient = self._ambient(0.0)
        flow = self._flow(0.0, None, 0)
        state: dict[str, float] = {self._ambient_tag: ambient}
        for train in range(self._trains):
            state[self._tag(FLOW, train, 0)] = flow
            inlet = self._feed_temp_c
            for stage in range(self._stages):
                target = self._temp_setpoint_c
                state[self._tag(TEMPERATURE, train, stage)] = target
                state[self._tag(TEMPERATURE_SETPOINT, train, stage)] = target
                state[self._tag(DUTY, train, stage)] = self._duty_for(inlet, target, ambient, flow)
                inlet = target
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
        """Apply the lasting part of an event: a moved temperature setpoint."""
        for key, value in event.parameters.items():
            role = self._plant_spec.role_of(key)
            if role is not None and role.role == TEMPERATURE_SETPOINT and key in self._state:
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run every vessel's temperature loop, each on what its own transmitter reported."""
        commands: dict[str, float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                commands[self._tag(DUTY, train, stage)] = self._loops[(train, stage)].update(
                    measurement=report[self._tag(TEMPERATURE, train, stage)],
                    setpoint=report[self._tag(TEMPERATURE_SETPOINT, train, stage)],
                    dt_seconds=dt_seconds,
                    bias=self._biases[(train, stage)],
                )
        return commands

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the chain one sample, vessel by vessel down the direction of flow."""
        ambient = self._ambient(elapsed_hours)
        feed = self._feed_temperature(active)
        capacity = self._holdup_kg * self._heat_capacity
        advanced: dict[str, float] = {self._ambient_tag: ambient}

        for train in range(self._trains):
            flow = self._flow(elapsed_hours, active, train)
            advanced[self._tag(FLOW, train, 0)] = flow
            inlet = feed
            flow_capacity = max(flow / 3600.0 * self._heat_capacity, 1e-9)
            residence_tau = capacity / flow_capacity
            for stage in range(self._stages):
                previous = state[self._tag(TEMPERATURE, train, stage)]
                after_flow = first_order(
                    previous, target=inlet, dt_seconds=dt_seconds, tau_seconds=residence_tau
                )
                duty = clamp(actuators[self._tag(DUTY, train, stage)], 0.0, 100.0)
                heater_kw = duty / 100.0 * self._rated_kw
                loss_kw = self._ua_kw_per_k * (previous - ambient)
                temperature = clamp(
                    after_flow + (heater_kw - loss_kw) * dt_seconds / capacity,
                    0.0,
                    self._temp_high_c,
                )
                advanced[self._tag(TEMPERATURE, train, stage)] = temperature
                advanced[self._tag(DUTY, train, stage)] = duty
                advanced[self._tag(TEMPERATURE_SETPOINT, train, stage)] = state[
                    self._tag(TEMPERATURE_SETPOINT, train, stage)
                ]
                inlet = temperature
        return advanced

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return each vessel's energy balance residual over the run.

        The statement checked is the physical one, not the one the integrator happens to
        implement: over the whole run, the heat the heater put in must equal the heat the stream
        carried away, plus the heat lost through the walls, plus whatever is stored in the
        vessel's own temperature change.

        That is deliberate. Checking the balance in the discretised form `advance` uses would
        close to the last bit by construction and verify nothing. Stating it physically means the
        residual carries the integration error as well — which is the honest thing for it to
        carry, because a vessel whose residence time is short against the sample interval really
        is being modelled coarsely, and a reviewer should see that rather than be reassured.

        Args:
            steps: Every sample of the run, in order.
            interval_seconds: The integration step.

        Returns:
            ``{"train N vessel M energy": relative residual}``.
        """
        residuals: dict[str, float] = {}
        if len(steps) < 2:
            return residuals
        capacity = self._holdup_kg * self._heat_capacity
        for train in range(self._trains):
            for stage in range(self._stages):
                heater = 0.0
                carried = 0.0
                lost = 0.0
                for step in steps[:-1]:
                    values = step.truth.values
                    temperature = values[self._tag(TEMPERATURE, train, stage)]
                    inlet = (
                        values[self._tag(TEMPERATURE, train, stage - 1)]
                        if stage
                        else self._feed_temp_c
                    )
                    flow_kw_per_k = values[self._tag(FLOW, train, 0)] / 3600.0 * self._heat_capacity
                    heater += (
                        values[self._tag(DUTY, train, stage)] / 100.0 * self._rated_kw
                    ) * interval_seconds
                    carried += flow_kw_per_k * (temperature - inlet) * interval_seconds
                    lost += (
                        self._ua_kw_per_k
                        * (temperature - values[self._ambient_tag])
                        * interval_seconds
                    )
                stored = capacity * (
                    steps[-1].truth.values[self._tag(TEMPERATURE, train, stage)]
                    - steps[0].truth.values[self._tag(TEMPERATURE, train, stage)]
                )
                throughput = max(abs(heater), abs(carried) + abs(lost), 1e-9)
                residuals[f"train {train + 1} vessel {stage + 1} energy"] = (
                    heater - carried - lost - stored
                ) / throughput
        return residuals

    def tracking_loops(self) -> tuple[str, ...]:
        """Every temperature loop. All of them hold their setpoint for the whole of a normal run."""
        return tuple(
            duty_loop_id(train, stage)
            for train in range(self._trains)
            for stage in range(self._stages)
        )

    def _ambient(self, elapsed_hours: float) -> float:
        """Return the temperature of the room, which nobody controls."""
        return self._ambient_base_c + cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._ambient_daily_c,
            phase_hours=15.0,
        )

    def _feed_temperature(self, active: BenignEvent | None) -> float:
        """Return what is arriving at the front of the chain, colder during an excursion."""
        if active is None or active.kind != COLD_FEED:
            return self._feed_temp_c
        return self._feed_temp_c - active.parameters.get("feed_drop_c", 0.0)

    def _flow(self, elapsed_hours: float, active: BenignEvent | None, train: int) -> float:
        """Return one train's stream: a daily rhythm, stepped during a throughput change."""
        swing = cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._flow_base_kgph * self._flow_daily_fraction,
            phase_hours=7.0,
        )
        flow = self._flow_base_kgph + swing
        if active is not None and active.kind == THROUGHPUT_CHANGE:
            flow *= 1.0 + active.parameters.get("throughput_fraction", 0.0)
        del train
        return max(flow, self._flow_base_kgph * 0.05)

    def _duty_for(self, inlet: float, target: float, ambient: float, flow: float) -> float:
        """Return the heater duty that holds a vessel at its target, at steady state.

        The algebraic answer to the energy balance with ``dT/dt`` set to zero. Used only to start
        a run settled; from then on the loop decides.
        """
        flow_kw_per_k = flow / 3600.0 * self._heat_capacity
        needed_kw = flow_kw_per_k * (target - inlet) + self._ua_kw_per_k * (target - ambient)
        return clamp(100.0 * needed_kw / self._rated_kw, 0.0, 100.0)

    def _tag(self, role: str, train: int = 0, stage: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=train, stage=stage)


register_template(THERMAL_PROCESS, ThermalPlant)
