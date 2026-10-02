"""What happened to one attack, what happened to one hostile case, and why they are different types.

D2 made the two flavours unrepresentable in one place: `HostileGroundTruth` has no `interval()`, so
there is no route from a malformed record to something a harness would score as a missed detection.
D3 has to keep that property on the results side, where the temptation is stronger — a single
`Outcome` type with a `detected` field would be convenient, and would let a robustness pass quietly
inflate a detection rate. So there are two unrelated types here:

* `AttackOutcome` — a detection attack. Carries `detected`, `latency`, a `verdict`, and the
  fingerprint status that decides which column of the report it may appear in.
* `RobustnessOutcome` — an input-hostile case. Carries **no** `detected` field, no latency, no
  verdict and no fingerprint status, because none of them mean anything about a corrupted file.
  There is no constructor, method or function anywhere in this package that turns one into the
  other.

**The verdict is where the honesty rules meet.** A detection result is not simply caught-or-missed,
because two of the four cases mean something a bare boolean would hide:

* `INERT` — D2's zero-magnitude control. The manipulation was arithmetically nothing, so there was
  never anything to catch and a "miss" here would be a lie about Atlas. Kept on the map because a
  *detection* on an inert attack would be a leaked fingerprint caught red-handed.
* `MISSED_DANGEROUS` — the plant's true state went somewhere five days of unattacked operation
  never reached, and Atlas said nothing. This is the worst cell on the map, it is the cell the liar
  attack exists to reach, and it is judged from D1's true-state record rather than from the
  readings Atlas saw, because for a liar those readings were fabricated.

`MISSED_DANGEROUS` is deliberately *not* a subtype of `MISSED` that a reader might aggregate away.
It is a distinct verdict, and `is_miss` is the only thing that pools them.
"""

from datetime import timedelta
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from phos.breaking.fingerprint import FingerprintAssessment, FingerprintStatus
from phos.breaking.truth import TrueStateVerdict
from phos.synth.attacks import AttackType, DifficultyLevel

__all__ = [
    "AttackOutcome",
    "DetectionVerdict",
    "RobustnessOutcome",
    "RobustnessVerdict",
]


class DetectionVerdict(str, Enum):
    """What became of one detection attack.

    Attributes:
        CAUGHT: At least one Atlas alert landed in the attack's window.
        MISSED: Atlas said nothing, and D1's true-state record shows the plant stayed inside
            ordinary operation. A miss, and the least alarming kind.
        MISSED_DANGEROUS: Atlas said nothing while the true state went somewhere unattacked
            operation never reached. The worst outcome on the map.
        INERT: The manipulation had exactly zero magnitude — D2's anti-fingerprint control. There
            was nothing to detect, so this is neither a catch nor a miss.
    """

    CAUGHT = "CAUGHT"
    MISSED = "MISSED"
    MISSED_DANGEROUS = "MISSED_DANGEROUS"
    INERT = "INERT"


class RobustnessVerdict(str, Enum):
    """What became of one input-hostile case. Never a statement about detection.

    Attributes:
        REFUSED: The pipeline raised a clear, typed error naming what was wrong. Safe: a loud
            failure is a failure an operator finds out about.
        COMPLETED: The pipeline consumed the corrupted input and ran to completion. Safe only if
            what it produced is still right, which `baseline_shift` is what measures.
        CRASHED: The pipeline failed in a way its own error handling did not describe — an
            unexpected exception type escaping the boundary. A defect.
    """

    REFUSED = "REFUSED"
    COMPLETED = "COMPLETED"
    CRASHED = "CRASHED"


class AttackOutcome(BaseModel):
    """What Atlas did about one detection attack, and what the plant really did meanwhile.

    Attributes:
        attack_id: Stable identifier, as D2's ground truth gave it.
        attack_type: Which attack this was.
        subtlety: Where on D2's difficulty dial it ran.
        difficulty: The band that subtlety falls in.
        corpus: The dataset it was injected into.
        plant_id: Which plant that corpus is a run of. Carried because a breaking point is a
            property of an attack type *on a given plant*: the same type against a different
            machine, with a different baseline and a different daily rhythm, is a different
            measurement and pooling the two would hide the structure the map exists to show.
        detected: Whether any alert landed inside the attack's window.
        n_alerts: How many did.
        latency_seconds: Delay from the window's start to the first alert inside it, or ``None``
            when nothing landed there.
        fingerprint: Whether this result may be reported as clean evidence, and why.
        true_state: What D1's record says the plant actually did.
        peak_truth_departure: D2's own measured peak true-state gap against the clean twin,
            carried through so the two independent records can be compared.
        peak_report_departure: The same for what the instruments reported. For a liar attack the
            gap between this and `peak_truth_departure` *is* the attack.

    Invariants:
        A detected attack has at least one alert and a non-detected one has none, so the flag and
        its count cannot disagree.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    attack_type: AttackType
    subtlety: float = Field(ge=0.0, le=1.0)
    difficulty: DifficultyLevel
    corpus: str = ""
    plant_id: str = ""
    detected: bool
    n_alerts: int = Field(default=0, ge=0)
    latency_seconds: float | None = None
    fingerprint: FingerprintAssessment
    true_state: TrueStateVerdict
    peak_truth_departure: float = Field(default=0.0, ge=0.0)
    peak_report_departure: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.detected != (self.n_alerts > 0):
            raise ValueError(
                f"outcome for {self.attack_id!r} is incoherent: detected={self.detected} with "
                f"{self.n_alerts} alert(s) in the window"
            )
        if not self.detected and self.latency_seconds is not None:
            raise ValueError(
                f"outcome for {self.attack_id!r} reports a latency but no detection; a latency is "
                "the delay to an alert that landed, so an undetected window cannot have one"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> DetectionVerdict:
        """The verdict, derived rather than stored so it cannot contradict the facts behind it.

        The order of the tests is the point. An inert attack is settled first, because a nil
        of exactly zero magnitude was never there to be caught and calling it a miss would slander
        Atlas with D2's own control case. Then a catch. Then the true-state record decides which
        kind of miss this was — which is the whole reason the harness reads that record at all.
        """
        if self.is_inert:
            return DetectionVerdict.INERT
        if self.detected:
            return DetectionVerdict.CAUGHT
        if self.true_state.dangerous:
            return DetectionVerdict.MISSED_DANGEROUS
        return DetectionVerdict.MISSED

    @property
    def is_inert(self) -> bool:
        """Whether this was D2's zero-magnitude control rather than an attack.

        Read off the dial rather than off the measured departure: `strength_of(1.0)` is exactly
        ``0.0``, so a subtlety of one is a manipulation that provably did nothing.
        """
        return self.subtlety >= 1.0

    @property
    def is_miss(self) -> bool:
        """Whether Atlas failed to see an attack that was really there.

        Pools `MISSED` and `MISSED_DANGEROUS` — the only place the two are ever pooled — and
        excludes `INERT`, which was not there to be seen.
        """
        return self.verdict in (DetectionVerdict.MISSED, DetectionVerdict.MISSED_DANGEROUS)

    @property
    def is_clean_evidence(self) -> bool:
        """Whether this result belongs in the headline map rather than the caveated column."""
        return self.fingerprint.status is FingerprintStatus.CLEAN

    @property
    def latency(self) -> timedelta | None:
        """Detection latency as a duration, or ``None`` when nothing was detected."""
        if self.latency_seconds is None:
            return None
        return timedelta(seconds=self.latency_seconds)


class RobustnessOutcome(BaseModel):
    """What Atlas's software did when handed a corrupted corpus.

    Carries no `detected`, no latency, no verdict about detection and no fingerprint status, and
    has no method that produces any of them. An input-hostile case is not something Atlas was
    supposed to detect, so there is no route from here into a breaking-point map — the same
    boundary D2 draws by giving `HostileGroundTruth` no `interval()`.

    Attributes:
        attack_id: Stable identifier, as D2's ground truth gave it.
        attack_type: Which corruption this was, or ``None`` when the corruption defeated even the
            manifest and there is therefore no declared ground truth to name it from. ``None`` is
            the honest answer there: guessing a kind would put a specific claim on a corpus nothing
            could read.
        corpus: The dataset that was corrupted.
        target: The column corrupted, or empty for a corruption of the file as a whole.
        rows_affected: How many records the corruption touched.
        verdict: Whether the pipeline refused it, completed on it, or crashed.
        error_type: The exception class name when it refused or crashed, else empty.
        detail: What happened, in a sentence — the error message, or what ran to completion.
        baseline_shift: For a poisoned baseline, how far the contamination moved what the model
            calls abnormal: the absolute difference, on the same untouched holdout, between the
            out-of-band rate of a model fitted on the poisoned corpus and one fitted on clean data.
            ``None`` when the case does not poison a baseline or the comparison could not be made.
            This is the one number that distinguishes "survived" from "silently went wrong", since
            a baseline learned from contaminated data runs without error and is still wrong.

    Invariants:
        A refusal or a crash names the exception that caused it.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    attack_type: AttackType | None = None
    corpus: str = ""
    target: str = ""
    rows_affected: int = Field(default=0, ge=0)
    verdict: RobustnessVerdict
    error_type: str = ""
    detail: str = ""
    baseline_shift: float | None = None

    @model_validator(mode="after")
    def _check_error(self) -> Self:
        failed = self.verdict in (RobustnessVerdict.REFUSED, RobustnessVerdict.CRASHED)
        if failed and not self.error_type:
            raise ValueError(
                f"input-hostile case {self.attack_id!r} reports {self.verdict.value} without "
                "naming the exception that caused it, so nobody could act on it"
            )
        return self

    @property
    def is_safe(self) -> bool:
        """Whether the software behaved acceptably: a loud refusal, or a completion.

        A crash is the only unsafe outcome here, and completing is *conditionally* safe — see
        `baseline_shift`, which is what says whether a completion was also correct. This property
        deliberately says nothing about detection.
        """
        return self.verdict is not RobustnessVerdict.CRASHED
