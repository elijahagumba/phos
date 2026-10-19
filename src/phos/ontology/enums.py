"""Closed vocabularies shared by every PHOS engine and screen.

All enums are ``str``-backed so they serialise to readable JSON and can be compared against
string literals coming from the API boundary without conversion.
"""

from enum import Enum

__all__ = [
    "Domain",
    "EntityType",
    "EvidenceKind",
    "EvidenceRole",
    "FacetKind",
    "HypothesisStatus",
]


class Domain(str, Enum):
    """Which engine's world an object belongs to.

    ``INTELLIGENCE`` marks objects produced by cross-engine correlation rather than by Atlas or
    Sentiel alone.
    """

    ATLAS = "ATLAS"
    SENTIEL = "SENTIEL"
    INTELLIGENCE = "INTELLIGENCE"


class EntityType(str, Enum):
    """The kind of thing an :class:`~phos.ontology.entities.Entity` is.

    The first block is the industrial/OT set (Atlas); the second is the enterprise/cloud set
    (Sentiel). The split is deliberate: the two environments have different notions of normal,
    so they do not share an entity taxonomy.
    """

    # Industrial / OT
    PLC = "PLC"
    RTU = "RTU"
    HMI = "HMI"
    SCADA_SERVER = "SCADA_SERVER"
    ENGINEERING_WORKSTATION = "ENGINEERING_WORKSTATION"
    INDUSTRIAL_SWITCH = "INDUSTRIAL_SWITCH"

    # Enterprise / cloud
    USER = "USER"
    DEVICE = "DEVICE"
    SERVER = "SERVER"
    APPLICATION = "APPLICATION"
    DATABASE = "DATABASE"
    CLOUD_SERVICE = "CLOUD_SERVICE"
    EXTERNAL_CONNECTION = "EXTERNAL_CONNECTION"


class EvidenceKind(str, Enum):
    """What sort of behavioural fact a piece of evidence was derived from."""

    DEVIATION = "DEVIATION"
    FORECAST_MISS = "FORECAST_MISS"
    RELATIONSHIP_CHANGE = "RELATIONSHIP_CHANGE"
    SEQUENCE_ANOMALY = "SEQUENCE_ANOMALY"


class FacetKind(str, Enum):
    """Which *sub-kind* of fact an `Evidence` carries, within its `EvidenceKind`.

    `EvidenceKind` says how a fact was produced — a deviation, a relationship change. It does not
    say *which* fact, and several Atlas explanations turn on exactly that: a device that has never
    commanded this target is an attacker's shape, while a function-code change on a learned link is
    a commissioning engineer's. Both are one `EvidenceKind.RELATIONSHIP_CHANGE`.

    Before this enum, that distinction was carried as a declared prefix on the free-text
    ``summary`` and read back by string parsing, which made a template's matcher depend on the
    exact wording of a sentence written for a human (ADR 0070). The facet is that same declaration
    as a closed vocabulary, so a matcher asks a typed question instead.

    A facet is optional: most evidence has none, and ``None`` means "this fact declares no
    sub-kind", never "unknown". Paired with `Evidence.facet`, which names the feature within the
    facet — the graph finding, the command-behaviour feature, the work-order feature.
    """

    GRAPH_FINDING = "GRAPH_FINDING"
    COMMAND_BEHAVIOUR = "COMMAND_BEHAVIOUR"
    WORK_ORDER = "WORK_ORDER"
    CONSISTENCY = "CONSISTENCY"
    """A reading that disagrees with what the rest of the plant implies (ADR 0108)."""

    UNCOVERED_SETPOINT = "UNCOVERED_SETPOINT"
    """A setpoint left its training envelope and the work order does not name it."""

    COMMAND_EFFECT = "COMMAND_EFFECT"
    """What a setpoint write did to the plant, apart from who sent it (ADR 0250)."""


class EvidenceRole(str, Enum):
    """How a piece of evidence bears on a hypothesis.

    The role is a property of the *link*, not of the evidence: the same evidence may support one
    hypothesis and contradict another.
    """

    SUPPORTING = "SUPPORTING"
    CONTRADICTORY = "CONTRADICTORY"


class HypothesisStatus(str, Enum):
    """Where a hypothesis sits in its lifecycle.

    ``ACTIVE`` is still accumulating evidence; ``PRUNED`` was dropped by reasoning as no longer
    plausible; ``CONFIRMED`` and ``DISMISSED`` are terminal judgements.
    """

    ACTIVE = "ACTIVE"
    PRUNED = "PRUNED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"
