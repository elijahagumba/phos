"""The `Entity` — a device, user, service or application in the protected environment."""

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology.enums import Domain, EntityType
from phos.ontology.ids import ENTITY_PREFIX, EntityId, UtcDatetime, new_id, utc_now

__all__ = ["Entity"]


class Entity(BaseModel):
    """A thing in the protected environment that behaviour can be attributed to.

    Entities are the anchors of the ontology: observations, evidence and narratives all reference
    entities by id. Immutable — a change of name or attributes produces a new object.

    Attributes:
        id: Stable opaque identifier, ``ent_*``.
        type: What kind of thing this is.
        domain: Which engine owns it.
        name: Human-readable label as operators know it, e.g. ``"PLC-4"``.
        attributes: Free-form string metadata (vendor, location, firmware, ...). Deliberately
            ``str -> str`` so it stays serialisable and no engine hides typed state here.
        created_at: When this entity was first recorded, UTC.
    """

    model_config = ConfigDict(frozen=True)

    id: EntityId = Field(default_factory=lambda: new_id(ENTITY_PREFIX))
    type: EntityType
    domain: Domain
    name: str
    attributes: dict[str, str] = Field(default_factory=dict)
    created_at: UtcDatetime = Field(default_factory=utc_now)

    def matches(self, entity_type: EntityType) -> bool:
        """Return whether this entity is of ``entity_type``."""
        return self.type is entity_type
