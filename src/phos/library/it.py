"""IT person-day fixtures: labelled behavioural observations, not malware and not CERT.

Each persona is a declared pattern over starter counts (and a few peer companions) so Sentiel's
scorer can be exercised on hundreds of person-days where busy administration, role change, and
multi-family insider onsets are *known*. Entity-scoped labels name the malicious users; time-only
labels are refused by `evaluate_entity_aware`.

This is not CERT r3.1. Peer-relative advantage on that corpus remains unmeasured (ADR 0023).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.eval import Dataset
from phos.library.caveats import PERSON_DAYS_ARE_OURS_CAVEAT, SYNTHETIC_LIBRARY_CAVEATS
from phos.ontology import Domain, Observation
from phos.sentiel import STARTER_FEATURES, EntityLabelledInterval, user_entity_id

__all__ = [
    "IT_FEATURES",
    "ItPersona",
    "generate_it_library",
    "it_catalogue_payload",
    "it_person_days",
    "it_personas",
    "load_it_library",
    "write_it_catalogue",
]

logger = logging.getLogger(__name__)

IT_FEATURES: Final[tuple[str, ...]] = (
    *STARTER_FEATURES,
    "logon_count_peer",
    "file_access_count_peer",
    "distinct_http_hosts_peer",
)
TRAIN_DAYS: Final = 35
TEST_DAYS: Final = 15
START: Final = datetime(2010, 1, 4, tzinfo=UTC)
_LOUD: Final = 28.0
_VOLUME: Final = frozenset({"file_access_count", "distinct_files"})
_INSIDER_STEMS: Final = frozenset(
    {
        "removable_device_connects",
        "file_access_count",
        "off_hours_logon_count",
        "distinct_files",
    }
)
_CREDENTIAL_STEMS: Final = frozenset({"distinct_pcs", "off_hours_logon_count", "logon_count"})
_SHADOW_STEMS: Final = frozenset({"distinct_http_hosts", "file_access_count", "distinct_files"})
_ROLE_STEMS: Final = frozenset({"distinct_pcs", "logon_count"})
_PEER_MATCH_KINDS: Final = frozenset({"backup_team", "role_change", "chronic_admin"})


class ItPersona(BaseModel):
    """One synthetic person and the behaviour they were built to exercise.

    Attributes:
        user_id: Corpus identifier, e.g. ``N03``.
        kind: Declared pattern. Not an attack name — a fixture role.
        labelled: Whether entity-scoped ground truth marks this user malicious in the test half.
        scenario: Short tag for labelled users, or ``None``.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    labelled: bool = False
    scenario: str | None = None


def it_personas() -> tuple[ItPersona, ...]:
    """Return the fixed population: 48 people, eight of them labelled in the test half."""
    people: list[ItPersona] = []
    people.extend(ItPersona(user_id=f"N{index:02d}", kind="normal") for index in range(16))
    people.extend(ItPersona(user_id=f"B{index:02d}", kind="backup_team") for index in range(8))
    people.extend(ItPersona(user_id=f"C{index:02d}", kind="chronic_admin") for index in range(8))
    people.extend(ItPersona(user_id=f"R{index:02d}", kind="role_change") for index in range(4))
    people.extend(ItPersona(user_id=f"H{index:02d}", kind="off_hours") for index in range(4))
    people.extend(
        ItPersona(
            user_id=f"M{index:02d}",
            kind="insider_multi",
            labelled=True,
            scenario="multi-family",
        )
        for index in range(4)
    )
    people.extend(
        ItPersona(
            user_id=f"K{index:02d}",
            kind="credential_reuse",
            labelled=True,
            scenario="credential-reuse",
        )
        for index in range(2)
    )
    people.extend(
        ItPersona(
            user_id=f"S{index:02d}",
            kind="shadow_http",
            labelled=True,
            scenario="shadow-http",
        )
        for index in range(2)
    )
    return tuple(people)


def it_person_days(personas: Sequence[ItPersona] | None = None, *, days: int | None = None) -> int:
    """Return ``len(personas) * days`` — the person-day count the catalogue advertises."""
    chosen = personas if personas is not None else it_personas()
    span = TRAIN_DAYS + TEST_DAYS if days is None else days
    return len(chosen) * span


def _base(day: int) -> float:
    """Return a slowly varying ordinary count so a per-key Gaussian has spread."""
    return 10.0 + (day % 5) * 0.4


def _fires(kind: str, stem: str) -> bool:
    """Return whether this fixture kind is loud on ``stem`` in the test half."""
    if kind == "backup_team":
        return stem in _VOLUME
    if kind == "chronic_admin":
        return stem in _VOLUME
    if kind == "role_change":
        return stem in _ROLE_STEMS
    if kind == "off_hours":
        return stem == "off_hours_logon_count"
    if kind == "insider_multi":
        return stem in _INSIDER_STEMS
    if kind == "credential_reuse":
        return stem in _CREDENTIAL_STEMS
    if kind == "shadow_http":
        return stem in _SHADOW_STEMS
    return False


def _value(persona: ItPersona, day: int, feature: str) -> float:
    """Return one user-day-feature value: baseline in training, declared pattern in test."""
    base = _base(day)
    stem = feature.removesuffix("_peer")
    if day < TRAIN_DAYS:
        return base
    if feature.endswith("_peer"):
        if persona.kind in _PEER_MATCH_KINDS:
            return base
        if persona.labelled and _fires(persona.kind, stem):
            return base + _LOUD
        return base
    if _fires(persona.kind, stem):
        return base + _LOUD
    return base


def generate_it_observations(
    personas: Sequence[ItPersona] | None = None,
    *,
    train_days: int = TRAIN_DAYS,
    test_days: int = TEST_DAYS,
    start: datetime = START,
) -> tuple[list[Observation], list[EntityLabelledInterval]]:
    """Return a time-ordered observation stream and entity-scoped labels for the test half."""
    chosen = tuple(personas) if personas is not None else it_personas()
    total = train_days + test_days
    stream: list[Observation] = []
    for day in range(total):
        stamp = start + timedelta(days=day)
        for persona in chosen:
            for index, feature in enumerate(IT_FEATURES):
                stream.append(
                    Observation(
                        id=f"obs_{persona.user_id}_{day:03d}_{index:02d}",
                        entity_ids=[user_entity_id(persona.user_id)],
                        feature=feature,
                        value=_value(persona, day, feature),
                        timestamp=stamp,
                        domain=Domain.SENTIEL,
                    )
                )
    test_start = start + timedelta(days=train_days)
    test_end = start + timedelta(days=total - 1)
    labels = [
        EntityLabelledInterval(
            user_id=persona.user_id,
            start=test_start,
            end=test_end,
            scenario=persona.scenario,
            release="library-it",
        )
        for persona in chosen
        if persona.labelled
    ]
    return stream, labels


def it_catalogue_payload(personas: Sequence[ItPersona] | None = None) -> dict[str, object]:
    """Return the committed catalogue document for the IT library."""
    chosen = tuple(personas) if personas is not None else it_personas()
    return {
        "schema_version": 1,
        "domain": "SENTIEL",
        "caveats": list(SYNTHETIC_LIBRARY_CAVEATS),
        "n_personas": len(chosen),
        "n_labelled": sum(1 for persona in chosen if persona.labelled),
        "train_days": TRAIN_DAYS,
        "test_days": TEST_DAYS,
        "n_person_days": it_person_days(chosen),
        "features": list(IT_FEATURES),
        "personas": [persona.model_dump() for persona in chosen],
    }


def write_it_catalogue(root: Path, personas: Sequence[ItPersona] | None = None) -> Path:
    """Write ``IT/catalogue.json`` under the dataset library root and return its path."""
    directory = root / "IT"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "catalogue.json"
    path.write_text(json.dumps(it_catalogue_payload(personas), indent=2) + "\n", encoding="utf-8")
    return path


def generate_it_library(root: Path, personas: Sequence[ItPersona] | None = None) -> Path:
    """Write the catalogue, observation JSONL, and labels JSON. Returns the generated directory."""
    write_it_catalogue(root, personas)
    generated = root / "IT" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    observations, labels = generate_it_observations(personas)
    payload = generated / "observations.jsonl"
    with payload.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(observation.model_dump_json() + "\n")
    labels_path = generated / "labels.json"
    labels_path.write_text(
        json.dumps([label.model_dump(mode="json") for label in labels], indent=2) + "\n",
        encoding="utf-8",
    )
    (generated / "README.txt").write_text(
        PERSON_DAYS_ARE_OURS_CAVEAT + "\n",
        encoding="utf-8",
    )
    logger.info(
        "wrote %d observations, %d labelled users -> %s",
        len(observations),
        len(labels),
        generated,
    )
    return generated


def load_it_library(root: Path) -> tuple[Dataset, Dataset, list[EntityLabelledInterval]]:
    """Load train and test datasets plus entity-scoped labels from a generated IT library.

    Raises:
        FileNotFoundError: If the generated payload is missing.
    """
    generated = root / "IT" / "generated"
    payload = generated / "observations.jsonl"
    labels_path = generated / "labels.json"
    if not payload.is_file() or not labels_path.is_file():
        raise FileNotFoundError(
            f"IT library payload missing under {generated}; run scripts/generate_dataset_library.py"
        )
    observations = [
        Observation.model_validate_json(line)
        for line in payload.read_text(encoding="utf-8").splitlines()
        if line
    ]
    labels = [
        EntityLabelledInterval.model_validate(row)
        for row in json.loads(labels_path.read_text(encoding="utf-8"))
    ]
    test_start = START + timedelta(days=TRAIN_DAYS)
    train_obs = [item for item in observations if item.timestamp < test_start]
    test_obs = [item for item in observations if item.timestamp >= test_start]
    note = " ".join(SYNTHETIC_LIBRARY_CAVEATS)
    train = Dataset(
        name="lib-it-person-days-train",
        domain=Domain.SENTIEL,
        observations=train_obs,
        source_note=note,
    )
    test = Dataset(
        name="lib-it-person-days-test",
        domain=Domain.SENTIEL,
        observations=test_obs,
        source_note=note,
    )
    return train, test, labels
