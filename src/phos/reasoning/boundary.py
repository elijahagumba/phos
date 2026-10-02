"""Where a measurement stops being a score and becomes something reasoning may weigh.

PART 3 left one word doing two jobs. A `Deviation` is emitted whenever an observation's magnitude
reaches the model's ``emit_k``, and the default ``emit_k`` (1.0) sits *below* the default
``band_k`` (3.0) that shapes the reported `ExpectedRange`. That is deliberate and useful — a dense
candidate set is what makes the harness's threshold sweep meaningful — but it means a `Deviation`
is not necessarily a departure from normal at all. Roughly a third of the candidates a Gaussian
baseline emits lie comfortably inside their own expected range.

This module fixes the vocabulary permanently, in three terms the rest of PHOS is expected to use:

- **Scored candidate** — any `Deviation` a model emits. It exists to give the harness a dense
  threshold sweep, and it *never* becomes `Evidence`.
- **Out-of-band deviation** — a scored candidate whose observation value falls outside its
  `ExpectedRange` ``[low, high]``. This is a genuine departure from learned normal.
- **Evidence** — constructed *only* from an out-of-band deviation, by
  :func:`evidence_from_deviation`, which refuses anything else.

That refusal is the whole point of the module. PART 4B builds competing hypotheses out of
`Evidence`; if an in-band candidate could reach it, every hypothesis downstream would rest on a
non-event while looking perfectly well-supported.

**The test is the value against the range, never the magnitude.** The three baselines do not agree
on what a magnitude means — an IQR magnitude is an overshoot beyond a fence, a Gaussian magnitude
is a z-score, an EWMA magnitude is a z-score against a moving level — so any single magnitude
threshold would draw the line in a different place for each of them. The bounds are the one thing
every model states in the same units: those of the measurement itself.

**PART P3 adds a second door, for the one kind of fact a `Deviation` cannot carry.** A structural
change — a command relationship that has never been seen, one that has gone silent, a function code
never used on a link — is not a numeric departure from a learned band, and there is no
`ExpectedRange` for "this link has never existed". Routing one through `evidence_from_deviation`
would mean inventing a range nobody learned, which is exactly the fabrication the first door exists
to prevent. `evidence_from_relationship_change` is therefore its sibling rather than its bypass: the
same module, the same two refusals — a non-event may not become evidence, and a weight that is not a
probability may not either — producing `EvidenceKind.RELATIONSHIP_CHANGE` instead of
`EvidenceKind.DEVIATION`. What stands in for "in-band" is a **zero-or-negative measured change**,
because a finding quantifies how much the structure differs and a difference of nothing is a
non-event by the same argument.
"""

import logging
from typing import Final

from phos.ontology import Deviation, Evidence, EvidenceKind, FacetKind, Observation

__all__ = ["evidence_from_deviation", "evidence_from_relationship_change", "is_out_of_band"]

logger = logging.getLogger(__name__)

_RELATIONSHIP_ENDS: Final = 2
"""Fewest entities a relationship change names. A structure holds between things, not within one."""


def _require_pairing(deviation: Deviation, observation: Observation) -> None:
    """Raise unless ``deviation`` is the one that judged ``observation``.

    A deviation names the observation it came from, and every question in this module is really a
    question about that pair. Answering about a mismatched pair would produce `Evidence` whose
    stored ``source_id`` leads back to a measurement other than the one it describes — a
    traceability hole (Constitution §3.2), and a silent one.

    Raises:
        ValueError: If the deviation's ``observation_id`` is not the observation's id.
    """
    if deviation.observation_id != observation.id:
        raise ValueError(
            f"deviation {deviation.id!r} does not describe observation {observation.id!r} "
            f"(it describes {deviation.observation_id!r})"
        )


def is_out_of_band(deviation: Deviation, observation: Observation) -> bool:
    """Return whether the observation fell outside the range that judged it.

    This is the exact, model-agnostic definition of "a real departure from normal". It reduces to
    ``not deviation.expected.contains(observation.value)``, and the bounds are inclusive, so a
    value sitting exactly on ``low`` or ``high`` is still normal.

    Args:
        deviation: The scored candidate. Carries the `ExpectedRange` it was judged against.
        observation: The measurement the deviation came from, paired by ``observation_id``.

    Returns:
        ``True`` for an out-of-band deviation; ``False`` for a candidate that never left its
        expected range.

    Raises:
        ValueError: If the deviation does not describe this observation.
    """
    _require_pairing(deviation, observation)
    return not deviation.expected.contains(observation.value)


def _facet_fields(facet: tuple[FacetKind, str] | None) -> tuple[FacetKind | None, str | None]:
    """Split an optional facet into the pair `Evidence` stores.

    An **empty feature declares nothing**, and is normalised to no facet at all rather than
    refused. `Observation.feature` carries no length constraint, so an unnamed feature was always
    constructible; before the facet existed it produced a marker like ``"work-order::"`` that
    `work_order_feature_of` read back as ``None``. Normalising here reproduces that exactly, so
    adding the field introduces no new failure on an input that previously promoted (ADR 0070).
    """
    if facet is None:
        return None, None
    facet_kind, feature = facet
    if not feature:
        return None, None
    return facet_kind, feature


def evidence_from_deviation(
    deviation: Deviation,
    observation: Observation,
    calibrated_confidence: float,
    *,
    summary: str,
    facet: tuple[FacetKind, str] | None = None,
) -> Evidence:
    """Promote an out-of-band deviation into `Evidence`, or refuse.

    This is the only sanctioned route from a model's output into reasoning, and it is a narrow one
    on purpose. Both refusals below are constitutional rather than defensive.

    Args:
        deviation: The out-of-band deviation to promote. Becomes the evidence's ``source_id``.
        observation: The measurement it came from. Supplies the entities, timestamp and domain, so
            the evidence describes the world rather than the model's bookkeeping.
        calibrated_confidence: The evidence's ``weight``, and the reason this argument is not
            optional. It must be a *calibrated* probability — see `phos.reasoning.calibration` —
            because `Evidence.weight` is the number a hypothesis's confidence is later built from,
            and Constitution §3.3 forbids an uncalibrated one reaching a user.
        summary: Short human-readable description, e.g. ``"Unexpected Modbus write to PLC-4"``.
        facet: Optional ``(kind, feature)`` naming which sub-kind of fact this is, for a matcher
            that needs to tell one from another within `EvidenceKind.DEVIATION` (ADR 0070).
            Omitted, the evidence declares no facet — which is what most deviations are.

    Returns:
        `Evidence` of kind `EvidenceKind.DEVIATION`.

    Raises:
        ValueError: If the deviation does not describe this observation; if the deviation is
            in-band, because evidence may never rest on a non-event; or if the confidence is not in
            ``[0, 1]``, because such a number is not a probability.
    """
    _require_pairing(deviation, observation)

    if not is_out_of_band(deviation, observation):
        raise ValueError(
            f"refusing to build evidence from in-band deviation {deviation.id!r}: "
            f"value {observation.value} lies inside its expected range "
            f"[{deviation.expected.low}, {deviation.expected.high}], so it is a scored candidate, "
            "not a departure from normal"
        )

    if not 0.0 <= calibrated_confidence <= 1.0:
        raise ValueError(
            f"calibrated_confidence must be a calibrated probability in [0, 1], got "
            f"{calibrated_confidence}"
        )

    logger.debug(
        "evidence from deviation %s (value %s outside [%s, %s]), weight %s",
        deviation.id,
        observation.value,
        deviation.expected.low,
        deviation.expected.high,
        calibrated_confidence,
    )
    facet_kind, facet_feature = _facet_fields(facet)
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=deviation.id,
        entity_ids=list(observation.entity_ids),
        timestamp=observation.timestamp,
        domain=observation.domain,
        weight=calibrated_confidence,
        summary=summary,
        facet_kind=facet_kind,
        facet=facet_feature,
    )


def evidence_from_relationship_change(
    finding: Observation,
    calibrated_confidence: float,
    *,
    summary: str,
    facet: tuple[FacetKind, str] | None = None,
) -> Evidence:
    """Promote a measured structural change into `Evidence`, or refuse.

    The sibling of `evidence_from_deviation`, for facts about the *structure between* entities
    rather than about one entity's readings. It exists because such a fact has no `ExpectedRange`
    behind it — see this module's docstring — and inventing one to reuse the other door would put a
    learned band behind something nobody learned.

    Args:
        finding: The measured change, as an `Observation` whose value quantifies it: how many
            commands crossed a link the baseline has never seen, how much traffic a silent link
            should have carried, how many commands used an unfamiliar function. Becomes the
            evidence's ``source_id``, so the finding's own ``context`` — which names the frames the
            measurement was taken from — remains one hop from anything a user sees (§3.2). Its
            entities, timestamp and domain are carried across unchanged.
        calibrated_confidence: The evidence's ``weight``, and a *calibrated* probability for the
            same reason `evidence_from_deviation` insists on one: `Evidence.weight` is what a
            hypothesis's confidence is built from, and Constitution §3.3 forbids an uncalibrated
            number reaching a user through it.
        summary: Short human-readable description, e.g. ``"10.0.0.9 commanded 10.0.0.20, a
            relationship never seen while the baseline was learned"``.
        facet: Optional ``(kind, feature)`` naming which sub-kind of fact this is. The three
            structural changes and a work order are all one `EvidenceKind`, and Atlas's matchers
            have to tell them apart; the facet is how they ask (ADR 0070). Omitted, the evidence
            declares no facet and a matcher falls back to the summary marker.

    Returns:
        `Evidence` of kind `EvidenceKind.RELATIONSHIP_CHANGE`.

    Raises:
        ValueError: If the finding names fewer than two entities, because a relationship holds
            *between* things and a one-entity fact is a reading rather than a structure; if its
            value is zero or negative, because a change of nothing is a non-event and evidence may
            never rest on one; or if the confidence is not in ``[0, 1]``, because such a number is
            not a probability.
    """
    if len(finding.entity_ids) < _RELATIONSHIP_ENDS:
        raise ValueError(
            f"refusing to build relationship evidence from observation {finding.id!r}: it names "
            f"{len(finding.entity_ids)} entity/entities, and a relationship change describes at "
            f"least {_RELATIONSHIP_ENDS} — a fact about one entity is a reading, not a structure"
        )

    if finding.value <= 0.0:
        raise ValueError(
            f"refusing to build evidence from non-event {finding.id!r}: its {finding.feature!r} "
            f"measures {finding.value}, and a structural change of zero or less is something that "
            "did not happen. Evidence may only rest on a change that was actually measured"
        )

    if not 0.0 <= calibrated_confidence <= 1.0:
        raise ValueError(
            f"calibrated_confidence must be a calibrated probability in [0, 1], got "
            f"{calibrated_confidence}"
        )

    logger.debug(
        "evidence from relationship change %s (%s = %s), weight %s",
        finding.id,
        finding.feature,
        finding.value,
        calibrated_confidence,
    )
    facet_kind, facet_feature = _facet_fields(facet)
    return Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id=finding.id,
        entity_ids=list(finding.entity_ids),
        timestamp=finding.timestamp,
        domain=finding.domain,
        weight=calibrated_confidence,
        summary=summary,
        facet_kind=facet_kind,
        facet=facet_feature,
    )
