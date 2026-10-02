"""Who is allowed to command this plant, what they actually commanded, and which of those was.

`phos.synth.plant` already models control traffic: a SCADA server polls register blocks, an
operator writes a setpoint when an event calls for one, and `phos.synth.traffic` turns both into
Modbus/TCP. Two things were missing, and this module supplies them.

**The write did not cause anything.** A benign event moved a setpoint by mutating plant state, and
the write emitted afterwards carried the value the setpoint had *already* taken. The wire reported
the physics rather than driving it, so a capture could be deleted without changing one reading.
That is the wrong way round for a harness whose purpose is to exercise command attribution: an
attacker whose writes are cosmetic is an attacker the physics never felt. Here a write is applied
to the plant's own state *before* the controllers run, so it moves the setpoint, which moves the
loop, which moves the true state — and deleting the command changes the process.

**Authorisation was not recorded.** `CommandIntent.reason` is a free-text provenance string that
`traffic.py` deliberately never puts in a byte. It is not ground truth: a scenario asserting its
own writes are unauthorised would be labelling itself. So authority is **declared** here, per
plant, as which device may write which signal, and the authorisation of an observed write is
*derived* from that declaration — the same discipline the repository applies to topology, which is
declared and never clustered, and to peer groups, which come from the directory and never from
behaviour. A scenario cannot label its own command.

**The ground truth is kept apart from the observable.** `IssuedCommand` records what was really
commanded and whether it was really authorised; `CommandIntent` is what a capture shows. Nothing
in the recorded truth reaches the wire, exactly as `TrueState` never reaches `SensorReport`. An
attacker's write and an engineer's write are the same bytes, which is the honest case — ADR 0014
records that a commissioning engineer and an intruder leave behind the same new relationship, and
nothing here weakens that.

**A source sees what an attacker on the HMI would see, and no more.** `CommandSource.writes_at`
receives the *reported* readings. It never receives `TrueState` or the plant's internal state,
because an adversary reading the plant's unmeasured inventories is not an adversary, it is an
oracle. A source that has falsified the readings is therefore fooled by its own manipulation,
which is a property of real falsification and one this harness should not paper over.

**No source may draw randomness at step time.** The plant's bit-identity rests on one fixed-size
block of deviates per step drawn before anything can branch. A source that sampled per step would
shift that stream, so schedules are drawn once, at construction, in the idiom `lay_out_events`
already uses.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

__all__ = [
    "COMMAND_AUTHORITY_IS_DECLARED_CAVEAT",
    "SYNTHETIC_COMMAND_TRUTH_CAVEAT",
    "Authorisation",
    "CommandSource",
    "IssuedCommand",
    "NoCommands",
    "PlannedCommandSource",
    "PlannedWrite",
    "WriteAuthority",
]

COMMAND_AUTHORITY_IS_DECLARED_CAVEAT: Final = (
    "Which device may write which signal is DECLARED by the plant, not inferred from what any "
    "device was seen doing. The authorisation recorded against a write is derived from that "
    "declaration, so a scenario cannot label its own commands and a detector's opinion never "
    "enters the ground truth. The declaration is a model of one plant's access policy; it is not "
    "evidence about how real plants grant write access."
)

SYNTHETIC_COMMAND_TRUTH_CAVEAT: Final = (
    "An authorised write and an unauthorised write are the same bytes on the wire. The "
    "authorisation lives only in the recorded ground truth, never in the capture, because in a "
    "real plant it is not on the wire either. A harness result that separated them by reading "
    "the capture alone would be reading a tell this generator did not intend to leave."
)


class Authorisation(str, Enum):
    """Whether the plant's declared policy permitted a write. Ground truth, never observable.

    Attributes:
        AUTHORISED: The issuing device is declared as permitted to write this signal.
        UNAUTHORISED: It is not. Says nothing about intent — a misconfigured but legitimate tool
            and an intruder both land here, which is the honest reading of an access policy.
    """

    AUTHORISED = "AUTHORISED"
    UNAUTHORISED = "UNAUTHORISED"


class WriteAuthority(BaseModel):
    """Which device the plant permits to write which signals. Declared once, per plant.

    Attributes:
        grants: ``{node_id: signal keys that device may write}``. A device absent from the mapping
            may write nothing, which is the correct default for a workstation that has never been
            commissioned to command anything.

    Invariants:
        No grant names an empty signal set — an entry that permits nothing is a declaration
        mistake rather than a policy, and reading it as "denied" would hide the mistake.
    """

    model_config = ConfigDict(frozen=True)

    grants: Mapping[str, frozenset[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_grants(self) -> "WriteAuthority":
        for node_id, signals in self.grants.items():
            if not signals:
                raise ValueError(
                    f"{node_id!r} is granted an empty signal set; omit the node instead, so that "
                    "'permitted to write nothing' and 'never declared' are not two spellings of "
                    "one thing"
                )
        return self

    @field_serializer("grants")
    def _serialise_grants(self, grants: Mapping[str, frozenset[str]]) -> dict[str, list[str]]:
        """Write each grant's signals in sorted order, and the nodes in sorted order too.

        A `frozenset` has no order, so serialising one iterates it in hash order, which for strings
        varies between processes. That leaked straight into ``manifest.json`` — three generations of
        the same dataset, from the same code and the same seed, produced two different
        orderings here while every payload byte stayed identical. A manifest that cannot be
        reproduced makes "this corpus is unchanged" unfalsifiable, which is the one claim the
        manifest exists to support.

        Sorting is the only reproducible choice available, because the set genuinely has no
        intrinsic order to preserve. Found while establishing the corpus-identity proof that
        Usefulness Phase U3 requires before wiring `phos.synth.realism`; the defect predates that
        work and is not caused by it.
        """
        return {node: sorted(signals) for node, signals in sorted(grants.items())}

    def permits(self, node_id: str, signal: str) -> bool:
        """Return whether ``node_id`` is declared as permitted to write ``signal``."""
        return signal in self.grants.get(node_id, frozenset())

    def authorisation_of(self, node_id: str, signal: str) -> Authorisation:
        """Return the ground-truth authorisation of a write, derived from the declaration."""
        if self.permits(node_id, signal):
            return Authorisation.AUTHORISED
        return Authorisation.UNAUTHORISED

    def writers(self) -> frozenset[str]:
        """Return every device declared as permitted to write something."""
        return frozenset(self.grants)


@dataclass(frozen=True)
class PlannedWrite:
    """A write a source wants to perform, in the plant's own units, before anything applies it.

    Deliberately carries no authorisation field. What a write *is* comes from the issuer and the
    plant's declared policy, so letting a source state it would let a scenario mark its own
    commands and make the label a restatement of the author's intent.

    Attributes:
        issuer: ``node_id`` of the device performing the write.
        signal: Signal key being written. Must be writable on this plant.
        value: The engineering value written, not a register count. The plant converts.
        reason: Provenance for ground truth only. Never reaches a byte.
    """

    issuer: str
    signal: str
    value: float
    reason: str


@dataclass(frozen=True)
class IssuedCommand:
    """One write that actually happened, and what it actually did. Ground truth.

    Not a Pydantic model, for the reason `TrueState` is not one: thousands exist per run and none
    of them is ontology.

    Attributes:
        step_index: The sample the write landed on.
        timestamp: The instant, UTC.
        issuer: ``node_id`` of the writing device.
        target: ``node_id`` of the device holding the register.
        address: Register address written.
        signal: Signal key the register carries.
        requested: The value the source asked for, in engineering units.
        applied: The value the plant actually took, after the signal's span clamped it. Differs
            from ``requested`` when a source asked for something the instrument cannot represent,
            which is a fact about the write worth keeping rather than silently discarding.
        authorised: Derived from the plant's declared `WriteAuthority`.
        reason: Provenance. Never on the wire.
    """

    step_index: int
    timestamp: datetime
    issuer: str
    target: str
    address: int
    signal: str
    requested: float
    applied: float
    authorised: Authorisation
    reason: str

    @property
    def was_clamped(self) -> bool:
        """Return whether the plant's span refused part of what was asked for."""
        return self.requested != self.applied


class CommandSource(ABC):
    """Something that writes to a plant over its control network.

    One method, called once per sample, before the controllers run. Implementations must be
    deterministic and must not draw randomness at step time — see the module docstring.
    """

    @abstractmethod
    def writes_at(
        self, index: int, clock: datetime, reported: Mapping[str, float]
    ) -> Sequence[PlannedWrite]:
        """Return the writes this source performs at one sample.

        Args:
            index: Zero-based sample number.
            clock: The instant, UTC.
            reported: What the instruments said at the previous sample — what a device on the
                network could actually see. Never the true state.

        Returns:
            The writes to apply, in order. Empty is the normal answer.
        """


class NoCommands(CommandSource):
    """The empty inlet: a real object executing the same code, not a branch that skips it.

    A plant given this must be byte-identical to a plant given nothing, which is what makes the
    command layer additive rather than a rewrite of every existing corpus.
    """

    def writes_at(
        self, index: int, clock: datetime, reported: Mapping[str, float]
    ) -> Sequence[PlannedWrite]:
        """Return no writes, always."""
        return ()


class PlannedCommandSource(CommandSource):
    """Writes fixed at construction and replayed by sample index.

    The schedule is built once — by an operator model, a maintenance plan or an attack scenario —
    so nothing is drawn while the plant is stepping.
    """

    def __init__(self, schedule: Mapping[int, Sequence[PlannedWrite]]) -> None:
        """Prepare a source from a sample-indexed schedule.

        Args:
            schedule: ``{step_index: writes at that sample}``. Indices outside the run are kept
                rather than refused; a scenario trimmed by a shorter run is a caller's decision.

        Raises:
            ValueError: If a step index is negative, which cannot be reached and would silently
                mean "never".
        """
        for index in schedule:
            if index < 0:
                raise ValueError(
                    f"write scheduled at step {index}, which no run reaches; a negative index is "
                    "silently never, and silence is the failure this refuses"
                )
        self._schedule = {index: tuple(writes) for index, writes in schedule.items() if writes}

    def writes_at(
        self, index: int, clock: datetime, reported: Mapping[str, float]
    ) -> Sequence[PlannedWrite]:
        """Return the writes scheduled for this sample."""
        return self._schedule.get(index, ())

    @property
    def scheduled_steps(self) -> tuple[int, ...]:
        """Return every sample this source writes at, in order. Lets a caller assert coverage."""
        return tuple(sorted(self._schedule))
