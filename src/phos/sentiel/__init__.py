"""Sentiel's enterprise data intake: the path from a real activity corpus to the ontology.

Import everything public from here — ``from phos.sentiel import CertReader`` — rather than from the
submodules, so internal layout can change without breaking callers.

This package is deliberately about **data, not modelling**. Sentiel's behavioural models,
peer-group baselining, hypothesis templates and engine are PARTs 6A, 6B and 6C. This one exists so
that when those arrive they are measured against a real, labelled enterprise corpus from their
first commit, rather than against synthetic fixtures. Atlas's reasoning layer was built starved
because attack-dense real data arrived late; Sentiel does not repeat that.

The path, in order:

- `EnterpriseEvent` — one normalised shape for every activity log (`events`).
- `CertReader` — a CERT release directory tree read into that shape, headers introspected rather
  than assumed, streamed rather than loaded (`cert`).
- `EntityCatalogue` — users mapped to ontology `Entity` objects carrying role, team, department and
  supervisor, read from the release's own LDAP directory (`entities`). Peer grouping (6B) depends
  on it, so it is read from the corpus now rather than invented later.
- `Featuriser` — events aggregated into per-``(user, day)`` `Observation`s (`featurise`), in one
  of two sets: PART 6·D's eight **starter** counts, or PART 6A's **enriched** set, which adds
  baseline-relative, temporal and first-order relationship features over `TrailingHistory`
  (`history`). Both are per-entity only; neither has peer-group context.
- `EntityLabelledInterval` — ground truth that names *which user* was malicious and when
  (`labels`). Sentiel's truth is entity-scoped; flattening it to a time-only window would score a
  detection about the wrong user as a hit.
- `evaluate_entity_aware` — the evaluation that honours that scoping (`evaluation`). It reuses
  PART 2's metric math by importing and calling it, and modifies nothing in PART 2.

Nothing here detects anything. The first baseline is produced by
``scripts/evaluate_sentiel_baseline.py`` from the models PART 3 already shipped.
"""

from phos.sentiel.cert import (
    CERT_TIMESTAMP_FORMAT,
    CertFormatError,
    CertReader,
    CertRelease,
    LogSpec,
)
from phos.sentiel.cert_curve import CERT_R31_BUDGET_CURVE, CERT_R31_HEADLINE_ALERTS
from phos.sentiel.engine import (
    BORROWED_SCALE_CAVEAT,
    COARSE_RECALL_CAVEAT,
    EXPLAINED_SUBSET_CAVEAT,
    GROUPED_WEIGHT_CAVEAT,
    PEER_REGISTER_UNTESTED_CAVEAT,
    SCALE_BORROWED_WEIGHT_FACTOR,
    SENTIEL_VERTICAL_CAVEATS,
    SYNTHETIC_CORPUS_CAVEAT,
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    UNQUANTIFIED_WEIGHT_FACTOR,
    ExplanationSummary,
    SentielConfig,
    SentielEngine,
    annotate_with_caveats,
    provenance_factor,
    require_independent_judgement,
)
from phos.sentiel.entities import (
    ABSENT_FROM_DIRECTORY,
    DIRECTORY_RECORD_ATTRIBUTE,
    EntityCatalogue,
    user_entity_id,
    user_id_of,
)
from phos.sentiel.evaluation import (
    SENTIEL_CAVEATS,
    base_rate,
    entity_aware_detections,
    evaluate_entity_aware,
    sentiel_source_note,
)
from phos.sentiel.events import (
    DETAIL_ACTIVITY,
    DETAIL_EVENT_ID,
    DETAIL_FILENAME,
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_RECIPIENTS,
    DETAIL_SENDER,
    DETAIL_URL,
    DETAIL_URL_HOST,
    DETAIL_VALUE_SEPARATOR,
    EnterpriseEvent,
    EventKind,
    domain_of,
    host_of,
)
from phos.sentiel.featurise import (
    BASELINE_RELATIVE_FEATURES,
    COUNTERPARTY_KINDS,
    ENRICHED_CAVEATS,
    ENRICHED_FEATURES,
    ONSET_SIGNALS,
    PEER_CAVEATS,
    PEER_FEATURES,
    PEER_RELATIVE_FEATURES,
    RELATIONSHIP_FEATURES,
    STARTER_FEATURES,
    SUPERSEDED_CAVEAT_MARKER,
    SUPERSEDED_ENRICHED_MARKERS,
    TEMPORAL_FEATURES,
    FeatureSet,
    Featuriser,
    WorkingHours,
    enriched_source_note,
    peer_source_note,
)
from phos.sentiel.history import (
    NEUTRAL_VALUE,
    HistoryPolicy,
    TrailingHistory,
)
from phos.sentiel.hr_tickets import (
    HR_TICKET_MARKER,
    HrTicketEvidence,
    promote_hr_tickets,
)
from phos.sentiel.interaction import (
    UNDECLARED_INTERACTION_CAVEAT,
    DeclaredCounterpartyDirectory,
    interaction_is_expected,
)
from phos.sentiel.labels import (
    INSIDER_LABEL,
    INSIDERS_FILENAME,
    EntityLabelledInterval,
    malicious_user_ids,
    read_insiders,
)
from phos.sentiel.peer_routing import (
    CERT_R31_ROLE_COHORT_SIZE,
    cert_r31_role_is_not_a_peer_group,
    peer_features_allowed,
)
from phos.sentiel.peers import (
    DEFAULT_GROUP_ATTRIBUTE,
    PeerGroups,
    PeerHistory,
    PeerPolicy,
)
from phos.sentiel.scoring import (
    AggregatedDetector,
    AggregationPolicy,
    FeatureContribution,
    PrecomputedDetector,
    ScoredWindow,
    ScoringSummary,
    WindowScorer,
    borrowed_scale_range,
    precision_policy,
    static_range_model,
    stem_of,
    stream_scored_windows,
)
from phos.sentiel.templates import (
    BEHAVIOUR_EVENT_MARKER,
    BENIGN_ROLE_CHANGE_TEMPLATE_ID,
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    FEATURE_FAMILIES,
    INSIDER_MISUSE_TEMPLATE_ID,
    LOWEST_BASE_RATE_PRIOR,
    PEER_ANOMALY_TEMPLATE_ID,
    RANK_ODDS_FACTOR,
    RESIDUAL_PRIOR,
    BehaviourFamily,
    BehaviourFamilyPattern,
    behaviour_event_source_id,
    behaviour_family_of,
    behaviour_member_ids,
    family_of,
    feature_families,
    is_behaviour_event,
    prior_at_rank,
    sentiel_library,
    sentiel_templates,
)

__all__ = [
    "ABSENT_FROM_DIRECTORY",
    "BASELINE_RELATIVE_FEATURES",
    "BEHAVIOUR_EVENT_MARKER",
    "BENIGN_ROLE_CHANGE_TEMPLATE_ID",
    "BORROWED_SCALE_CAVEAT",
    "CERT_R31_BUDGET_CURVE",
    "CERT_R31_HEADLINE_ALERTS",
    "CERT_R31_ROLE_COHORT_SIZE",
    "CERT_TIMESTAMP_FORMAT",
    "COARSE_RECALL_CAVEAT",
    "COMPROMISED_ACCOUNT_TEMPLATE_ID",
    "COUNTERPARTY_KINDS",
    "DEFAULT_GROUP_ATTRIBUTE",
    "DETAIL_ACTIVITY",
    "DETAIL_EVENT_ID",
    "DETAIL_FILENAME",
    "DETAIL_PC",
    "DETAIL_RECIPIENTS",
    "DETAIL_RECIPIENT_DOMAINS",
    "DETAIL_SENDER",
    "DETAIL_URL",
    "DETAIL_URL_HOST",
    "DETAIL_VALUE_SEPARATOR",
    "DIRECTORY_RECORD_ATTRIBUTE",
    "ENRICHED_CAVEATS",
    "ENRICHED_FEATURES",
    "EXPLAINED_SUBSET_CAVEAT",
    "FEATURE_FAMILIES",
    "GROUPED_WEIGHT_CAVEAT",
    "HR_TICKET_MARKER",
    "INSIDERS_FILENAME",
    "INSIDER_LABEL",
    "INSIDER_MISUSE_TEMPLATE_ID",
    "LOWEST_BASE_RATE_PRIOR",
    "NEUTRAL_VALUE",
    "ONSET_SIGNALS",
    "PEER_ANOMALY_TEMPLATE_ID",
    "PEER_CAVEATS",
    "PEER_FEATURES",
    "PEER_REGISTER_UNTESTED_CAVEAT",
    "PEER_RELATIVE_FEATURES",
    "RANK_ODDS_FACTOR",
    "RELATIONSHIP_FEATURES",
    "RESIDUAL_PRIOR",
    "SCALE_BORROWED_WEIGHT_FACTOR",
    "SENTIEL_CAVEATS",
    "SENTIEL_VERTICAL_CAVEATS",
    "STARTER_FEATURES",
    "SUPERSEDED_CAVEAT_MARKER",
    "SUPERSEDED_ENRICHED_MARKERS",
    "SYNTHETIC_CORPUS_CAVEAT",
    "TEMPORAL_FEATURES",
    "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT",
    "UNDECLARED_INTERACTION_CAVEAT",
    "UNQUANTIFIED_WEIGHT_FACTOR",
    "AggregatedDetector",
    "AggregationPolicy",
    "BehaviourFamily",
    "BehaviourFamilyPattern",
    "CertFormatError",
    "CertReader",
    "CertRelease",
    "DeclaredCounterpartyDirectory",
    "EnterpriseEvent",
    "EntityCatalogue",
    "EntityLabelledInterval",
    "EventKind",
    "ExplanationSummary",
    "FeatureContribution",
    "FeatureSet",
    "Featuriser",
    "HistoryPolicy",
    "HrTicketEvidence",
    "LogSpec",
    "PeerGroups",
    "PeerHistory",
    "PeerPolicy",
    "PrecomputedDetector",
    "ScoredWindow",
    "ScoringSummary",
    "SentielConfig",
    "SentielEngine",
    "TrailingHistory",
    "WindowScorer",
    "WorkingHours",
    "annotate_with_caveats",
    "base_rate",
    "behaviour_event_source_id",
    "behaviour_family_of",
    "behaviour_member_ids",
    "borrowed_scale_range",
    "cert_r31_role_is_not_a_peer_group",
    "domain_of",
    "enriched_source_note",
    "entity_aware_detections",
    "evaluate_entity_aware",
    "family_of",
    "feature_families",
    "host_of",
    "interaction_is_expected",
    "is_behaviour_event",
    "malicious_user_ids",
    "peer_features_allowed",
    "peer_source_note",
    "precision_policy",
    "prior_at_rank",
    "promote_hr_tickets",
    "provenance_factor",
    "read_insiders",
    "require_independent_judgement",
    "sentiel_library",
    "sentiel_source_note",
    "sentiel_templates",
    "static_range_model",
    "stem_of",
    "stream_scored_windows",
    "user_entity_id",
    "user_id_of",
]
