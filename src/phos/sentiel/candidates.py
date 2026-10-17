"""The three Bet 001 aggregations, declared before any labelled CERT score.

ADR 0084 allows at most three candidates and requires every parameter to be pinned
by a test before a labelled measurement. This module is that declaration. It does
not read CERT, does not rank an insider, and does not write ``eval_runs/log.jsonl``.

The fourth family in that ADR, an L*p* norm, is not declared. Any ``p`` would be a
knob with no value already in the scorer. The three below use inherited numbers:
the emission bar, the standard normal a z-score already is, and the existing
behaviour families.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from phos.models.base import MAX_MAGNITUDE
from phos.sentiel.templates import family_of

__all__ = [
    "DECLARED_CANDIDATES",
    "EMIT_K",
    "FormulaScore",
    "FormulaTerm",
    "TermShare",
    "neg_log_standard_normal_survival",
    "score_candidate",
]

#: The existing emission bar (`FittedModel.emit_k`). Inherited, not searched.
EMIT_K: float = 1.0

_FROZEN_DETECTOR_NAME = "aggregate:gaussian:peer set (34 features)"


class FormulaTerm(BaseModel):
    """One feature's magnitude, as the frozen scorer would hand it to an aggregation.

    Attributes:
        feature: Feature name. Family-max looks this up in the existing partition.
        magnitude: Non-negative anomaly magnitude. A z-score for a quantified feature.
        unquantified: True when neither the entity nor the population had a spread, so
            the magnitude is the clamp rather than a measurement.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    magnitude: float = Field(ge=0.0)
    unquantified: bool = False


class TermShare(BaseModel):
    """One feature's piece of a candidate score.

    Attributes:
        feature: The feature.
        contribution: What that feature added. Summing these returns the score.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    contribution: float = Field(ge=0.0)


class FormulaScore(BaseModel):
    """A candidate's score and the parts that add up to it.

    Attributes:
        candidate_id: Which declared formula produced this.
        score: Sum of `shares`. Zero when nothing quantified spoke.
        shares: One entry per input term, in input order.
        unquantified_count: How many terms were excluded as unmeasured.
    """

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    score: float = Field(ge=0.0)
    shares: tuple[TermShare, ...]
    unquantified_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _shares_reconstruct_the_score(self) -> FormulaScore:
        """Refuse a score that is not the sum of its shares."""
        total = math.fsum(share.contribution for share in self.shares)
        if not math.isclose(total, self.score, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"{self.candidate_id} score {self.score} is not the sum of its shares ({total})"
            )
        return self


class DeclaredCandidate(BaseModel):
    """One pre-registered formula and the parameters it is allowed to use.

    Attributes:
        candidate_id: Stable name. Also the `log_tag`, so a later detector name cannot
            be the frozen 6B row.
        log_tag: Suffix a later log row must carry. Empty is refused.
        formula: The expression, in the form ADR 0084 named.
        emit_k: A feature speaks only at or above this magnitude.
        within_family: ``max`` for the family candidate; empty for the others.
        tail: ``standard-normal-survival`` for the tail candidate; empty otherwise.
        feature_weights: Must stay empty. A weight would be the answer key.
        stem_weights: Must stay empty, for the same reason.
    """

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    log_tag: str
    formula: str
    emit_k: float = Field(gt=0.0)
    within_family: str = ""
    tail: str = ""
    feature_weights: dict[str, float] = Field(default_factory=dict)
    stem_weights: dict[str, float] = Field(default_factory=dict)

    @field_validator("log_tag")
    @classmethod
    def _tag_cannot_be_the_frozen_row(cls, value: str) -> str:
        """Refuse an empty tag or the frozen detector's own name."""
        if not value.strip():
            raise ValueError("a Bet 001 candidate needs a log_tag, or it could overwrite 6B")
        if value == _FROZEN_DETECTOR_NAME:
            raise ValueError("a Bet 001 log_tag cannot be the frozen 6B detector name")
        return value

    @field_validator("feature_weights", "stem_weights")
    @classmethod
    def _weights_stay_empty(cls, value: dict[str, float]) -> dict[str, float]:
        """Refuse a weight. ADR 0084 forbids fitting one to the two insiders."""
        if value:
            raise ValueError("Bet 001 candidates are unweighted; a weight is the answer key")
        return value


def neg_log_standard_normal_survival(magnitude: float) -> float:
    """Return ``-log(1 - Φ(magnitude))`` for a standard normal.

    ``magnitude`` is already a z-score, so the tail is one-sided. Where ``math.erfc``
    still returns a positive value this is that value's log, negated. Where float64
    underflows, the mills-ratio asymptotic is used so a large finite magnitude stays
    finite. The switch is the underflow, not a detection threshold.

    Args:
        magnitude: A non-negative z-score.

    Returns:
        The negative log survival. ``log(2)`` at zero.

    Raises:
        ValueError: If ``magnitude`` is negative. A z-score magnitude is not signed.
    """
    if magnitude < 0.0:
        raise ValueError(f"a magnitude is non-negative, got {magnitude}")
    if magnitude == 0.0:
        return math.log(2.0)
    tail = 0.5 * math.erfc(magnitude / math.sqrt(2.0))
    if tail > 0.0:
        return -math.log(tail)
    return _asymptotic_neg_log_survival(magnitude)


def _asymptotic_neg_log_survival(magnitude: float) -> float:
    """Return the mills-ratio approximation of ``-log`` survival for a huge z-score.

    ``1 - Φ(m) ~ φ(m) / m``. The first correction ``1 - 1/m²`` is included. This is
    the same function as the erfc form, evaluated where that form is zero in float64.
    """
    log_density = 0.5 * magnitude * magnitude + 0.5 * math.log(2.0 * math.pi)
    mills = math.log(magnitude) - math.log1p(-1.0 / (magnitude * magnitude))
    return log_density + mills


def _excluded(term: FormulaTerm) -> bool:
    """Return whether ``term`` is unmeasured and must not enter the sum."""
    return term.unquantified or term.magnitude >= MAX_MAGNITUDE


def _speaks(term: FormulaTerm) -> bool:
    """Return whether a quantified term cleared the inherited emission bar."""
    return not _excluded(term) and term.magnitude >= EMIT_K


def _score_linear_excess(terms: Sequence[FormulaTerm]) -> FormulaScore:
    """Sum ``max(0, m - emit_k)`` over quantified features that spoke."""
    shares: list[TermShare] = []
    unquantified = 0
    for term in terms:
        if _excluded(term):
            unquantified += 1
            shares.append(TermShare(feature=term.feature, contribution=0.0))
            continue
        excess = max(0.0, term.magnitude - EMIT_K)
        shares.append(TermShare(feature=term.feature, contribution=excess))
    return FormulaScore(
        candidate_id="linear-excess",
        score=math.fsum(share.contribution for share in shares),
        shares=tuple(shares),
        unquantified_count=unquantified,
    )


def _score_gaussian_tail(terms: Sequence[FormulaTerm]) -> FormulaScore:
    """Sum ``-log`` standard-normal survival over quantified features that spoke."""
    shares: list[TermShare] = []
    unquantified = 0
    for term in terms:
        if _excluded(term):
            unquantified += 1
            shares.append(TermShare(feature=term.feature, contribution=0.0))
            continue
        contribution = neg_log_standard_normal_survival(term.magnitude) if _speaks(term) else 0.0
        shares.append(TermShare(feature=term.feature, contribution=contribution))
    return FormulaScore(
        candidate_id="gaussian-tail",
        score=math.fsum(share.contribution for share in shares),
        shares=tuple(shares),
        unquantified_count=unquantified,
    )


def _score_family_max(terms: Sequence[FormulaTerm]) -> FormulaScore:
    """Take the max quantified magnitude in each family, then sum those maxima.

    A feature the existing partition does not name is its own family, keyed by its
    own name, so it is not dropped and not merged into a family nobody declared.
    Ties inside a family go to the lexicographically first feature name.
    """
    best: dict[str, tuple[str, float]] = {}
    unquantified = 0
    for term in terms:
        if _excluded(term):
            unquantified += 1
            continue
        if not _speaks(term):
            continue
        family = family_of(term.feature)
        key = family.value if family is not None else term.feature
        current = best.get(key)
        if (
            current is None
            or term.magnitude > current[1]
            or (term.magnitude == current[1] and term.feature < current[0])
        ):
            best[key] = (term.feature, term.magnitude)
    winners = dict(best.values())
    awarded: set[str] = set()
    shares_list: list[TermShare] = []
    for term in terms:
        contribution = 0.0
        if term.feature in winners and term.feature not in awarded and not _excluded(term):
            contribution = winners[term.feature]
            awarded.add(term.feature)
        shares_list.append(TermShare(feature=term.feature, contribution=contribution))
    shares = tuple(shares_list)
    return FormulaScore(
        candidate_id="family-max",
        score=math.fsum(share.contribution for share in shares),
        shares=shares,
        unquantified_count=unquantified,
    )


_SCORERS: Mapping[str, Callable[[Sequence[FormulaTerm]], FormulaScore]] = {
    "linear-excess": _score_linear_excess,
    "gaussian-tail": _score_gaussian_tail,
    "family-max": _score_family_max,
}

DECLARED_CANDIDATES: tuple[DeclaredCandidate, ...] = (
    DeclaredCandidate(
        candidate_id="linear-excess",
        log_tag="linear-excess",
        formula="sum over quantified speaking features of max(0, m_i - emit_k)",
        emit_k=EMIT_K,
    ),
    DeclaredCandidate(
        candidate_id="gaussian-tail",
        log_tag="gaussian-tail",
        formula="sum over quantified speaking features of -log(1 - Φ(m_i))",
        emit_k=EMIT_K,
        tail="standard-normal-survival",
    ),
    DeclaredCandidate(
        candidate_id="family-max",
        log_tag="family-max",
        formula="sum across behaviour families of the max quantified speaking magnitude",
        emit_k=EMIT_K,
        within_family="max",
    ),
)


def score_candidate(candidate_id: str, terms: Sequence[FormulaTerm]) -> FormulaScore:
    """Score ``terms`` with one declared candidate.

    Args:
        candidate_id: One of `DECLARED_CANDIDATES`.
        terms: Feature magnitudes. Order does not change the score.

    Returns:
        The score and one share per input term.

    Raises:
        ValueError: If ``candidate_id`` was not declared. A fourth formula is a new
            session, not a quiet addition.
    """
    scorer = _SCORERS.get(candidate_id)
    if scorer is None:
        known = ", ".join(candidate.candidate_id for candidate in DECLARED_CANDIDATES)
        raise ValueError(f"unknown candidate {candidate_id!r}; declared: {known}")
    return scorer(terms)
