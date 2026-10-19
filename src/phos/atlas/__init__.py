"""Atlas: the industrial engine, complete. 5A models the plant, 5B maps it, 5C explains it.

Import everything public from here — ``from phos.atlas import PcaResidualModel`` — rather than
from the submodules, so internal layout can change without breaking callers.

**The claim this package exists to make.** An industrial environment is not a collection of
independent signals; it is one machine. A pump's flow moves with a valve's position, a tank's
level with its inflow and outflow. Normal operation therefore lives on a low-dimensional manifold
of correlated behaviour, and the right question about a reading is not "is this signal high?" but
"does this reading still fit the plant?".

**The evidence that the distinction is not cosmetic.** PART 3's per-signal Gaussian, one
independent baseline per signal, posts roughly 8,390 false positives per normal hour on HAI's
79-signal corpus. That is not a tuning failure. Modelling 79 signals as 79 strangers means normal,
correlated movement on any one of them looks anomalous in isolation, and across dozens of signals
the false alarms compound. `scripts/evaluate_atlas.py` measures what modelling the joint structure
does to that number.

What 5A ships:

- **`vectorise`** — the one place ontology observations become a ``(time x signal)`` matrix, with
  an explicit missing-data policy that carries a stale reading or drops the timestamp, and never
  fabricates a zero.
- **`PcaResidualModel`** — the primary model. Learns the correlation structure of normal, then
  scores a reading by how badly it reconstructs from that structure. An excursion *along* normal
  correlations reconstructs well and is not flagged; one that *breaks* them does not and is.
- **`MahalanobisModel`** — the covariance-based alternative, which judges each signal against
  what every other signal implies it should be. It catches a combination of individually
  unremarkable values that is jointly impossible.
- **`stability`** — the plant-health metrics Atlas's dashboards will later report, built only from
  what process telemetry can actually support.

**Both models keep explainability (Constitution §3.2).** A joint model could easily degrade into
"something, somewhere, is wrong". These do not: an anomaly is attributed back to the specific
signal whose reading broke the structure, and the `Deviation` carries a *dynamic* `ExpectedRange`
— the value the rest of the plant implied that signal should have had, plus or minus its learned
band. "Given everything else, this should have read 42.1 +/- 0.4; it read 61.8" is a sentence an
operator can act on.

**They are ordinary `BehaviouralModel`s.** The joint work happens inside `fit` and `score`; the
interface is PART 3's, unchanged, so `ModelDetector`, `CalibratedModelDetector` and the PART 2
harness measure them without knowing anything has changed.

**What 5B adds, and why it is not a model.** Attributing an anomaly to the breaking signal is the
right unit for *explaining* it and the wrong unit for *counting* it: ten instruments on one pump
depart together, and Atlas emits ten deviations for one event. `topology` holds the fact that
collapses them — which signals share a physical unit — as a **declared** claim about plumbing,
sourced to process documentation and never derived from co-movement in the data, because deriving
it that way would answer "did these share a cause?" with the very statistics that raised the
deviations. `SubsystemMap` enforces that membership is a total partition of the corpus's signals at
construction.

**What 5C adds: the vertical, and the two things it must never let a reader assume.**

- **`grouping`** — spends 5B's map. Evidence sharing a ``(subsystem, time window)`` collapses into
  one **subsystem event** that names its unit, lists the signals that departed, carries the
  strongest member's calibrated weight, and keeps the ids of every member so an operator can
  expand it again. Nothing is discarded: it is a counting change and the tests assert the count and
  the coverage separately.
- **`templates`** — five curated OT explanations and no mechanism for a sixth. Their priors are
  *computed* from two anchors that already exist in PHOS — the reasoning engine's pruning threshold
  and the size of one piece of fully-trusted evidence — so the base-rate ordering (equipment fault ≫
  maintenance ≈ upset ≫ attack) is a derivation rather than a preference, and no explanation starts
  ahead of "we do not know".
- **`engine`** — `AtlasEngine.run`: score, promote through 4A's boundary, group, reason, narrate.
  Grouping deliberately precedes reasoning, because a confidence built before the collapse would
  count one plant event once per instrument.

**Measured on HAI: 5,123 per-signal alerts become 424 subsystem events — 12.1x fewer things to
investigate — with both attack windows still covered.** That is a *counting* result, and
`ATLAS_VERTICAL_CAVEATS` travels with it into the experiment log precisely so it is not read as a
detection result. Two of those caveats are mandatory: HAI's topology is coarse, so the reduction
says grouping is correctly implemented rather than correctly resolved; and **a hypothesis confidence
is not a calibrated probability and must not be surfaced** (Constitution §3.3) — the priors and
`EVIDENCE_STRENGTH` are unmeasured, and the belief update treats persisting events as independent
when they are not.

**What P1 adds, and why it is a subpackage rather than a model.** Everything above reads the
plant's sensor *values*. `phos.atlas.packet` reads its *commands* — the control traffic between
engineering stations, PLCs and SCADA servers — because a tank level leaving its expected range says
something is wrong, and only the command stream can begin to separate an operator who opened a
valve from an attacker who did. `dissect_capture` turns a ``.pcap`` into typed, traceable
`IcsMessage`s, hardened against hostile input on the principle that a parser inside a security
product is itself an attack surface.

**What P2 adds: the commands become behaviour.** A single command is not normal or abnormal — only
a device's commanding *over time* is. `featurise_commands` turns the message stream into ordinary
`Observation`s per device per window (volume, function mix, write targets and values, read/write
balance, polling rhythm), so the models above consume command behaviour through the path they
already use for telemetry, unchanged. `learn_device_command_graph` and `compare_to_graph` add the
structure between devices: who commands whom, and the three departures from that — a relationship
never seen, a learned one gone silent, an unfamiliar function on a known link. Every value traces
through a `FrameSource` back to specific frames in a specific file, and `COMMAND_BASELINE_CAVEATS`
must travel with any number computed from it, because a command baseline describes the capture it
was learned from rather than the plant.

**What P3 adds: the commands become evidence, and one explanation stops being unanswerable.**
`command_evidence` routes both P2 streams through the evidence boundary — behaviour through
`evidence_from_deviation`, structural change through 4A's new sibling door — so command evidence
arrives at the reasoning engine as the same `Evidence` a sensor departure does, with the same
calibrated weight and a chain that walks back to a frame range in a capture file.
`AtlasEngine.run` takes that bundle beside a corpus and interleaves it with the subsystem events.

The point of all of it is one asymmetry. 5C recorded that `unauthorised_control_activity` and
`process_disturbance` weighed evidence *identically* and were told apart only by their priors,
because process telemetry carries no control context. A change in the command graph separates them,
and the claim is physical rather than tuned: **a real process upset moves readings, and it does not
make a workstation begin commanding a PLC.** The same fact gives `engineering_maintenance` its first
real matcher. An *untyped* new relationship still supports maintenance and an attacker equally,
because a commissioning engineer and an intruder can leave the same link. A *marked unknown master*
does not: a device that has never commanded this target beginning to write is not how plant
engineers work, so that finding supports the attack explanation and contradicts maintenance.

**And the number that would justify the whole adapter does not exist.** Atlas's claim is that
reading commands separates a legitimate operator action from an attacker's identical one.
Demonstrating that needs a capture containing such an attack, labelled, and PHOS has none.
`command_eval` is the complete measurement path — a capture adapter, two detectors, the harness —
and `scripts/evaluate_command_detection.py` refuses to print a metric, naming exactly what data it
needs instead. The pipeline is proved in mechanism on hand-built fixtures and nothing more;
`UNMEASURED_COMMAND_DETECTION_CAVEAT` says so and travels with every output.

The full packet surface lives in `phos.atlas.packet`; the entry points are re-exported here.

Not here yet: predictive behaviour, calibration of hypothesis confidence (it needs data labelling
which *explanation* was true, which no corpus PHOS uses carries), a finer HAI topology, a grouping
for command evidence, and above all a labelled attack capture — without which Atlas can hear the
commands, describe them and reason about them, and nobody knows how well.
"""

from phos.atlas.cmms import (
    MAXIMO_SCHEMA,
    SAP_PM_SCHEMA,
    WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE,
    CmmsExportMissingError,
    CmmsSchema,
    UndeclaredAssetError,
    WorkOrderRecord,
    covering_order,
    discover_work_order_exports,
    load_work_order_export,
    observations_from_work_orders,
)
from phos.atlas.command_eval import (
    INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS,
    LABELLED_COMMAND_CORPUS_REQUIREMENTS,
    CommandBehaviourDetector,
    CommandCaptureAdapter,
    CommandCorpus,
    CommandGraphDetector,
    UnlabelledCommandCorpusError,
    default_registry,
    discover_labelled_command_corpora,
    render_missing_corpus,
    require_labelled_intervals,
)
from phos.atlas.command_evidence import (
    COMMAND_BEHAVIOUR_MARKER,
    COMMAND_EVIDENCE_CAVEATS,
    GRAPH_FINDING_FEATURES,
    GRAPH_FINDING_MARKER,
    POOLED_GRAPH_CALIBRATION_CAVEAT,
    UNGROUPED_COMMAND_EVIDENCE_CAVEAT,
    UNMEASURED_COMMAND_DETECTION_CAVEAT,
    CommandDeparture,
    CommandEvidence,
    GraphChange,
    command_behaviour_feature_of,
    command_behaviour_marker,
    graph_finding_feature_of,
    graph_finding_marker,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.command_grounding import (
    CommandGrounding,
    attachable_graph_changes,
    command_act_entities,
    command_act_entities_near,
    graph_finding_is_attachable,
    ground_event,
)
from phos.atlas.consistency_evidence import (
    COMMAND_TO_RESPONSE_MISMATCH,
    CONSISTENCY_FEATURES,
    CROSS_SIGNAL_MISMATCH,
    EXPECTED_VALUE_CONTEXT_KEY,
    ConsistencyEvidence,
    ConsistencyFact,
    consistency_feature_of,
    promote_consistency,
)
from phos.atlas.dynamics import (
    DYNAMICS_ASSUMPTIONS,
    DYNAMICS_BREAK_CONDITIONS,
    LinearDynamicsFittedModel,
    LinearDynamicsModel,
)
from phos.atlas.engine import (
    ATLAS_VERTICAL_CAVEATS,
    CO_OCCURRING_FAULT_MASKING_CAVEAT,
    COARSE_MAP_CAVEAT,
    GROUPED_WEIGHT_CAVEAT,
    SATURATED_FP_LOAD_CAVEAT,
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    AtlasConfig,
    AtlasEngine,
    annotate_with_caveats,
)
from phos.atlas.grouping import (
    SUBSYSTEM_EVENT_MARKER,
    group_evidence,
    is_subsystem_event,
    member_evidence_ids,
)
from phos.atlas.maintenance_closure import (
    OVERLAP_IS_NOT_CLOSURE,
    AlertClosure,
    JobCitation,
    OpenAlert,
    close_maintenance_alerts,
)
from phos.atlas.multivariate import (
    MANIFOLD_BREAK_CONDITIONS,
    SNAPSHOT_ASSUMPTIONS,
    JointMomentDetector,
    MahalanobisFittedModel,
    MahalanobisModel,
    MultivariateFittedModel,
    MultivariateModel,
    PcaResidualFittedModel,
    PcaResidualModel,
    ShrinkageTarget,
)
from phos.atlas.packet import (
    COMMAND_BASELINE_CAVEATS,
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
    CommandFeaturePolicy,
    DeviceCommandGraph,
    DissectorRegistry,
    GraphComparePolicy,
    ModbusDissector,
    compare_to_graph,
    dissect_capture,
    featurise_commands,
    learn_device_command_graph,
    render_graph,
)
from phos.atlas.phased import (
    DEFAULT_SETTLING_WINDOW,
    InnerFittedModel,
    InnerModel,
    PhaseConditionalFittedModel,
    PhaseConditionalModel,
    phase_at,
)
from phos.atlas.queue import (
    ARBITRARY_CUT_CAVEAT,
    QUEUE_CAVEATS,
    QUEUE_DETECTOR_PREFIX,
    RANKING_KEYS,
    BudgetOutcome,
    QueueCurve,
    QueuedAlert,
    RankingKey,
    outcome_at_budget,
    queue_curve,
    queue_detector_name,
    rank_queue,
    render_queue_markdown,
    windows_overlapped,
)
from phos.atlas.reconstructability import observations_under, walk_evidence_to_observation
from phos.atlas.stability import (
    ProcessCycle,
    baseline_similarity,
    dominant_period,
    learn_process_cycle,
    process_cycle_deviation,
)
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    LOWEST_BASE_RATE_PRIOR,
    ONE_DEVICE_MAX_SIGNALS,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    RANK_ODDS_FACTOR,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    CommandBehaviourPattern,
    CommandResponsePattern,
    ConsistencyPattern,
    GraphFindingPattern,
    SubsystemBreadthPattern,
    UntypedStructurePattern,
    WorkOrderPattern,
    atlas_library,
    atlas_templates,
    prior_at_rank,
)
from phos.atlas.topology import (
    SCHEMA_VERSION,
    Subsystem,
    SubsystemMap,
    TopologyError,
    load_topology,
    render_topology,
)
from phos.atlas.vectorise import (
    NO_OBSERVATION,
    SignalSpace,
    VectorisedSeries,
    VectorisePolicy,
    vectorise,
)
from phos.atlas.work_orders import (
    WORK_ORDER_FEATURE,
    WORK_ORDER_MARKER,
    WorkOrderEvidence,
    WorkOrderFact,
    promote_work_orders,
    work_order_feature_of,
    work_order_marker,
)

__all__ = [
    "ARBITRARY_CUT_CAVEAT",
    "ATLAS_VERTICAL_CAVEATS",
    "COARSE_MAP_CAVEAT",
    "COMMAND_BASELINE_CAVEATS",
    "COMMAND_BEHAVIOUR_MARKER",
    "COMMAND_EVIDENCE_CAVEATS",
    "COMMAND_TO_RESPONSE_MISMATCH",
    "CONSISTENCY_FEATURES",
    "CO_OCCURRING_FAULT_MASKING_CAVEAT",
    "CROSS_SIGNAL_MISMATCH",
    "DEFAULT_SETTLING_WINDOW",
    "DYNAMICS_ASSUMPTIONS",
    "DYNAMICS_BREAK_CONDITIONS",
    "ENGINEERING_MAINTENANCE_TEMPLATE_ID",
    "EXPECTED_VALUE_CONTEXT_KEY",
    "GRAPH_FINDING_FEATURES",
    "GRAPH_FINDING_MARKER",
    "GROUPED_WEIGHT_CAVEAT",
    "INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS",
    "LABELLED_COMMAND_CORPUS_REQUIREMENTS",
    "LOWEST_BASE_RATE_PRIOR",
    "MANIFOLD_BREAK_CONDITIONS",
    "MAXIMO_SCHEMA",
    "NO_OBSERVATION",
    "ONE_DEVICE_MAX_SIGNALS",
    "OVERLAP_IS_NOT_CLOSURE",
    "POOLED_GRAPH_CALIBRATION_CAVEAT",
    "PROCESS_DISTURBANCE_TEMPLATE_ID",
    "QUEUE_CAVEATS",
    "QUEUE_DETECTOR_PREFIX",
    "RANKING_KEYS",
    "RANK_ODDS_FACTOR",
    "SAP_PM_SCHEMA",
    "SATURATED_FP_LOAD_CAVEAT",
    "SCHEMA_VERSION",
    "SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID",
    "SILENT_COMMAND_RELATIONSHIP",
    "SNAPSHOT_ASSUMPTIONS",
    "SUBSYSTEM_EVENT_MARKER",
    "UNAUTHORISED_CONTROL_TEMPLATE_ID",
    "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT",
    "UNEXPECTED_COMMAND_FUNCTION",
    "UNGROUPED_COMMAND_EVIDENCE_CAVEAT",
    "UNKNOWN_COMMAND_RELATIONSHIP",
    "UNMEASURED_COMMAND_DETECTION_CAVEAT",
    "WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE",
    "WORK_ORDER_FEATURE",
    "WORK_ORDER_MARKER",
    "AlertClosure",
    "AtlasConfig",
    "AtlasEngine",
    "BudgetOutcome",
    "CmmsExportMissingError",
    "CmmsSchema",
    "CommandBehaviourDetector",
    "CommandBehaviourPattern",
    "CommandCaptureAdapter",
    "CommandCorpus",
    "CommandDeparture",
    "CommandEvidence",
    "CommandFeaturePolicy",
    "CommandGraphDetector",
    "CommandGrounding",
    "CommandResponsePattern",
    "ConsistencyEvidence",
    "ConsistencyFact",
    "ConsistencyPattern",
    "DeviceCommandGraph",
    "DissectorRegistry",
    "GraphChange",
    "GraphComparePolicy",
    "GraphFindingPattern",
    "InnerFittedModel",
    "InnerModel",
    "JobCitation",
    "JointMomentDetector",
    "LinearDynamicsFittedModel",
    "LinearDynamicsModel",
    "MahalanobisFittedModel",
    "MahalanobisModel",
    "ModbusDissector",
    "MultivariateFittedModel",
    "MultivariateModel",
    "OpenAlert",
    "PcaResidualFittedModel",
    "PcaResidualModel",
    "PhaseConditionalFittedModel",
    "PhaseConditionalModel",
    "ProcessCycle",
    "QueueCurve",
    "QueuedAlert",
    "RankingKey",
    "ShrinkageTarget",
    "SignalSpace",
    "Subsystem",
    "SubsystemBreadthPattern",
    "SubsystemMap",
    "TopologyError",
    "UndeclaredAssetError",
    "UnlabelledCommandCorpusError",
    "UntypedStructurePattern",
    "VectorisePolicy",
    "VectorisedSeries",
    "WorkOrderEvidence",
    "WorkOrderFact",
    "WorkOrderPattern",
    "WorkOrderRecord",
    "annotate_with_caveats",
    "atlas_library",
    "atlas_templates",
    "attachable_graph_changes",
    "baseline_similarity",
    "close_maintenance_alerts",
    "command_act_entities",
    "command_act_entities_near",
    "command_behaviour_feature_of",
    "command_behaviour_marker",
    "compare_to_graph",
    "consistency_feature_of",
    "covering_order",
    "default_registry",
    "discover_labelled_command_corpora",
    "discover_work_order_exports",
    "dissect_capture",
    "dominant_period",
    "featurise_commands",
    "graph_finding_feature_of",
    "graph_finding_is_attachable",
    "graph_finding_marker",
    "ground_event",
    "group_evidence",
    "is_subsystem_event",
    "learn_device_command_graph",
    "learn_process_cycle",
    "load_topology",
    "load_work_order_export",
    "member_evidence_ids",
    "observations_from_work_orders",
    "observations_under",
    "outcome_at_budget",
    "phase_at",
    "prior_at_rank",
    "process_cycle_deviation",
    "promote_command_behaviour",
    "promote_consistency",
    "promote_graph_findings",
    "promote_work_orders",
    "queue_curve",
    "queue_detector_name",
    "rank_queue",
    "render_graph",
    "render_missing_corpus",
    "render_queue_markdown",
    "render_topology",
    "require_labelled_intervals",
    "vectorise",
    "walk_evidence_to_observation",
    "windows_overlapped",
    "work_order_feature_of",
    "work_order_marker",
]
