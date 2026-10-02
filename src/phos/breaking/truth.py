"""Judging what really happened from D1's true-state record, not from the readings Atlas saw.

For most attacks the readings and the truth agree well enough that it does not matter which one
scores the result. For the liar it matters completely: a false-data-injection attack drives the
plant somewhere dangerous *while the instruments report calm*, so the telemetry is at its most
reassuring exactly when the plant is at its worst. Scoring that from the telemetry would credit
Atlas for staying quiet about a tank it was being lied to about.

D1 records the plant's true state at every sample, independently of what the instruments reported,
and writes it beside every corpus as ``truth.csv``. This module reads it and answers one question:
**did the true state go somewhere the plant never went when nobody was attacking it?**

**The envelope is non-parametric, and that is deliberate.** These plants have a daily demand cycle,
so a mean and a standard deviation over the whole run describe a distribution the plant is never
actually at: the mean sits between the night trough and the afternoon peak. The envelope here is
instead the observed *range* of each signal across every attack-free sample — the full sweep of
ordinary operation, cycle included — widened by a margin of a few measurement noises. Leaving it
means the true state reached a value that five days of unattacked operation never produced.

**A signal the attacker held is not evidence that the plant was harmed.** A rogue command writes a
setpoint and an actuator manipulation drives a valve; the true value of *that* signal then leaves
its envelope by construction, and counting it would score every attack as dangerous and the word
would stop meaning anything. So danger is judged only on **consequence signals**: those the
manipulation did not drive directly. The test is the signal's declared `SignalKind` — an actuator
or a setpoint named as a target was moved by the attacker, whereas a sensor named as a target had
only its *reading* falsified, leaving its true value a consequence like any other. That is exactly
the liar case, and it is why the liar is judged correctly here without being special-cased.

Nothing in this module consults telemetry, a detector, or a label. It reads the truth record and
the plant's declaration, and returns what the plant did.
"""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Self

import pandas
from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.eval import LabelledInterval
from phos.ontology import UtcDatetime
from phos.synth import PlantDescription
from phos.synth.attacks import AttackGroundTruth
from phos.synth.plant import SignalKind

__all__ = [
    "DEFAULT_DANGER_MARGIN",
    "DRIVEN_KINDS",
    "SignalExcursion",
    "TrueStateRecord",
    "TrueStateVerdict",
    "attack_windows_of",
    "judge_true_state",
    "load_true_state",
]

logger = logging.getLogger(__name__)

TIMESTAMP_COLUMN: Final = "timestamp"
"""The truth record's first column, as `phos.synth.attacks.truth_lines` writes it."""

DEFAULT_DANGER_MARGIN: Final = 3.0
"""Measurement noises past the attack-free envelope before a true state is called dangerous.

Three rather than one because the envelope is already the extreme of every unattacked sample, so a
value just past it is the tail of ordinary operation rather than a new regime. Raising it makes the
harness harder to convince that the plant was harmed, which is the direction an honest default
errs in.
"""

DRIVEN_KINDS: Final = frozenset({SignalKind.ACTUATOR, SignalKind.SETPOINT})
"""Signal kinds an attacker moves *directly* when it names one as a target.

A targeted actuator or setpoint leaves its envelope because the attack put it there, so it says
nothing about whether the plant was harmed. A targeted **sensor** had only its reading falsified —
its true value is a consequence, and is exactly what the liar attack must be judged on.
"""


class SignalExcursion(BaseModel):
    """How far one signal's true state went beyond anything unattacked operation produced.

    Attributes:
        signal: The signal key.
        envelope_low: Lowest true value across every attack-free sample.
        envelope_high: Highest.
        window_low: Lowest true value inside the attack's window.
        window_high: Highest.
        excess: How far outside the envelope the window reached, in engineering units. Zero when
            the window stayed inside it.
        margin: Engineering units the excess had to clear to count as dangerous.
        driven: Whether the attacker moved this signal directly, in which case its excursion is the
            attack rather than a consequence of it and does not count toward danger.

    Invariants:
        ``excess`` is never negative; a window inside the envelope reports zero rather than a gap.
    """

    model_config = ConfigDict(frozen=True)

    signal: str = Field(min_length=1)
    envelope_low: float
    envelope_high: float
    window_low: float
    window_high: float
    excess: float = Field(ge=0.0)
    margin: float = Field(ge=0.0)
    driven: bool = False

    @property
    def is_dangerous(self) -> bool:
        """Whether this excursion counts as the plant having been driven somewhere it does not go.

        False for a signal the attacker held directly, however far it moved.
        """
        return not self.driven and self.excess > self.margin


class TrueStateVerdict(BaseModel):
    """What the plant really did during one attack, judged from D1's record alone.

    Attributes:
        attack_id: The attack judged.
        dangerous: Whether any consequence signal's true state left its attack-free envelope by
            more than the margin. This is the fact a detection result is scored against — an
            attack that reached here while Atlas stayed silent is the worst outcome on the map.
        excursions: Every signal that left its envelope at all, worst first. Includes the ones
            discounted as directly driven, so a reader can see what was excluded and why.
        peak_excess: The largest qualifying excess, in engineering units. Zero when nothing
            qualified.
        peak_signal: The consequence signal that went furthest, or empty.
        physical_effect: D2's own measured verdict on whether the plant moved at all, carried
            through for cross-checking. A `dangerous` verdict on an attack D2 measured as having
            no physical effect would mean the two records disagree.

    Invariants:
        ``dangerous`` is true exactly when some excursion is dangerous, so the headline and its
        evidence cannot disagree.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    dangerous: bool
    excursions: tuple[SignalExcursion, ...] = ()
    peak_excess: float = Field(default=0.0, ge=0.0)
    peak_signal: str = ""
    physical_effect: bool = False

    @model_validator(mode="after")
    def _check_agreement(self) -> Self:
        if self.dangerous != any(item.is_dangerous for item in self.excursions):
            raise ValueError(
                f"verdict for {self.attack_id!r} is incoherent: dangerous={self.dangerous} but "
                f"{sum(1 for item in self.excursions if item.is_dangerous)} of its excursions "
                "qualify. A danger verdict must name the excursion that justifies it"
            )
        return self


class TrueStateRecord(BaseModel):
    """D1's record of what the plant was actually doing, sample by sample.

    Not telemetry. These are the process variables before the instruments saw them, so they are
    correct even where an attack made the instruments lie. Never hand this to a detector.

    Attributes:
        timestamps: Every sample instant, ascending.
        values: Per signal key, the true value at each timestamp. Same length as ``timestamps``.
        source: Where the record was read from, for provenance.

    Invariants:
        Every series is the same length as ``timestamps``, so a value always has an instant.
    """

    model_config = ConfigDict(frozen=True)

    timestamps: tuple[UtcDatetime, ...]
    values: dict[str, tuple[float, ...]]
    source: str = ""

    @model_validator(mode="after")
    def _check_lengths(self) -> Self:
        expected = len(self.timestamps)
        wrong = sorted(key for key, series in self.values.items() if len(series) != expected)
        if wrong:
            raise ValueError(
                f"true-state record from {self.source or 'memory'} is ragged: "
                f"{', '.join(wrong)} do not have one value per sample instant"
            )
        return self

    def signals(self) -> tuple[str, ...]:
        """Return every signal key the record carries, in declaration order."""
        return tuple(self.values)

    def excursion(
        self,
        signal: str,
        window: LabelledInterval,
        attack_windows: Sequence[LabelledInterval],
        margin: float,
        *,
        driven: bool = False,
    ) -> SignalExcursion | None:
        """Measure how far one signal's true state left unattacked operation during ``window``.

        Args:
            signal: The signal key to judge.
            window: The attack's window.
            attack_windows: Every attack window in the corpus. Samples inside any of them are
                excluded from the envelope, so one attack cannot widen the envelope another is
                judged against.
            margin: Engineering units past the envelope before an excess counts.
            driven: Whether the attacker moved this signal directly.

        Returns:
            The excursion, or ``None`` when the window or the attack-free set holds no samples —
            there is nothing to compare, and inventing a comparison would be worse than declining.

        Raises:
            KeyError: If the record carries no such signal.
        """
        series = self.values[signal]
        free = [
            value
            for stamp, value in zip(self.timestamps, series, strict=True)
            if not any(interval.contains(stamp) for interval in attack_windows)
        ]
        inside = [
            value
            for stamp, value in zip(self.timestamps, series, strict=True)
            if window.contains(stamp)
        ]
        if not free or not inside:
            logger.debug(
                "%s: no comparison available for %s (%d free, %d in window)",
                self.source,
                signal,
                len(free),
                len(inside),
            )
            return None

        low, high = min(free), max(free)
        return SignalExcursion(
            signal=signal,
            envelope_low=low,
            envelope_high=high,
            window_low=min(inside),
            window_high=max(inside),
            excess=max(0.0, max(inside) - high, low - min(inside)),
            margin=margin,
            driven=driven,
        )


def load_true_state(path: Path) -> TrueStateRecord:
    """Read a corpus's ``truth.csv`` into a `TrueStateRecord`.

    Args:
        path: The truth file D1 wrote beside the telemetry.

    Returns:
        The record, with every non-timestamp column as a signal series.

    Raises:
        ValueError: If the file has no timestamp column or no signals. Both would silently produce
            a record that judges every attack as harmless, which is the failure this whole module
            exists to prevent.
    """
    frame = pandas.read_csv(path)
    if TIMESTAMP_COLUMN not in frame.columns:
        raise ValueError(
            f"{path} has no {TIMESTAMP_COLUMN!r} column, so its rows cannot be placed in time"
        )
    keys = [column for column in frame.columns if column != TIMESTAMP_COLUMN]
    if not keys:
        raise ValueError(f"{path} carries timestamps and no signals, so it records no true state")

    stamps = pandas.to_datetime(frame[TIMESTAMP_COLUMN], utc=True)
    return TrueStateRecord(
        timestamps=tuple(stamp.to_pydatetime() for stamp in stamps),
        values={key: tuple(float(value) for value in frame[key]) for key in keys},
        source=str(path),
    )


def judge_true_state(
    truth: AttackGroundTruth,
    record: TrueStateRecord,
    description: PlantDescription,
    attack_windows: Sequence[LabelledInterval],
    margin_noises: float = DEFAULT_DANGER_MARGIN,
) -> TrueStateVerdict:
    """Decide whether one attack drove the plant's true state somewhere it does not go.

    Args:
        truth: Measured ground truth for the attack, supplying its window and its targets.
        record: D1's true-state record for the same run.
        description: The plant's declaration, supplying each signal's kind and measurement noise.
        attack_windows: Every attack window in the corpus, excluded from the envelope.
        margin_noises: Measurement noises past the envelope before an excess counts as dangerous.

    Returns:
        The verdict, naming the consequence signal that went furthest.

    Raises:
        ValueError: If ``margin_noises`` is negative — a negative margin would call ordinary
            operation dangerous.
    """
    if margin_noises < 0.0:
        raise ValueError(f"margin_noises must not be negative, got {margin_noises}")

    driven_targets = {
        key
        for key in truth.target_signals
        if key in description.signal_keys() and description.signal(key).kind in DRIVEN_KINDS
    }
    window = truth.interval()

    excursions: list[SignalExcursion] = []
    for key in record.signals():
        if key not in description.signal_keys():
            continue
        excursion = record.excursion(
            key,
            window,
            attack_windows,
            margin=margin_noises * description.signal(key).noise_stddev,
            driven=key in driven_targets,
        )
        if excursion is not None and excursion.excess > 0.0:
            excursions.append(excursion)

    excursions.sort(key=lambda item: (-item.excess, item.signal))
    qualifying = [item for item in excursions if item.is_dangerous]
    return TrueStateVerdict(
        attack_id=truth.attack_id,
        dangerous=bool(qualifying),
        excursions=tuple(excursions),
        peak_excess=qualifying[0].excess if qualifying else 0.0,
        peak_signal=qualifying[0].signal if qualifying else "",
        physical_effect=truth.physical_effect,
    )


def attack_windows_of(truths: Sequence[AttackGroundTruth]) -> tuple[LabelledInterval, ...]:
    """Return every attack's labelled window, for excluding attacked time from an envelope."""
    return tuple(item.interval() for item in truths)
