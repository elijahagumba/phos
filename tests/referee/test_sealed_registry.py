"""Tests for the sealed registry: bars b2, b4 and b5 of E-0016.

The registry is deliberately not `data/registry.json`. That file is the catalogue of public
corpora, every test around it asserts its exact contents, and a sealed batch has no homepage, no
licence and no URL to put there. These tests hold the separate file to the same job without
weakening the public catalogue's tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.referee.sealed_batch import (
    SealedBatch,
    SealedBatchError,
    check_against_registered,
)
from phos.referee.sealed_registry import (
    REGISTRY_PATH,
    SCHEMA_VERSION,
    SealedBatchEntry,
    SealedRegistryError,
    entry_for,
    find,
    load,
)
from phos.referee.seeds import SeedEntry

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A family name for the constructed entries below.
#:
#: These tests build `SealedBatchEntry` and `SeedEntry` objects directly and never resolve a
#: family, so the string is arbitrary. It used to be the real sealed family's identifier, which
#: published that identifier in a file anyone can read for no benefit at all. The one place the
#: real name still appears is the assertion that the committed registry matches itself, below.
FAMILY_UNDER_TEST = "sealed-under-test"


def test_the_committed_registry_loads_and_is_the_declared_schema() -> None:
    """b4. The file exists, parses, matches its own schema version, and names the first batch.

    This is the one test that names the real sealed family, because it is checking the committed
    record against itself. The record is `data/sealed-registry.json`, which ADR 0467 decision 5
    deliberately commits, so the name is published there whatever this test does.
    """
    registry = load(REPO_ROOT)
    assert registry.schema_version == SCHEMA_VERSION
    entry = find(registry, "phos-referee-sealed-1")
    assert entry.family == "gas_pressure"


def test_the_committed_first_batch_is_registered_before_it_exists() -> None:
    """b4. A batch registered ahead of generation says so, and carries no generation date."""
    entry = find(load(REPO_ROOT), "phos-referee-sealed-1")
    assert entry.generated_on is None
    assert "REGISTERED BEFORE IT EXISTS" in entry.note


def test_the_placeholder_fingerprint_cannot_be_mistaken_for_a_real_one() -> None:
    """b4. The stand-in digest is refused by the check it will eventually be compared against."""
    entry = find(load(REPO_ROOT), "phos-referee-sealed-1")
    real = SealedBatch(entries=(SeedEntry(family=FAMILY_UNDER_TEST, seed=123_456_789_012_345),))
    with pytest.raises(SealedBatchError, match="does not match the registered one"):
        check_against_registered(real, entry.fingerprint)


def test_a_registry_entry_carries_no_seed_value_and_no_path_into_a_corpus() -> None:
    """b4. What is committed must not be a way to find the seeds or the payload.

    The check is for a seed *value*, not the word. An entry's note should say that seeds live
    outside the repository, so banning the word would ban the sentence that explains the rule.
    What must not appear is a long integer, which is what a seed is, or a mount path.
    """
    raw = (REPO_ROOT / REGISTRY_PATH).read_text(encoding="utf-8")
    for entry in load(REPO_ROOT).batches:
        # The fingerprint is a long hex string and is meant to be there. Everything else in the
        # entry is prose or a small count, so a long run of digits anywhere else is a seed.
        body = entry.model_dump()
        body.pop("fingerprint")
        rendered = json.dumps(body)
        assert not re.search(r"\d{10,}", rendered), "an entry appears to carry a seed value"
        assert "/Volumes/" not in rendered, "an entry must not name a mount path"
    assert not re.search(r'"seed"\s*:', raw), "the registry file must have no seed field"


def test_a_digest_that_is_not_lowercase_hex_is_refused() -> None:
    """b4. A digest in the wrong case would never match, and would look like a refused run."""
    with pytest.raises(ValidationError, match="not a lowercase hex"):
        SealedBatchEntry(name="x", family=FAMILY_UNDER_TEST, plants=1, fingerprint="AB" * 32)


def test_an_unknown_field_is_refused_rather_than_ignored() -> None:
    """b4. `extra=forbid` means a typo is an error, not a silently dropped record."""
    with pytest.raises(ValidationError):
        SealedBatchEntry(
            name="x",
            family=FAMILY_UNDER_TEST,
            plants=1,
            fingerprint="00" * 32,
            seeds=[1, 2, 3],  # type: ignore[call-arg]
        )


def test_an_entry_computed_from_seeds_stores_the_digest_and_the_count_only() -> None:
    """b2 and b4. Building an entry from a batch keeps no seed."""
    entries = [
        SeedEntry(family=FAMILY_UNDER_TEST, seed=111_111_111_111_111),
        SeedEntry(family=FAMILY_UNDER_TEST, seed=222_222_222_222_222),
    ]
    entry = entry_for("a-future-batch", entries, family=FAMILY_UNDER_TEST)
    assert entry.plants == 2
    assert len(entry.fingerprint) == 64
    dumped = entry.model_dump_json()
    assert "111111111111111" not in dumped
    assert "222222222222222" not in dumped


def test_a_missing_registry_file_is_refused_not_treated_as_empty(tmp_path: Path) -> None:
    """b4. "No batches" and "the registry did not load" must not look the same."""
    with pytest.raises(SealedRegistryError, match="is missing"):
        load(tmp_path)


def test_a_malformed_registry_is_refused(tmp_path: Path) -> None:
    """b4. A file that will not parse is an error, not a licence to proceed."""
    (tmp_path / "data").mkdir()
    (tmp_path / REGISTRY_PATH).write_text("{not json", encoding="utf-8")
    with pytest.raises(SealedRegistryError, match="will not parse"):
        load(tmp_path)


def test_an_unregistered_name_is_refused(tmp_path: Path) -> None:
    """b4. Asking for a batch nobody registered is a refusal, not an empty answer."""
    (tmp_path / "data").mkdir()
    (tmp_path / REGISTRY_PATH).write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "batches": []}), encoding="utf-8"
    )
    with pytest.raises(SealedRegistryError, match="no sealed batch named"):
        find(load(tmp_path), "absent")


def test_the_registry_is_not_the_public_catalogue() -> None:
    """b4. The sealed registry must not have been merged into `data/registry.json`."""
    public = json.loads((REPO_ROOT / "data" / "registry.json").read_text(encoding="utf-8"))
    names = {entry["name"] for entry in public["datasets"]}
    assert "phos-referee-sealed-1" not in names, (
        "a sealed batch was added to the public catalogue; that file is for corpora with a "
        "homepage and a licence, and its tests assert its exact contents"
    )
