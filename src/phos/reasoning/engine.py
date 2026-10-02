"""The engine that holds several explanations at once and lets the evidence sort them out.

This is the subsystem PHOS exists for. Everything below it answers "is this unusual?"; this answers
"what could account for it, what argues for and against each, and how sure can anyone be yet?" —
and it answers with a *set*, always. Three rules give it that shape:

- **It never collapses to one answer.** Every competing set keeps all the explanations the evidence
  bears on, including the ones the evidence has argued against, and including the always-present
  "insufficient evidence" residual. PHOS reports what to investigate and why; deciding is the
  operator's job, so a confident hypothesis is never allowed to hide its rivals.
- **It only ever weighs `Evidence`.** 4A's boundary guarantees a piece of evidence came from a real
  departure from normal, so nothing here reaches back to raw deviations, and `ingest` refuses
  anything that is not `Evidence` even when the caller is untyped.
- **It invents nothing.** Explanations come from `phos.reasoning.templates`; confidences come from
  `phos.reasoning.belief`. This module's whole job is bookkeeping: which hypothesis is currently
  accumulating for which template, which facts belong to the same story, and when an explanation
  has become implausible.

**Two clocks, one window.** `correlation_window` decides both what counts as the same incident and
what counts as the same hypothesis. Evidence that co-occurs — same domain, overlapping entities,
within the window — belongs to one story; and a hypothesis keeps accumulating only while new
evidence keeps arriving inside the window of its last. A burst tomorrow starts a fresh hypothesis at
its prior rather than continuing today's, because a confidence built across unrelated hours is a
confidence in nothing an operator would recognise.

**Pruning marks; it does not delete, and it does not silence.** A hypothesis whose confidence falls
below `pruning_threshold` is marked `PRUNED` and stays in the competing set, because "considered,
and the evidence argues against it" is worth showing. The mark is recomputed on every update, so
later evidence can revive it. If a future PART needs pruning to bound memory, it should expire
hypotheses by window rather than by confidence — dropping an explanation because it is unpopular is
exactly the collapse this engine refuses.

Narratives here are **single-domain**: Atlas evidence and Sentiel evidence never enter the same
story. Correlating across engines is PART 7's job, and doing it early would mean doing it without
the two engines that produce the evidence.
"""

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import (
    Domain,
    Evidence,
    EvidenceId,
    EvidenceRole,
    EvidenceStore,
    Hypothesis,
    HypothesisId,
    HypothesisStatus,
    Narrative,
    utc_now,
)
from phos.reasoning.belief import rank_hypotheses, update_confidence
from phos.reasoning.templates import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    HypothesisTemplate,
    TemplateLibrary,
)

__all__ = ["ReasoningConfig", "ReasoningEngine"]

logger = logging.getLogger(__name__)

_TemplateKey = tuple[Domain, str]
"""How a hypothesis is identified while it accumulates: its domain and its template."""


class ReasoningConfig(BaseModel):
    """How the engine correlates evidence and when it calls an explanation implausible.

    Attributes:
        correlation_window: How far apart two pieces of evidence may be and still belong to the
            same story — and, equally, how long a hypothesis keeps accumulating after its most
            recent evidence before a fresh one is spawned at its prior.
        pruning_threshold: Confidence below which a hypothesis is marked `PRUNED`. It is still
            reported; see this module's docstring on what pruning does and does not do.
        seed: Seed for any randomness in reasoning. **Nothing in this engine is stochastic** —
            every output is a deterministic function of the evidence and its order — so this is
            currently unused. It is here because Constitution §6 requires all randomness to be
            seeded from one configurable place, and a later stochastic step must take it from here
            rather than introducing a second source. Said plainly rather than left to be discovered.

    Invariants:
        The correlation window is a positive duration.
    """

    model_config = ConfigDict(frozen=True)

    correlation_window: timedelta = timedelta(minutes=30)
    pruning_threshold: float = Field(default=0.02, ge=0.0, lt=1.0)
    seed: int = 0

    @model_validator(mode="after")
    def _check_window_is_positive(self) -> Self:
        if self.correlation_window <= timedelta(0):
            raise ValueError(
                f"correlation_window must be a positive duration, got {self.correlation_window}: "
                "a zero or negative window would put every piece of evidence in its own story"
            )
        return self


def _require_evidence(item: object) -> Evidence:
    """Return ``item`` if it is `Evidence`, else raise.

    The engine's door. 4A's boundary guarantees that `Evidence` can only have come from a genuine
    out-of-band deviation, which makes the *type* the carrier of that guarantee — so it is worth
    checking at runtime and not only in mypy. PART 8 will feed this engine objects rebuilt from
    JSON, where the static guarantee does not reach.

    Raises:
        TypeError: If ``item`` is anything else — in particular a `Deviation`, which is a scored
            candidate and may never become a hypothesis without passing 4A's boundary first.
    """
    if not isinstance(item, Evidence):
        raise TypeError(
            f"the reasoning engine weighs only Evidence, got {type(item).__name__}. A Deviation is "
            "a scored candidate; promote it with phos.reasoning.evidence_from_deviation, which "
            "refuses the ones that never left their expected range"
        )
    return item


class ReasoningEngine:
    """Turns a stream of `Evidence` into competing hypotheses and the narratives they belong to.

    Not a Pydantic model: this object has working memory that changes as evidence arrives, whereas
    everything it produces is an immutable ontology value. Nothing it holds is global — construct
    one per stream of evidence and pass it explicitly.

    Attributes are private; the engine is read through `hypotheses`, `competing` and `narratives`.
    """

    def __init__(
        self,
        library: TemplateLibrary,
        store: EvidenceStore,
        config: ReasoningConfig | None = None,
    ) -> None:
        """Create an engine over a template library.

        Args:
            library: The curated explanations this engine may draw on. PARTs 5 and 6 supply
                domain-specific ones; 4B ships only a generic set.
            store: The ontology store. Read from, never written to: the engine resolves entities
                from it so that templates can constrain on entity type. Persisting the hypotheses
                and narratives it produces is the caller's decision, not the engine's.
            config: Correlation window, pruning threshold and seed. Defaults are used if omitted.

        Note:
            One "insufficient evidence" hypothesis is created immediately for every domain the
            library covers, so that before any observation the only explanation on the table is
            that we do not know.
        """
        self._library = library
        self._store = store
        self._config = ReasoningConfig() if config is None else config
        self._evidence: dict[EvidenceId, Evidence] = {}
        self._hypotheses: dict[HypothesisId, Hypothesis] = {}
        self._current: dict[_TemplateKey, HypothesisId] = {}
        self._latest: dict[Domain, datetime] = {}

        for domain in sorted(
            {template.domain for template in library.templates}, key=lambda d: d.value
        ):
            self._spawn_residual(domain)

    # -- ingestion ------------------------------------------------------------------------------

    def ingest(self, evidence: Iterable[Evidence]) -> None:
        """Weigh each piece of evidence against every explanation it bears on.

        For each piece: match it against the library, spawn any explanation that is not currently
        accumulating, apply the belief update, and attach the evidence to the supporting or
        contradictory list. Evidence no template explains still opens the domain's residual
        hypothesis, because "nothing on offer accounts for this" is an answer.

        A marked silent graph finding is not matched unless it shares an entity with in-window
        command activity (unknown master or unexpected function). It remains in the working set
        so it can be its own story; it does not accumulate on this window's explanations.

        Args:
            evidence: The facts to weigh, in the order they should be weighed. The order affects
                which hypotheses spawn, but not — because the belief rule is additive in log-odds —
                where their confidences end up.

        Raises:
            TypeError: If anything that is not `Evidence` is passed.
            ValueError: If a piece of evidence carries an uncalibrated weight, propagated from
                `phos.reasoning.belief.update_confidence`.

        Note:
            A piece of evidence whose id has already been weighed is skipped, so redelivering the
            same fact cannot invent support for anything.
        """
        entities = {entity.id: entity for entity in self._store.entities()}
        incoming: list[Evidence] = []
        for item in evidence:
            fact = _require_evidence(item)
            if fact.id in self._evidence:
                logger.debug("evidence %s has already been weighed; skipping", fact.id)
                continue
            self._evidence[fact.id] = fact
            incoming.append(fact)

        for fact in incoming:
            self._spawn_residual(fact.domain)
            if not self._attachable(fact):
                logger.debug(
                    "graph finding %s does not share an entity with in-window command activity; "
                    "not attaching it to this story's explanations",
                    fact.id,
                )
                continue
            for match in self._library.matches(fact, entities):
                self._weigh(match.template, match.role, fact)

            latest = self._latest.get(fact.domain)
            if latest is None or fact.timestamp > latest:
                self._latest[fact.domain] = fact.timestamp

    def _attachable(self, fact: Evidence) -> bool:
        """Return whether ``fact`` may accumulate on this window's explanations.

        Sensor evidence and unmarked relationship changes always attach. A marked graph finding
        attaches only by entity-reachability from in-window command activity (unknown master or
        unexpected function), or as the unknown-master finding itself. The rule lives in
        `phos.atlas.command_grounding` so the engine does not invent a second grouping. Imported
        lazily to avoid a load-time cycle with the command-evidence promoter.
        """
        from phos.atlas.command_grounding import (
            command_act_entities_near,
            graph_finding_is_attachable,
        )

        act = command_act_entities_near(
            tuple(self._evidence.values()),
            fact.timestamp,
            self._config.correlation_window,
        )
        return graph_finding_is_attachable(fact, act)

    def _weigh(self, template: HypothesisTemplate, role: EvidenceRole, fact: Evidence) -> None:
        """Apply one piece of evidence to the hypothesis currently accumulating for a template."""
        hypothesis = self._accumulating(template, fact)
        confidence = update_confidence(hypothesis, fact, role, hypothesis.confidence)
        updated = hypothesis.with_evidence(fact.id, role).with_confidence(confidence)
        self._hypotheses[updated.id] = self._judged(updated)

    def _accumulating(self, template: HypothesisTemplate, fact: Evidence) -> Hypothesis:
        """Return the hypothesis this evidence should join, spawning a fresh one if the window slid.

        A hypothesis accumulates while evidence keeps arriving within `correlation_window` of its
        most recent. Once it does not, the story is over: the old hypothesis keeps its evidence and
        its confidence as history, and a new one starts at the template's prior.
        """
        key: _TemplateKey = (template.domain, template.template_id)
        current_id = self._current.get(key)
        if current_id is not None:
            current = self._hypotheses[current_id]
            latest = self._latest_evidence_time(current)
            if latest is None or abs(fact.timestamp - latest) <= self._config.correlation_window:
                return current
            logger.info(
                "evidence %s is outside %s's window; starting a fresh hypothesis for %s",
                fact.id,
                current.id,
                template.template_id,
            )

        fresh = template.instantiate()
        self._hypotheses[fresh.id] = fresh
        self._current[key] = fresh.id
        return fresh

    def _spawn_residual(self, domain: Domain) -> None:
        """Ensure this domain has its "insufficient evidence" hypothesis. Idempotent."""
        key: _TemplateKey = (domain, INSUFFICIENT_EVIDENCE_TEMPLATE_ID)
        if key in self._current:
            return
        residual = self._library.residual_for(domain).instantiate()
        self._hypotheses[residual.id] = residual
        self._current[key] = residual.id

    def _judged(self, hypothesis: Hypothesis) -> Hypothesis:
        """Return the hypothesis with its status set from its current confidence.

        A live reading rather than a tombstone: an explanation that falls below the threshold is
        marked `PRUNED`, and evidence that revives it marks it `ACTIVE` again. `CONFIRMED` and
        `DISMISSED` are operator judgements; this engine never makes them.
        """
        status = (
            HypothesisStatus.ACTIVE
            if hypothesis.confidence >= self._config.pruning_threshold
            else HypothesisStatus.PRUNED
        )
        if hypothesis.status is status:
            return hypothesis
        logger.info(
            "hypothesis %s (%s) is now %s at confidence %.4f",
            hypothesis.id,
            hypothesis.template_id,
            status.value,
            hypothesis.confidence,
        )
        return hypothesis.model_copy(update={"status": status, "updated_at": utc_now()})

    # -- reading --------------------------------------------------------------------------------

    def hypotheses(self, domain: Domain | None = None) -> list[Hypothesis]:
        """Return every hypothesis this engine has spawned, oldest first.

        History included: hypotheses whose window has passed are still here, because the story they
        explained happened and the evidence that moved them is still attached.
        """
        return [
            hypothesis
            for hypothesis in self._hypotheses.values()
            if domain is None or hypothesis.domain is domain
        ]

    def competing(self, domain: Domain) -> list[Hypothesis]:
        """Return the explanations currently on the table for ``domain``.

        Always includes the "insufficient evidence" residual, and always includes explanations the
        evidence has argued against — a set with the losers removed would be a verdict.

        Args:
            domain: Which engine's explanations to report.

        Returns:
            The hypotheses currently accumulating in this domain, ordered by confidence descending
            and then by template id, so the listing is a function of the evidence alone. When two
            or more contentful explanations share the lead, `insufficient_evidence` is raised to
            the front rather than an alphabetical unique winner.
        """
        latest = self._latest.get(domain)
        window = self._config.correlation_window
        current: list[Hypothesis] = []
        for (candidate_domain, template_id), hypothesis_id in self._current.items():
            if candidate_domain is not domain:
                continue
            hypothesis = self._hypotheses[hypothesis_id]
            if template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
                current.append(hypothesis)
                continue
            evidence_time = self._latest_evidence_time(hypothesis)
            if latest is None or evidence_time is None or abs(latest - evidence_time) <= window:
                current.append(hypothesis)
        return self._ranked(current)

    def narratives(self) -> list[Narrative]:
        """Group the evidence and its explanations into stories, earliest first.

        Two pieces of evidence belong to the same story when they **co-occur** — same domain,
        overlapping entities, within `correlation_window` — or when the same hypothesis rests on
        both. The second rule is what makes a narrative self-contained: a story shows every piece of
        evidence its confidences were built from, so the number an operator reads can be rebuilt
        from the story printed beside it.

        Returns:
            One `Narrative` per story, each carrying its evidence in time order, its competing
            explanations ordered by confidence, ``overall_confidence`` left unset (hypothesis
            confidence is uncalibrated; Constitution §3.3), and ``causal_edges`` running from
            evidence to the explanations it bears on, in time order. Those edges are the
            reconstructable evidence→hypothesis bearings already stored on each hypothesis
            (Constitution §3.2); they are not a declared plant causal graph. Empty until evidence
            has been ingested.

        Note:
            Co-occurrence is tested pairwise, so this is quadratic in the evidence held. Fine for a
            working set; a long-running engine should be given a bounded stream.
        """
        facts = list(self._evidence.values())
        if not facts:
            return []

        return [self._narrative(group, facts) for group in self._grouped(facts)]

    # -- internals ------------------------------------------------------------------------------

    def _grouped(self, facts: Sequence[Evidence]) -> list[list[int]]:
        """Return indices of ``facts`` partitioned into stories.

        Each group is in time order, and the groups themselves are ordered by when their earliest
        evidence occurred — never by identifier, which is a random uuid and would make the output
        differ between runs of the same input.
        """
        parent = list(range(len(facts)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            roots = sorted((find(left), find(right)))
            parent[roots[1]] = roots[0]

        for left in range(len(facts)):
            for right in range(left + 1, len(facts)):
                if self._co_occur(facts[left], facts[right]):
                    union(left, right)

        position = {fact.id: index for index, fact in enumerate(facts)}
        for hypothesis in self._hypotheses.values():
            cited = [
                position[evidence_id]
                for evidence_id in (*hypothesis.supporting, *hypothesis.contradictory)
            ]
            for other in cited[1:]:
                union(cited[0], other)

        groups: dict[int, list[int]] = {}
        for index in range(len(facts)):
            groups.setdefault(find(index), []).append(index)
        ordered = [
            sorted(group, key=lambda index: (facts[index].timestamp, index))
            for group in groups.values()
        ]
        return sorted(ordered, key=lambda group: (facts[group[0]].timestamp, group[0]))

    def _co_occur(self, one: Evidence, other: Evidence) -> bool:
        """Return whether two facts are close enough, and related enough, to be one story."""
        if one.domain is not other.domain:
            return False
        if not set(one.entity_ids) & set(other.entity_ids):
            return False
        return abs(one.timestamp - other.timestamp) <= self._config.correlation_window

    def _narrative(self, group: Sequence[int], facts: Sequence[Evidence]) -> Narrative:
        """Assemble one story from the evidence indices in ``group``."""
        members = [facts[index] for index in group]
        domain = members[0].domain
        cited = {fact.id for fact in members}

        involved = [
            hypothesis
            for hypothesis in self._hypotheses.values()
            if cited & {*hypothesis.supporting, *hypothesis.contradictory}
        ]
        # Every story gets the residual, and it is never already in `involved`: its template
        # declares no evidence patterns, so no evidence can ever have been attached to it.
        residual_id = self._current[(domain, INSUFFICIENT_EVIDENCE_TEMPLATE_ID)]
        involved.append(self._hypotheses[residual_id])

        ranked = self._ranked(involved)
        leading = ranked[0]
        return Narrative(
            title=f"{leading.label} ({len(members)} pieces of evidence)",
            domain=domain,
            hypothesis_ids=[hypothesis.id for hypothesis in ranked],
            evidence_ids=[fact.id for fact in members],
            overall_confidence=None,
            causal_edges=[
                (fact.id, hypothesis.id)
                for fact in members
                for hypothesis in ranked
                if fact.id in {*hypothesis.supporting, *hypothesis.contradictory}
            ],
        )

    def _ranked(self, hypotheses: Sequence[Hypothesis]) -> list[Hypothesis]:
        """Order hypotheses by confidence descending, without treating a tie as a unique winner.

        Delegates to `phos.reasoning.belief.rank_hypotheses` so Atlas narratives, Sentiel
        narratives, and the unit tests share one ADR 0036 implementation. Insertion order is
        the order hypotheses were minted in this engine, not the uuid they carry.
        """
        position = {hypothesis_id: index for index, hypothesis_id in enumerate(self._hypotheses)}
        return rank_hypotheses(hypotheses, insertion_order=position)

    def _latest_evidence_time(self, hypothesis: Hypothesis) -> datetime | None:
        """Return when this hypothesis last saw evidence, or ``None`` if it has seen none."""
        timestamps = [
            self._evidence[evidence_id].timestamp
            for evidence_id in (*hypothesis.supporting, *hypothesis.contradictory)
        ]
        return max(timestamps) if timestamps else None
