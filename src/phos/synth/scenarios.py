"""Attacks stated as what the adversary wants the plant to do, never as what a detector would see.

An attack here is a **goal in the plant's own terms** plus the constraints the adversary is working
under, and a citation saying where that shape comes from in the real world. What it does to the
readings and to the traffic is *derived* by simulating it. Nothing in this module says how large a
deviation should be, how many writes to send, or which quantity ought to move — because every one
of those is a sentence about the detector wearing an attacker's clothes.

**Why the specification is the interesting part.** If the same author writes both "an attack looks
like this" and "the detector looks for that", a good score measures the agreement of two beliefs.
The repository already refuses the one-level-down version of this: topology is declared and never
clustered, peer groups come from the directory and never from behaviour. This is the same refusal
one level up. `PhysicalGoal` can only be phrased in signals the plant declares; `tests/synth/
test_anti_bias.py` asserts that no scenario's text contains any name Atlas exports.

**Provenance is mandatory and is checked.** Every scenario cites a documented incident, a published
ICS attack taxonomy, a process-engineering failure mode, or a vendor advisory. "This would be
interesting for Atlas" is not a provenance, and a scenario carrying one is rejected in review — the
`Provenance` model has nowhere to put it. The citation is not decoration: it is the argument that
the shape came from the world rather than from what we happen to be able to catch.

**An adversary is closed-loop and can be wrong.** `GoalSeekingSource` watches the *reported*
readings, exactly as someone on a hijacked HMI would, and writes until the goal appears to be met.
An adversary that had also falsified those readings is therefore fooled by its own manipulation and
overshoots — which is a real property of real falsification, and one the harness should not smooth
away.

**Difficulty is a property of the goal, not a dial on a signal.** `patience` says how long the
adversary is willing to take. A patient adversary moves the setpoint in small steps over hours; an
impatient one moves it at once. That is an operational choice an attacker actually makes, and the
band of cases a detector should miss falls out of it rather than being placed there.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.synth.command import CommandSource, PlannedWrite

__all__ = [
    "ATTACKS_ARE_SPECIFIED_BY_INTENT_CAVEAT",
    "Direction",
    "GoalSeekingSource",
    "PhysicalGoal",
    "Provenance",
    "ProvenanceKind",
    "Scenario",
]

ATTACKS_ARE_SPECIFIED_BY_INTENT_CAVEAT: Final = (
    "Every scenario states a goal in the plant's own terms and lets the simulation derive what "
    "that does to the readings and the traffic. No scenario names a detector feature, a score, a "
    "threshold or a magnitude to hit. A scenario written as 'make signal X deviate by Y' would be "
    "a restatement of what the detector measures, and a result obtained against it would report "
    "the agreement of two beliefs rather than a detection."
)


class ProvenanceKind(str, Enum):
    """Where a scenario's shape came from in the real world.

    Attributes:
        DOCUMENTED_INCIDENT: A published account of a real intrusion.
        ATTACK_TAXONOMY: A published classification of ICS attack technique.
        PROCESS_FAILURE_MODE: A process-engineering account of how this plant can be driven wrong.
        VENDOR_ADVISORY: A vendor or national-CERT advisory.
    """

    DOCUMENTED_INCIDENT = "DOCUMENTED_INCIDENT"
    ATTACK_TAXONOMY = "ATTACK_TAXONOMY"
    PROCESS_FAILURE_MODE = "PROCESS_FAILURE_MODE"
    VENDOR_ADVISORY = "VENDOR_ADVISORY"


class Provenance(BaseModel):
    """The real-world source a scenario's shape is taken from.

    There is deliberately nowhere here to record "because it would exercise Atlas". A scenario
    whose justification is what we can catch is the circularity this whole module exists to avoid,
    and it is refused at the point of definition rather than in review.

    Attributes:
        kind: What sort of source this is.
        citation: The source itself, named specifically enough to be looked up.
        shape: What the source lends the scenario — the behaviour being borrowed, in the plant's
            terms.

    Invariants:
        The citation is not a bare placeholder.
    """

    model_config = ConfigDict(frozen=True)

    kind: ProvenanceKind
    citation: str = Field(min_length=12)
    shape: str = Field(min_length=12)

    @model_validator(mode="after")
    def _check_citation(self) -> "Provenance":
        lowered = self.citation.lower()
        for placeholder in ("tbd", "todo", "n/a", "interesting", "atlas", "sentiel"):
            if placeholder in lowered:
                raise ValueError(
                    f"provenance citation {self.citation!r} reads as a placeholder or as a "
                    "statement about our own detector; cite a documented incident, a published "
                    "taxonomy, a process failure mode or an advisory"
                )
        return self


class Direction(str, Enum):
    """Which way the adversary wants the process to go. The plant's terms, not a magnitude."""

    RAISE = "RAISE"
    LOWER = "LOWER"


class PhysicalGoal(BaseModel):
    """What the adversary wants the plant to actually do, and what they are working around.

    Attributes:
        narrative: The goal in a sentence, in plant language — "drive the clearwell above its safe
            level while the reported level stays inside its normal band".
        signal: The setpoint the adversary can reach. A declared plant signal.
        direction: Which way they want the process to move.
        limit: The true value the adversary is driving the process toward, in engineering units.
            A statement about the plant's safe operation, taken from the goal — not a deviation
            size, and not a distance from any learned band.
        constraints: What the adversary is trying to respect while doing it, in plant terms.

    Invariants:
        The narrative and the constraints are phrased, not empty.
    """

    model_config = ConfigDict(frozen=True)

    narrative: str = Field(min_length=12)
    signal: str = Field(min_length=1)
    direction: Direction
    limit: float
    constraints: tuple[str, ...] = ()


class Scenario(BaseModel):
    """One attack, specified by intent and bound to a plant.

    Attributes:
        scenario_id: Stable identifier.
        plant_id: The plant this scenario is written against.
        goal: What the adversary wants the process to do.
        provenance: Where the shape comes from in the real world.
        issuer: The device the adversary writes from. Whether that device holds a grant is the
            plant's declaration to make, not this scenario's — see `phos.synth.command`.
        asset_id: The plant unit the goal acts on, so a maintenance window can be asked about it.
        patience_steps: How many samples the adversary is willing to spread the move over. One is
            an impatient adversary who moves the setpoint at once; a large number is a patient one
            who walks it. An operational choice, not a detector dial.
        first_step: The sample the adversary begins at.

    Invariants:
        Patience is at least one sample and the start is not before the run.
    """

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    goal: PhysicalGoal
    provenance: Provenance
    issuer: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    patience_steps: int = Field(ge=1)
    first_step: int = Field(ge=0)

    def prose(self) -> str:
        """Return every free-text field, joined. What `test_anti_bias.py` scans."""
        return " ".join(
            (
                self.scenario_id,
                self.goal.narrative,
                *self.goal.constraints,
                self.provenance.citation,
                self.provenance.shape,
            )
        )

    def source(self, low: float, high: float) -> "GoalSeekingSource":
        """Return the adversary that pursues this goal on a plant.

        Args:
            low: Bottom of the target signal's declared span.
            high: Top of it.

        Returns:
            A closed-loop source. What it does to the readings is whatever the physics does.
        """
        return GoalSeekingSource(self, low=low, high=high)


class GoalSeekingSource(CommandSource):
    """An adversary who watches the reported readings and writes until the goal looks met.

    Closed-loop on purpose. The alternative — a fixed schedule of writes computed up front — would
    need the author to decide in advance how far the process moves, which is the physics' answer
    and not the attacker's. Watching the reports is also what an adversary on a hijacked operator
    station can actually do, and it means an adversary who has falsified those same reports is
    misled by them.
    """

    def __init__(self, scenario: Scenario, *, low: float, high: float) -> None:
        """Prepare an adversary pursuing ``scenario`` on a signal spanning ``low`` to ``high``."""
        self._scenario = scenario
        self._low = low
        self._high = high
        self._anchor: float | None = None

    def writes_at(
        self, index: int, clock: datetime, reported: Mapping[str, float]
    ) -> Sequence[PlannedWrite]:
        """Return the write this adversary performs at one sample, if any.

        The move is walked over `Scenario.patience_steps` samples toward the goal's limit. Nothing
        here consults a band, a baseline or a score — only the goal, the span the instrument
        declares, and how much of the adversary's own patience has elapsed.
        """
        goal = self._scenario.goal
        offset = index - self._scenario.first_step
        if offset < 0 or offset >= self._scenario.patience_steps:
            return ()

        start = reported.get(goal.signal)
        if start is None:
            raise KeyError(
                f"scenario {self._scenario.scenario_id!r} targets {goal.signal!r}, which this "
                "plant does not report"
            )
        if self._anchor is None:
            # Where the setpoint stood when the adversary began. Fixed once, so the walk is a
            # straight line to the goal rather than a chase of a value it is itself moving.
            self._anchor = start
        fraction = (offset + 1) / self._scenario.patience_steps
        bound = (
            min(goal.limit, self._high)
            if goal.direction is Direction.RAISE
            else max(goal.limit, self._low)
        )
        value = self._anchor + (bound - self._anchor) * fraction
        return (
            PlannedWrite(
                issuer=self._scenario.issuer,
                signal=goal.signal,
                value=value,
                reason=f"scenario: {self._scenario.scenario_id}",
            ),
        )
