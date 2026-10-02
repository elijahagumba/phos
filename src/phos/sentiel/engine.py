"""The Sentiel vertical: an organisation's behaviour in, competing explanations out.

Everything Sentiel needed has existed for three PARTs without being joined up. This module is the
join, and — like `phos.atlas.engine`, which it deliberately mirrors — it is thin. It owns no
detection logic, no belief arithmetic, no narrative assembly and no explanations of its own. Its
whole job is to put existing pieces in the one order that makes them mean something:

1. **Score** the corpus into one aggregate per ``(entity, window)`` with PART 6B's `WindowScorer`,
   which is where a wide feature set stops multiplying alerts.
2. **Promote** each of that window's per-feature contributions through 4A's evidence boundary,
   weighting it with a calibrated probability. This is the only route into reasoning, and it is the
   *same* boundary Atlas's signals pass through.
3. **Group** the surviving evidence into at most one **behaviour event** per family per window
   (`phos.sentiel.templates`). Thirty-four features become at most four things to explain.
4. **Reason** over those events with the enterprise template library, holding every explanation the
   evidence bears on at once — 4B's `ReasoningEngine`, unchanged, run **once per entity**.
5. **Narrate** — return the stories, each carrying its rivals, the always-present "insufficient
   evidence" residual, and a path back to every measurement underneath.

**Reasoning is per entity, and that is the one place this vertical is not shaped like Atlas's.**
`ReasoningEngine` identifies an accumulating hypothesis by its domain and template alone, which is
correct for a plant and wrong for an organisation: one pass over everybody would accumulate two
unrelated colleagues' access departures into a single `compromised_account`, and then merge their
stories, because sharing a hypothesis is how the engine recognises one incident. A person's
confidence would be built partly from somebody else's behaviour. `SentielEngine._reason` therefore
runs one pass per entity — see its docstring for why that costs nothing else, and for why each
story is completed with the explanations no evidence touched.

**Grouping comes before reasoning, and the order carries PART 6B's finding one layer up.** 6A
measured what happens when a wider feature set multiplies the alerts: an irreducible floor of 1,668
alerts containing no true positive. Letting it multiply the *evidence* would reproduce that inside
the reasoning layer, where it would be worse — a hypothesis's confidence would grow with the width
of the feature set rather than with anything the person did. Because a family yields one event per
window, 34 features produce no more evidence than 26 do, and what accumulation remains is
accumulation over *time*.

**Only an out-of-band contribution becomes evidence, and that is 4A's rule rather than a new one.**
The scorer emits a candidate at ``emit_k`` (1.0 by default), well below the ``band_k`` (3.0) that
shapes the reported `ExpectedRange`, because a dense candidate set is what makes a threshold sweep
meaningful. A hypothesis may not rest on a value that never left its expected range, so a large
share of the contributions behind a window's *score* never appear in its *explanation*.
`ExplanationSummary.in_band` counts them, and `EXPLAINED_SUBSET_CAVEAT` says so on every report,
because a reader comparing "score 6.2" against "three pieces of evidence" would otherwise assume
arithmetic that is not there.

**The re-scoring seam is checked, not assumed.** `WindowScorer` does not expose the `Deviation` and
`Observation` behind a contribution, and PART 6C may not modify it, so this module keeps its own
index of the observations it fed in and re-scores one at a time to recover the pair. That is exact
only because `phos.models.StaticRangeFittedModel` judges each observation independently of the
others — so `require_independent_judgement` verifies it on every contribution rather than trusting
it, and a future model that loses the guarantee fails loudly at the seam.

**A borrowed scale is worth less, and the discount is declared rather than hidden.** PART 6B's
answer to a `(user, feature)` baseline with no spread is to keep the entity's own centre and borrow
the population's spread. That is a real measurement of a real departure, but one of the two numbers
behind it did not come from this entity — so its evidence carries `SCALE_BORROWED_WEIGHT_FACTOR`.
Where no spread existed anywhere the magnitude is the clamp rather than a measurement and only the
departure's *existence* survives, so `UNQUANTIFIED_WEIGHT_FACTOR` applies. Both are unmeasured
placeholders in the same sense the template priors and `EVIDENCE_STRENGTH` are, and
`BORROWED_SCALE_CAVEAT` says so.

**Everything this vertical produces must never be read as more than it is** — see
`SENTIEL_VERTICAL_CAVEATS`, which `annotate_with_caveats` writes onto every report the vertical
logs. Hypothesis confidences are not calibrated probabilities; the `peer_anomaly` explanation has
no positive case anywhere in the data PHOS reads; CERT is synthetic; and two labelled insiders
cannot support a quotable recall.

Not here, and deliberately: no new detection models, no new features, no calibration of *hypothesis*
confidence — which needs data labelling which explanation was true, and no corpus PHOS uses carries
it — and no cross-engine correlation, which is PART 7's.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from phos.eval import Dataset, EvaluationReport
from phos.models.base import StaticRangeFittedModel
from phos.ontology import (
    Deviation,
    Domain,
    EntityId,
    Evidence,
    EvidenceKind,
    EvidenceStore,
    Hypothesis,
    InMemoryEvidenceStore,
    Narrative,
    Observation,
)
from phos.reasoning import (
    FittedCalibrator,
    ReasoningConfig,
    ReasoningEngine,
    TemplateLibrary,
    calibrated_probabilities,
    evidence_from_deviation,
    is_out_of_band,
    rank_hypotheses,
)
from phos.sentiel.entities import user_id_of
from phos.sentiel.scoring import (
    AggregationPolicy,
    FeatureContribution,
    ScoredWindow,
    WindowScorer,
    borrowed_scale_range,
)
from phos.sentiel.templates import (
    BehaviourFamily,
    behaviour_event_source_id,
    family_of,
    sentiel_library,
)

__all__ = [
    "BORROWED_SCALE_CAVEAT",
    "COARSE_RECALL_CAVEAT",
    "EXPLAINED_SUBSET_CAVEAT",
    "GROUPED_WEIGHT_CAVEAT",
    "PEER_REGISTER_UNTESTED_CAVEAT",
    "SCALE_BORROWED_WEIGHT_FACTOR",
    "SENTIEL_VERTICAL_CAVEATS",
    "SYNTHETIC_CORPUS_CAVEAT",
    "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT",
    "UNQUANTIFIED_WEIGHT_FACTOR",
    "ExplanationSummary",
    "SentielConfig",
    "SentielEngine",
    "annotate_with_caveats",
    "provenance_factor",
    "require_independent_judgement",
]

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------------------
# What must travel with any number this vertical produces
# ------------------------------------------------------------------------------------------------

UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT: Final = (
    "Uncalibrated hypothesis confidence: the confidences on these hypotheses are NOT calibrated "
    "probabilities and must not be surfaced to a user under Constitution §3.3. Four reasons. (1) "
    "The enterprise template priors are reasoned placeholders derived from a base-rate ordering, "
    "not measured base rates, and they are conditional on 'an entity-window on which an "
    "out-of-band departure was already raised' rather than on an entity-day. (2) EVIDENCE_STRENGTH "
    "is a placeholder too, and measuring either needs data labelling WHICH EXPLANATION IS TRUE — "
    "CERT labels insider and normal, never 'compromised account' versus 'role change'. (3) The "
    "belief update treats each behaviour event as independent, and consecutive daily windows of "
    "one persistent behaviour are plainly not, so a confidence built across them counts one cause "
    "many times. (4) The evidence WEIGHTS are calibrated; nothing downstream of them is. Sentiel "
    "may rank and reason over these hypotheses; it may not present their confidences as calibrated."
)

PEER_REGISTER_UNTESTED_CAVEAT: Final = (
    "The peer_anomaly explanation is BUILT AND WIRED BUT UNEXERCISED BY ANY REAL POSITIVE. PART 6B "
    "read CERT r3.1's own answers/scenarios.txt and found both labelled insiders written in the "
    "SELF-relative register — a user who 'did not previously' use removable drives or work after "
    "hours and begins, and a user acting 'at markedly higher rates than their previous activity'. "
    "The insider who is unremarkable against their own past and remarkable against their team's is "
    "not among r3.1's labelled examples. Every positive case peer_anomaly has anywhere in PHOS is "
    "a hand-built fixture, so this run says nothing about whether peer reasoning works."
)

SYNTHETIC_CORPUS_CAVEAT: Final = (
    "CERT is SYNTHETIC: simulated users and simulated attackers, not observed enterprise activity. "
    "A coherent, traceable narrative here demonstrates that the reasoning machinery works on real "
    "files; it does not demonstrate that Sentiel is enterprise-ready, and simulated insiders may "
    "be cleaner and more obvious than real ones."
)

COARSE_RECALL_CAVEAT: Final = (
    "Only 2 users are labelled malicious in r3.1, so window recall can take only the values 0, 0.5 "
    "and 1.0. It is not independently quotable and must not be read as a continuous rate. PART 6C "
    "changes EXPLANATION, not detection ranking, so no detection number here supersedes PART 6B's."
)

GROUPED_WEIGHT_CAVEAT: Final = (
    "Grouped weight is a maximum: a behaviour event carries its strongest member's calibrated "
    "weight, and a maximum over a set of calibrated probabilities is not itself a calibrated "
    "probability — it is biased upward by how many features the family carries. This is the same "
    "limit phos.atlas.engine records for a subsystem event, and it is deliberate: making an "
    "event's weight grow with the number of features in it would let a wider feature set inflate "
    "confidence, which is exactly what PART 6B's aggregation removed one layer down."
)

BORROWED_SCALE_CAVEAT: Final = (
    "Borrowed and unquantified departures are DISCOUNTED BY DECLARED, UNMEASURED FACTORS. A "
    "contribution whose entity-level baseline had no spread is judged against the population's, so "
    "one of the two numbers behind its magnitude did not come from this entity, and its evidence "
    "weight is multiplied by 0.5. Where no spread existed anywhere the magnitude is the clamp "
    "rather than a measurement and only the departure's existence survives, so the factor is 0.25. "
    "Both are placeholders chosen for sane ordering, in the same sense the template priors and "
    "EVIDENCE_STRENGTH are placeholders; neither is a measured discount."
)

EXPLAINED_SUBSET_CAVEAT: Final = (
    "A window's SCORE and its EXPLANATION count different things. The score sums every per-feature "
    "contribution the model emitted at emit_k; only the contributions whose value actually left "
    "its ExpectedRange may become evidence (Constitution §3.2 via phos.reasoning.boundary), so a "
    "high-scoring window can rest on far fewer pieces of evidence than it has contributions. "
    "ExplanationSummary.in_band reports how many were refused."
)

SENTIEL_VERTICAL_CAVEATS: Final = (
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    PEER_REGISTER_UNTESTED_CAVEAT,
    SYNTHETIC_CORPUS_CAVEAT,
    COARSE_RECALL_CAVEAT,
    GROUPED_WEIGHT_CAVEAT,
    BORROWED_SCALE_CAVEAT,
    EXPLAINED_SUBSET_CAVEAT,
)
"""Everything that must travel with a number this vertical produces.

The first four are PART 6C §6's non-negotiable honesty guards; the last three are limits the
mapping itself has. They are attached to the logged report rather than kept in a document, because
a document is not what a reader of ``eval_runs/log.jsonl`` has in front of them.
"""

_CAVEAT_SEPARATOR: Final = " | "


def annotate_with_caveats(report: EvaluationReport) -> EvaluationReport:
    """Return ``report`` with every caveat in `SENTIEL_VERTICAL_CAVEATS` appended to its provenance.

    Args:
        report: The report to annotate. Not modified.

    Returns:
        A copy whose ``source_note`` keeps the corpus's own provenance and then carries every
        caveat. Idempotent: annotating an already-annotated report returns it unchanged, so a
        script that annotates on the way to more than one destination cannot duplicate the text.
    """
    if all(caveat in report.source_note for caveat in SENTIEL_VERTICAL_CAVEATS):
        return report
    parts = [part for part in (report.source_note,) if part]
    return report.model_copy(
        update={"source_note": _CAVEAT_SEPARATOR.join([*parts, *SENTIEL_VERTICAL_CAVEATS])}
    )


# ------------------------------------------------------------------------------------------------
# How much a departure is worth once you know how it was measured
# ------------------------------------------------------------------------------------------------

SCALE_BORROWED_WEIGHT_FACTOR: Final = 0.5
"""What a departure judged against the population's spread is worth, against one judged on its own.

A magnitude needs two numbers: a centre and a spread. PART 6B's substitution keeps the entity's own
centre — the thing the model did learn about this person — and borrows the population's spread,
because a constant training slice supplied none. One of the two therefore describes other people,
so the evidence counts as half an observation. An unmeasured placeholder, and said to be one.
"""

UNQUANTIFIED_WEIGHT_FACTOR: Final = SCALE_BORROWED_WEIGHT_FACTOR**2
"""What a departure with no spread available anywhere is worth.

Its magnitude is `phos.models.MAX_MAGNITUDE` — the clamp — rather than a measurement, so it is
identical for every such contribution and carries no information about size. What survives is that
the value was outside everything training saw, and nothing about by how much. Halved twice, by the
same convention: each of the two numbers behind a magnitude that this entity did not supply costs
the evidence half its weight.
"""


def provenance_factor(contribution: FeatureContribution) -> float:
    """Return how much of its calibrated weight a contribution keeps, given how it was measured.

    Args:
        contribution: One feature's contribution to an entity-window's score, carrying PART 6B's
            ``scale_borrowed`` and ``unquantified`` flags.

    Returns:
        ``1.0`` for a departure measured against the entity's own learned spread,
        `SCALE_BORROWED_WEIGHT_FACTOR` for one judged against the population's, and
        `UNQUANTIFIED_WEIGHT_FACTOR` for one no spread could be found for.
    """
    if contribution.unquantified:
        return UNQUANTIFIED_WEIGHT_FACTOR
    if contribution.scale_borrowed:
        return SCALE_BORROWED_WEIGHT_FACTOR
    return 1.0


def require_independent_judgement(deviation: Deviation, contribution: FeatureContribution) -> None:
    """Raise unless re-scoring one observation reproduces the judgement the scorer made of it.

    `WindowScorer` judges a whole entity-window at once and does not hand back the `Deviation`
    behind each contribution; this vertical needs that deviation to pass the contribution through
    4A's boundary, so it re-scores the observation on its own. That is exact **only** because
    `phos.models.StaticRangeFittedModel` guarantees each observation is judged independently of the
    others — a guarantee `phos.sentiel.static_range_model` enforces by type, and this function
    verifies by value on every contribution that reaches it.

    Args:
        deviation: The deviation produced by re-scoring the observation on its own.
        contribution: The contribution the scorer produced for the same observation, whose
            ``scale_borrowed`` case is excluded because there the scorer deliberately re-judged
            against a substituted range.

    Raises:
        ValueError: If the two magnitudes disagree, which means the model's judgement depends on
            what else was scored beside it and every piece of evidence built this way would
            describe a measurement the scorer never made.
    """
    if contribution.scale_borrowed:
        return
    if deviation.magnitude != contribution.magnitude:
        raise ValueError(
            f"re-scoring {contribution.feature!r} on its own gave magnitude "
            f"{deviation.magnitude!r}, but the window scorer measured {contribution.magnitude!r}. "
            "A StaticRangeFittedModel must judge each observation independently of the others; "
            "this one does not, so the evidence built from it would not describe what was scored"
        )


# ------------------------------------------------------------------------------------------------
# Configuration and the summary of a run
# ------------------------------------------------------------------------------------------------


class SentielConfig(BaseModel):
    """How the vertical scores, which windows it explains, and how it correlates what is left.

    Attributes:
        scoring: PART 6B's aggregation policy, passed through unchanged so there is one place to
            configure it.
        reasoning: The reasoning engine's own settings. The correlation window defaults to seven
            days rather than 4B's thirty minutes because Sentiel's behavioural window is a **day**
            (PART 6·D): a window shorter than three days would split a working pattern across a
            weekend's absence, and a week is the cadence an organisation already runs on. A burst
            next month starts a fresh hypothesis at its prior, which is what stops a confidence
            being built across unrelated months.
        alert_threshold: Minimum `phos.sentiel.ScoredWindow.score` for a window to be explained.
            Zero explains everything, which is what a fixture wants; a corpus run should set it
            from an operating point on PART 6B's budget curve, because explaining every
            entity-window in a corpus explains nothing.
        features: Score only these features, or ``None`` for every feature the stream carries.

    Invariants:
        The alert threshold is non-negative, matching `ScoredWindow.score`.
    """

    model_config = ConfigDict(frozen=True)

    scoring: AggregationPolicy = AggregationPolicy()
    reasoning: ReasoningConfig = ReasoningConfig(correlation_window=timedelta(days=7))
    alert_threshold: float = Field(default=0.0, ge=0.0)
    features: frozenset[str] | None = None


class ExplanationSummary(BaseModel):
    """What one run of the vertical did, including the parts that never became evidence.

    Attributes:
        windows_scored: Entity-windows the scorer produced.
        windows_explained: Those whose score met `SentielConfig.alert_threshold`.
        contributions: Feature contributions inside the explained windows.
        in_band: Contributions refused by 4A's boundary because the value never left its expected
            range. Reported rather than dropped silently — see `EXPLAINED_SUBSET_CAVEAT`.
        unfamilied: Contributions whose feature belongs to no `BehaviourFamily`, and which
            therefore could not reach any explanation. Should be zero; a non-zero count means the
            featuriser has grown a feature `phos.sentiel.templates` has not been told about.
        promoted: Contributions that became per-feature `Evidence`.
        borrowed: Promoted contributions judged against the population's spread.
        unquantified: Promoted contributions left at the clamped maximum.
        events: Behaviour events the promoted evidence was grouped into.
        narratives: Stories the reasoning engine assembled.
    """

    model_config = ConfigDict(frozen=True)

    windows_scored: int = Field(default=0, ge=0)
    windows_explained: int = Field(default=0, ge=0)
    contributions: int = Field(default=0, ge=0)
    in_band: int = Field(default=0, ge=0)
    unfamilied: int = Field(default=0, ge=0)
    promoted: int = Field(default=0, ge=0)
    borrowed: int = Field(default=0, ge=0)
    unquantified: int = Field(default=0, ge=0)
    events: int = Field(default=0, ge=0)
    narratives: int = Field(default=0, ge=0)

    def note(self) -> str:
        """Return the one line a report carries so the unexplained part is never invisible."""
        return (
            f"SENTIEL REASONING: {self.windows_explained:,} of {self.windows_scored:,} "
            f"entity-windows explained, holding {self.contributions:,} feature contributions. "
            f"{self.in_band:,} were refused by the evidence boundary because the value never left "
            f"its expected range, {self.unfamilied:,} belonged to no behaviour family, and "
            f"{self.promoted:,} became evidence — of which {self.borrowed:,} were judged against "
            f"the population's spread and {self.unquantified:,} stayed at the clamped maximum. "
            f"Grouped into {self.events:,} behaviour event(s) and {self.narratives:,} narrative(s)."
        )


_FAMILY_PHRASE: Final[Mapping[BehaviourFamily, str]] = {
    BehaviourFamily.ACCESS: "where and when they worked",
    BehaviourFamily.DATA_HANDLING: "what they did with data",
    BehaviourFamily.RELATIONSHIP: "who and what they connect to",
    BehaviourFamily.PEER: "how they compare with their declared peers",
}
"""How each family reads in a sentence an operator sees. Total over `BehaviourFamily` on purpose."""


class _Scored(NamedTuple):
    """One scored entity-window and the observations it was scored from, by feature."""

    window: ScoredWindow
    sources: dict[str, Observation]


class _Candidate(NamedTuple):
    """One contribution on its way to becoming evidence, with everything it traces back to."""

    entity_id: EntityId
    timestamp: datetime
    family: BehaviourFamily
    contribution: FeatureContribution
    observation: Observation
    deviation: Deviation


class SentielEngine:
    """The complete enterprise engine: score, promote, group, reason, narrate.

    Not a Pydantic model, for the same reason `phos.atlas.AtlasEngine` is not: it writes into a
    store as it runs, whereas everything it produces is an immutable ontology value. Nothing it
    holds is global — construct one per store and pass it explicitly.

    Every component is injected already fitted. The engine does not split, fit or calibrate, so it
    cannot accidentally let a model see the data its own numbers are reported from; arranging that
    — a train slice for the model, a held-out calibration slice for the calibrator, and a test
    slice for the run — is the caller's job. No corpus-scale runner exists yet: `SentielEngine` is
    exercised on a real CERT slice by ``tests/sentiel/test_engine.py`` and nowhere else, so this
    PART has no published detection number of its own and PART 6B's stands unsuperseded.
    """

    def __init__(
        self,
        fitted: StaticRangeFittedModel,
        calibrator: FittedCalibrator,
        library: TemplateLibrary | None = None,
        config: SentielConfig | None = None,
        store: EvidenceStore | None = None,
    ) -> None:
        """Assemble a vertical from already-fitted parts.

        Args:
            fitted: The fitted behavioural model. `StaticRangeFittedModel` rather than any
                `FittedModel`, for the reason `phos.sentiel.static_range_model` gives: a scorer
                that silently restarted an order-dependent model's state at every window would
                produce entirely ordinary-looking numbers that mean nothing.
            calibrator: A calibrator fitted on a **held-out calibration slice**. Supplies each
                piece of evidence's weight, which Constitution §3.3 requires to be a calibrated
                probability.
            library: The explanations to reason with. Defaults to `sentiel_library`, the
                enterprise set.
            config: Scoring, threshold and reasoning settings. Defaults are used if omitted.
            store: Where the run's objects are recorded. Defaults to a fresh in-memory store; pass
                one in to accumulate several runs, or to inspect afterwards.
        """
        self._fitted = fitted
        self._calibrator = calibrator
        self._library = sentiel_library() if library is None else library
        self._config = SentielConfig() if config is None else config
        self._store: EvidenceStore = InMemoryEvidenceStore() if store is None else store
        self._explained: tuple[ScoredWindow, ...] = ()
        self._summary = ExplanationSummary()

    @property
    def name(self) -> str:
        """Identifies the vertical in reports and the experiment log.

        Carries the model and the calibrator, because both are part of what produced the numbers.
        """
        return f"sentiel-vertical:{self._fitted.name}+{self._calibrator.name}"

    @property
    def store(self) -> EvidenceStore:
        """The store holding everything this engine has produced.

        Read through it to walk the drill-down path: a narrative's evidence ids resolve to
        behaviour events, `phos.sentiel.behaviour_member_ids` gives their members, each member's
        ``source_id`` gives its `Deviation`, and that gives the `Observation` a feature was
        measured in.
        """
        return self._store

    def explained_windows(self) -> tuple[ScoredWindow, ...]:
        """Return the entity-windows the last run explained, in scoring order."""
        return self._explained

    def summary(self) -> ExplanationSummary:
        """Return what the last run did, the parts that never became evidence included."""
        return self._summary

    def run(self, dataset: Dataset) -> list[Narrative]:
        """Run the whole vertical over one corpus and return the stories it produced.

        Args:
            dataset: The corpus to explain, time-ordered. Should be a test slice neither the model
                nor the calibrator has seen.

        Returns:
            One `Narrative` per story, earliest first. Each carries its competing explanations
            ordered by confidence, the always-present "insufficient evidence" residual, and
            evidence ids that resolve — through this engine's `store` — all the way back to the
            measurements. Empty when nothing in the corpus left its expected range.

        Raises:
            ValueError: If one ``(entity, window, feature)`` is measured more than once, which
                would leave a contribution untraceable to a unique measurement; if the model's
                judgement of an observation depends on what else was scored beside it; or if the
                calibrator returns something that is not a probability.

        Note:
            Deterministic. The same corpus and the same fitted parts produce the same narratives,
            save for the identifiers and timestamps every ontology object mints for itself.
        """
        scored = self._score(dataset)
        candidates = self._promote(scored)
        events = self._group(candidates)
        narratives = self._reason(events)

        self._summary = self._summary.model_copy(
            update={"events": len(events), "narratives": len(narratives)}
        )
        logger.info(
            "%s explained %s: %s",
            self.name,
            dataset.name,
            self._summary.note(),
        )
        return narratives

    # -- the five steps -------------------------------------------------------------------------

    def _score(self, dataset: Dataset) -> list[_Scored]:
        """Aggregate the corpus into entity-windows, keeping the observations behind each.

        `WindowScorer` buffers a window's observations and drops them once it has scored them, and
        PART 6C may not change it, so this keeps a second index under the identical key. The two
        stay in step because a window is flushed strictly before the observation that completed it
        is buffered, which is the order `WindowScorer.push` already imposes.
        """
        scorer = WindowScorer(self._fitted, self._config.scoring, self._config.features)
        buffers: dict[tuple[EntityId, datetime], dict[str, Observation]] = {}
        scored: list[_Scored] = []

        def drain(windows: Sequence[ScoredWindow]) -> None:
            for window in windows:
                key = (window.entity_id, window.timestamp)
                scored.append(_Scored(window, buffers.pop(key, {})))

        for observation in dataset.observations:
            drain(scorer.push(observation))
            if (
                self._config.features is not None
                and observation.feature not in self._config.features
            ):
                continue
            sources = buffers.setdefault((observation.entity_ids[0], observation.timestamp), {})
            if observation.feature in sources:
                raise ValueError(
                    f"{observation.feature!r} is measured more than once for "
                    f"{observation.entity_ids[0]!r} at {observation.timestamp.isoformat()}. A "
                    "feature's contribution to an entity-window must trace back to exactly one "
                    "measurement, or the evidence built from it names a value nobody can find"
                )
            sources[observation.feature] = observation
        drain(scorer.close())

        explained = [item for item in scored if item.window.score >= self._config.alert_threshold]
        self._explained = tuple(item.window for item in explained)
        self._summary = ExplanationSummary(
            windows_scored=len(scored),
            windows_explained=len(explained),
            contributions=sum(len(item.window.contributions) for item in explained),
        )
        return explained

    def _promote(self, scored: Sequence[_Scored]) -> list[_Candidate]:
        """Keep the contributions 4A's boundary would admit, with the pair each traces back to."""
        candidates: list[_Candidate] = []
        in_band = 0
        unfamilied = 0
        for item in scored:
            for contribution in item.window.contributions:
                family = family_of(contribution.feature)
                if family is None:
                    unfamilied += 1
                    logger.warning(
                        "feature %r belongs to no behaviour family, so its departure on %s cannot "
                        "reach any explanation",
                        contribution.feature,
                        item.window.entity_id,
                    )
                    continue
                observation = item.sources[contribution.feature]
                deviation = self._deviation_for(contribution, observation)
                if not is_out_of_band(deviation, observation):
                    in_band += 1
                    continue
                candidates.append(
                    _Candidate(
                        entity_id=item.window.entity_id,
                        timestamp=item.window.timestamp,
                        family=family,
                        contribution=contribution,
                        observation=observation,
                        deviation=deviation,
                    )
                )
        self._summary = self._summary.model_copy(
            update={"in_band": in_band, "unfamilied": unfamilied}
        )
        return candidates

    def _deviation_for(
        self, contribution: FeatureContribution, observation: Observation
    ) -> Deviation:
        """Return the deviation that judged this contribution, substituted scale included.

        For a borrowed contribution the range the scorer actually judged against is rebuilt with
        PART 6B's own `borrowed_scale_range`, so the stored deviation carries the band the
        magnitude was measured in rather than the degenerate one the entity's baseline offered.
        Testing out-of-band against the degenerate range would call every departure from a constant
        baseline a departure from normal, which is the clamp PART 6B removed, reintroduced.
        """
        judged = self._fitted.score([observation])[0]
        require_independent_judgement(judged, contribution)
        if not contribution.scale_borrowed:
            return judged
        population = self._fitted.feature_ranges[observation.feature]
        return Deviation(
            observation_id=observation.id,
            expected=borrowed_scale_range(judged.expected, population),
            magnitude=contribution.magnitude,
            timestamp=judged.timestamp,
        )

    def _group(self, candidates: Sequence[_Candidate]) -> list[Evidence]:
        """Promote each candidate, then collapse them into one behaviour event per family."""
        weights = calibrated_probabilities(
            self._calibrator, [candidate.contribution.magnitude for candidate in candidates]
        )
        grouped: dict[tuple[EntityId, datetime, BehaviourFamily], list[_Candidate]] = {}
        members: dict[tuple[EntityId, datetime, BehaviourFamily], list[Evidence]] = {}
        borrowed = 0
        unquantified = 0

        for candidate, calibrated in zip(candidates, weights, strict=True):
            weight = calibrated * provenance_factor(candidate.contribution)
            evidence = evidence_from_deviation(
                candidate.deviation,
                candidate.observation,
                weight,
                summary=_summarise_contribution(candidate),
            )
            if self._store.get_observation(candidate.observation.id) is None:
                self._store.add_observation(candidate.observation)
            self._store.add_deviation(candidate.deviation)
            self._store.add_evidence(evidence)

            borrowed += int(candidate.contribution.scale_borrowed)
            unquantified += int(candidate.contribution.unquantified)
            key = (candidate.entity_id, candidate.timestamp, candidate.family)
            grouped.setdefault(key, []).append(candidate)
            members.setdefault(key, []).append(evidence)

        events = [
            _behaviour_event(key, grouped[key], members[key]) for key in sorted(grouped, key=_order)
        ]
        for event in events:
            self._store.add_evidence(event)

        self._summary = self._summary.model_copy(
            update={
                "promoted": len(candidates),
                "borrowed": borrowed,
                "unquantified": unquantified,
            }
        )
        return events

    def _reason(self, events: Sequence[Evidence]) -> list[Narrative]:
        """Reason once **per entity**, and give every story the whole competing set.

        Two departures from `phos.atlas.engine`, and both follow from what an enterprise corpus is
        rather than from taste.

        **One reasoning pass per person.** `ReasoningEngine` identifies an accumulating hypothesis
        by ``(domain, template_id)`` and nothing else, which is right for Atlas — its evidence is
        all about one plant, so one story per window is the answer. Sentiel's evidence is about a
        thousand *different people*, and a single pass would put them in one hypothesis: two
        unrelated colleagues who each departed in access would accumulate into the same
        ``compromised_account``, and `ReasoningEngine.narratives` would then merge their stories,
        because it treats sharing a hypothesis as evidence of belonging to one incident. The
        confidence an operator read for one person would have been built partly from another
        person's behaviour, which is both wrong and untraceable. Reasoning per entity gives each
        person their own hypotheses and their own story, and costs nothing else: the belief update
        is additive in log-odds, so nothing about a single person's arithmetic changes.

        **Every story reports every explanation, including the untouched ones.** A template spawns
        a hypothesis only when evidence matches it, so a story assembled from matched templates
        alone silently drops the explanations that were considered and not supported — and a
        competing set with the unsupported explanations removed is a verdict, which Constitution §3
        and this engine's whole purpose refuse. Each narrative is therefore completed with a fresh
        `phos.reasoning.HypothesisTemplate.instantiate` for every registered template no evidence
        touched. Those sit at their prior, hold no evidence, and are ranked with the rest, so
        "considered, and nothing here bears on it" is visible rather than absent.

        Args:
            events: The behaviour events to explain, in the order `_group` produced them.

        Returns:
            One `Narrative` per story, ordered by their earliest evidence and then by entity, so
            the sequence is a function of the evidence rather than of dictionary iteration.
        """
        by_entity: dict[EntityId, list[Evidence]] = {}
        for event in events:
            by_entity.setdefault(event.entity_ids[0], []).append(event)

        held = {event.id: event for event in events}
        ordered: list[tuple[datetime, EntityId, Narrative]] = []
        for entity_id in sorted(by_entity):
            reasoning = ReasoningEngine(self._library, self._store, self._config.reasoning)
            reasoning.ingest(by_entity[entity_id])
            for hypothesis in reasoning.hypotheses():
                self._store.add_hypothesis(hypothesis)
            for narrative in reasoning.narratives():
                completed = self._completed(narrative)
                earliest = min(
                    held[evidence_id].timestamp for evidence_id in completed.evidence_ids
                )
                ordered.append((earliest, entity_id, completed))

        ordered.sort(key=lambda item: (item[0], item[1]))
        narratives = [narrative for _, _, narrative in ordered]
        for narrative in narratives:
            self._store.add_narrative(narrative)
        return narratives

    def _completed(self, narrative: Narrative) -> Narrative:
        """Return ``narrative`` with the explanations no evidence touched added and all re-ranked.

        The untouched hypotheses are minted here rather than reused across stories, because two
        incidents explained by the same template are two hypotheses — `instantiate`'s own rule —
        and sharing one would let a story cite an explanation whose identity belongs to another.

        Ranking is `phos.reasoning.belief.rank_hypotheses` (ADR 0036): a ceiling or epsilon tie
        among contentful explanations raises `insufficient_evidence` rather than crowning a
        unique leader by `template_id` alphabet. ``overall_confidence`` is left unset.
        """
        reasoned = [self._hypothesis(hypothesis_id) for hypothesis_id in narrative.hypothesis_ids]
        explained = {hypothesis.template_id for hypothesis in reasoned}
        untouched = [
            template.instantiate()
            for template in self._library.for_domain(narrative.domain)
            if template.template_id not in explained
        ]
        for hypothesis in untouched:
            self._store.add_hypothesis(hypothesis)

        ranked = rank_hypotheses([*reasoned, *untouched])
        leading = ranked[0]
        return narrative.model_copy(
            update={
                "title": f"{leading.label} ({len(narrative.evidence_ids)} pieces of evidence)",
                "hypothesis_ids": [hypothesis.id for hypothesis in ranked],
                "overall_confidence": None,
            }
        )

    def _hypothesis(self, hypothesis_id: str) -> Hypothesis:
        """Return a hypothesis this engine just stored, or fail loudly rather than guess."""
        hypothesis = self._store.get_hypothesis(hypothesis_id)
        if hypothesis is None:  # pragma: no cover - the store was written a line earlier
            raise ValueError(
                f"hypothesis {hypothesis_id!r} is cited by a narrative this engine just built but "
                "is not in the store. A story whose explanations cannot be resolved is a "
                "traceability failure, not an empty list"
            )
        return hypothesis


def _order(key: tuple[EntityId, datetime, BehaviourFamily]) -> tuple[datetime, str, str]:
    """Order behaviour events by time, then entity, then family.

    Ingestion order decides which hypotheses spawn — though not, because the belief update is
    additive in log-odds, where their confidences end up — so it must be a function of the evidence
    rather than of dictionary iteration.
    """
    return key[1], key[0], key[2].value


def _behaviour_event(
    key: tuple[EntityId, datetime, BehaviourFamily],
    candidates: Sequence[_Candidate],
    members: Sequence[Evidence],
) -> Evidence:
    """Return one entity-window's evidence for one behaviour family, collapsed into one fact.

    The event's ``weight`` is its strongest member's, mirroring `phos.atlas.grouping` — see
    `GROUPED_WEIGHT_CAVEAT` for what a maximum over calibrated probabilities is and is not, and
    why a sum would be the wrong choice here even though the *score* underneath is one.
    """
    entity_id, timestamp, family = key
    leading = candidates[0]
    borrowed = sum(candidate.contribution.scale_borrowed for candidate in candidates)
    unquantified = sum(candidate.contribution.unquantified for candidate in candidates)
    provenance = ""
    if borrowed or unquantified:
        provenance = (
            f"; {borrowed} judged against the population's spread and {unquantified} left "
            "unmeasurable"
        )
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=behaviour_event_source_id(family, [member.id for member in members]),
        entity_ids=[entity_id],
        timestamp=timestamp,
        domain=Domain.SENTIEL,
        weight=max(member.weight for member in members),
        summary=(
            f"{user_id_of(entity_id)}: {_FAMILY_PHRASE[family]} departed on "
            f"{timestamp.date().isoformat()} across {len(candidates)} feature(s), led by "
            f"{leading.contribution.feature} at {leading.contribution.magnitude:.2f} spreads "
            f"out{provenance}"
        ),
    )


def _summarise_contribution(candidate: _Candidate) -> str:
    """Render one feature's departure as a sentence an operator can act on.

    States what this person's own learned normal was, what they actually did, and how far outside
    that is — and, when the scale was not their own, says so rather than presenting a borrowed
    measurement as a measured one.
    """
    expected = candidate.deviation.expected
    note = ""
    if candidate.contribution.unquantified:
        note = " — outside everything training saw, by an amount no spread anywhere could measure"
    elif candidate.contribution.scale_borrowed:
        note = (
            " — judged against the population's spread, which this person's own baseline did not "
            "supply"
        )
    return (
        f"{candidate.observation.feature} read {candidate.observation.value:.6g}; this person's "
        f"learned normal is {expected.mean:.6g} (usual range {expected.low:.6g} to "
        f"{expected.high:.6g}), {candidate.contribution.magnitude:.2f} spreads out{note}"
    )
