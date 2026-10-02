"""Tests for the belief-update rule.

The properties matter more than any particular number here, and they are the ones the architecture
claims: confidence *evolves* as evidence accumulates, it moves in the direction the evidence
argues, it is proportional to how trustworthy 4A said that evidence was, and it never reaches
certainty. `test_confidence_is_reconstructable_from_the_evidence_lists` is Constitution §3.2 stated
as a test — if it fails, a number PHOS shows an operator cannot be explained from what PHOS stored.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from phos.ontology import (
    Domain,
    Evidence,
    EvidenceId,
    EvidenceKind,
    EvidenceRole,
    Hypothesis,
    HypothesisStatus,
)
from phos.reasoning.belief import (
    EVIDENCE_STRENGTH,
    LEAD_TIE_EPSILON,
    normalise,
    rank_hypotheses,
    reconstruct_confidence,
    tied_lead_ids,
    update_confidence,
)

T0 = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
PLC = "ent_000000000001"


def hypothesis(
    *,
    prior: float = 0.1,
    confidence: float | None = None,
    domain: Domain = Domain.ATLAS,
    supporting: Sequence[EvidenceId] = (),
    contradictory: Sequence[EvidenceId] = (),
) -> Hypothesis:
    return Hypothesis(
        label="Anomalous activity",
        template_id="test_anomalous",
        domain=domain,
        prior=prior,
        confidence=prior if confidence is None else confidence,
        status=HypothesisStatus.ACTIVE,
        supporting=list(supporting),
        contradictory=list(contradictory),
    )


def evidence(
    weight: float = 1.0,
    *,
    identifier: EvidenceId = "ev_000000000001",
    domain: Domain = Domain.ATLAS,
) -> Evidence:
    return Evidence(
        id=identifier,
        kind=EvidenceKind.DEVIATION,
        source_id="dev_000000000001",
        entity_ids=[PLC],
        timestamp=T0,
        domain=domain,
        weight=weight,
        summary="a departure from normal",
    )


def odds(probability: float) -> float:
    return probability / (1.0 - probability)


# ------------------------------------------------------------------------------------------------
# What one piece of evidence means
# ------------------------------------------------------------------------------------------------


def test_fully_trusted_supporting_evidence_multiplies_the_odds_by_the_evidence_strength() -> None:
    """This is the rule's whole content, stated as a number.

    `EVIDENCE_STRENGTH` is the log of the Bayes factor a fully-trusted (weight 1) piece of evidence
    carries. Working in odds rather than probabilities is what makes the update composable and
    bounded: the odds are multiplied, so the probability can approach 1 without ever arriving.
    """
    before = 0.2

    after = update_confidence(hypothesis(), evidence(1.0), EvidenceRole.SUPPORTING, before)

    assert math.isclose(odds(after), math.exp(EVIDENCE_STRENGTH) * odds(before))


def test_fully_trusted_contradictory_evidence_divides_the_odds_by_it() -> None:
    before = 0.2

    after = update_confidence(hypothesis(), evidence(1.0), EvidenceRole.CONTRADICTORY, before)

    assert math.isclose(odds(after), odds(before) / math.exp(EVIDENCE_STRENGTH))


def test_a_half_trusted_piece_of_evidence_moves_half_as_far_in_log_odds() -> None:
    """Proportional to the calibrated weight 4A attached, which is the point of calibrating it.

    Evidence the calibrator says is 50% likely to be a genuine departure contributes half the
    log-Bayes-factor of evidence it is certain about.
    """
    before = 0.2

    half = update_confidence(hypothesis(), evidence(0.5), EvidenceRole.SUPPORTING, before)
    full = update_confidence(hypothesis(), evidence(1.0), EvidenceRole.SUPPORTING, before)

    assert math.isclose(math.log(odds(half) / odds(before)), EVIDENCE_STRENGTH * 0.5)
    assert math.isclose(math.log(odds(full) / odds(before)), EVIDENCE_STRENGTH)


def test_worthless_evidence_moves_nothing() -> None:
    """A calibrated weight of 0 says "this is almost certainly not a real departure"."""
    before = 0.2

    assert update_confidence(hypothesis(), evidence(0.0), EvidenceRole.SUPPORTING, before) == before
    assert (
        update_confidence(hypothesis(), evidence(0.0), EvidenceRole.CONTRADICTORY, before) == before
    )


# ------------------------------------------------------------------------------------------------
# The properties the architecture claims
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("before", [0.001, 0.05, 0.2, 0.5, 0.8, 0.999])
def test_supporting_raises_and_contradictory_lowers_wherever_you_start(before: float) -> None:
    raised = update_confidence(hypothesis(), evidence(0.7), EvidenceRole.SUPPORTING, before)
    lowered = update_confidence(hypothesis(), evidence(0.7), EvidenceRole.CONTRADICTORY, before)

    assert raised > before
    assert lowered < before


def test_confidence_climbs_monotonically_as_supporting_evidence_accumulates() -> None:
    confidence = 0.1
    history = [confidence]

    for _ in range(20):
        confidence = update_confidence(
            hypothesis(), evidence(0.9), EvidenceRole.SUPPORTING, confidence
        )
        history.append(confidence)

    assert history == sorted(history)
    assert history[-1] > 0.99


def test_no_amount_of_evidence_reaches_certainty() -> None:
    """The stance, not an implementation detail: PHOS reports, it does not conclude.

    A logistic asymptotes but float64 does not — ``1 / (1 + exp(-40))`` rounds to exactly 1.0 — so
    the log-odds are bounded to keep the arithmetic honest about what the mathematics says.
    """
    climbing = 0.5
    falling = 0.5

    for _ in range(500):
        climbing = update_confidence(hypothesis(), evidence(1.0), EvidenceRole.SUPPORTING, climbing)
        falling = update_confidence(
            hypothesis(), evidence(1.0), EvidenceRole.CONTRADICTORY, falling
        )

    assert 0.0 < falling < climbing < 1.0


def test_even_a_confidence_of_zero_or_one_can_still_move() -> None:
    """A hand-built hypothesis at the bounds is treated as very-nearly-certain, not as stuck.

    A multiplicative rule on probabilities would pin 0 at 0 forever. Log-odds with bounded ends
    keeps every state reachable from every other, which is what "confidence evolves" has to mean.
    """
    assert update_confidence(hypothesis(), evidence(1.0), EvidenceRole.SUPPORTING, 0.0) > 0.0
    assert update_confidence(hypothesis(), evidence(1.0), EvidenceRole.CONTRADICTORY, 1.0) < 1.0


def test_the_update_is_deterministic() -> None:
    args = (hypothesis(), evidence(0.63), EvidenceRole.SUPPORTING, 0.317)

    assert update_confidence(*args) == update_confidence(*args)


def test_the_order_evidence_arrives_in_does_not_change_where_it_lands() -> None:
    """Why the lost interleaving between the two evidence lists costs nothing.

    `Hypothesis` records supporting and contradictory evidence in separate lists, so the order the
    two were mixed in is not stored. In log-odds each piece contributes an additive term, and
    addition commutes — so reconstruction from the two lists lands exactly where the live run did.
    """
    weights = [
        (0.9, EvidenceRole.SUPPORTING),
        (0.4, EvidenceRole.CONTRADICTORY),
        (0.7, EvidenceRole.SUPPORTING),
    ]

    forwards = 0.1
    for weight, role in weights:
        forwards = update_confidence(hypothesis(), evidence(weight), role, forwards)

    backwards = 0.1
    for weight, role in reversed(weights):
        backwards = update_confidence(hypothesis(), evidence(weight), role, backwards)

    assert math.isclose(forwards, backwards)


# ------------------------------------------------------------------------------------------------
# What the rule refuses
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("before", [-0.01, 1.01, 2.0])
def test_the_rule_refuses_a_starting_confidence_that_is_not_a_probability(before: float) -> None:
    with pytest.raises(ValueError, match="probability"):
        update_confidence(hypothesis(), evidence(0.5), EvidenceRole.SUPPORTING, before)


def test_the_rule_refuses_an_uncalibrated_evidence_weight() -> None:
    """`Evidence.weight` is merely non-negative; a confidence may only be built from a probability.

    Constitution §3.3 lives at this line. `evidence_from_deviation` already guarantees a weight in
    ``[0, 1]``, so a weight above 1 means the evidence came from somewhere that skipped the
    calibrated boundary — and weighing it would put an uncalibrated number on a user-facing path.
    """
    with pytest.raises(ValueError, match="calibrated probability"):
        update_confidence(hypothesis(), evidence(1.5), EvidenceRole.SUPPORTING, 0.2)


def test_the_rule_refuses_evidence_from_another_domain() -> None:
    """4B's narratives are single-domain; correlating Atlas with Sentiel is PART 7's job."""
    with pytest.raises(ValueError, match="domain"):
        update_confidence(
            hypothesis(domain=Domain.ATLAS),
            evidence(0.8, domain=Domain.SENTIEL),
            EvidenceRole.SUPPORTING,
            0.2,
        )


# ------------------------------------------------------------------------------------------------
# Traceability
# ------------------------------------------------------------------------------------------------


def test_confidence_is_reconstructable_from_the_evidence_lists() -> None:
    """Constitution §3.2: any number a user could see must be rebuildable from stored evidence."""
    facts = [
        evidence(0.9, identifier="ev_000000000001"),
        evidence(0.3, identifier="ev_000000000002"),
        evidence(0.6, identifier="ev_000000000003"),
    ]
    roles = [EvidenceRole.SUPPORTING, EvidenceRole.CONTRADICTORY, EvidenceRole.SUPPORTING]

    live = hypothesis()
    for fact, role in zip(facts, roles, strict=True):
        live = live.with_evidence(fact.id, role).with_confidence(
            update_confidence(live, fact, role, live.confidence)
        )

    rebuilt = reconstruct_confidence(live, {fact.id: fact for fact in facts})

    assert math.isclose(rebuilt, live.confidence)


def test_reconstruction_of_an_untouched_hypothesis_returns_its_prior() -> None:
    assert reconstruct_confidence(hypothesis(prior=0.25), {}) == 0.25


def test_reconstruction_refuses_to_guess_at_missing_evidence() -> None:
    """A hypothesis whose evidence cannot be resolved is a traceability failure, not a number."""
    orphan = hypothesis(supporting=["ev_00000000dead"])

    with pytest.raises(KeyError, match="ev_00000000dead"):
        reconstruct_confidence(orphan, {})


# ------------------------------------------------------------------------------------------------
# normalise
# ------------------------------------------------------------------------------------------------


def competing() -> list[Hypothesis]:
    return [
        hypothesis(prior=0.1, confidence=0.68),
        hypothesis(prior=0.25, confidence=0.25),
        hypothesis(prior=0.30, confidence=0.30),
    ]


def test_normalise_turns_a_competing_set_into_a_distribution() -> None:
    before = competing()

    shares = normalise(before)

    assert math.isclose(sum(h.confidence for h in shares), 1.0)
    total = sum(h.confidence for h in before)
    assert [h.confidence for h in shares] == [h.confidence / total for h in before]


def test_normalise_preserves_order_and_relative_strength() -> None:
    """A presentation transform must not reorder the explanations or change what beats what."""
    before = competing()

    after = normalise(before)

    assert [h.id for h in after] == [h.id for h in before]
    assert math.isclose(
        after[0].confidence / after[1].confidence, before[0].confidence / before[1].confidence
    )


def test_the_residual_keeps_every_explanation_below_certainty() -> None:
    """Why "insufficient evidence" is in the set rather than implied by the leftover.

    Without a residual carrying real mass, a single well-supported explanation normalises to 100%
    and the UI shows a verdict.
    """
    dominant = hypothesis(confidence=0.999999)
    residual = hypothesis(prior=0.30, confidence=0.30)

    shares = normalise([dominant, residual])

    assert shares[0].confidence < 1.0
    assert shares[1].confidence > 0.0


def test_normalise_of_nothing_is_nothing() -> None:
    assert normalise([]) == []


def test_normalise_refuses_a_set_with_no_belief_in_it() -> None:
    """Zero total is not a distribution, and silently returning zeros would look like an answer."""
    with pytest.raises(ValueError, match="no confidence to distribute"):
        normalise([hypothesis(prior=0.1, confidence=0.0), hypothesis(prior=0.1, confidence=0.0)])


def test_normalise_leaves_the_stored_confidences_alone() -> None:
    """The returned objects are for display; the hypotheses keep the posterior evidence supports."""
    before = competing()

    normalise(before)

    assert [h.confidence for h in before] == [0.68, 0.25, 0.30]


# ------------------------------------------------------------------------------------------------
# Lead ties — a reproducible set, not an alphabetical winner
# ------------------------------------------------------------------------------------------------


def _named(template_id: str, confidence: float) -> Hypothesis:
    return Hypothesis(
        label=template_id.replace("_", " "),
        template_id=template_id,
        domain=Domain.ATLAS,
        prior=0.1,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
    )


def test_two_hypotheses_at_the_ceiling_share_the_lead() -> None:
    """The D2 defect: saturated attack and maintenance are a tie, not a maintenance win."""
    tied = tied_lead_ids(
        (
            _named("unauthorised_control_activity", 1.0),
            _named("engineering_maintenance", 1.0),
            _named("process_disturbance", 0.4),
        )
    )

    assert tied == ("engineering_maintenance", "unauthorised_control_activity")


def test_a_unique_leader_is_not_a_tie() -> None:
    assert tied_lead_ids((_named("unauthorised_control_activity", 0.8), _named("other", 0.4))) == ()


def test_the_residual_is_not_a_member_of_a_contentful_tie() -> None:
    """Insufficient evidence is the refusal, not a competitor for the ceiling."""
    tied = tied_lead_ids(
        (
            _named("insufficient_evidence", 0.30),
            _named("engineering_maintenance", 1.0),
            _named("unauthorised_control_activity", 1.0),
        )
    )

    assert tied == ("engineering_maintenance", "unauthorised_control_activity")
    assert "insufficient_evidence" not in tied


def test_lead_epsilon_is_numerical_not_a_fitted_band() -> None:
    """1e-6 is a real gap. A D2-fitted 0.05 would have swallowed it; this epsilon does not."""
    assert tied_lead_ids((_named("a_first", 0.50), _named("b_second", 0.50 + 1e-6))) == ()
    assert tied_lead_ids(
        (_named("a_first", 0.50), _named("b_second", 0.50 + LEAD_TIE_EPSILON / 2))
    ) == ("a_first", "b_second")


def test_rank_hypotheses_raises_the_residual_on_a_ceiling_tie() -> None:
    """Alphabetical template_id would crown a_first; the residual must lead instead."""
    first = _named("a_first", 1.0)
    second = _named("b_second", 1.0)
    residual = _named("insufficient_evidence", 0.30)
    ranked = rank_hypotheses((second, first, residual))

    assert ranked[0].template_id == "insufficient_evidence"
    assert tied_lead_ids(ranked) == ("a_first", "b_second")
    assert [item.template_id for item in ranked[1:]] == ["a_first", "b_second"]


def test_rank_hypotheses_keeps_a_unique_leader() -> None:
    """A unique leader is not replaced by the residual just because the residual is present."""
    ranked = rank_hypotheses(
        (_named("b_second", 0.8), _named("a_first", 0.4), _named("insufficient_evidence", 0.30))
    )
    assert ranked[0].template_id == "b_second"
