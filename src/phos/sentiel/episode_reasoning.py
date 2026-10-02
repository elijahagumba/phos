"""Explaining an episode, with two kinds of evidence Sentiel has never been able to offer.

PART 6C reasons over an entity-**day**: per-feature contributions become evidence, group into at
most one behaviour event per family, and reach `phos.reasoning.ReasoningEngine` once per person.
Two things were missing from that picture and both are supplied here.

**`EvidenceKind.SEQUENCE_ANOMALY` has existed since PART 1 and has never been emitted by anything.**
Two templates in `phos.reasoning.templates` match on it; no engine has ever produced one, so those
matchers have never fired against a corpus. `sequence_evidence` produces the first.

**A declared-path finding has no home in the per-day evidence set at all**, because the whole set
is built from `phos.sentiel.FEATURE_FAMILIES`, and a route through the org chart is not a feature.
`path_evidence` gives it one, as `EvidenceKind.RELATIONSHIP_CHANGE` — the ontology member that
already means "the structure around this thing is not what it was".

**Each new kind supports exactly one explanation, and the choice is argued from shape.** ADR 0023
made the case plainly: a template supported by everything is separated from its rivals only by its
prior, so attaching a new fact to every hypothesis it might plausibly touch destroys the
discrimination the competing set exists for. So:

* A **rare ordered path** supports `compromised_account` and nothing else. The account holder knows
  their own workflow; somebody else driving the account performs the same ordinary actions in an
  unfamiliar order. It is deliberately **not** evidence for `insider_misuse`: a misusing holder
  still works the way they have always worked, so an unusual order does not tell the two apart.
* A **declared-path finding** supports `insider_misuse` and nothing else. It is the holder using
  access they legitimately have to reach across the structure the directory declares. It is
  deliberately **not** evidence for `compromised_account`: an intruder's first problem is
  establishing access, and where an account's mail goes says nothing about who is typing.

Neither is listed as contradictory anywhere, for the reason `phos.sentiel.templates` already gives
about role changes: manufacturing a contradiction to tidy up a ranking corrupts the belief
arithmetic.

**The competing set is still complete, and the residual still cannot be displaced by construction.**
`explain_episode` re-applies ADR 0023 Decision 2 — every registered explanation appears in every
story, including the ones no evidence touched, sitting at its prior — and ranks with
`phos.reasoning.rank_hypotheses`, which raises `insufficient_evidence` on a tie rather than
crowning a leader alphabetically (ADR 0036). ``overall_confidence`` is left unset (ADR 0045).

**Confidence here is no more calibrated than it was.** Everything
`UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT` says still holds, and the episode unit *sharpens* its
third clause rather than fixing it: the belief update treats each behaviour event as independent,
and an episode is precisely a set of days that are not. `EPISODE_BELIEF_CAVEAT` states the
consequence in the one place a reader will meet the number.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

from phos.ontology import (
    Domain,
    EntityId,
    Evidence,
    EvidenceKind,
    EvidenceStore,
    Hypothesis,
    Narrative,
)
from phos.reasoning import (
    EvidencePattern,
    HypothesisTemplate,
    ReasoningConfig,
    ReasoningEngine,
    TemplateLibrary,
    rank_hypotheses,
)
from phos.sentiel.entities import user_id_of
from phos.sentiel.episodes import Episode
from phos.sentiel.paths import PathFindings
from phos.sentiel.sequence_scoring import SequenceScores
from phos.sentiel.templates import (
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    INSIDER_MISUSE_TEMPLATE_ID,
    sentiel_templates,
)

__all__ = [
    "EPISODE_BELIEF_CAVEAT",
    "PATH_EVIDENCE_MARKER",
    "SEQUENCE_EVIDENCE_MARKER",
    "episode_library",
    "explain_episode",
    "path_evidence",
    "sequence_evidence",
]

logger = logging.getLogger(__name__)

EPISODE_BELIEF_CAVEAT: Final = (
    "An episode's hypothesis confidence counts one cause many times. The belief update is "
    "additive in log-odds over facts it treats as INDEPENDENT, and an episode is by construction a "
    "run of days that are not independent — that is what makes it an episode. So a long episode "
    "accumulates a higher confidence than a short one for the same behaviour, and the difference "
    "measures duration, not certainty. This sharpens clause (3) of "
    "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT rather than answering it. Rank on these; never "
    "surface them."
)

PATH_EVIDENCE_MARKER: Final = "declared-path:"
"""Prefix marking an `Evidence.source_id` as a declared-graph path finding rather than a deviation.

Explicit, on the pattern `phos.sentiel.BEHAVIOUR_EVENT_MARKER` and
`phos.atlas.grouping.SUBSYSTEM_EVENT_MARKER` already set: what a piece of evidence is about is a
question about a declared marker, never about how identifiers happen to be spelled.
"""

SEQUENCE_EVIDENCE_MARKER: Final = "sequence-path:"
"""Prefix marking an `Evidence.source_id` as an ordered-path surprise."""

_SEQUENCE_RARE: Final = EvidencePattern(kinds=(EvidenceKind.SEQUENCE_ANOMALY,))
"""This account did ordinary things in an order its own organisation's history rarely shows."""

_PATH_UNDECLARED: Final = EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))
"""This account's activity travelled a route the directory declares no close relationship for."""


def episode_library() -> TemplateLibrary:
    """Return the enterprise explanations, extended to hear sequence and path evidence.

    The four explanations and the residual are `phos.sentiel.sentiel_templates`' own, with their
    ids, labels and priors untouched — so an episode story and a 6C day story rank the same
    explanations against the same base rates. Only two ``supported_by`` tuples grow.

    Returns:
        The library.
    """
    extended: list[HypothesisTemplate] = []
    for template in sentiel_templates():
        if template.template_id == COMPROMISED_ACCOUNT_TEMPLATE_ID:
            extended.append(
                template.model_copy(
                    update={"supported_by": (*template.supported_by, _SEQUENCE_RARE)}
                )
            )
        elif template.template_id == INSIDER_MISUSE_TEMPLATE_ID:
            extended.append(
                template.model_copy(
                    update={"supported_by": (*template.supported_by, _PATH_UNDECLARED)}
                )
            )
        else:
            extended.append(template)
    return TemplateLibrary(templates=tuple(extended))


def sequence_evidence(
    entity_id: EntityId,
    day: datetime,
    scores: SequenceScores,
    cut: float,
    weight: float,
) -> Evidence | None:
    """Return the first `EvidenceKind.SEQUENCE_ANOMALY` any PHOS engine has produced, or ``None``.

    Args:
        entity_id: Whose day this is.
        day: The window start.
        scores: The day's ordered and order-blind surprises.
        cut: The declared alert cut, read off the training distribution.
        weight: The evidence weight. **Not** a calibrated probability — no calibrator has been
            fitted for sequence surprise, and pretending otherwise would breach Constitution §3.3
            more loudly than the existing caveats already do.

    Returns:
        The evidence, or ``None`` when the day's path is not rare enough to say anything.
    """
    if scores.population < cut:
        return None
    return Evidence(
        kind=EvidenceKind.SEQUENCE_ANOMALY,
        source_id=f"{SEQUENCE_EVIDENCE_MARKER}{user_id_of(entity_id)}:{day.date().isoformat()}",
        entity_ids=[entity_id],
        timestamp=day,
        domain=Domain.SENTIEL,
        weight=weight,
        summary=(
            f"{user_id_of(entity_id)}: the order of this day's {scores.n_tokens} activity step(s) "
            f"carries {scores.population:.2f} nats of surprise against the organisation's "
            f"attack-free history (cut {cut:.2f}); the same day's actions ignoring order carry "
            f"{scores.count_baseline:.2f}"
        ),
    )


def path_evidence(
    entity_id: EntityId,
    day: datetime,
    findings: PathFindings,
    weight: float,
) -> Evidence | None:
    """Return a declared-path finding as evidence, or ``None`` when the day travelled no such route.

    Args:
        entity_id: Whose day this is.
        day: The window start.
        findings: What the day did against the declared structure.
        weight: The evidence weight, uncalibrated for the same reason `sequence_evidence` gives.

    Returns:
        The evidence, or ``None`` when nothing this day reached past the declared boundary.
    """
    if not findings.novel_beyond_counts:
        return None
    parts: list[str] = []
    if findings.distant_internal_recipients:
        parts.append(
            f"mailed {findings.distant_internal_recipients} colleague(s) the directory places "
            "outside this person's department"
        )
    if findings.shared_device_distant:
        parts.append(
            f"used {findings.shared_device_distant} machine(s) that also carried a "
            "declared-distant colleague's activity the same day"
        )
    return Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id=f"{PATH_EVIDENCE_MARKER}{user_id_of(entity_id)}:{day.date().isoformat()}",
        entity_ids=[entity_id],
        timestamp=day,
        domain=Domain.SENTIEL,
        weight=weight,
        summary=(
            f"{user_id_of(entity_id)}: {'; '.join(parts)}. Longest declared route this day: "
            f"{findings.max_hops} edge(s) through the org chart"
        ),
    )


def explain_episode(
    episode: Episode,
    evidence: Sequence[Evidence],
    store: EvidenceStore,
    library: TemplateLibrary | None = None,
    config: ReasoningConfig | None = None,
) -> list[Narrative]:
    """Reason over one episode's evidence, completing the competing set.

    Args:
        episode: The episode being explained. Its entity scopes the whole pass — a hypothesis is a
            claim about somebody, which is ADR 0023 Decision 1 and holds identically here.
        evidence: Every piece of evidence about this episode, in ingestion order.
        store: Where hypotheses and narratives are recorded.
        library: The explanations. Defaults to `episode_library`.
        config: Reasoning settings. Defaults to a correlation window matching the episode's own
            declared gap, so two facts inside one episode are always correlatable and two facts in
            different episodes of the same entity are not.

    Returns:
        One `Narrative` per story, each carrying every registered explanation — including the ones
        no evidence touched, at their priors — ranked by `phos.reasoning.rank_hypotheses`.

    Raises:
        ValueError: If any evidence is about a different entity, which would build a confidence for
            one person partly out of another's behaviour.
    """
    stray = {item.entity_ids[0] for item in evidence if item.entity_ids[0] != episode.entity_id}
    if stray:
        raise ValueError(
            f"episode for {episode.entity_id} was given evidence about {sorted(stray)}. A "
            "hypothesis is a claim about somebody, and mixing entities would build one person's "
            "confidence out of another's behaviour (ADR 0023)"
        )

    settings = config or ReasoningConfig(correlation_window=episode.gap)
    templates = library or episode_library()
    # The store enforces referential integrity: a hypothesis may not cite evidence the store has
    # never seen. Recording it here rather than requiring the caller to means that invariant
    # cannot be broken from outside, which is how `SentielEngine._group` already handles it.
    for item in evidence:
        if store.get_evidence(item.id) is None:
            store.add_evidence(item)
    engine = ReasoningEngine(templates, store, settings)
    engine.ingest(list(evidence))
    for hypothesis in engine.hypotheses():
        store.add_hypothesis(hypothesis)

    narratives: list[Narrative] = []
    for narrative in engine.narratives():
        completed = _completed(narrative, templates, store)
        store.add_narrative(completed)
        narratives.append(completed)
    return narratives


def _completed(narrative: Narrative, library: TemplateLibrary, store: EvidenceStore) -> Narrative:
    """Add the explanations no evidence touched and re-rank, per ADR 0023 Decision 2."""
    reasoned = [_hypothesis(store, item) for item in narrative.hypothesis_ids]
    explained = {hypothesis.template_id for hypothesis in reasoned}
    untouched = [
        template.instantiate()
        for template in library.for_domain(narrative.domain)
        if template.template_id not in explained
    ]
    for hypothesis in untouched:
        store.add_hypothesis(hypothesis)
    ranked = rank_hypotheses([*reasoned, *untouched])
    return narrative.model_copy(
        update={
            "title": f"{ranked[0].label} ({len(narrative.evidence_ids)} pieces of evidence)",
            "hypothesis_ids": [hypothesis.id for hypothesis in ranked],
            "overall_confidence": None,
        }
    )


def _hypothesis(store: EvidenceStore, hypothesis_id: str) -> Hypothesis:
    """Return a hypothesis just stored, or fail loudly rather than guess."""
    hypothesis = store.get_hypothesis(hypothesis_id)
    if hypothesis is None:  # pragma: no cover - written a line earlier
        raise ValueError(
            f"hypothesis {hypothesis_id!r} is cited by a narrative just built but is not in the "
            "store; a story whose explanations cannot be resolved is a traceability failure"
        )
    return hypothesis


def evidence_by_episode(
    episodes: Sequence[Episode], evidence: Sequence[Evidence]
) -> Mapping[str, list[Evidence]]:
    """Partition evidence to the episode whose member days it falls on.

    Evidence on a day no episode contains is dropped rather than attached to the nearest one: an
    episode's days are its members, and a gap day is not one.
    """
    buckets: dict[str, list[Evidence]] = {}
    for episode in episodes:
        key = f"{episode.entity_id}:{episode.start.date().isoformat()}"
        buckets[key] = [
            item
            for item in evidence
            if item.entity_ids[0] == episode.entity_id and episode.covers(item.timestamp)
        ]
    return buckets
