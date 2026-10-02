"""How a hypothesis's confidence changes when a piece of evidence arrives.

The rule is Bayesian and lives in **log-odds**. A hypothesis's current confidence is converted to
log-odds, each piece of evidence adds a term — positive when it supports, negative when it
contradicts — and a logistic converts back. Three things follow from that choice, and all three are
requirements rather than conveniences:

- **It stays in ``[0, 1]`` by construction.** No clamping of a score that wandered out of range, no
  invented squashing function on top of numbers that were already probabilities.
- **It never reaches certainty.** Multiplying odds can approach infinity but never arrive, so
  confidence approaches 1 and never arrives either. No finite pile of observations makes PHOS
  certain; that is the system's stance, not a numerical accident. (Float64 would round to exactly
  1.0 around 40 log-odds, so the log-odds themselves are bounded to keep the arithmetic saying what
  the mathematics says.)
- **It is order-independent.** Addition commutes, so the same evidence in any order lands in the
  same place. `Hypothesis` stores supporting and contradictory evidence in two separate lists, and
  therefore does not record how the two were interleaved — order-independence is what makes that
  loss free, and what makes `reconstruct_confidence` exact.

The size of each term is ``EVIDENCE_STRENGTH * weight``, where the weight is the calibrated
probability 4A attached to the evidence. Read it as: a fully-trusted piece of evidence carries a
Bayes factor of `EVIDENCE_STRENGTH` nats, and evidence the calibrator only half-believes carries
half of it. That is the whole reason 4A insisted on calibrating the weight first.

**What this does not claim.** The evidence weights are calibrated; the *hypothesis* confidence
built from them is not, and must not be surfaced as a calibrated confidence under Constitution §3.3
until it is. Two inputs are unmeasured: each template's prior, and `EVIDENCE_STRENGTH` — the
discriminating power of one piece of evidence for one explanation. Both are placeholders chosen for
sane behaviour, and measuring them needs labelled data about *explanations*, which the corpora PHOS
uses do not carry (they label attack and normal, not "unauthorised control" versus "maintenance").
PARTs 5 and 6 own that measurement for their domains. Until then these numbers order competing
explanations honestly and are not probabilities of anything.
"""

import logging
import math
from collections.abc import Mapping, Sequence

from phos.ontology import Evidence, EvidenceId, EvidenceRole, Hypothesis
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID

__all__ = [
    "CONFIDENCE_CEILING",
    "EVIDENCE_STRENGTH",
    "LEAD_TIE_EPSILON",
    "evidence_fingerprint",
    "normalise",
    "prior_only_rivals",
    "rank_hypotheses",
    "reconstruct_confidence",
    "tied_lead_ids",
    "update_confidence",
]

logger = logging.getLogger(__name__)

EVIDENCE_STRENGTH = math.log(3.0)
"""Log-Bayes-factor of one fully-trusted piece of evidence, in nats.

``log(3)``: a piece of evidence the calibrator is certain about makes its hypothesis three times
more likely relative to the alternatives. Deliberately modest — it takes several independent
observations to move an explanation from unlikely to probable, which is the behaviour an analyst
should expect from a system that reasons rather than alerts. It is a **placeholder, not a measured
discriminating power**; see this module's docstring.
"""

_EPSILON = 1e-12
"""How close to 0 or 1 a confidence is allowed to get. Bounds the log-odds at ±27.6."""

_MAX_LOG_ODDS = math.log((1.0 - _EPSILON) / _EPSILON)

CONFIDENCE_CEILING = 1.0
"""The upper bound of the confidence interval. Saturated log-odds sit just below this."""

LEAD_TIE_EPSILON = 1e-9
"""How close two confidences must be to share the lead, and how close to `CONFIDENCE_CEILING`
a confidence must be to count as saturated.

Declared, not fitted. Constitution §3.7 requires a reproducible order of a tied set. It does not
license picking a unique winner by `template_id` alphabet when the numbers cannot separate them.
Do not widen this on a battery to manufacture leads or blanket refusal.
"""


def _to_log_odds(probability: float) -> float:
    """Convert a probability to log-odds, treating the bounds as very-nearly-certain.

    A confidence of exactly 0 or 1 has infinite log-odds, and adding a finite amount to infinity
    leaves it there — a hypothesis that could never change its mind. Nudging the bounds inward keeps
    every state reachable from every other.
    """
    bounded = min(max(probability, _EPSILON), 1.0 - _EPSILON)
    return math.log(bounded / (1.0 - bounded))


def _from_log_odds(log_odds: float) -> float:
    """Convert log-odds back to a probability strictly inside ``(0, 1)``."""
    bounded = min(max(log_odds, -_MAX_LOG_ODDS), _MAX_LOG_ODDS)
    return 1.0 / (1.0 + math.exp(-bounded))


def update_confidence(
    hypothesis: Hypothesis,
    evidence: Evidence,
    role: EvidenceRole,
    prior_confidence: float,
) -> float:
    """Return the confidence in ``hypothesis`` after weighing one piece of ``evidence``.

    Pure and deterministic: the same four arguments always give the same float, and the result
    depends on nothing the caller cannot see.

    Args:
        hypothesis: The explanation being weighed. Supplies the domain the evidence must belong to,
            and identifies the hypothesis in the debug log; the running confidence comes from
            ``prior_confidence`` rather than from ``hypothesis.confidence`` so that a caller can
            replay a sequence of updates without rebuilding the object each time.
        evidence: The fact to weigh. Its ``weight`` must be the calibrated probability 4A attached.
        role: Whether this evidence supports or contradicts the hypothesis. The role belongs to the
            link, so the same evidence can raise one explanation while lowering another.
        prior_confidence: The confidence to update, in ``[0, 1]``.

    Returns:
        The updated confidence, strictly inside ``(0, 1)``. Never lower than ``prior_confidence``
        for supporting evidence, never higher for contradictory evidence, and unchanged for
        evidence of weight 0 — which is what a calibrated weight of 0 should mean.

    Raises:
        ValueError: If ``prior_confidence`` is not a probability; if the evidence's weight is above
            1, which means it did not come through `evidence_from_deviation` and is therefore not
            calibrated (Constitution §3.3); or if the evidence belongs to a different domain from
            the hypothesis, which is PART 7's business and not something to do silently.
    """
    if not 0.0 <= prior_confidence <= 1.0:
        raise ValueError(
            f"prior_confidence must be a probability in [0, 1], got {prior_confidence}"
        )
    if evidence.weight > 1.0:
        raise ValueError(
            f"evidence {evidence.id!r} has weight {evidence.weight}, which is not a calibrated "
            "probability in [0, 1]. A hypothesis confidence may only be built from calibrated "
            "weights — see phos.reasoning.boundary.evidence_from_deviation"
        )
    if evidence.domain is not hypothesis.domain:
        raise ValueError(
            f"evidence {evidence.id!r} is {evidence.domain.value} but hypothesis "
            f"{hypothesis.id!r} is {hypothesis.domain.value}: a 4B narrative is single-domain, and "
            "correlating evidence across engines is PART 7's job"
        )

    strength = EVIDENCE_STRENGTH * evidence.weight
    contribution = strength if role is EvidenceRole.SUPPORTING else -strength
    updated = _from_log_odds(_to_log_odds(prior_confidence) + contribution)

    logger.debug(
        "hypothesis %s (%s): %s evidence %s of weight %.4f moves confidence %.4f -> %.4f",
        hypothesis.id,
        hypothesis.template_id,
        role.value.lower(),
        evidence.id,
        evidence.weight,
        prior_confidence,
        updated,
    )
    return updated


def reconstruct_confidence(
    hypothesis: Hypothesis, evidence: Mapping[EvidenceId, Evidence]
) -> float:
    """Rebuild a hypothesis's confidence by replaying its evidence through `update_confidence`.

    This is Constitution §3.2 made executable: a confidence an operator sees must be reconstructable
    from stored evidence, and this is the function that reconstructs it. Because the update is
    order-independent, replaying the two stored lists one after the other lands exactly where the
    live run did, even though the order they were interleaved in was never recorded.

    Args:
        hypothesis: The explanation to rebuild, carrying its prior and its evidence lists.
        evidence: Lookup for every evidence id the hypothesis cites, normally built from an
            `EvidenceStore`.

    Returns:
        The confidence the hypothesis's evidence supports, starting from its prior.

    Raises:
        KeyError: If the hypothesis cites evidence the mapping does not hold. A hypothesis whose
            evidence cannot be resolved is a traceability failure, not a number to guess at.
        ValueError: Propagated from `update_confidence` for evidence that should never have been
            attached — an uncalibrated weight, or another domain's evidence.

    Note:
        Reconstruction is exact unless the confidence saturated during the live run. Saturation
        needs roughly twenty-five fully-trusted pieces of evidence pulling one way, and past it the
        log-odds are no longer recoverable from the stored probability.
    """
    confidence = hypothesis.prior
    for evidence_id in hypothesis.supporting:
        confidence = update_confidence(
            hypothesis, evidence[evidence_id], EvidenceRole.SUPPORTING, confidence
        )
    for evidence_id in hypothesis.contradictory:
        confidence = update_confidence(
            hypothesis, evidence[evidence_id], EvidenceRole.CONTRADICTORY, confidence
        )
    return confidence


def normalise(hypotheses: Sequence[Hypothesis]) -> list[Hypothesis]:
    """Rescale a competing set's confidences into a distribution that sums to 1.

    This is how a competing set becomes the percentages a UI lists beside each other. Each
    hypothesis's confidence answers "how well does the evidence support this?" independently of the
    others; normalising answers the different question "of the explanations on the table, how does
    belief divide between them?".

    The always-present "insufficient evidence" hypothesis is what keeps the second question honest.
    It holds real mass and accumulates no evidence, so it shrinks as the explanations earn support
    and dominates when none of them do — and because it is in the set, no explanation can normalise
    to 100%.

    Args:
        hypotheses: The competing set, in the order it should be presented. Not reordered.

    Returns:
        New `Hypothesis` objects in the same order, whose confidences sum to 1.

    Raises:
        ValueError: If the set holds no confidence at all, which is not a distribution.

    Warning:
        The returned objects are **for presentation only**. Their confidence is a share of a set,
        not the posterior its evidence supports, so it will not survive `reconstruct_confidence`.
        Never store them back as a hypothesis's state or feed them into `update_confidence`.
    """
    if not hypotheses:
        return []

    total = sum(hypothesis.confidence for hypothesis in hypotheses)
    if total <= 0.0:
        raise ValueError(
            f"cannot normalise {len(hypotheses)} hypotheses with no confidence to distribute "
            "between them"
        )
    return [hypothesis.with_confidence(hypothesis.confidence / total) for hypothesis in hypotheses]


def tied_lead_ids(hypotheses: Sequence[Hypothesis]) -> tuple[str, ...]:
    """Return the template ids that share the lead, in deterministic `template_id` order.

    A unique leader returns an empty tuple. So does an empty or single-explanation set. The
    always-present "insufficient evidence" residual is excluded: it is the refusal raised when
    this function is non-empty, not a competitor for the ceiling.

    Two or more contentful hypotheses share the lead when they sit within `LEAD_TIE_EPSILON` of
    `CONFIDENCE_CEILING`, or — away from the ceiling — within `LEAD_TIE_EPSILON` of the current
    top confidence. The sort `(-confidence, template_id)` remains the reproducible listing of
    the set; it is not a unique winner.

    Args:
        hypotheses: The competing set, in any order.

    Returns:
        Sorted template ids sharing the lead, or ``()`` when the lead is unique.
    """
    contentful = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    ]
    if len(contentful) < 2:
        return ()

    top = max(hypothesis.confidence for hypothesis in contentful)
    if top >= CONFIDENCE_CEILING - LEAD_TIE_EPSILON:
        cluster = [
            hypothesis
            for hypothesis in contentful
            if hypothesis.confidence >= CONFIDENCE_CEILING - LEAD_TIE_EPSILON
        ]
    else:
        cluster = [
            hypothesis
            for hypothesis in contentful
            if abs(hypothesis.confidence - top) <= LEAD_TIE_EPSILON
        ]
    if len(cluster) < 2:
        return ()
    return tuple(sorted({hypothesis.template_id for hypothesis in cluster}))


def evidence_fingerprint(
    hypothesis: Hypothesis,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the supporting and contradictory evidence ids, order-insensitive."""
    return (frozenset(hypothesis.supporting), frozenset(hypothesis.contradictory))


def prior_only_rivals(hypotheses: Sequence[Hypothesis]) -> bool:
    """Return whether the contentful leader is separated from a rival only by prior.

    Session E2: if two operational hypotheses carry the same evidence lists, the
    narrative must not present a prior winner as knowledge (ADR 0036 already
    refuses a ceiling tie; this catches the non-saturated case).
    """
    contentful = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    ]
    if len(contentful) < 2:
        return False
    ordered = sorted(contentful, key=lambda item: (-item.confidence, item.template_id))
    leader = ordered[0]
    fingerprint = evidence_fingerprint(leader)
    if not fingerprint[0] and not fingerprint[1]:
        return False
    return any(
        item.id != leader.id and evidence_fingerprint(item) == fingerprint for item in ordered
    )


def rank_hypotheses(
    hypotheses: Sequence[Hypothesis],
    *,
    insertion_order: Mapping[str, int] | None = None,
) -> list[Hypothesis]:
    """Order competing explanations without treating a tie as a unique winner.

    The listing is ``(-confidence, template_id, insertion)`` so two runs agree
    (Constitution §3.7). When two or more contentful explanations share the lead,
    or when they are separated only by prior (identical evidence lists, Session E2),
    ``insufficient_evidence`` is raised to the front if it is in the set: silence,
    not an alphabetical favourite (ADR 0036). The tied rivals stay listed underneath
    in that same deterministic order.

    The breaking harness does **not** insert the residual into its ``templates``
    tuple — it records ``tied_leaders`` and keeps ``leads`` false so ordinals stay
    comparable. This function is the reasoning/narrative path used by
    `ReasoningEngine` and `SentielEngine`.

    Args:
        hypotheses: The competing set, in any order.
        insertion_order: Optional map from hypothesis id to insertion index. When
            omitted, the sequence order of ``hypotheses`` is the insertion order.

    Returns:
        The competing set, strongest first, with the residual leading when the
        contentful lead is tied or prior-only.
    """
    if insertion_order is None:
        position = {hypothesis.id: index for index, hypothesis in enumerate(hypotheses)}
    else:
        position = dict(insertion_order)
        for index, hypothesis in enumerate(hypotheses):
            position.setdefault(hypothesis.id, index)

    ordered = sorted(
        hypotheses,
        key=lambda item: (-item.confidence, item.template_id, position[item.id]),
    )
    tied = tied_lead_ids(ordered)
    prior_only = prior_only_rivals(ordered)
    if not tied and not prior_only:
        return ordered
    residual = next(
        (item for item in ordered if item.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID),
        None,
    )
    if residual is None:
        return ordered
    rest = [item for item in ordered if item.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID]
    logger.debug(
        "lead tied among %s (prior_only=%s); raising %s rather than a unique leader",
        ",".join(tied) if tied else "prior-only rivals",
        prior_only,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    )
    return [residual, *rest]
