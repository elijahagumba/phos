"""The standard corpora still hash to what they hashed to before PART R1.

This is the safeguard the declarative refactor is built behind. `scripts/synth_golden.py` records
what every corpus in ``configs/synth/`` produces — each file's digest, and the manifest's digest,
which covers the plant's whole declaration — and this module regenerates them and compares.

It is deliberately **not** marked ``slow``. The six corpora take a few seconds between them, and a
golden check that the default suite deselects is a safeguard nobody runs. The ``slow`` marker is
for runs that need a real downloaded payload on disk (ADR 0092); nothing here reads one, because
every corpus is generated into a temporary directory and thrown away.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.synth_golden import (
    CONFIG_DIR,
    GOLDEN_PATH,
    SCHEMA_VERSION,
    capture,
    compare,
    load_golden,
)

from phos.synth.catalogue import load_configs


@pytest.fixture(scope="module")
def golden() -> dict[str, object]:
    """The committed golden record."""
    return load_golden()


@pytest.fixture(scope="module")
def fresh() -> dict[str, object]:
    """Every standard corpus, regenerated now. Shared, because generating them is the slow part."""
    return capture(load_configs(CONFIG_DIR))


def test_every_standard_corpus_matches_the_golden_record(
    fresh: dict[str, object], golden: dict[str, object]
) -> None:
    differences = compare(fresh, golden)
    assert not differences, "generator output moved:\n  " + "\n  ".join(differences)


def test_the_golden_record_covers_every_committed_config(golden: dict[str, object]) -> None:
    corpora = golden["corpora"]
    assert isinstance(corpora, dict)
    configured = {config.name for config in load_configs(CONFIG_DIR)}
    assert configured == set(corpora), (
        "a config with no golden entry is a corpus the refactor could change unnoticed"
    )


def test_the_record_pins_the_manifest_as_well_as_the_payload(golden: dict[str, object]) -> None:
    corpora = golden["corpora"]
    assert isinstance(corpora, dict)
    for name, record in corpora.items():
        assert isinstance(record, dict)
        assert len(str(record["manifest_sha256"])) == 64, (
            f"{name} has no manifest digest, so its declaration is unpinned"
        )
        files = record["files"]
        assert isinstance(files, dict)
        assert "telemetry.csv" in files and "topology.toml" in files


def test_comparison_names_a_moved_digest(
    fresh: dict[str, object], golden: dict[str, object]
) -> None:
    tampered = json.loads(json.dumps(golden))
    corpus = tampered["corpora"]["synth-water-treatment-holdout"]
    corpus["files"]["telemetry.csv"]["sha256"] = "0" * 64

    differences = compare(fresh, tampered)

    assert any(
        "synth-water-treatment-holdout" in line and "telemetry.csv" in line and "sha256" in line
        for line in differences
    ), differences


def test_comparison_names_a_corpus_that_stopped_being_generated(
    fresh: dict[str, object], golden: dict[str, object]
) -> None:
    tampered = json.loads(json.dumps(golden))
    tampered["corpora"]["synth-not-generated-any-more"] = {}

    differences = compare(fresh, tampered)

    assert any("synth-not-generated-any-more" in line for line in differences), differences


def test_a_record_from_another_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "corpus_digests.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION + 1, "corpora": {}}))

    with pytest.raises(ValueError, match="schema_version"):
        load_golden(path)


def test_an_absent_record_says_how_to_capture_one(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="--write"):
        load_golden(tmp_path / "absent.json")


def test_the_golden_record_is_committed() -> None:
    assert GOLDEN_PATH.exists(), (
        "the golden record is the only evidence the refactor preserved behaviour"
    )
