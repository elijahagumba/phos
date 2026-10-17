"""Pins the held-out liar seeds and the pass share. It does not run a liar attack."""

from fractions import Fraction

import pytest

from phos.eval.liar_declaration import (
    CITATION_FACETS,
    DEVELOPMENT_SEEDS,
    LEADING_TEMPLATE_ID,
    LIAR_HELD_OUT_SEEDS,
    LIAR_PLANTS,
    PASS_SHARE_LOWER_BOUND,
    liar_run_count,
    liar_run_passes,
    plants_that_already_have_liar,
    share_passes,
)
from phos.library.ot import SEEDS, SUBTLETIES
from phos.ontology.enums import Domain, HypothesisStatus
from phos.ontology.hypotheses import Hypothesis
from phos.synth.attacks.spec import DifficultyLevel

_RUNS = 3 * 20 * 6


def _hypothesis(
    template_id: str,
    confidence: float,
    supporting: list[str] | None = None,
) -> Hypothesis:
    return Hypothesis(
        label=template_id,
        template_id=template_id,
        domain=Domain.ATLAS,
        prior=0.1,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
        supporting=supporting or [],
    )


def test_seeds_are_twenty_and_disjoint_from_development() -> None:
    assert LIAR_HELD_OUT_SEEDS == tuple(range(94001, 94021))
    assert len(set(LIAR_HELD_OUT_SEEDS)) == 20
    assert set(LIAR_HELD_OUT_SEEDS).isdisjoint(DEVELOPMENT_SEEDS)
    assert set(LIAR_HELD_OUT_SEEDS).isdisjoint(SEEDS)
    assert {80001, 80002, 80003, 11, 71001}.issubset(DEVELOPMENT_SEEDS)


def test_plants_and_graded_magnitudes_are_the_ones_already_declared() -> None:
    assert LIAR_PLANTS == plants_that_already_have_liar()
    assert SUBTLETIES == (0.0, 0.2, 0.4, 0.6, 0.8, 0.9)
    assert DifficultyLevel.for_subtlety(0.6) is DifficultyLevel.SUBTLE
    assert DifficultyLevel.for_subtlety(0.8) is DifficultyLevel.SUBTLE
    assert DifficultyLevel.for_subtlety(0.9) is DifficultyLevel.NEAR_INVISIBLE
    assert liar_run_count() == _RUNS


def test_pass_share_is_strictly_greater_than_one_half() -> None:
    assert PASS_SHARE_LOWER_BOUND == Fraction(1, 2)
    half = _RUNS // 2
    assert share_passes(half + 1, _RUNS) is True
    assert share_passes(half, _RUNS) is False
    assert share_passes(0, _RUNS) is False
    with pytest.raises(ValueError, match="declaration"):
        share_passes(half + 1, _RUNS - 1)


def test_a_pass_needs_a_unique_instrument_lead_and_a_declared_citation() -> None:
    cited = _hypothesis(LEADING_TEMPLATE_ID, 0.6, ["ev_reading"])
    upset = _hypothesis("process_disturbance", 0.2, ["ev_other"])
    facets = {"ev_reading": CITATION_FACETS[0]}
    assert liar_run_passes((cited, upset), facets) is True
    assert liar_run_passes((cited, upset), {"ev_reading": "a plain deviation"}) is False
    assert liar_run_passes((upset, cited), {}) is False
    tied = (
        _hypothesis(LEADING_TEMPLATE_ID, 0.5, ["ev_reading"]),
        _hypothesis("process_disturbance", 0.5, ["ev_other"]),
    )
    assert liar_run_passes(tied, facets) is False
    silent = _hypothesis("insufficient_evidence", 0.4)
    assert liar_run_passes((silent,), facets) is False
