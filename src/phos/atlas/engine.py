"""The Atlas vertical: industrial readings in, competing explanations out.

Everything Atlas needed has existed for two PARTs without being joined up. This module is the join,
and it is deliberately thin — it owns no detection logic, no belief arithmetic and no explanations
of its own. Its whole job is to put five existing pieces in the one order that makes them mean
something:

1. **Score** the corpus with a fitted joint model (5A). Out comes a scored candidate per
   ``(instant, signal)`` whose reading strayed from what the rest of the plant implied.
2. **Promote** only the candidates that genuinely left their expected range, through 4A's evidence
   boundary, weighting each with a calibrated probability. This is the only route into reasoning.
3. **Group** the surviving evidence by physical unit and time window (5B's map, this PART's
   `phos.atlas.grouping`). Ten instruments on one pump become one thing to investigate.
4. **Reason** over the subsystem events with the OT template library (4B, this PART's
   `phos.atlas.templates`), holding every explanation the evidence bears on at once.
5. **Narrate** — return the stories, each carrying its rivals, the always-present "insufficient
   evidence" residual, and a path back to every measurement underneath.

**Grouping comes before reasoning, and the order is the point.** Reasoning after grouping counts a
pump event once; reasoning before it would count the same event once per instrument, and every
confidence downstream would be inflated by the size of the instrumentation rather than by anything
that happened in the plant.

**PART P3 adds a second inlet, and it is deliberately narrow.** `run` accepts a `CommandEvidence`
bundle produced by `phos.atlas.command_evidence` — command-behaviour departures and command-graph
changes that have already come through 4A's boundary from a *capture* rather than from this
corpus. The engine stores each bundle's whole traceability chain and interleaves its evidence with
the subsystem events by time, so one reasoning pass sees both and a structural change can land in
the same story as the readings around it.

Command evidence is **not** grouped, and the omission is the honest one rather than an oversight:
5B's `SubsystemMap` partitions a plant's *signals* and says nothing about devices on a network, and
deriving a device grouping from co-movement is precisely the circularity `phos.atlas.topology`
refuses. `UNGROUPED_COMMAND_EVIDENCE_CAVEAT` states what that leaves.

**The stale-cell invariant is checked here, not assumed.** 5A's vectoriser may carry a reading
forward to reconstruct the rest of the plant, and 5A's `_emit` already refuses to raise a
`Deviation` about a carried cell. This module verifies rather than trusts: a deviation whose
observation is at a different instant, or names a different signal, is refused outright. Cheap, and
it turns the invariant into something that fails loudly if a future model loses it.

**Two things this vertical produces must never be read as more than they are** — see
`ATLAS_VERTICAL_CAVEATS`, which `annotate_with_caveats` writes onto every report the vertical logs.
The grouping reduction on HAI is inflated by the coarseness of HAI's declared topology, and the
hypothesis confidences are not calibrated probabilities and may not be surfaced under Constitution
§3.3. Both travel with the numbers rather than living only in a document.

Not here, and deliberately: predictive behaviour and `ForecastMiss` evidence, behaviour-graph
relationship edges, and any calibration of hypothesis confidence — the last of which needs data
that labels *which explanation was true*, which no corpus PHOS uses carries.
"""

import logging
from collections.abc import Sequence
from datetime import timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from phos.atlas.command_evidence import CommandEvidence
from phos.atlas.grouping import group_evidence
from phos.atlas.templates import atlas_library
from phos.atlas.topology import SubsystemMap
from phos.atlas.work_orders import WorkOrderEvidence
from phos.eval import Dataset, EvaluationReport
from phos.models import FittedModel
from phos.ontology import (
    Deviation,
    Evidence,
    EvidenceStore,
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
)

__all__ = [
    "ATLAS_VERTICAL_CAVEATS",
    "COARSE_MAP_CAVEAT",
    "CO_OCCURRING_FAULT_MASKING_CAVEAT",
    "GROUPED_WEIGHT_CAVEAT",
    "SATURATED_FP_LOAD_CAVEAT",
    "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT",
    "AtlasConfig",
    "AtlasEngine",
    "annotate_with_caveats",
]

logger = logging.getLogger(__name__)

COARSE_MAP_CAVEAT: Final = (
    "Coarse-map inflation: HAI's declared topology could not be partitioned below process level "
    "for P1 and P2, so unrelated departures anywhere on one process collapse into a single "
    "subsystem event. A large reduction here is evidence that grouping is correctly IMPLEMENTED, "
    "not that it is correctly RESOLVED. A finer map would lower the headline number and raise its "
    "meaning."
)

UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT: Final = (
    "Uncalibrated hypothesis confidence: the confidences on these hypotheses are NOT calibrated "
    "probabilities and must not be surfaced to a user under Constitution §3.3. Three reasons, and "
    "the third is measured rather than asserted. (1) The template priors are reasoned "
    "placeholders, not measured base rates. (2) EVIDENCE_STRENGTH is a placeholder too, and "
    "measuring either needs data labelling WHICH EXPLANATION IS TRUE, which no corpus PHOS uses "
    "carries — HAI labels attack and normal. (3) The belief update treats each subsystem event as "
    "independent, and on a "
    "plant they are plainly not: one disturbance persisting across consecutive windows arrives as "
    "many near-identical events, so a confidence built from them counts one cause many times. "
    "Atlas may rank and reason over these hypotheses; it may not present their confidences as "
    "calibrated. Evidence weights, separately, are calibrated."
)

CO_OCCURRING_FAULT_MASKING_CAVEAT: Final = (
    "Co-occurring-fault masking: a coarse group can hide a second, unrelated event inside one "
    "subsystem event. Two independent faults on one process are indistinguishable from one, and an "
    "attack co-occurring with a fault is reported as a single thing to investigate. That is a "
    "recall risk carried by the grouping, not a win."
)

GROUPED_WEIGHT_CAVEAT: Final = (
    "Grouped weight is a maximum: a subsystem event carries the strongest member's calibrated "
    "weight, and a maximum over a set of calibrated probabilities is not itself a calibrated "
    "probability — it is biased upward by how many signals the unit carries. The calibration error "
    "reported for subsystem events may therefore come out better or worse than the per-signal one "
    "for reasons that have nothing to do with the calibrator, and is not a reading of it."
)

SATURATED_FP_LOAD_CAVEAT: Final = (
    "Saturated false-positive load: when a declared SaturationPolicy fires, the row is "
    "REFUSED as a detection claim even if recall looks excellent. Metrics stay on the "
    "report; they must not be quoted as detection. Public distillation 18.72 and Data4Cyber "
    "Track A keep their log names and stay MEASURED unless a caller applies a policy. "
    "Do not raise dwell_samples to chase a quieter public ZIP."
)

ATLAS_VERTICAL_CAVEATS: Final = (
    COARSE_MAP_CAVEAT,
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    CO_OCCURRING_FAULT_MASKING_CAVEAT,
    GROUPED_WEIGHT_CAVEAT,
    SATURATED_FP_LOAD_CAVEAT,
)
"""Everything that must travel with a number this vertical produces.

The first two are PART 5C's non-negotiable honesty guards; the third and fourth are limits the
measurement itself has. They are attached to the logged report rather than kept in a document,
because a document is not what a reader of ``eval_runs/log.jsonl`` has in front of them.
"""

_CAVEAT_SEPARATOR: Final = " | "


def annotate_with_caveats(report: EvaluationReport) -> EvaluationReport:
    """Return ``report`` with every caveat in `ATLAS_VERTICAL_CAVEATS` appended to its provenance.

    Args:
        report: The report to annotate. Not modified.

    Returns:
        A copy whose ``source_note`` keeps the corpus's own provenance and then carries every
        caveat. Idempotent: annotating an already-annotated report returns it unchanged, so a
        script that annotates on the way to more than one destination cannot duplicate the text.
    """
    if all(caveat in report.source_note for caveat in ATLAS_VERTICAL_CAVEATS):
        return report
    parts = [part for part in (report.source_note,) if part]
    return report.model_copy(
        update={"source_note": _CAVEAT_SEPARATOR.join([*parts, *ATLAS_VERTICAL_CAVEATS])}
    )


class AtlasConfig(BaseModel):
    """How the vertical collapses evidence and how it correlates what is left.

    Attributes:
        grouping_window: Width of the tumbling window that decides which of a unit's departures
            belong to one subsystem event. Distinct from the reasoning correlation window and
            much shorter: this one asks "is this the same moment on this machine?", where the
            other asks "is this the same incident?".
        reasoning: The reasoning engine's own settings — correlation window, pruning threshold,
            seed — passed through unchanged so there is one place to configure them.

    Invariants:
        The grouping window is a positive duration.
    """

    model_config = ConfigDict(frozen=True)

    grouping_window: timedelta = timedelta(minutes=1)
    reasoning: ReasoningConfig = ReasoningConfig()

    @model_validator(mode="after")
    def _check_window_is_positive(self) -> Self:
        if self.grouping_window <= timedelta(0):
            raise ValueError(
                f"grouping_window must be a positive duration, got {self.grouping_window}: a zero "
                "or negative window would put every departure in its own event and collapse "
                "nothing"
            )
        return self


class AtlasEngine:
    """The complete industrial engine: score, promote, group, reason, narrate.

    Not a Pydantic model, for the same reason `ReasoningEngine` is not: it writes into a store as
    it runs, whereas everything it produces is an immutable ontology value. Nothing it holds is
    global — construct one per store and pass it explicitly.

    Every component is injected already fitted. The engine does not split, fit or calibrate, so it
    cannot accidentally let a model see the data its own numbers are reported from; arranging that
    is the caller's job, and `scripts/evaluate_atlas_vertical.py` is where it is arranged.
    """

    def __init__(
        self,
        fitted: FittedModel,
        calibrator: FittedCalibrator,
        subsystem_map: SubsystemMap,
        library: TemplateLibrary | None = None,
        config: AtlasConfig | None = None,
        store: EvidenceStore | None = None,
    ) -> None:
        """Assemble a vertical from already-fitted parts.

        Args:
            fitted: The fitted behavioural model. `MahalanobisModel` is the 5A winner on HAI and
                what the evaluation script uses; any `FittedModel` works, because the engine only
                ever asks it to score.
            calibrator: A calibrator fitted on a **held-out calibration slice**. Supplies each
                piece of evidence's weight, which Constitution §3.3 requires to be a calibrated
                probability.
            subsystem_map: 5B's declared partition. The sole source of physical-unit membership.
            library: The explanations to reason with. Defaults to `atlas_library`, the OT set.
            config: Grouping window and reasoning settings. Defaults are used if omitted.
            store: Where the run's objects are recorded. Defaults to a fresh in-memory store; pass
                one in to accumulate several runs, or to inspect afterwards.
        """
        self._fitted = fitted
        self._calibrator = calibrator
        self._map = subsystem_map
        self._library = atlas_library() if library is None else library
        self._config = AtlasConfig() if config is None else config
        self._store: EvidenceStore = InMemoryEvidenceStore() if store is None else store

    @property
    def name(self) -> str:
        """Identifies the vertical in reports and the experiment log.

        Carries the model and the calibrator, because both are part of what produced the numbers.
        """
        return f"atlas-vertical:{self._fitted.name}+{self._calibrator.name}"

    @property
    def store(self) -> EvidenceStore:
        """The store holding everything this engine has produced.

        Read through it to walk the drill-down path: a narrative's evidence ids resolve to
        subsystem events, `phos.atlas.member_evidence_ids` gives their members, each member's
        ``source_id`` gives its `Deviation`, and that gives the `Observation`.
        """
        return self._store

    def run(
        self,
        dataset: Dataset,
        commands: CommandEvidence | None = None,
        work_orders: WorkOrderEvidence | None = None,
    ) -> list[Narrative]:
        """Run the whole vertical over one corpus and return the stories it produced.

        Args:
            dataset: The corpus to explain. Should be a test slice the model and the calibrator
                have not seen.
            commands: Evidence read from a capture of the same period, already promoted by
                `phos.atlas.command_evidence`. Omitted — or empty — the run is exactly the
                sensor-only one, which is what a corpus with no capture beside it must get.
            work_orders: Optional sanctioned-change facts (Session E3). Omitted or empty, the
                run is byte-identical to the commands-off path for this inlet.

        Returns:
            One `Narrative` per story, earliest first. Each carries its competing explanations
            ordered by confidence, the always-present "insufficient evidence" residual, and
            evidence ids that resolve — through this engine's `store` — all the way back to the
            measurements. Empty when nothing in the corpus left its expected range.

        Raises:
            ValueError: If the model emits a deviation for an observation the corpus does not
                hold; if a deviation does not describe a fresh measurement at its own instant; or
                if the calibrator returns something that is not a probability.
            TopologyError: If a signal is outside the corpus the subsystem map was built against.

        Note:
            Deterministic. The same corpus and the same fitted parts produce the same narratives,
            save for the identifiers and timestamps every ontology object mints for itself.
        """
        promoted = self._promote(dataset)
        for deviation, observation, evidence in promoted:
            if self._store.get_observation(observation.id) is None:
                self._store.add_observation(observation)
            self._store.add_deviation(deviation)
            self._store.add_evidence(evidence)

        events = group_evidence(
            [evidence for _, _, evidence in promoted],
            self._map,
            self._config.grouping_window,
            {deviation.id: deviation for deviation, _, _ in promoted},
        )
        for event in events:
            self._store.add_evidence(event)

        from_commands = self._record(commands)
        from_work_orders = self._record_work_orders(work_orders)
        extra = (*from_commands, *from_work_orders)

        reasoning = ReasoningEngine(self._library, self._store, self._config.reasoning)
        reasoning.ingest(_interleaved(events, extra))
        for hypothesis in reasoning.hypotheses():
            self._store.add_hypothesis(hypothesis)

        narratives = reasoning.narratives()
        for narrative in narratives:
            self._store.add_narrative(narrative)

        logger.info(
            "%s explained %s: %d observation(s) -> %d piece(s) of evidence -> %d subsystem "
            "event(s) + %d from commands + %d from work orders -> %d narrative(s)",
            self.name,
            dataset.name,
            len(dataset.observations),
            len(promoted),
            len(events),
            len(from_commands),
            len(from_work_orders),
            len(narratives),
        )
        return narratives

    def _record(self, commands: CommandEvidence | None) -> tuple[Evidence, ...]:
        """Store a command bundle's whole traceability chain and return its evidence.

        The measurements go in as ordinary `Observation`s — a command feature and a graph finding
        both are one — so that every ``source_id`` this bundle carries resolves inside the same
        store an operator drills through (Constitution §3.2).

        **Recording is idempotent, and it has to be here in a way the sensor path does not.**
        `_promote` mints fresh `Evidence` on every run, so re-running one corpus against one store
        can never collide. A bundle is built once by the caller and carries the identity it was
        built with, so without the checks below a store could accumulate one run and no more — and
        scoring a capture in overlapping slices, which is the obvious way to use a long one, would
        abort partway through with half its evidence already written.
        """
        if commands is None:
            return ()
        for departure in commands.departures:
            if self._store.get_observation(departure.observation.id) is None:
                self._store.add_observation(departure.observation)
            if self._store.get_deviation(departure.deviation.id) is None:
                self._store.add_deviation(departure.deviation)
        for change in commands.changes:
            if self._store.get_observation(change.finding.id) is None:
                self._store.add_observation(change.finding)

        evidence = commands.evidence()
        for item in evidence:
            if self._store.get_evidence(item.id) is None:
                self._store.add_evidence(item)
        return evidence

    def _record_work_orders(self, work_orders: WorkOrderEvidence | None) -> tuple[Evidence, ...]:
        """Store sanctioned-change facts. Empty or omitted is a no-op (Session E3)."""
        if work_orders is None:
            return ()
        for fact in work_orders.facts:
            if self._store.get_observation(fact.observation.id) is None:
                self._store.add_observation(fact.observation)
        evidence = work_orders.evidence()
        for item in evidence:
            if self._store.get_evidence(item.id) is None:
                self._store.add_evidence(item)
        return evidence

    def _promote(self, dataset: Dataset) -> list[tuple[Deviation, Observation, Evidence]]:
        """Score the corpus and promote the genuine departures into calibrated `Evidence`."""
        by_id = {observation.id: observation for observation in dataset.observations}

        departures: list[tuple[Deviation, Observation]] = []
        for deviation in self._fitted.score(dataset.observations):
            observation = by_id.get(deviation.observation_id)
            if observation is None:
                raise ValueError(
                    f"{self.name} scored {dataset.name} and produced a deviation for unknown "
                    f"observation {deviation.observation_id!r}, which cannot be traced back to a "
                    "measurement"
                )
            _require_fresh_measurement(deviation, observation)
            if is_out_of_band(deviation, observation):
                departures.append((deviation, observation))

        weights = calibrated_probabilities(
            self._calibrator, [deviation.magnitude for deviation, _ in departures]
        )
        return [
            (
                deviation,
                observation,
                evidence_from_deviation(
                    deviation, observation, weight, summary=_summarise(deviation, observation)
                ),
            )
            for (deviation, observation), weight in zip(departures, weights, strict=True)
        ]


def _interleaved(events: Sequence[Evidence], from_commands: Sequence[Evidence]) -> list[Evidence]:
    """Return one stream of evidence in time order, or the events untouched when there are none.

    Ingestion order decides which hypotheses spawn (though not, because the belief update is
    additive in log-odds, where their confidences end up), so a run with a capture beside it must
    weigh a structural change at the moment it happened rather than after every reading. The
    early return is not an optimisation: it keeps a sensor-only run byte-identical to what it was
    before P3, so nothing already measured has quietly changed.
    """
    if not from_commands:
        return list(events)
    return sorted(
        [*events, *from_commands], key=lambda item: (item.timestamp, item.kind.value, item.summary)
    )


def _require_fresh_measurement(deviation: Deviation, observation: Observation) -> None:
    """Raise unless ``deviation`` describes a reading actually taken at its own instant.

    5A's vectoriser may carry a signal's last reading forward so the rest of the plant can still be
    reconstructed, and nothing may raise a `Deviation` about such a cell: there is no measurement at
    that instant for the deviation to point back to, so an operator following the trail would
    arrive at a different moment or a different signal (Constitution §3.2).

    5A's emitter already upholds this. Checking it here rather than assuming it means a future
    model that loses the invariant fails loudly at the seam instead of quietly producing evidence
    about a value nobody measured.

    Raises:
        ValueError: If the paired observation is at another instant or names another signal.
    """
    if (
        observation.timestamp == deviation.timestamp
        and observation.feature == deviation.expected.feature
    ):
        return
    raise ValueError(
        f"deviation {deviation.id!r} does not describe a fresh measurement: it reports "
        f"{deviation.expected.feature!r} at {deviation.timestamp.isoformat()}, but observation "
        f"{observation.id!r} is {observation.feature!r} at "
        f"{observation.timestamp.isoformat()}. A carried-forward reading may inform a "
        "reconstruction; it may never raise a deviation about itself"
    )


def _summarise(deviation: Deviation, observation: Observation) -> str:
    """Render one departure as a sentence an operator can act on.

    States what the rest of the plant implied the signal should have read, what it actually read,
    and how far outside that is — which is the whole reason 5A attributes a joint anomaly back to a
    single signal instead of reporting that something, somewhere, is wrong.
    """
    expected = deviation.expected
    return (
        f"{observation.feature} read {observation.value:.6g}; the rest of the plant implied "
        f"{expected.mean:.6g} (normal {expected.low:.6g} to {expected.high:.6g}), "
        f"{deviation.magnitude:.2f} spreads out"
    )
