"""What Atlas's software does when handed rubbish — and the claim that is not.

An input-hostile case tests whether the pipeline survives malformed, out-of-range, truncated or
poisoned input without crashing, corrupting its baseline, or going quietly wrong. Passing every one
of them is **not** evidence that PHOS is secure against an attacker. That claim needs a live
deployment, an exposed attack surface and an adversary who did not read this repository, none of
which exist here. D2 says so in `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`; this module produces
`RobustnessOutcome`s, which carry no detection fields at all, and nothing anywhere combines them
with a breaking-point map.

**Three outcomes, and which of them is actually bad.** A crash is a defect. A *refusal* is not:
software that raises a clear, typed error naming the bad input has failed loudly, and a loud
failure is one an operator finds out about. The subtle case is `COMPLETED` — the pipeline ate the
corrupted file and produced an answer. That is only safe if the answer is still right, which is
what `baseline_shift` exists to measure, because a poisoned baseline's whole point is to produce a
model that runs perfectly and is wrong.

**Refused versus crashed is decided by an explicit list, not by a feeling.** `EXPECTED_REFUSALS`
names the exception types the pipeline documents itself as raising. Anything else escaping is a
crash, including the ones that look harmless: an `IndexError` out of a parser is a parser that did
not know its input was short.
"""

import json
import logging
from pathlib import Path
from typing import Final

import pandas
from pydantic import BaseModel, ConfigDict, Field

from phos.atlas import MahalanobisModel
from phos.atlas.topology import TopologyError
from phos.breaking.corpus import AttackCorpus, CorpusNotFoundError, NormalCorpus, load_attack_corpus
from phos.breaking.outcome import RobustnessOutcome, RobustnessVerdict
from phos.eval import Dataset
from phos.models import FittedModel
from phos.reasoning import is_out_of_band
from phos.synth.attacks import MANIFEST_FILE, AttackType, HostileGroundTruth

__all__ = [
    "EXPECTED_REFUSALS",
    "CorpusRobustness",
    "out_of_band_rate",
    "run_robustness",
]

logger = logging.getLogger(__name__)

EXPECTED_REFUSALS: Final[tuple[type[Exception], ...]] = (
    ValueError,
    TopologyError,
    CorpusNotFoundError,
    pandas.errors.ParserError,
    pandas.errors.EmptyDataError,
    UnicodeDecodeError,
)
"""Exception types the pipeline documents itself as raising on bad input.

One of these escaping is a **loud refusal**: the software declined the input and said why, which is
the correct behaviour for a security product handed something it cannot trust. Anything else is a
crash — a failure the code did not anticipate and therefore did not describe. `TopologyError` and
`CorpusNotFoundError` derive from `ValueError` and `FileNotFoundError` respectively and are listed
explicitly so the intent survives a refactor of either hierarchy.
"""


class CorpusRobustness(BaseModel):
    """What one input-hostile corpus did to Atlas's software.

    Attributes:
        corpus: The corrupted corpus's name.
        plant_id: Which plant it was built from.
        outcomes: One per hostile case in the corpus.
        loaded: Whether the corpus could be read at all. False is a result, not an error — a
            truncated file that the adapter refuses is the adapter working.

    Invariants:
        None beyond its members'. Deliberately carries no recall, no latency and no verdict about
        detection, because an input-hostile corpus declares no attack windows to detect.
    """

    model_config = ConfigDict(frozen=True)

    corpus: str = Field(min_length=1)
    plant_id: str = ""
    outcomes: tuple[RobustnessOutcome, ...] = ()
    loaded: bool = False

    @property
    def all_safe(self) -> bool:
        """Whether every case ended in a refusal or a completion rather than a crash.

        Says nothing about detection, and is not a security claim. See the module docstring.
        """
        return all(outcome.is_safe for outcome in self.outcomes)


def out_of_band_rate(fitted: FittedModel, dataset: Dataset) -> float:
    """Return the fraction of a corpus's readings the model considers outside its expected range.

    The one number that says whether a baseline is still the right baseline. Measured through 4A's
    `is_out_of_band`, the same door the engine promotes evidence through, so a shift measured here
    is a shift in what Atlas would actually alert on.

    Args:
        fitted: The model to interrogate.
        dataset: Readings believed normal.

    Returns:
        Out-of-band readings over total readings, or ``0.0`` for an empty corpus.
    """
    if not dataset.observations:
        return 0.0
    by_id = {observation.id: observation for observation in dataset.observations}
    departures = 0
    scored = 0
    for deviation in fitted.score(dataset.observations):
        observation = by_id.get(deviation.observation_id)
        if observation is None:
            continue
        scored += 1
        if is_out_of_band(deviation, observation):
            departures += 1
    return departures / scored if scored else 0.0


def _baseline_shift(
    corpus: AttackCorpus, clean: NormalCorpus, reference: NormalCorpus
) -> float | None:
    """Return how far a poisoned fit moved what the model calls abnormal on genuinely normal data.

    Fits one model on the poisoned corpus and one on the clean training corpus, then scores the
    *same* untouched holdout with both. The difference between their out-of-band rates is the
    silent damage: a baseline learned from contaminated data can run without error and still call
    normal operation abnormal, or — worse — call the abnormal normal.

    Returns:
        The absolute difference in out-of-band rate, in ``[0, 1]``, or ``None`` if either fit
        failed. Zero means the poisoning changed nothing Atlas would act on.
    """
    try:
        poisoned = MahalanobisModel().fit(corpus.dataset.observations)
        honest = MahalanobisModel().fit(clean.dataset.observations)
    except (ValueError, TopologyError) as error:
        logger.warning("%s: could not fit a comparison baseline: %s", corpus.name, error)
        return None
    shifted = out_of_band_rate(poisoned, reference.dataset)
    expected = out_of_band_rate(honest, reference.dataset)
    logger.info(
        "%s: out-of-band rate on %s is %.4f from a poisoned fit against %.4f from a clean one",
        corpus.name,
        reference.name,
        shifted,
        expected,
    )
    return abs(shifted - expected)


def _attempt(directory: Path) -> tuple[AttackCorpus | None, Exception | None]:
    """Try to read a corrupted corpus, returning either it or whatever stopped us."""
    try:
        return load_attack_corpus(directory), None
    except Exception as error:
        return None, error


def _verdict_for(error: Exception | None) -> tuple[RobustnessVerdict, str, str]:
    """Classify what happened into a verdict, an exception name and a readable detail."""
    if error is None:
        return RobustnessVerdict.COMPLETED, "", "the pipeline read the corpus and ran to completion"
    if isinstance(error, EXPECTED_REFUSALS):
        return (
            RobustnessVerdict.REFUSED,
            type(error).__name__,
            f"refused loudly: {error}"[:400],
        )
    return (
        RobustnessVerdict.CRASHED,
        type(error).__name__,
        f"escaped uncaught: {error}"[:400],
    )


def _declared_hostile(directory: Path) -> tuple[HostileGroundTruth, ...]:
    """Return a corpus's declared input-hostile cases, reading the manifest alone.

    Used when the payload defeated the reader. The manifest is a separate file from the telemetry,
    so a malformed CSV leaves it perfectly readable, and it is the only honest source for what the
    corruption *was*.

    Returns:
        The declared cases, or empty when the manifest is missing or itself unreadable.
    """
    path = directory / MANIFEST_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return tuple(HostileGroundTruth.model_validate(entry) for entry in raw.get("hostile", []))
    except (OSError, ValueError) as error:
        logger.warning(
            "%s: could not read declared ground truth from %s: %s", directory.name, path, error
        )
        return ()


def _unreadable_outcomes(
    directory: Path, verdict: RobustnessVerdict, error_type: str, detail: str
) -> tuple[RobustnessOutcome, ...]:
    """Record what happened to a corpus whose payload could not be read.

    One outcome per *declared* case, so the report names the real corruption kinds. When even the
    manifest is unreadable there is no declared ground truth, and the single outcome carries
    ``attack_type=None`` rather than a guess.
    """
    declared = _declared_hostile(directory)
    if not declared:
        return (
            RobustnessOutcome(
                attack_id=directory.name,
                attack_type=None,
                corpus=directory.name,
                verdict=verdict,
                error_type=error_type,
                detail=f"{detail} (no readable manifest, so the corruption kind is undeclared)",
            ),
        )
    return tuple(
        RobustnessOutcome(
            attack_id=case.attack_id,
            attack_type=case.type,
            corpus=directory.name,
            target=case.target,
            rows_affected=case.rows_affected,
            verdict=verdict,
            error_type=error_type,
            detail=f"{case.description} -> {detail}" if case.description else detail,
        )
        for case in declared
    )


def run_robustness(
    directory: Path,
    clean: NormalCorpus | None = None,
    reference: NormalCorpus | None = None,
) -> CorpusRobustness:
    """Measure what one input-hostile corpus does to Atlas's software.

    Args:
        directory: The corrupted corpus's directory.
        clean: The plant's normal training corpus, for the poisoned-baseline comparison. Omitted,
            no baseline shift is measured and `RobustnessOutcome.baseline_shift` stays ``None``.
        reference: An untouched holdout to score both baselines against. Omitted, ``clean`` is
            used, which is weaker — a model scored on its own training data understates its own
            out-of-band rate — so the caller is expected to pass a separate holdout.

    Returns:
        The corpus's robustness result. Never a detection result: there is no route from here to a
        breaking-point map.

    Note:
        This function catches broadly on purpose. Classifying whatever escapes *is* the
        measurement, so an exception is data rather than a failure of the run.
    """
    corpus, error = _attempt(directory)
    verdict, error_type, detail = _verdict_for(error)

    if corpus is None:
        # The payload would not load. The manifest is a *different file*, so it usually still
        # reads — and it carries the declared ground truth, which is where the corruption's kind
        # comes from. Naming a kind any other way would be a guess dressed as a measurement.
        return CorpusRobustness(
            corpus=directory.name,
            outcomes=_unreadable_outcomes(directory, verdict, error_type, detail),
            loaded=False,
        )

    shift: float | None = None
    if clean is not None and any(
        case.type is AttackType.POISONED_BASELINE for case in corpus.manifest.hostile
    ):
        shift = _baseline_shift(corpus, clean, reference or clean)

    outcomes = tuple(
        _outcome_for(case, corpus, verdict, error_type, detail, shift)
        for case in corpus.manifest.hostile
    )
    logger.info(
        "%s: %d input-hostile case(s), verdict %s", corpus.name, len(outcomes), verdict.value
    )
    return CorpusRobustness(
        corpus=corpus.name,
        plant_id=corpus.manifest.plant_id,
        outcomes=outcomes,
        loaded=True,
    )


def _outcome_for(
    case: HostileGroundTruth,
    corpus: AttackCorpus,
    verdict: RobustnessVerdict,
    error_type: str,
    detail: str,
    shift: float | None,
) -> RobustnessOutcome:
    """Build one case's outcome, attaching the baseline shift only where it means something."""
    return RobustnessOutcome(
        attack_id=case.attack_id,
        attack_type=case.type,
        corpus=corpus.name,
        target=case.target,
        rows_affected=case.rows_affected,
        verdict=verdict,
        error_type=error_type,
        detail=f"{case.description} -> {detail}" if case.description else detail,
        baseline_shift=shift if case.type is AttackType.POISONED_BASELINE else None,
    )
