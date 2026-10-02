"""What a generated corpus records about itself.

The payload is not committed, so the manifest is the only thing that travels with it. It has to
carry the recipe that regenerates the run, the plant's own claim about what makes its signals
related, the benign events that occurred, and a digest of every file — enough that someone holding
a corpus and this file can say whether they match.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from phos.synth.manifest import (
    MANIFEST_SCHEMA_VERSION,
    GeneratedFile,
    SynthManifest,
    build_manifest,
    digest_of,
    write_manifest,
)
from phos.synth.plant import MODEL_NOT_REALITY_CAVEAT, RunSpec
from phos.synth.run import run_plant
from phos.synth.telemetry import write_csv
from phos.synth.topology import SYNTHETIC_TOPOLOGY_CAVEAT

SPEC = RunSpec(
    seed=808,
    start=datetime(2026, 10, 1, tzinfo=UTC),
    duration=timedelta(hours=6),
    sample_interval=timedelta(seconds=30),
)


def a_manifest() -> SynthManifest:
    """Return a manifest for a short water-treatment run."""
    run = run_plant("water-treatment", SPEC)
    return build_manifest(run, name="example", files=(), traffic_seed=99, note="an example")


class TestTheManifestCarriesTheRecipe:
    def test_the_run_can_be_reproduced_from_what_it_records(self) -> None:
        manifest = a_manifest()
        assert manifest.plant_id == "water-treatment"
        assert manifest.spec == SPEC
        assert manifest.samples == SPEC.n_steps
        assert manifest.traffic_seed == 99

    def test_it_embeds_the_plants_declared_couplings_rather_than_summarising_them(self) -> None:
        manifest = a_manifest()
        assert manifest.description.couplings
        for coupling in manifest.description.couplings:
            assert coupling.relation
            assert coupling.drivers

    def test_it_records_what_legitimately_happened_during_the_run(self) -> None:
        manifest = a_manifest()
        assert manifest.events
        for event in manifest.events:
            assert event.kind and event.label
            assert event.started_at >= SPEC.start

    def test_it_states_that_every_sample_is_normal(self) -> None:
        assert "normal" in a_manifest().label_policy

    def test_it_carries_both_standing_caveats(self) -> None:
        caveats = a_manifest().caveats
        assert MODEL_NOT_REALITY_CAVEAT in caveats
        assert SYNTHETIC_TOPOLOGY_CAVEAT in caveats

    def test_it_declares_the_schema_version_it_was_written_under(self) -> None:
        assert a_manifest().schema_version == MANIFEST_SCHEMA_VERSION


class TestDigests:
    def test_a_digest_identifies_the_bytes_and_their_size(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.csv"
        run = run_plant("batch-reactor", SPEC)
        write_csv(run, path)
        sha256, size = digest_of(path)
        assert len(sha256) == 64
        assert size == path.stat().st_size

    def test_two_identical_files_digest_identically(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a.csv", tmp_path / "b.csv"
        write_csv(run_plant("batch-reactor", SPEC), first)
        write_csv(run_plant("batch-reactor", SPEC), second)
        assert digest_of(first) == digest_of(second)

    def test_a_changed_byte_changes_the_digest(self, tmp_path: Path) -> None:
        path = tmp_path / "a.csv"
        write_csv(run_plant("batch-reactor", SPEC), path)
        before = digest_of(path)
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        assert digest_of(path) != before


class TestWritingIt:
    def test_it_round_trips_through_the_file_it_is_written_to(self, tmp_path: Path) -> None:
        original = build_manifest(
            run_plant("water-treatment", SPEC),
            name="example",
            files=(
                GeneratedFile(
                    filename="telemetry.csv",
                    kind="telemetry-csv",
                    records=720,
                    sha256="0" * 64,
                    size_bytes=1234,
                ),
            ),
            traffic_seed=3,
        )
        path = tmp_path / "manifest.json"
        write_manifest(original, path)
        restored = SynthManifest.model_validate_json(path.read_text(encoding="utf-8"))
        assert restored == original

    def test_it_is_written_as_readable_json(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        write_manifest(a_manifest(), path)
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert "\n  " in text
        assert json.loads(text)["plant_id"] == "water-treatment"
