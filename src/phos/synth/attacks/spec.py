"""What an attack is, what it declares about itself, and the two things it may never be.

D2 produces two kinds of adversary, and the single most damaging thing this PART could do is let
them blur. They support different claims and the claims are not interchangeable:

* A **detection attack** acts on the simulated plant, through the plant's own mechanisms. It
  supports the claim *"Atlas detects plant attacks down to this level of subtlety"*, and nothing
  else.
* An **input-hostile attack** acts on the data feeding Atlas. It supports the claim *"Atlas
  handles hostile input safely"* — that the software does not crash, corrupt its baseline, or go
  quietly wrong when handed rubbish. It is **not** evidence that PHOS is secure against a
  real-world attacker, which would require a live deployment this project does not have.

So the separation here is structural rather than conventional. Three things enforce it and none of
them is a habit someone has to remember:

1. **A flavour is derived from the type, never assigned.** `AttackType.LIAR.flavour` is
   `DETECTION` because of what the type *is*. `AttackGroundTruth.flavour` is a computed field, so
   a caller who passes a flavour is overruled rather than believed.
2. **The two plans are different types.** `AttackPlan` refuses an input-hostile type at
   construction and `HostilePlan` refuses a detection one, so a config file cannot express the
   confusion in the first place.
3. **`HostileGroundTruth` has no route to a `LabelledInterval`.** A detection attack yields the
   interval that labels its window in the corpus; an input-hostile case has no such method, so it
   cannot be scored as something Atlas was supposed to detect. The boundary is the absence of a
   road, not a rule about which road to take.

**The difficulty dial.** Every detection attack carries a `subtlety` in ``[0, 1]``. Zero is the
blatant end; one is a manipulation of exactly zero magnitude, which is the anti-fingerprint
control. `strength_of` turns it into the multiplier every manipulation scales itself by, and it
returns *exactly* ``0.0`` at full subtlety — not nearly zero, because the property being defended
is bit-identity with a normal run, and a strength of 1e-17 is a manipulation that is present.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from phos.eval import LabelledInterval
from phos.ontology import UtcDatetime
from phos.synth.injection import TimeWindow

__all__ = [
    "ATTACKS_ARE_OURS_CAVEAT",
    "ATTACK_LABEL",
    "INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT",
    "AttackFlavour",
    "AttackGroundTruth",
    "AttackPlan",
    "AttackType",
    "DifficultyLevel",
    "HostileGroundTruth",
    "HostilePlan",
    "strength_of",
]

ATTACK_LABEL: Final = "attack"
"""The ground-truth class every detection window is labelled with, matching the convention
`phos.eval` reads from published corpora."""

ATTACKS_ARE_OURS_CAVEAT: Final = (
    "These are attacks WE designed. Atlas catching them shows that Atlas handles our imagination, "
    "not a real adversary's: the library was written by someone who could read the detector, and "
    "an attack nobody here thought of is not in it. Two consequences follow and both are load "
    "bearing. A detection rate measured here is an upper bound on this library, never a lower "
    "bound on reality. And if Atlas ever scores suspiciously well, the first hypothesis is a "
    "leaked fingerprint — some incidental tell in timing, formatting, ordering or numerical "
    "precision that lets the detector find the injection rather than the attack — and not "
    "brilliance. Rule that out before believing the number."
)
"""Travels with every attack corpus, manifest and report D2 produces."""

INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT: Final = (
    "An input-hostile case tests whether Atlas's SOFTWARE survives malformed, out-of-range, "
    "truncated or poisoned input without crashing, corrupting its baseline or producing silently "
    "wrong output. Passing it is not evidence that PHOS is secure against a real-world attacker. "
    "That claim needs a live deployment, an exposed attack surface and an adversary who did not "
    "read this file, none of which exist here. An input-hostile case is never labelled as a plant "
    "attack and never appears in a corpus's attack intervals."
)
"""Travels with every input-hostile corpus, and states the boundary the code enforces."""

_OBVIOUS_BELOW: Final = 0.25
_MODERATE_BELOW: Final = 0.6
_SUBTLE_BELOW: Final = 0.9


class AttackFlavour(str, Enum):
    """Which of the two non-interchangeable claims an attack supports.

    Attributes:
        DETECTION: Acts on the simulated plant. Supports a claim about what Atlas can see.
        INPUT_HOSTILE: Acts on the data pipeline. Supports a claim about what Atlas's software
            survives, and no claim whatever about security.
    """

    DETECTION = "DETECTION"
    INPUT_HOSTILE = "INPUT_HOSTILE"


class AttackType(str, Enum):
    """The kinds of attack the library builds, each belonging to exactly one flavour.

    Attributes:
        BLATANT: A large, obvious manipulation. The control case at the easy end of the dial.
        STEALTH_DRIFT: Tiny increments, each passing as ordinary drift, accumulating over a long
            window to a dangerous true state. Attacks a threshold view of normal.
        CORRELATION_BREAK: Every signal stays inside its own normal range while a *declared*
            physical relationship between signals is violated. Attacks Atlas's central claim.
        LIAR: False data injection. The true state is driven somewhere dangerous while the
            instruments report calm. The data looks calmest when things are worst.
        MIMIC: A malicious action shaped like one of the plant's genuine benign events, so it
            hides among ordinary operations. The maintenance-versus-attack problem, made concrete.
        ROGUE_COMMAND: A control-network command from a device with no legitimate history of
            issuing it.
        MIMIC_COMMAND: A command sequence shaped like the legitimate operator's own pattern.
        MALFORMED_RECORD: Records that violate the expected format.
        OUT_OF_RANGE: Values that are physically impossible for the signal that carries them.
        TRUNCATED: A corrupted or half-written file.
        POISONED_BASELINE: A fitting window deliberately contaminated so what is learned as
            "normal" is subtly wrong.
    """

    BLATANT = "BLATANT"
    STEALTH_DRIFT = "STEALTH_DRIFT"
    CORRELATION_BREAK = "CORRELATION_BREAK"
    LIAR = "LIAR"
    MIMIC = "MIMIC"
    ROGUE_COMMAND = "ROGUE_COMMAND"
    MIMIC_COMMAND = "MIMIC_COMMAND"
    MALFORMED_RECORD = "MALFORMED_RECORD"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    TRUNCATED = "TRUNCATED"
    POISONED_BASELINE = "POISONED_BASELINE"

    @property
    def flavour(self) -> AttackFlavour:
        """Return which claim this type supports.

        Derived from the type rather than stored beside it, so the two flavours cannot be mixed by
        anyone setting a field wrongly. See the module docstring.
        """
        if self in _INPUT_HOSTILE_TYPES:
            return AttackFlavour.INPUT_HOSTILE
        return AttackFlavour.DETECTION

    @property
    def is_command_attack(self) -> bool:
        """Return whether this type acts on the control network rather than on the process."""
        return self in _COMMAND_TYPES


_INPUT_HOSTILE_TYPES: Final = frozenset(
    {
        AttackType.MALFORMED_RECORD,
        AttackType.OUT_OF_RANGE,
        AttackType.TRUNCATED,
        AttackType.POISONED_BASELINE,
    }
)

_COMMAND_TYPES: Final = frozenset({AttackType.ROGUE_COMMAND, AttackType.MIMIC_COMMAND})

_NEEDS_REFERENCE: Final = frozenset({AttackType.CORRELATION_BREAK, AttackType.LIAR})
"""Types whose manipulation is defined against a second signal: the coupling driver whose relation
is broken, or the setpoint a falsified reading is quoted against."""

_NEEDS_MIMICS: Final = frozenset({AttackType.MIMIC, AttackType.MIMIC_COMMAND})
"""Types that wear a genuine benign event as a disguise, and must name which one. Checked against
the events the clean run actually contained, so the disguise cannot be of something the plant
never does."""

_HOSTILE_NEEDS_TARGET: Final = frozenset({AttackType.OUT_OF_RANGE, AttackType.POISONED_BASELINE})
"""Input-hostile kinds that corrupt one column, as opposed to the file as a whole."""


class DifficultyLevel(str, Enum):
    """The band a subtlety falls in, for a report that has to name it rather than plot it.

    Attributes:
        OBVIOUS: Subtlety below 0.25. A naive detector should catch this.
        MODERATE: Below 0.6.
        SUBTLE: Below 0.9.
        NEAR_INVISIBLE: 0.9 and above, up to the zero-magnitude control at 1.0.
    """

    OBVIOUS = "OBVIOUS"
    MODERATE = "MODERATE"
    SUBTLE = "SUBTLE"
    NEAR_INVISIBLE = "NEAR_INVISIBLE"

    @classmethod
    def for_subtlety(cls, subtlety: float) -> "DifficultyLevel":
        """Return the band a subtlety falls in.

        Args:
            subtlety: Position on the dial, ``0.0`` blatant to ``1.0`` invisible.

        Returns:
            The band.

        Raises:
            ValueError: If the subtlety is off the dial. A value outside ``[0, 1]`` would scale a
                manipulation past its full magnitude or invert its sign, so it is refused rather
                than clamped.
        """
        if not 0.0 <= subtlety <= 1.0:
            raise ValueError(f"subtlety must lie in [0, 1], got {subtlety}")
        if subtlety < _OBVIOUS_BELOW:
            return cls.OBVIOUS
        if subtlety < _MODERATE_BELOW:
            return cls.MODERATE
        if subtlety < _SUBTLE_BELOW:
            return cls.SUBTLE
        return cls.NEAR_INVISIBLE


def strength_of(subtlety: float) -> float:
    """Return the multiplier a manipulation scales its full magnitude by.

    Args:
        subtlety: Position on the dial, ``0.0`` blatant to ``1.0`` invisible.

    Returns:
        ``1 - subtlety``: full magnitude at zero subtlety, and **exactly** ``0.0`` at full
        subtlety. Exactness is the point — a zero-strength manipulation must be a no-op by
        arithmetic, so that the run it produces is bit-identical to a normal one and the
        anti-fingerprint property is provable rather than approximate.

    Raises:
        ValueError: If the subtlety is off the dial.
    """
    if not 0.0 <= subtlety <= 1.0:
        raise ValueError(f"subtlety must lie in [0, 1], got {subtlety}")
    return 1.0 - subtlety


class AttackPlan(BaseModel):
    """One detection attack, as a committed config declares it, before it meets a plant.

    Extra keys are forbidden: this is a type humans write by hand, and a mistyped field that was
    quietly ignored would produce a corpus whose attack is not the attack the file describes.

    Attributes:
        attack_id: Stable identifier, unique within a corpus. Names the attack in ground truth.
        type: Which attack to build. Must be a detection type.
        subtlety: Position on the difficulty dial, ``0.0`` blatant to ``1.0`` zero-magnitude.
        start_hours: When the attack opens, in hours after the run's first sample.
        duration_hours: How long it lasts.
        target: The signal the manipulation acts on — the actuator driven, the reading falsified,
            or the signal whose register a rogue command writes.
        reference: The second signal the manipulation is defined against: the coupling driver
            whose relation is broken, or the setpoint a falsified reading is quoted against.
            Required only for the types that need one.
        issuer: For a command attack, the ``node_id`` that issued it. The device written *to* is
            not configured — it is read off the plant's register map from ``target``, so a plan
            cannot name an address nothing is exposed at.
        mimics: For a mimic attack, the ``kind`` of genuine benign event it wears as a disguise.
            Checked against the events the clean run actually contained, so an attack cannot claim
            to hide among operations the plant never performs.
        note: Why this attack is in the battery, in a sentence.

    Invariants:
        The type is a detection type; the subtlety is on the dial; the window covers time and
        begins within the run; and every field the type needs is present.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attack_id: str = Field(min_length=1)
    type: AttackType
    subtlety: float = Field(ge=0.0, le=1.0)
    start_hours: float = Field(ge=0.0)
    duration_hours: float = Field(gt=0.0)
    target: str = ""
    reference: str = ""
    issuer: str = ""
    mimics: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _check_plan(self) -> Self:
        if self.type.flavour is not AttackFlavour.DETECTION:
            raise ValueError(
                f"{self.type.value} is an input-hostile type and cannot be an AttackPlan; "
                "input-hostile cases are declared as a HostilePlan so the two flavours cannot be "
                "confused at the config"
            )
        if not self.target:
            raise ValueError(
                f"attack {self.attack_id!r} of type {self.type.value} must name the target signal "
                "it manipulates"
            )
        if self.type in _NEEDS_REFERENCE and not self.reference:
            raise ValueError(
                f"attack {self.attack_id!r} of type {self.type.value} is defined against a second "
                "signal and must name it as reference"
            )
        if self.type.is_command_attack and not self.issuer:
            raise ValueError(
                f"attack {self.attack_id!r} of type {self.type.value} must name the issuer device "
                "the command came from"
            )
        if self.type in _NEEDS_MIMICS and not self.mimics:
            raise ValueError(
                f"attack {self.attack_id!r} of type {self.type.value} hides among genuine "
                "operations and must name the kind of benign event it mimics"
            )
        return self

    @property
    def difficulty(self) -> DifficultyLevel:
        """The band this plan's subtlety falls in."""
        return DifficultyLevel.for_subtlety(self.subtlety)

    @property
    def strength(self) -> float:
        """The multiplier this plan's manipulation scales its full magnitude by."""
        return strength_of(self.subtlety)

    def window(self, run_start: datetime) -> TimeWindow:
        """Return the half-open window this attack is active over.

        Args:
            run_start: The run's first sample instant.

        Returns:
            The window, in D1's own `TimeWindow` type so the attack enters through the same hook
            every other manipulation does.
        """
        start = run_start + timedelta(hours=self.start_hours)
        return TimeWindow(start=start, end=start + timedelta(hours=self.duration_hours))


class HostilePlan(BaseModel):
    """One input-hostile case, as a committed config declares it.

    A different type from `AttackPlan` on purpose. The two flavours support claims that must never
    be swapped, and the cheapest way to guarantee that is to make the confusion unrepresentable.

    Attributes:
        attack_id: Stable identifier, unique within a corpus.
        type: Which corruption to apply. Must be an input-hostile type.
        fraction: How much of the corpus it touches, in ``[0, 1]``. What that means depends on the
            kind: the share of rows made malformed, the share of the tail removed, the share of a
            column given impossible values, or the share of the fitting window contaminated.
        start_hours: When the corruption begins, in hours after the run's first sample. Ignored by
            kinds that act on the file as a whole.
        target: The column corrupted. Required for the kinds that corrupt one column; the kinds
            that corrupt the file as a whole need none.
        note: Why this case is in the set, in a sentence.

    Invariants:
        The type is an input-hostile type, the fraction is on the unit interval, and a kind that
        corrupts a column names one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attack_id: str = Field(min_length=1)
    type: AttackType
    fraction: float = Field(ge=0.0, le=1.0)
    start_hours: float = Field(default=0.0, ge=0.0)
    target: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _check_plan(self) -> Self:
        if self.type.flavour is not AttackFlavour.INPUT_HOSTILE:
            raise ValueError(
                f"{self.type.value} is a detection type and cannot be a HostilePlan; a plant "
                "attack is declared as an AttackPlan so the two flavours cannot be confused at "
                "the config"
            )
        if self.type in _HOSTILE_NEEDS_TARGET and not self.target:
            raise ValueError(
                f"input-hostile case {self.attack_id!r} of type {self.type.value} corrupts one "
                "column and must name it as target"
            )
        return self


class AttackGroundTruth(BaseModel):
    """What a detection attack actually did, recorded with perfect precision.

    Written after the attacked run has been simulated and compared against the clean one, so the
    departures here are *measured* rather than intended. That distinction matters: an attack whose
    parameters looked dangerous but which the plant absorbed is an attack that did nothing, and a
    corpus that labelled it as an attack anyway would be ground truth that lies.

    Attributes:
        attack_id: Stable identifier, as the plan gave it.
        type: Which attack this was.
        subtlety: Where on the dial it was run.
        started_at: First instant of the attack window, UTC.
        ended_at: Last instant, UTC.
        target_signals: The signals the manipulation acted on directly.
        issuer: The device a command attack issued from, or empty.
        manipulation: What was done, in words a reviewer can check by eye.
        physical_effect: Whether the manipulation moved the plant's true state at all, as opposed
            to only what its instruments reported. False is a real and honest answer — a
            correlation-break that falsifies telemetry has no physical consequence, and saying so
            is what stops D3 reading it as a near-miss on a dangerous event.
        truth_departure: Per signal, the largest absolute gap between this run's true state and
            the clean run's, over the whole run. The real danger, measured against D1's
            independently recorded truth, and therefore correct even where the instruments lie.
        report_departure: Per signal, the largest absolute gap between what this run reported and
            what the clean run reported. What a detector could actually have seen.
        commands_injected: How many extra control-network exchanges the attack put on the wire.

    Invariants:
        The window is not inverted, and the flavour is always `DETECTION` because it is derived
        from the type.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    type: AttackType
    subtlety: float = Field(ge=0.0, le=1.0)
    started_at: UtcDatetime
    ended_at: UtcDatetime
    target_signals: tuple[str, ...] = ()
    issuer: str = ""
    manipulation: str = ""
    physical_effect: bool = False
    truth_departure: dict[str, float] = Field(default_factory=dict)
    report_departure: dict[str, float] = Field(default_factory=dict)
    commands_injected: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError(
                f"attack {self.attack_id!r} is inverted: {self.started_at} > {self.ended_at}"
            )
        if self.type.flavour is not AttackFlavour.DETECTION:
            raise ValueError(
                f"{self.type.value} is input-hostile and cannot be recorded as a detection attack"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flavour(self) -> AttackFlavour:
        """Always `DETECTION`, derived from the type so it cannot be set to anything else.

        A computed field rather than a stored one: it is serialised into the manifest, where a
        reader needs it, but there is no input that produces a detection attack labelled
        input-hostile.
        """
        return self.type.flavour

    @computed_field  # type: ignore[prop-decorator]
    @property
    def difficulty(self) -> DifficultyLevel:
        """The band this attack's subtlety falls in, serialised for a report that names it."""
        return DifficultyLevel.for_subtlety(self.subtlety)

    def interval(self) -> LabelledInterval:
        """Return the ground-truth window that labels this attack in the corpus.

        Only detection attacks have this method. An input-hostile case has no counterpart, which
        is how the boundary in the module docstring is enforced: there is no route from a hostile
        record to something the evaluation harness would score as a missed detection.
        """
        return LabelledInterval(
            start=self.started_at,
            end=self.ended_at,
            label=ATTACK_LABEL,
            attack_type=self.type.value,
        )

    def peak_truth_departure(self) -> float:
        """Return the largest true-state gap this attack opened, across every signal.

        Zero for an attack that moved nothing, which is a result rather than an error — see
        `physical_effect`.
        """
        return max(self.truth_departure.values(), default=0.0)

    def peak_report_departure(self) -> float:
        """Return the largest reported gap this attack opened, across every signal."""
        return max(self.report_departure.values(), default=0.0)


class HostileGroundTruth(BaseModel):
    """What an input-hostile case did to a corpus.

    Deliberately has **no** `interval()`. An input-hostile case is not something Atlas was
    supposed to detect, so there is no method here that produces a `LabelledInterval` and
    therefore no way for one to reach a corpus's attack intervals. See the module docstring.

    Attributes:
        attack_id: Stable identifier, as the plan gave it.
        type: Which corruption this was.
        target: The column corrupted, or empty for a corruption of the file as a whole.
        description: What was done, in words a reviewer can check by eye.
        rows_affected: How many records the corruption touched.

    Invariants:
        The flavour is always `INPUT_HOSTILE` because it is derived from the type.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    type: AttackType
    target: str = ""
    description: str = ""
    rows_affected: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_type(self) -> Self:
        if self.type.flavour is not AttackFlavour.INPUT_HOSTILE:
            raise ValueError(
                f"{self.type.value} is a detection type and cannot be recorded as input-hostile"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flavour(self) -> AttackFlavour:
        """Always `INPUT_HOSTILE`, derived from the type so it cannot be set to anything else."""
        return self.type.flavour
