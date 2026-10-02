"""The three-way split that keeps a calibration win from being an artefact.

PART 3 needed two slices: fit on one, measure on the other. Calibration needs three, because a
calibrator is itself fitted on labels. Fitting it on the test split and then reporting the
resulting calibration error would be measuring a model on its own training data — the exact
dishonesty `train_test_split` was written to prevent, one level up. So:

- **train** — the attack-free prefix. Fits the behavioural model. Attack-free because a model that
  learns an attack as normal cannot be surprised by it later.
- **calib** — a labelled middle slice. Fits the calibrator. It needs *both* classes, because a
  score-to-probability map learned from one class is a constant.
- **test** — the labelled remainder. Every reported metric, including the calibration error, comes
  from here and from nothing else.

The three are disjoint, contiguous and time-ordered, so no observation is used twice and no
information leaks backwards from a later slice into an earlier one.

**Degenerate slices raise instead of returning.** This module is quite willing to refuse a corpus,
because each degenerate case produces a number that looks like a result. The one that matters most
is an attack-free *test* slice: every alert on it is a false positive, so a calibrator answering
"0.0" to everything scores a perfect calibration error, and the before/after comparison this PART
exists to make would report a spectacular improvement that means nothing at all. HAI is a live
example rather than a hypothetical — its attacks all fall in the first half of the corpus, so the
fractions that suit BATADAL leave HAI with nothing to be right about. When that happens the
operator narrows the fractions until every slice is viable, and the error says which one failed.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.eval.datasets import Dataset, LabelledInterval
from phos.models.base import SplitPolicy, train_test_split
from phos.ontology import Observation

__all__ = [
    "CalibrationSplitPolicy",
    "DegenerateSplitError",
    "attack_free_fit_calib_split",
    "prefix_split",
    "train_calib_test_split",
]

logger = logging.getLogger(__name__)


class DegenerateSplitError(ValueError):
    """A split whose slices cannot support an honest measurement.

    Subclasses `ValueError` so callers that only know about the built-in still catch it, while a
    caller that wants to distinguish "this corpus needs different fractions" from any other bad
    argument — `scripts/calibrate_corpora.py` does — can catch this instead.
    """


class CalibrationSplitPolicy(BaseModel):
    """How a corpus is divided into training, calibration and test slices.

    Both fractions are of the **whole corpus timeline**, and test takes whatever is left, so the
    two numbers here fully determine all three boundaries.

    Attributes:
        train_fraction: Largest share of the timeline the attack-free training prefix may cover.
            A ceiling, not a target: the prefix is cut shorter whenever that is what it takes to
            keep an attack out of training, and the space given up goes to calibration.
        calib_fraction: Share of the timeline covered by the calibration slice, measured from the
            corpus start alongside `train_fraction` — so calibration ends at
            ``train_fraction + calib_fraction`` of the timeline.

    Invariants:
        Both fractions are positive and together leave a non-empty remainder for test.
    """

    model_config = ConfigDict(frozen=True)

    train_fraction: float = Field(default=0.4, gt=0.0, lt=1.0)
    calib_fraction: float = Field(default=0.3, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _check_remainder(self) -> Self:
        if self.train_fraction + self.calib_fraction >= 1.0:
            raise ValueError(
                f"train_fraction ({self.train_fraction}) and calib_fraction "
                f"({self.calib_fraction}) must leave a test remainder, but together they cover "
                f"{self.train_fraction + self.calib_fraction:.2f} of the timeline"
            )
        return self


def train_calib_test_split(
    dataset: Dataset, policy: CalibrationSplitPolicy
) -> tuple[Dataset, Dataset, Dataset]:
    """Split ``dataset`` into an attack-free training prefix, a calibration slice and a test slice.

    The training prefix is delegated to `phos.models.train_test_split` so that "attack-free
    prefix" means exactly what it means in PART 3. What this adds is the second cut: the remainder
    is divided at ``train_fraction + calib_fraction`` of the corpus timeline.

    Args:
        dataset: The labelled corpus to divide.
        policy: The two fraction ceilings.

    Returns:
        ``(train, calib, test)``, disjoint and in time order, together holding every observation
        in ``dataset``.

    Raises:
        DegenerateSplitError: If any slice is empty, if the corpus has no attack-free prefix to
            train on, or if calib or test lacks either attack or normal points. Each message names
            the offending slice and what it is missing.

    Note:
        Pure and deterministic: the same dataset and policy always produce the same three slices.
    """
    if not dataset.observations:
        raise DegenerateSplitError(f"{dataset.name} has no observations to split")

    train, remainder = prefix_split(dataset, SplitPolicy(train_fraction=policy.train_fraction))
    if not train.observations:
        raise DegenerateSplitError(
            f"{dataset.name} yields no attack-free training prefix: its first observation is "
            "already inside a labelled attack window, so there is nothing to learn normal from"
        )

    start = dataset.observations[0].timestamp
    span = dataset.observations[-1].timestamp - start
    calib_cutoff = start + span * (policy.train_fraction + policy.calib_fraction)

    calib_observations = [o for o in remainder.observations if o.timestamp <= calib_cutoff]
    test_observations = remainder.observations[len(calib_observations) :]

    calib = _slice(dataset, "calib", calib_observations, policy)
    test = _slice(dataset, "test", test_observations, policy)
    train = _slice(dataset, "train", train.observations, policy)

    for part in (calib, test):
        _require_both_classes(part)

    logger.info(
        "three-way split of %s: train=%d (attack-free), calib=%d (%d attack points), "
        "test=%d (%d attack points)",
        dataset.name,
        len(train.observations),
        len(calib.observations),
        _attack_points(calib),
        len(test.observations),
        _attack_points(test),
    )
    return train, calib, test


def prefix_split(dataset: Dataset, policy: SplitPolicy) -> tuple[Dataset, Dataset]:
    """Return `phos.models.train_test_split`, made to respect unscored time (ADR 0082).

    The training prefix stops at the first unscored interval as well as the first attack: a blind
    phase carries a perturbation the data cannot yet see, so it is not verified normal. The test
    half carries the unscored intervals it overlaps, so its normal hours stay honest.

    ``phos.models`` is frozen since PART 6B (``tests/sentiel/test_engine.py``), so the rule lives
    here and delegates rather than editing the shared split. A corpus with no unscored intervals
    gets exactly what `train_test_split` returns.

    Args:
        dataset: The labelled corpus to divide.
        policy: The train fraction ceiling.

    Returns:
        ``(train, test)`` as `train_test_split` defines them, plus unscored intervals on ``test``.
    """
    if not dataset.unscored_intervals:
        return train_test_split(dataset, policy)
    bounded = dataset.model_copy(
        update={"attack_intervals": [*dataset.attack_intervals, *dataset.unscored_intervals]}
    )
    train, test = train_test_split(bounded, policy)
    test = test.model_copy(
        update={
            "attack_intervals": _intersecting(dataset.attack_intervals, test.observations),
            "unscored_intervals": _intersecting(dataset.unscored_intervals, test.observations),
        }
    )
    return train, test


def attack_free_fit_calib_split(
    dataset: Dataset, *, calib_fraction: float = 0.1
) -> tuple[Dataset, Dataset]:
    """Split an attack-free corpus into a fit prefix and a held-out normal calibration suffix.

    ADR 0083's one-class calibrator needs ordinary scores from data the model did **not** fit on.
    This cut is time-ordered and label-free: the last ``calib_fraction`` of the timeline is held
    out; the prefix trains the behavioural model. Neither slice may carry attacks or unscored
    intervals — both would poison "what normal scores look like".

    Args:
        dataset: Declared-normal / dual-clean training corpus.
        calib_fraction: Share of the timeline reserved for the normal-score calibrator. Must leave
            a non-empty fit prefix.

    Returns:
        ``(fit, calib)``, disjoint, time-ordered, both attack-free.

    Raises:
        DegenerateSplitError: If the corpus is empty, carries attacks or unscored time, or the
            fraction leaves either slice empty.
        ValueError: If ``calib_fraction`` is not in ``(0, 1)``.
    """
    if not 0.0 < calib_fraction < 1.0:
        raise ValueError(f"calib_fraction must be in (0, 1), got {calib_fraction}")
    if not dataset.observations:
        raise DegenerateSplitError(f"{dataset.name} has no observations to split")
    if dataset.attack_intervals:
        raise DegenerateSplitError(
            f"{dataset.name} is not attack-free: it carries {len(dataset.attack_intervals)} "
            "attack interval(s); attack-free fit/calib refuses to learn 'normal' from attacks"
        )
    if dataset.unscored_intervals:
        raise DegenerateSplitError(
            f"{dataset.name} carries {len(dataset.unscored_intervals)} unscored interval(s); "
            "unscored time is not verified normal and cannot teach a normal-score calibrator"
        )

    start = dataset.observations[0].timestamp
    span = dataset.observations[-1].timestamp - start
    if span.total_seconds() <= 0.0:
        raise DegenerateSplitError(
            f"{dataset.name} has no positive time span to split into fit and calib"
        )
    cutoff = start + span * (1.0 - calib_fraction)
    fit_observations = [o for o in dataset.observations if o.timestamp <= cutoff]
    calib_observations = [o for o in dataset.observations if o.timestamp > cutoff]
    if not fit_observations or not calib_observations:
        raise DegenerateSplitError(
            f"{dataset.name}: calib_fraction={calib_fraction} left an empty "
            f"{'fit' if not fit_observations else 'calib'} slice"
        )

    fit = Dataset(
        name=f"{dataset.name}-fit",
        domain=dataset.domain,
        observations=fit_observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note=(
            f"{dataset.source_note} | attack-free fit prefix, calib_fraction={calib_fraction}"
        ),
    )
    calib = Dataset(
        name=f"{dataset.name}-calib",
        domain=dataset.domain,
        observations=calib_observations,
        attack_intervals=[],
        unscored_intervals=[],
        source_note=(
            f"{dataset.source_note} | attack-free calib suffix, calib_fraction={calib_fraction}"
        ),
    )
    logger.info(
        "attack-free fit/calib split of %s: fit=%d, calib=%d (calib_fraction=%.2f)",
        dataset.name,
        len(fit.observations),
        len(calib.observations),
        calib_fraction,
    )
    return fit, calib


def _attack_points(dataset: Dataset) -> int:
    """Return how many of a slice's observations fall inside one of its attack windows."""
    return sum(1 for o in dataset.observations if dataset.is_attack(o.timestamp))


def _require_both_classes(dataset: Dataset) -> None:
    """Raise unless the slice holds at least one attack point and at least one normal point.

    Raises:
        DegenerateSplitError: Naming the slice and which class is missing.
    """
    part = dataset.name.rsplit("-", 1)[-1]
    if not dataset.observations:
        raise DegenerateSplitError(
            f"the {part} slice of {dataset.name} is empty; widen or narrow the split fractions"
        )

    attacks = _attack_points(dataset)
    if attacks == 0:
        raise DegenerateSplitError(
            f"the {part} slice of {dataset.name} contains no attack points, so it cannot "
            f"{'fit a calibrator' if part == 'calib' else 'measure whether one helped'}. "
            "This corpus's attacks do not reach this slice — narrow the split fractions until "
            "they do, or supply an explicit slice"
        )
    normal = sum(
        1
        for o in dataset.observations
        if not dataset.is_attack(o.timestamp) and not dataset.is_unscored(o.timestamp)
    )
    if normal == 0:
        raise DegenerateSplitError(
            f"the {part} slice of {dataset.name} contains no normal points — every one of its "
            f"{len(dataset.observations)} observations is inside an attack or unscored window, so "
            "there is no normal behaviour to contrast against"
        )


def _slice(
    dataset: Dataset,
    part: str,
    observations: Sequence[Observation],
    policy: CalibrationSplitPolicy,
) -> Dataset:
    """Build one slice, carrying the intervals it overlaps and recording the split in provenance."""
    return Dataset(
        name=f"{dataset.name}-{part}",
        domain=dataset.domain,
        observations=list(observations),
        attack_intervals=(
            [] if part == "train" else _intersecting(dataset.attack_intervals, observations)
        ),
        unscored_intervals=(
            [] if part == "train" else _intersecting(dataset.unscored_intervals, observations)
        ),
        source_note=(
            f"{dataset.source_note} | {part} slice of a three-way split, "
            f"train_fraction={policy.train_fraction} calib_fraction={policy.calib_fraction}"
        ),
    )


def _intersecting(
    intervals: Sequence[LabelledInterval], observations: Sequence[Observation]
) -> list[LabelledInterval]:
    """Return the labelled intervals overlapping the span ``observations`` covers."""
    if not observations:
        return []
    start: datetime = observations[0].timestamp
    end: datetime = observations[-1].timestamp
    return [interval for interval in intervals if interval.start <= end and interval.end >= start]
