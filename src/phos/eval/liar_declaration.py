"""The held-out liar measurement, declared before any run is scored.

T1 in ``docs/v1-five-moments.md``. The seeds, the plants, the graded magnitudes and the
pass share are fixed here. This module does not generate a plant, does not call Atlas,
and does not write ``eval_runs/log.jsonl``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction

from phos.atlas.templates import SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
from phos.library.ot import SEEDS, SUBTLETIES, ot_packs
from phos.ontology.hypotheses import Hypothesis
from phos.reasoning.belief import tied_lead_ids
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.synth.attacks.spec import AttackType

__all__ = [
    "CITATION_FACETS",
    "DEVELOPMENT_SEEDS",
    "LIAR_HELD_OUT_SEEDS",
    "LIAR_PLANTS",
    "PASS_SHARE_LOWER_BOUND",
    "liar_run_count",
    "liar_run_passes",
    "plants_that_already_have_liar",
    "share_passes",
]

#: Twenty seeds. None of them is a library seed, a train seed, or a seed the demo and
#: the diagnostic scenarios have already been shown on.
LIAR_HELD_OUT_SEEDS: tuple[int, ...] = tuple(range(94001, 94021))

#: Seeds already used to build or demonstrate the synthetic plant. The held-out list
#: must not meet this set. 71001-71003 are the library. 80001-80003 fit the library
#: trains. 11-30 are the demo and the diagnostic scenarios.
DEVELOPMENT_SEEDS: frozenset[int] = frozenset(
    {
        1,
        3,
        7,
        8,
        11,
        *range(11, 31),
        77,
        99,
        4242,
        *SEEDS,
        80001,
        80002,
        80003,
    }
)

#: Every plant that already has a ``LIAR`` recipe. Not a new plant.
LIAR_PLANTS: tuple[str, ...] = (
    "water-treatment",
    "power-generation",
    "batch-reactor",
)

#: The unique lead must be this template: the instrument failed, not the process.
LEADING_TEMPLATE_ID: str = SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID

#: The only citations that count. They are ``Evidence.facet`` values, not summary text.
#: Nothing in this commit emits them.
CITATION_FACETS: tuple[str, ...] = (
    "command_to_response_mismatch",
    "cross_signal_mismatch",
)

#: A share equal to one half does not pass. The comparison is strict.
PASS_SHARE_LOWER_BOUND: Fraction = Fraction(1, 2)


def liar_run_count() -> int:
    """Return how many liar runs the declaration contains.

    One run is one plant, one held-out seed, and one graded subtlety.
    """
    return len(LIAR_PLANTS) * len(LIAR_HELD_OUT_SEEDS) * len(SUBTLETIES)


def share_passes(passed: int, total: int) -> bool:
    """Return whether ``passed / total`` is strictly above one half.

    Args:
        passed: Runs that met `liar_run_passes`.
        total: Runs in the declaration. ``liar_run_count`` is that number.

    Returns:
        True only when the fraction is greater than one half.

    Raises:
        ValueError: If the counts are not a real fraction of the declared runs.
    """
    if total != liar_run_count() or not 0 <= passed <= total:
        raise ValueError(
            f"a liar share is {passed} of {total}; the declaration has {liar_run_count()} runs"
        )
    return Fraction(passed, total) > PASS_SHARE_LOWER_BOUND


def liar_run_passes(
    hypotheses: Sequence[Hypothesis],
    evidence_facets: Mapping[str, str | None],
) -> bool:
    """Return whether one run meets the declared catch.

    The lead is the existing order ``(-confidence, template_id)`` among contentful
    hypotheses. A tie is not a lead. ``insufficient_evidence`` is not the catch.
    The leader must be `LEADING_TEMPLATE_ID`, and at least one of its supporting
    evidence ids must carry a facet in `CITATION_FACETS`. Confidence is used only
    to rank. It is not a reported probability.

    Args:
        hypotheses: The competing set for one run, judged from the true state.
        evidence_facets: Evidence id to ``Evidence.facet``. Missing ids are not a citation.

    Returns:
        True when the unique leader is the instrument-fault explanation and it cites
        a command-to-response or cross-signal mismatch.
    """
    if tied_lead_ids(hypotheses):
        return False
    contentful = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    ]
    if not contentful:
        return False
    leader = min(contentful, key=lambda item: (-item.confidence, item.template_id))
    if leader.template_id != LEADING_TEMPLATE_ID:
        return False
    return any(
        evidence_facets.get(evidence_id) in CITATION_FACETS for evidence_id in leader.supporting
    )


def plants_that_already_have_liar() -> tuple[str, ...]:
    """Return plant ids whose library process pack contains ``AttackType.LIAR``.

    Pack order, each plant once. This reads the declared recipes. It does not simulate.
    """
    found: list[str] = []
    for pack in ot_packs():
        if pack.plant_id in found:
            continue
        if any(plan.type is AttackType.LIAR for plan in pack.attacks):
            found.append(pack.plant_id)
    return tuple(found)
