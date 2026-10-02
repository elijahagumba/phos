"""The messiness real plants have, which is where most false positives actually come from.

The existing plants are honest about their physics and thin about their bad days. They run at one
operating point, their instruments are good, their network never drops a frame, and the only thing
that ever changes is an operator moving a setpoint. A detector measured against that is measured
against a world in which anything unusual is an attack, and that world does not exist.

Everything here is a **benign** phenomenon. None of it is an attack, none of it is labelled as one,
and several are deliberately shaped to look like one — a transmitter losing calibration looks like
a slow falsification, a grade change looks like a coordinated multi-signal move, a comms dropout
looks like a device going silent. That resemblance is the point. `tests/synth/test_anti_bias.py`
fails a run that produces none of them, because a benign class with no hard cases makes any
false-positive figure measured on it meaningless.

**Additive, and off by default.** A `RealismProfile` left at its defaults changes nothing, so every
corpus generated before this module existed is reproduced byte for byte. Realism is something a
caller asks for.

**Randomness is drawn at construction.** The per-run characteristics — which instrument is drifting,
when the dropouts fall, where the grade changes sit — are drawn once, from the setup generator, in
the idiom `phos.synth.plant.lay_out_events` uses. Nothing here draws while the plant is stepping,
so the bit-identity the injection hook depends on survives.

**What this still gets wrong.** These are shapes, not measurements. Real fouling curves, real
transmitter drift and real dropout statistics were not fitted to anything — they were written from
descriptions of how such things behave. `docs/synthetic-harness-method.md` says so at length, and
says which of them is most likely to be wrong.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Final

from numpy.random import Generator
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "BENIGN_PHENOMENA_ARE_NOT_ATTACKS_CAVEAT",
    "AmbientDrift",
    "BenignPhenomenon",
    "CommsDropout",
    "PhenomenonKind",
    "RealismPlan",
    "RealismProfile",
    "SensorFault",
    "plan_realism",
]

BENIGN_PHENOMENA_ARE_NOT_ATTACKS_CAVEAT: Final = (
    "Everything this module generates is BENIGN. A drifting transmitter, a fouled filter, a grade "
    "change, a comms dropout and a startup transition are all things a plant does to itself. "
    "Several of them resemble an attack closely, and that resemblance is deliberate: a benign "
    "class with no hard cases cannot support a false-positive figure worth quoting. None of these "
    "is labelled as an attack, and a detector that fires on one has produced a false positive."
)


class PhenomenonKind(str, Enum):
    """What kind of ordinary trouble a plant is having.

    Attributes:
        GRADE_CHANGE: The process is asked to make something different — a new recipe, a different
            product grade. Several setpoints move together, which is the shape a coordinated
            attack also has.
        AMBIENT_DRIFT: Seasonal or daily environmental change working on the process.
        EQUIPMENT_AGEING: Fouling, wear, a filter loading up. Slow, one-directional, and the
            closest benign analogue of a patient manipulation.
        OPERATOR_INTERVENTION: A legitimate manual action outside the routine — someone taking a
            loop to manual and putting it back.
        SENSOR_FAULT: An instrument going wrong. A stuck reading, a step offset, or a calibration
            walking away. Not an attack, and shaped like a falsification.
        COMMS_DROPOUT: Frames lost and retransmitted, or a device briefly unreachable. Looks like
            a link going silent.
        STARTUP_TRANSITION: Coming up or shutting down. Every signal is out of its steady-state
            band at once, legitimately.
    """

    GRADE_CHANGE = "GRADE_CHANGE"
    AMBIENT_DRIFT = "AMBIENT_DRIFT"
    EQUIPMENT_AGEING = "EQUIPMENT_AGEING"
    OPERATOR_INTERVENTION = "OPERATOR_INTERVENTION"
    SENSOR_FAULT = "SENSOR_FAULT"
    COMMS_DROPOUT = "COMMS_DROPOUT"
    STARTUP_TRANSITION = "STARTUP_TRANSITION"


@dataclass(frozen=True)
class BenignPhenomenon:
    """One episode of ordinary trouble, placed in a run.

    Attributes:
        kind: What sort of trouble.
        started_at: When it began, UTC.
        ended_at: When it finished, UTC.
        signals: The signals it touches. Empty for something plant-wide.
        detail: What happened, in a phrase.
        resembles_attack: Whether this episode is one of the deliberately confusing ones. Used for
            labelling and for the anti-bias check; never consulted while placing anything.
    """

    kind: PhenomenonKind
    started_at: datetime
    ended_at: datetime
    signals: tuple[str, ...]
    detail: str
    resembles_attack: bool

    def contains(self, clock: datetime) -> bool:
        """Return whether ``clock`` falls inside the episode, both bounds inclusive."""
        return self.started_at <= clock <= self.ended_at


@dataclass(frozen=True)
class SensorFault:
    """An instrument going wrong, as an effect applied to one signal's reported value.

    Attributes:
        signal: The signal whose instrument is faulty.
        started_at: When the fault began.
        ended_at: When it ended.
        offset: A constant added to the reading, in engineering units. A calibration that has
            walked.
        stuck_at: A value the reading is pinned to, if the transmitter has frozen.
    """

    signal: str
    started_at: datetime
    ended_at: datetime
    offset: float = 0.0
    stuck_at: float | None = None

    def apply(self, clock: datetime, value: float) -> float:
        """Return the reading this instrument gives at ``clock``."""
        if not self.started_at <= clock <= self.ended_at:
            return value
        if self.stuck_at is not None:
            return self.stuck_at
        return value + self.offset


@dataclass(frozen=True)
class AmbientDrift:
    """A slow environmental influence on one signal.

    Attributes:
        signal: The affected signal.
        amplitude: Peak influence in engineering units.
        period_hours: How long one cycle takes. A season, or a day.
        phase_hours: Where in the cycle the run starts.
    """

    signal: str
    amplitude: float
    period_hours: float
    phase_hours: float

    def at(self, elapsed_hours: float) -> float:
        """Return the influence at ``elapsed_hours`` into the run."""
        angle = 2.0 * math.pi * (elapsed_hours + self.phase_hours) / self.period_hours
        return self.amplitude * math.sin(angle)


@dataclass(frozen=True)
class CommsDropout:
    """A stretch where the control network loses frames.

    Attributes:
        started_at: When the dropout began.
        ended_at: When it ended.
        node_id: The device that went quiet, or ``None`` for the whole segment.
        retransmits: Whether the lost exchanges are retried once service returns.
    """

    started_at: datetime
    ended_at: datetime
    node_id: str | None
    retransmits: bool

    def drops(self, clock: datetime, node_id: str) -> bool:
        """Return whether an exchange from ``node_id`` at ``clock`` is lost."""
        if not self.started_at <= clock <= self.ended_at:
            return False
        return self.node_id is None or self.node_id == node_id


class RealismProfile(BaseModel):
    """How messy a plant is asked to be. Every default is off.

    A profile left alone produces no phenomena at all, which is what keeps every corpus generated
    before this module existed reproducible byte for byte.

    Attributes:
        grade_changes: How many recipe or grade changes to place across the run.
        ambient_signals: Signals to put a seasonal or daily environmental influence on.
        ambient_amplitude: Peak size of that influence, as a fraction of the signal's span.
        ageing_signals: Signals to put a slow one-directional wander on.
        ageing_fraction: How far ageing carries a signal across the whole run, as a fraction of
            its span.
        operator_interventions: How many out-of-routine manual actions to place.
        sensor_faults: How many instrument faults to place.
        stuck_fault_share: Fraction of those faults that freeze a reading rather than offset it.
        comms_dropouts: How many dropouts to place.
        dropout_duration: How long a dropout lasts.
        startup_transitions: How many startup or shutdown transitions to place.

    Invariants:
        Counts are non-negative and the fractions are fractions.
    """

    model_config = ConfigDict(frozen=True)

    grade_changes: int = Field(default=0, ge=0)
    ambient_signals: tuple[str, ...] = ()
    ambient_amplitude: float = Field(default=0.02, ge=0.0, le=1.0)
    ageing_signals: tuple[str, ...] = ()
    ageing_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    operator_interventions: int = Field(default=0, ge=0)
    sensor_faults: int = Field(default=0, ge=0)
    stuck_fault_share: float = Field(default=0.3, ge=0.0, le=1.0)
    comms_dropouts: int = Field(default=0, ge=0)
    dropout_duration: timedelta = timedelta(minutes=5)
    startup_transitions: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_profile(self) -> "RealismProfile":
        if self.dropout_duration <= timedelta(0):
            raise ValueError("dropout_duration must be positive")
        return self

    def is_quiet(self) -> bool:
        """Return whether this profile asks for nothing at all."""
        return not (
            self.grade_changes
            or self.ambient_signals
            or self.ageing_signals
            or self.operator_interventions
            or self.sensor_faults
            or self.comms_dropouts
            or self.startup_transitions
        )


@dataclass(frozen=True)
class RealismPlan:
    """Everything a run's realism amounts to, drawn once.

    Attributes:
        phenomena: Every episode, for labelling.
        faults: The instrument faults, as applicable effects.
        drifts: The ambient influences.
        dropouts: The comms dropouts.
        ageing: ``{signal: total engineering-unit change across the run}``.
    """

    phenomena: tuple[BenignPhenomenon, ...]
    faults: tuple[SensorFault, ...]
    drifts: tuple[AmbientDrift, ...]
    dropouts: tuple[CommsDropout, ...]
    ageing: Mapping[str, float]

    def attack_like(self) -> tuple[BenignPhenomenon, ...]:
        """Return the episodes deliberately shaped to resemble an attack."""
        return tuple(item for item in self.phenomena if item.resembles_attack)


def plan_realism(
    rng: Generator,
    start: datetime,
    duration: timedelta,
    profile: RealismProfile,
    spans: Mapping[str, tuple[float, float]],
) -> RealismPlan:
    """Lay a run's ordinary trouble out, drawn once from the setup generator.

    Takes ``start`` and ``duration`` rather than a `phos.synth.plant.RunSpec`, and that is
    deliberate in two ways. It is the *whole* of what this function reads from a run, so the
    signature states its real dependency; and it keeps this module from importing
    `phos.synth.plant`, which is what lets the plant import **this** one and apply the plan at
    the point where readings are produced. Widening it back would reintroduce that cycle.

    Like `phos.synth.maintenance.plan_maintenance`, this takes no attack schedule and no scenario.
    A benign phenomenon placed to coincide with an attack — or placed to avoid one — would make the
    benign class a function of the attack class, and the confusability that makes these cases hard
    would be something the author arranged rather than something the plant does.

    Args:
        rng: The setup generator. Drawn from here and nowhere else.
        start: First instant of the run, UTC.
        duration: How long the run lasts.
        profile: How messy to be.
        spans: ``{signal: (low, high)}`` from the plant's declared signals, so effect sizes can be
            expressed as fractions of a real instrument span.

    Returns:
        The plan. Empty in every field for a quiet profile.

    Raises:
        KeyError: If the profile names a signal the plant does not declare.
    """
    if profile.is_quiet():
        return RealismPlan((), (), (), (), {})

    for signal in (*profile.ambient_signals, *profile.ageing_signals):
        if signal not in spans:
            raise KeyError(f"realism profile names undeclared signal {signal!r}")

    run_seconds = duration.total_seconds()
    # Named once. Three inner scopes bind their own episode start, and computing the run's end
    # from that name instead of this one would clamp each episode against itself.
    run_end = start + duration
    keys = sorted(spans)
    phenomena: list[BenignPhenomenon] = []

    def moment() -> datetime:
        return start + timedelta(seconds=round(float(rng.random()) * run_seconds))

    def episode(
        kind: PhenomenonKind,
        length: timedelta,
        signals: tuple[str, ...],
        detail: str,
        resembles_attack: bool,
    ) -> None:
        began = moment()
        phenomena.append(
            BenignPhenomenon(
                kind=kind,
                started_at=began,
                ended_at=min(began + length, run_end),
                signals=signals,
                detail=detail,
                resembles_attack=resembles_attack,
            )
        )

    for _ in range(profile.grade_changes):
        touched = tuple(rng.choice(keys, size=min(3, len(keys)), replace=False).tolist())
        episode(
            PhenomenonKind.GRADE_CHANGE,
            timedelta(hours=2),
            touched,
            f"grade change moving {len(touched)} setpoints together",
            True,
        )

    for _ in range(profile.operator_interventions):
        episode(
            PhenomenonKind.OPERATOR_INTERVENTION,
            timedelta(minutes=45),
            (str(rng.choice(keys)),),
            "loop taken to manual and returned",
            True,
        )

    for _ in range(profile.startup_transitions):
        episode(
            PhenomenonKind.STARTUP_TRANSITION,
            timedelta(hours=3),
            (),
            "plant taken down and brought back up",
            True,
        )

    faults: list[SensorFault] = []
    for _ in range(profile.sensor_faults):
        signal = str(rng.choice(keys))
        low, high = spans[signal]
        began = moment()
        end = min(began + timedelta(hours=8), run_end)
        stuck = bool(rng.random() < profile.stuck_fault_share)
        faults.append(
            SensorFault(
                signal=signal,
                started_at=began,
                ended_at=end,
                offset=0.0 if stuck else float(rng.uniform(-0.08, 0.08)) * (high - low),
                stuck_at=(low + high) / 2.0 if stuck else None,
            )
        )
        phenomena.append(
            BenignPhenomenon(
                kind=PhenomenonKind.SENSOR_FAULT,
                started_at=began,
                ended_at=end,
                signals=(signal,),
                detail="transmitter frozen" if stuck else "calibration walked off",
                resembles_attack=True,
            )
        )

    dropouts: list[CommsDropout] = []
    for _ in range(profile.comms_dropouts):
        began = moment()
        end = min(began + profile.dropout_duration, run_end)
        retransmits = bool(rng.random() < 0.5)
        dropouts.append(
            CommsDropout(started_at=began, ended_at=end, node_id=None, retransmits=retransmits)
        )
        phenomena.append(
            BenignPhenomenon(
                kind=PhenomenonKind.COMMS_DROPOUT,
                started_at=began,
                ended_at=end,
                signals=(),
                detail="frames lost, retransmitted" if retransmits else "frames lost",
                resembles_attack=True,
            )
        )

    drifts = tuple(
        AmbientDrift(
            signal=signal,
            amplitude=profile.ambient_amplitude * (spans[signal][1] - spans[signal][0]),
            period_hours=float(rng.uniform(2000.0, 4400.0)),
            phase_hours=float(rng.uniform(0.0, 2000.0)),
        )
        for signal in profile.ambient_signals
    )
    for drift in drifts:
        phenomena.append(
            BenignPhenomenon(
                kind=PhenomenonKind.AMBIENT_DRIFT,
                started_at=start,
                ended_at=run_end,
                signals=(drift.signal,),
                detail="seasonal influence",
                resembles_attack=False,
            )
        )

    ageing = {
        signal: profile.ageing_fraction * (spans[signal][1] - spans[signal][0])
        for signal in profile.ageing_signals
    }
    for signal in profile.ageing_signals:
        phenomena.append(
            BenignPhenomenon(
                kind=PhenomenonKind.EQUIPMENT_AGEING,
                started_at=start,
                ended_at=run_end,
                signals=(signal,),
                detail="fouling or wear across the run",
                resembles_attack=True,
            )
        )

    return RealismPlan(
        phenomena=tuple(sorted(phenomena, key=lambda item: (item.started_at, item.kind.value))),
        faults=tuple(faults),
        drifts=drifts,
        dropouts=tuple(dropouts),
        ageing=ageing,
    )
