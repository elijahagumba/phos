"""Pins the three Bet 001 formulas and every parameter they are allowed to use.

These cases are hand-built magnitudes. They are not CERT, and they do not name an insider.
"""

import math

import pytest

from phos.models.base import MAX_MAGNITUDE
from phos.sentiel.candidates import (
    DECLARED_CANDIDATES,
    EMIT_K,
    FormulaTerm,
    neg_log_standard_normal_survival,
    score_candidate,
)

_DECLARED_IDS = ("linear-excess", "gaussian-tail", "family-max")


def _term(feature: str, magnitude: float, *, unquantified: bool = False) -> FormulaTerm:
    return FormulaTerm(feature=feature, magnitude=magnitude, unquantified=unquantified)


def test_exactly_three_candidates_are_declared_and_lp_is_not() -> None:
    assert tuple(candidate.candidate_id for candidate in DECLARED_CANDIDATES) == _DECLARED_IDS
    assert all(candidate.log_tag == candidate.candidate_id for candidate in DECLARED_CANDIDATES)
    assert all(candidate.emit_k == EMIT_K == 1.0 for candidate in DECLARED_CANDIDATES)
    assert all(candidate.feature_weights == {} for candidate in DECLARED_CANDIDATES)
    assert all(candidate.stem_weights == {} for candidate in DECLARED_CANDIDATES)
    assert {candidate.within_family for candidate in DECLARED_CANDIDATES} == {"", "max"}
    assert {candidate.tail for candidate in DECLARED_CANDIDATES} == {"", "standard-normal-survival"}
    joined = " ".join(candidate.formula for candidate in DECLARED_CANDIDATES)
    assert "p-norm" not in joined
    assert "m_i^p" not in joined


def test_an_undeclared_formula_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown candidate"):
        score_candidate("lp-norm", (_term("logon_count", 4.0),))


def test_linear_excess_is_the_sum_of_depth_above_the_emission_bar() -> None:
    scored = score_candidate(
        "linear-excess",
        (
            _term("logon_count", 1.0),
            _term("file_access_count", 4.0),
            _term("new_counterparties", 2.5),
            _term("distinct_pcs", 0.4),
        ),
    )
    assert scored.score == pytest.approx(0.0 + 3.0 + 1.5 + 0.0)
    assert [share.contribution for share in scored.shares] == pytest.approx([0.0, 3.0, 1.5, 0.0])


def test_gaussian_tail_is_the_standard_normal_survival() -> None:
    magnitude = 1.0
    expected = -math.log(0.5 * math.erfc(magnitude / math.sqrt(2.0)))
    assert neg_log_standard_normal_survival(0.0) == pytest.approx(math.log(2.0))
    assert neg_log_standard_normal_survival(magnitude) == pytest.approx(expected)
    scored = score_candidate(
        "gaussian-tail",
        (_term("logon_count", magnitude), _term("file_access_count", 0.5)),
    )
    assert scored.score == pytest.approx(expected)
    assert neg_log_standard_normal_survival(100.0) > neg_log_standard_normal_survival(40.0)
    assert math.isfinite(neg_log_standard_normal_survival(100.0))


def test_family_max_keeps_one_voice_per_family_and_sums_them() -> None:
    scored = score_candidate(
        "family-max",
        (
            _term("logon_count", 5.0),
            _term("distinct_pcs", 2.0),
            _term("new_counterparties", 4.0),
            _term("not_a_sentiel_feature", 3.0),
        ),
    )
    assert scored.score == pytest.approx(5.0 + 4.0 + 3.0)
    by_feature = {share.feature: share.contribution for share in scored.shares}
    assert by_feature["logon_count"] == pytest.approx(5.0)
    assert by_feature["distinct_pcs"] == pytest.approx(0.0)
    assert by_feature["new_counterparties"] == pytest.approx(4.0)
    assert by_feature["not_a_sentiel_feature"] == pytest.approx(3.0)


def test_a_tied_family_maximum_goes_to_the_earlier_name() -> None:
    scored = score_candidate(
        "family-max",
        (_term("logon_count", 5.0), _term("distinct_pcs", 5.0)),
    )
    by_feature = {share.feature: share.contribution for share in scored.shares}
    assert by_feature["distinct_pcs"] == pytest.approx(5.0)
    assert by_feature["logon_count"] == pytest.approx(0.0)
    assert scored.score == pytest.approx(5.0)


def test_an_unquantified_feature_cannot_lead_on_its_own() -> None:
    alone = _term("removable_device_connects", MAX_MAGNITUDE, unquantified=True)
    quiet = score_candidate("linear-excess", (alone,))
    deep = score_candidate("linear-excess", (_term("logon_count", 4.0),))
    assert quiet.score == 0.0
    assert quiet.unquantified_count == 1
    assert quiet.score < deep.score
    for candidate_id in _DECLARED_IDS:
        without = score_candidate(candidate_id, (_term("logon_count", 4.0),))
        with_clamp = score_candidate(
            candidate_id,
            (_term("logon_count", 4.0), alone),
        )
        assert with_clamp.score == pytest.approx(without.score)
        assert with_clamp.unquantified_count == 1


def test_order_does_not_change_the_score_and_more_depth_does_not_lower_it() -> None:
    left = (
        _term("logon_count", 2.0),
        _term("file_access_count", 6.0),
        _term("new_counterparties", 3.0),
    )
    right = (left[2], left[0], left[1])
    deeper = (
        _term("logon_count", 2.0),
        _term("file_access_count", 7.0),
        _term("new_counterparties", 3.0),
    )
    for candidate_id in _DECLARED_IDS:
        assert score_candidate(candidate_id, left).score == pytest.approx(
            score_candidate(candidate_id, right).score
        )
        deeper_score = score_candidate(candidate_id, deeper).score
        assert deeper_score >= score_candidate(candidate_id, left).score
