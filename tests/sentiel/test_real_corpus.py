"""Integration tests against the real CERT release, skipped cleanly when it is absent.

The manifest is committed; the release it describes is not, so a fresh clone stays green without a
4.25 GB download. Everything here reads the *first slice* of the corpus rather than all of it —
these are correctness checks against real files, not a measurement. The measurement is
``scripts/evaluate_sentiel_baseline.py``.

What these catch that the inline fixture cannot: that the real headers are the ones the reader was
taught, that the real LDAP directory resolves the real email log's senders, and that the real
answers file names users who actually appear in the corpus. Each of those was wrong in the
published schema or in this project's own registry before the release was read.
"""

import itertools
import json
from pathlib import Path

import pytest

from phos.sentiel import (
    STARTER_FEATURES,
    CertReader,
    CertRelease,
    EventKind,
    Featuriser,
    read_insiders,
    user_entity_id,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MANIFEST = DATA_DIR / "cert-insider-threat" / "sentiel-manifest.json"

_SAMPLE_EVENTS = 200_000
"""Enough real rows to cross every log and several days; far short of the 13 GB corpus."""


def _manifest() -> dict[str, object] | None:
    """Return the committed CERT manifest if its release is actually on disk."""
    if not MANIFEST.is_file():
        return None
    manifest: dict[str, object] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release_dir = DATA_DIR / str(manifest["release_dir"])
    answers_dir = DATA_DIR / str(manifest["answers_dir"])
    return manifest if release_dir.is_dir() and answers_dir.is_dir() else None


MANIFEST_DATA = _manifest()

pytestmark = pytest.mark.skipif(
    MANIFEST_DATA is None,
    reason=(
        "the real CERT release is not present. Fetch it with:\n"
        "    python scripts/fetch_datasets.py cert-insider-threat --yes\n"
        "which downloads ~4.25 GB into data/cert-insider-threat/ and unpacks r3.1/ (~13 GB) and "
        "answers/ beside it. Both are git-ignored; only sentiel-manifest.json is committed."
    ),
)


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    assert MANIFEST_DATA is not None
    return MANIFEST_DATA


@pytest.fixture(scope="module")
def reader(manifest: dict[str, object]) -> CertReader:
    return CertReader.for_release(CertRelease.discover(DATA_DIR / str(manifest["release_dir"])))


def test_the_real_headers_are_the_ones_the_reader_was_taught(reader: CertReader) -> None:
    """If a release's schema drifts, this fails loudly rather than the numbers drifting quietly."""
    events = list(itertools.islice(reader.events(), _SAMPLE_EVENTS))
    assert len(events) == _SAMPLE_EVENTS


def test_every_log_type_is_reached(reader: CertReader) -> None:
    kinds = {event.event_kind for event in itertools.islice(reader.events(), _SAMPLE_EVENTS)}
    assert kinds == set(EventKind)


def test_the_real_stream_is_time_ordered(reader: CertReader) -> None:
    stamps = [event.timestamp for event in itertools.islice(reader.events(), _SAMPLE_EVENTS)]
    assert stamps == sorted(stamps)
    assert all(stamp.tzinfo is not None for stamp in stamps)


def test_the_real_directory_carries_the_org_chart(reader: CertReader) -> None:
    catalogue = reader.catalogue()

    assert len(catalogue.entities) >= 900
    assert catalogue.snapshots_read > 1
    assert catalogue.dominant_email_domain() == "dtaa.com"
    sample = next(iter(catalogue.entities.values()))
    assert sample.attributes["role"]
    assert sample.attributes["email"]


def test_real_email_rows_are_attributed_through_the_directory(reader: CertReader) -> None:
    """r3.1's email log has no `user` column; every attributed send proves the LDAP join works."""
    known = set(reader.catalogue().entities)
    sends = [
        event
        for event in itertools.islice(reader.events(), _SAMPLE_EVENTS)
        if event.event_kind is EventKind.EMAIL_SEND
    ]

    assert sends, "no email was attributed at all — the sender index is not resolving"
    assert all(event.user_id in known for event in sends)


def test_real_labels_name_users_that_exist_in_the_corpus(
    manifest: dict[str, object], reader: CertReader
) -> None:
    labels = read_insiders(DATA_DIR / str(manifest["answers_dir"]), str(manifest["release"]))
    catalogue = reader.catalogue()

    assert labels
    for label in labels:
        assert label.user_id in catalogue.entities, (
            f"ground truth names {label.user_id}, who is not in the release's own directory"
        )
        assert label.start < label.end


def test_real_events_featurise_into_the_ontology(reader: CertReader) -> None:
    observations = Featuriser().observations(itertools.islice(reader.events(), _SAMPLE_EVENTS))

    assert observations
    assert {observation.feature for observation in observations} == set(STARTER_FEATURES)
    stamps = [observation.timestamp for observation in observations]
    assert stamps == sorted(stamps)
    for observation in observations:
        assert observation.value >= 0.0
        assert observation.entity_ids == [user_entity_id(observation.context["user_id"])]


def test_the_manifest_records_the_licence_conflict_and_the_caveats(
    manifest: dict[str, object],
) -> None:
    """The catalogue says CC BY 4.0; the payload ships an ExactData EUA. Both must be on record."""
    provenance = manifest["provenance"]
    assert isinstance(provenance, dict)

    assert provenance["license"]["spdx"] == "CC-BY-4.0"
    assert provenance["payload_license"] is not None
    assert "ExactData" in provenance["payload_license"]["name"]
    assert manifest["attribution"]
    caveats = manifest["caveats"]
    assert isinstance(caveats, list)
    assert any("SYNTHETIC" in caveat for caveat in caveats)


def test_the_release_payload_is_git_ignored(manifest: dict[str, object]) -> None:
    """The nested-file check: a rule that ignores a directory must ignore what is inside it."""
    import subprocess

    repo = Path(__file__).resolve().parents[2]
    nested = [
        f"data/{manifest['release_dir']}/logon.csv",
        f"data/{manifest['release_dir']}/LDAP",
        f"data/{manifest['answers_dir']}/insiders.csv",
        "data/cert-insider-threat/r3.1.tar.bz2",
    ]
    try:
        completed = subprocess.run(
            ["git", "check-ignore", *nested],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env dependent
        pytest.skip(f"git unavailable: {error}")

    ignored = set(completed.stdout.split())
    assert ignored == set(nested), f"corpus payload is not git-ignored: {set(nested) - ignored}"


def test_the_manifest_itself_is_not_ignored() -> None:
    import subprocess

    repo = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "data/cert-insider-threat/sentiel-manifest.json"],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env dependent
        pytest.skip(f"git unavailable: {error}")
    assert completed.returncode != 0, "the manifest must be committed, not ignored"
