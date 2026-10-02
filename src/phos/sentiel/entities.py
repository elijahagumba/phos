"""The entity catalogue: who the organisation's people are, read from the corpus's own directory.

Sentiel's unit of behaviour is a person, and a person is only interpretable in context — their
role, their team, their department, who they report to. Peer-group baselining (PART 6B) is built
entirely on that context: "this user downloaded 400 files" means nothing until you know whether
their fifty peers downloaded four or four hundred.

This module builds that context **now**, one PART before anything uses it, and builds it by
*reading* rather than inventing. A hand-written org chart would be a fiction that happened to fit
the corpus; the CERT LDAP directory is what the corpus itself says its organisation looks like.

Two decisions worth stating plainly:

- **A user missing from the directory is never dropped.** They get a real `Entity` marked
  `ABSENT_FROM_DIRECTORY`. Silently discarding their events would quietly shrink the corpus, and
  the arithmetic would still look fine — the worst kind of defect. Peer grouping will have to
  decide what to do with such a user; recording them is what makes that decision possible.
- **Identifiers are derived, not minted.** `user_entity_id` is a pure function of the corpus's own
  user id, so two runs produce the same `EntityId` and an id read in a report can be traced back
  to a row in a file (Constitution §3.7). `phos.ontology.new_id` mints a random id, which is right
  for objects PHOS creates and wrong for objects PHOS is merely naming.
"""

import csv
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology import Domain, Entity, EntityId, EntityType, UtcDatetime

__all__ = [
    "ABSENT_FROM_DIRECTORY",
    "DIRECTORY_RECORD_ATTRIBUTE",
    "LDAP_REQUIRED_COLUMNS",
    "EntityCatalogue",
    "user_entity_id",
    "user_id_of",
]

logger = logging.getLogger(__name__)

_ENTITY_ID_PREFIX: Final = "ent_"

DIRECTORY_RECORD_ATTRIBUTE: Final = "directory_record"
"""`Entity.attributes` key recording whether the directory knew this user."""

ABSENT_FROM_DIRECTORY: Final = "absent"
"""Value of `DIRECTORY_RECORD_ATTRIBUTE` for a user the LDAP directory never listed."""

_PRESENT_IN_DIRECTORY: Final = "present"

LDAP_REQUIRED_COLUMNS: Final = frozenset({"user_id"})
"""Without this column a directory row names nobody, so its absence is fatal."""

_LDAP_OPTIONAL_COLUMNS: Final = frozenset(
    {
        "employee_name",
        "email",
        "role",
        "business_unit",
        "functional_unit",
        "department",
        "team",
        "supervisor",
    }
)
"""Columns carried onto `Entity.attributes` when the release provides them.

Releases differ in how much of the org chart they publish, so these are optional. Anything *not*
in this set or `LDAP_REQUIRED_COLUMNS` is refused rather than ignored — see
`EntityCatalogue.from_ldap_directory`.
"""

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)


def user_entity_id(user_id: str) -> EntityId:
    """Return the deterministic `EntityId` for a corpus user id.

    Args:
        user_id: The corpus's own identifier, e.g. ``"CSF0929"``.

    Returns:
        ``"ent_CSF0929"`` — readable, stable across runs, and reversible with `user_id_of`.
    """
    return f"{_ENTITY_ID_PREFIX}{user_id}"


def user_id_of(entity_id: EntityId) -> str:
    """Return the corpus user id behind an `EntityId` produced by `user_entity_id`.

    Args:
        entity_id: An entity id.

    Returns:
        The user id. An id that does not carry the ``ent_`` prefix is returned unchanged, so a
        caller holding a raw user id may pass it through this function harmlessly.
    """
    return entity_id.removeprefix(_ENTITY_ID_PREFIX)


class EntityCatalogue(BaseModel):
    """Every user the corpus's directory knows, as ontology `Entity` objects.

    Attributes:
        entities: ``user_id -> Entity``. Each entity carries the directory's columns on its
            `Entity.attributes`, so role, team, department and supervisor travel with it.
        directory_as_of: The most recent snapshot month the catalogue was built from. Recorded
            because a directory is a moving thing and a report should say which version it read.
        snapshots_read: How many snapshot files were merged.
        source_note: Provenance, copied onto any dataset built alongside this catalogue.
    """

    model_config = ConfigDict(frozen=True)

    entities: dict[str, Entity] = Field(default_factory=dict)
    directory_as_of: UtcDatetime = _EPOCH
    snapshots_read: int = Field(default=0, ge=0)
    source_note: str = ""

    @classmethod
    def from_ldap_directory(cls, directory: Path) -> Self:
        """Read every ``*.csv`` snapshot in a CERT ``LDAP/`` directory into one catalogue.

        CERT publishes the directory as monthly snapshots (``2010-01.csv``, ``2010-02.csv``, ...)
        because people join, leave and change teams. Snapshots are merged in filename order and
        the **last** record for a user wins, so the catalogue describes the organisation as it
        stood at the end of the corpus. That is the right default for a first baseline; a PART
        that needs the org chart *as of* a given day will need the snapshots kept apart, and this
        docstring is the note that it is not what happens here.

        Args:
            directory: The ``LDAP`` directory of an extracted release.

        Returns:
            The merged catalogue.

        Raises:
            CertFormatError: If the directory is missing, holds no snapshots, or a snapshot's
                header lacks ``user_id`` or carries a column this reader does not recognise.
        """
        from phos.sentiel.cert import CertFormatError

        if not directory.is_dir():
            raise CertFormatError(f"LDAP directory not found at {directory}")
        snapshots = sorted(directory.glob("*.csv"))
        if not snapshots:
            raise CertFormatError(f"no LDAP snapshots (*.csv) found in {directory}")

        entities: dict[str, Entity] = {}
        latest = _EPOCH
        for snapshot in snapshots:
            stamped = _snapshot_month(snapshot)
            latest = max(latest, stamped)
            for row in _read_ldap_rows(snapshot):
                user_id = row["user_id"].strip()
                if not user_id:
                    continue
                entities[user_id] = _entity_from_row(user_id, row, stamped)

        logger.info(
            "read %d LDAP snapshots from %s: %d users, directory as of %s",
            len(snapshots),
            directory,
            len(entities),
            latest.date(),
        )
        return cls(
            entities=entities,
            directory_as_of=latest,
            snapshots_read=len(snapshots),
            source_note=(
                f"LDAP directory: {len(snapshots)} snapshot(s) merged last-wins, "
                f"{len(entities)} users, as of {latest.date()}"
            ),
        )

    def entity_for(self, user_id: str) -> Entity:
        """Return the `Entity` for ``user_id``, synthesising one if the directory never listed it.

        A synthesised entity is a real, usable `Entity` marked
        ``attributes[DIRECTORY_RECORD_ATTRIBUTE] == ABSENT_FROM_DIRECTORY``. It carries no role,
        team or department, because none is known — and inventing one would be worse than the gap.

        Args:
            user_id: The corpus's own identifier.

        Returns:
            The catalogued entity, or a synthesised one.
        """
        known = self.entities.get(user_id)
        if known is not None:
            return known
        logger.debug("user %s is absent from the directory; synthesising an entity", user_id)
        return Entity(
            id=user_entity_id(user_id),
            type=EntityType.USER,
            domain=Domain.SENTIEL,
            name=user_id,
            attributes={DIRECTORY_RECORD_ATTRIBUTE: ABSENT_FROM_DIRECTORY},
            created_at=self.directory_as_of,
        )

    def absent_user_ids(self, user_ids: frozenset[str]) -> frozenset[str]:
        """Return which of ``user_ids`` the directory does not list.

        This is what a run reports rather than discovering silently: a corpus where a tenth of the
        actors are undirectoried is a different corpus from one where none are, and peer grouping
        (PART 6B) will need to know which it has.
        """
        return frozenset(user_ids - self.entities.keys())

    def email_domains(self) -> dict[str, int]:
        """Return ``domain -> user count`` over the directory's email addresses.

        The organisation's own mail domain is what makes "external email" meaningful, and reading
        it off the directory is how that stays a fact about the corpus rather than a constant
        somebody typed. Users with no email address contribute nothing.
        """
        from phos.sentiel.events import domain_of

        counts = Counter(
            domain
            for entity in self.entities.values()
            if (domain := domain_of(entity.attributes.get("email", "")))
        )
        return dict(counts.most_common())

    def dominant_email_domain(self) -> str:
        """Return the mail domain most of the directory shares, or ``""`` if there is none.

        Returns:
            The organisation's own domain — ``"dtaa.com"`` for every CERT release — or ``""``
            when no directory entry carries an email address.
        """
        domains = self.email_domains()
        return next(iter(domains), "")


def _snapshot_month(path: Path) -> datetime:
    """Return the month a CERT LDAP snapshot describes, from its ``YYYY-MM.csv`` filename.

    A snapshot whose name is not a month is still read — its records are what matter — but is
    stamped at the epoch, so the stamp is never a guess dressed up as a fact.
    """
    try:
        return datetime.strptime(path.stem, "%Y-%m").replace(tzinfo=UTC)
    except ValueError:
        logger.warning("LDAP snapshot %s is not named YYYY-MM; stamping it at the epoch", path)
        return _EPOCH


def _read_ldap_rows(path: Path) -> list[dict[str, str]]:
    """Read one LDAP snapshot, refusing a header this reader does not fully understand.

    Raises:
        CertFormatError: If ``user_id`` is missing or an unrecognised column is present.
    """
    from phos.sentiel.cert import CertFormatError

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = LDAP_REQUIRED_COLUMNS - set(header)
        if missing:
            raise CertFormatError(
                f"{path}: LDAP snapshot is missing required column(s) "
                f"{', '.join(sorted(missing))}; the file has: {', '.join(header) or '(no header)'}"
            )
        unknown = set(header) - LDAP_REQUIRED_COLUMNS - _LDAP_OPTIONAL_COLUMNS
        if unknown:
            raise CertFormatError(
                f"{path}: LDAP snapshot carries unrecognised column(s) "
                f"{', '.join(sorted(unknown))}. This reader was written against a release whose "
                "directory holds "
                f"{', '.join(sorted(LDAP_REQUIRED_COLUMNS | _LDAP_OPTIONAL_COLUMNS))}; teach it "
                "the new columns rather than letting them be dropped unnoticed."
            )
        return [
            {key.strip(): (value or "").strip() for key, value in row.items() if key is not None}
            for row in reader
        ]


def _entity_from_row(user_id: str, row: dict[str, str], stamped: datetime) -> Entity:
    """Build the ontology `Entity` for one directory row."""
    attributes = {
        column: row[column]
        for column in sorted(_LDAP_OPTIONAL_COLUMNS)
        if row.get(column)  # an empty directory cell is an absent fact, not an empty one
    }
    attributes[DIRECTORY_RECORD_ATTRIBUTE] = _PRESENT_IN_DIRECTORY
    return Entity(
        id=user_entity_id(user_id),
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name=row.get("employee_name") or user_id,
        attributes=attributes,
        created_at=stamped,
    )
