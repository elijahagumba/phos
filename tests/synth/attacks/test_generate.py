"""What an attack corpus is on disk, and whether it goes into Atlas through the doors it has.

The load tests are the ones that matter. A corpus that only D2 could read would prove nothing
about D2's output being usable, so the telemetry goes back in through an unmodified
`LabelledCsvAdapter`, the topology through an unmodified `load_topology`, and the capture through
an unmodified `dissect_capture` — and the attack windows have to come back out of the label column
that D2 wrote into.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.synth.attacks.conftest import (
    CLEARWELL_LEVEL,
    INTAKE_SPEED,
    LEVEL_SETPOINT,
    PLANT,
    a_spec,
)

from phos.atlas.packet import (
    CaptureStats,
    DissectorRegistry,
    MalformedFrame,
    ModbusDissector,
    UnparsedMessage,
    dissect_capture,
)
from phos.atlas.topology import load_topology
from phos.eval import LabelledCsvAdapter
from phos.synth.attacks.battery import AttackDatasetConfig, load_batteries, load_battery
from phos.synth.attacks.generate import (
    CAPTURE_FILE,
    MANIFEST_FILE,
    TELEMETRY_FILE,
    TOPOLOGY_FILE,
    TRUTH_FILE,
    AttackManifest,
    generate_attack_dataset,
    telemetry_lines,
    truth_lines,
)
from phos.synth.attacks.inject import ATTACK_LABEL_VALUE, NORMAL_LABEL_VALUE, inject
from phos.synth.attacks.spec import AttackFlavour, AttackType
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN

CONFIGS = Path(__file__).resolve().parents[3] / "configs" / "attacks"
REGISTRY = DissectorRegistry([ModbusDissector()])

BASE: dict[str, object] = {
    "name": "test-battery",
    "plant_id": PLANT,
    "seed": 4242,
    "traffic_seed": 7,
    "start": datetime(2026, 4, 1, tzinfo=UTC),
    "duration_hours": 12.0,
    "sample_interval_seconds": 30.0,
}

AN_ATTACK: dict[str, object] = {
    "attack_id": "blatant",
    "type": "BLATANT",
    "subtlety": 0.0,
    "start_hours": 2.0,
    "duration_hours": 2.0,
    "target": INTAKE_SPEED,
}

A_ROGUE: dict[str, object] = {
    "attack_id": "rogue",
    "type": "ROGUE_COMMAND",
    "subtlety": 0.0,
    "start_hours": 6.0,
    "duration_hours": 1.5,
    "target": LEVEL_SETPOINT,
    "issuer": "scada",
}

A_HOSTILE: dict[str, object] = {
    "attack_id": "poison",
    "type": "POISONED_BASELINE",
    "fraction": 0.3,
    "target": CLEARWELL_LEVEL,
}


def a_config(**overrides: object) -> AttackDatasetConfig:
    """Return a small battery config with the given fields replaced."""
    return AttackDatasetConfig.model_validate({**BASE, "attacks": [AN_ATTACK], **overrides})


class TestTheConfig:
    """A file humans write by hand, so it refuses to be half-right."""

    def test_a_detection_battery_survives(self) -> None:
        assert a_config().flavour is AttackFlavour.DETECTION

    def test_a_hostile_corpus_survives(self) -> None:
        config = a_config(attacks=[], hostile=[A_HOSTILE])
        assert config.flavour is AttackFlavour.INPUT_HOSTILE

    def test_a_corpus_may_not_hold_both_flavours(self) -> None:
        # A malformed record inside a labelled attack window makes it impossible to say whether
        # a detector missed the attack or choked on the rubbish.
        with pytest.raises(ValueError, match="not both"):
            a_config(hostile=[A_HOSTILE])

    def test_a_corpus_must_hold_one_of_them(self) -> None:
        with pytest.raises(ValueError, match="either attacks or hostile"):
            a_config(attacks=[])

    def test_a_repeated_identifier_is_refused(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            a_config(attacks=[AN_ATTACK, AN_ATTACK])

    def test_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValueError):
            a_config(sublety=0.5)

    def test_it_still_refuses_everything_a_normal_dataset_config_does(self) -> None:
        with pytest.raises(ValueError, match="no plant"):
            a_config(plant_id="no-such-plant")

    def test_it_yields_the_same_run_spec_a_normal_config_would(self) -> None:
        assert a_config().run_spec() == a_spec()


class TestTheCommittedBattery:
    """The configs this PART ships, checked as configs rather than as prose."""

    def test_they_all_load(self) -> None:
        assert len(load_batteries(CONFIGS)) == 8

    def test_every_dataset_name_is_unique(self) -> None:
        names = [config.name for config in load_batteries(CONFIGS)]
        assert len(set(names)) == len(names)

    def test_the_graded_batteries_span_every_band(self) -> None:
        for config in load_batteries(CONFIGS):
            if config.flavour is not AttackFlavour.DETECTION:
                continue
            bands = {plan.difficulty for plan in config.attacks}
            assert len(bands) == 4, f"{config.name} does not span the dial"

    def test_the_graded_batteries_carry_every_kind_the_plant_can_support(self) -> None:
        expected = {
            "synth-attack-water-treatment-graded": 7,
            "synth-attack-power-generation-graded": 7,
            # No control network, so no command attack can exist here. The absence is the point.
            "synth-attack-batch-reactor-graded": 5,
        }
        for config in load_batteries(CONFIGS):
            if config.name in expected:
                assert len({plan.type for plan in config.attacks}) == expected[config.name]

    def test_the_reactor_battery_declares_no_command_attack(self) -> None:
        config = next(
            c for c in load_batteries(CONFIGS) if c.name == "synth-attack-batch-reactor-graded"
        )
        assert not any(plan.type.is_command_attack for plan in config.attacks)

    def test_the_unknown_master_battery_is_only_engineering_writes(self) -> None:
        """ADR 0034's next measurement: not scada/hmi, and not mixed into the graded 0/16."""
        config = next(
            c for c in load_batteries(CONFIGS) if c.name == "synth-attack-water-unknown-master"
        )
        assert config.plant_id == "water-treatment"
        assert {plan.type for plan in config.attacks} == {AttackType.ROGUE_COMMAND}
        assert {plan.issuer for plan in config.attacks} == {"engineering"}
        assert len({plan.difficulty for plan in config.attacks}) == 4

    def test_every_input_hostile_kind_gets_a_corpus_of_its_own(self) -> None:
        # One corruption per corpus: four in one file mask each other, and then nothing is
        # learned about the three the first one hid.
        hostile = [c for c in load_batteries(CONFIGS) if c.flavour is AttackFlavour.INPUT_HOSTILE]
        assert len(hostile) == 4
        assert all(len(config.hostile) == 1 for config in hostile)
        assert {config.hostile[0].type for config in hostile} == {
            AttackType.MALFORMED_RECORD,
            AttackType.OUT_OF_RANGE,
            AttackType.TRUNCATED,
            AttackType.POISONED_BASELINE,
        }

    def test_no_committed_attack_sits_at_zero_magnitude(self) -> None:
        # Subtlety 1.0 is the anti-fingerprint control, not a shipped attack: its window would be
        # labelled over data nothing touched.
        for config in load_batteries(CONFIGS):
            assert all(plan.subtlety < 1.0 for plan in config.attacks)

    def test_every_config_declares_the_role_its_flavour_implies(self) -> None:
        for config in load_batteries(CONFIGS):
            assert config.role == config.expected_role

    def test_an_empty_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no attack dataset configs"):
            load_batteries(tmp_path)

    def test_a_file_that_is_not_toml_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.toml"
        path.write_text("this is not = = toml", encoding="utf-8")
        with pytest.raises(ValueError, match="not readable as TOML"):
            load_battery(path)

    def test_a_file_that_is_not_a_battery_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "wrong.toml"
        path.write_text('name = "x"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="not a valid attack dataset config"):
            load_battery(path)

    def test_two_datasets_of_one_name_are_refused(self, tmp_path: Path) -> None:
        body = (CONFIGS / "01-water-treatment-graded.toml").read_text(encoding="utf-8")
        (tmp_path / "a.toml").write_text(body, encoding="utf-8")
        (tmp_path / "b.toml").write_text(body, encoding="utf-8")
        with pytest.raises(ValueError, match="name twice"):
            load_batteries(tmp_path)


class TestTheWrittenCorpus:
    """The files, and whether Atlas can read them."""

    @pytest.fixture(scope="class")
    def written(self, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, AttackManifest]:
        """Generate a small two-attack corpus once for the whole class."""
        directory = tmp_path_factory.mktemp("corpus")
        return generate_attack_dataset(a_config(attacks=[AN_ATTACK, A_ROGUE]), directory)

    def test_every_file_is_written(self, written: tuple[Path, AttackManifest]) -> None:
        directory, _ = written
        for name in (TELEMETRY_FILE, TRUTH_FILE, TOPOLOGY_FILE, CAPTURE_FILE, MANIFEST_FILE):
            assert (directory / name).exists()

    def test_the_telemetry_loads_through_an_unmodified_adapter(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        directory, manifest = written
        dataset = LabelledCsvAdapter(
            path=directory / TELEMETRY_FILE,
            timestamp_column=TIMESTAMP_COLUMN,
            label_column=LABEL_COLUMN,
        ).load()
        assert len(dataset.observations) == manifest.samples * len(manifest.description.signals)

    def test_the_attack_windows_come_back_out_of_the_label_column(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        # The corpus carries its own ground truth. Nothing has to read the manifest to know when
        # the attacks were.
        directory, manifest = written
        dataset = LabelledCsvAdapter(
            path=directory / TELEMETRY_FILE,
            timestamp_column=TIMESTAMP_COLUMN,
            label_column=LABEL_COLUMN,
        ).load()
        assert len(dataset.attack_intervals) == len(manifest.attacks)
        for interval, attack in zip(
            sorted(dataset.attack_intervals, key=lambda i: i.start), manifest.attacks, strict=True
        ):
            assert interval.start == attack.started_at
            assert interval.end == attack.ended_at

    def test_the_topology_loads_through_an_unmodified_reader(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        directory, manifest = written
        subsystems = load_topology(
            directory / TOPOLOGY_FILE,
            manifest.description.signal_keys(),
            corpus=manifest.plant_id,
        )
        assert len(subsystems.subsystems) == len(manifest.description.units)

    def test_the_capture_dissects_without_one_malformed_frame(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        directory, _ = written
        stats = CaptureStats()
        results = list(dissect_capture(directory / CAPTURE_FILE, REGISTRY, stats))
        assert results
        assert not [
            result for result in results if isinstance(result, MalformedFrame | UnparsedMessage)
        ]
        assert stats.accounts_for_every_frame()

    def test_the_manifest_carries_the_measured_ground_truth(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        directory, manifest = written
        stored = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
        assert stored["flavour"] == "DETECTION"
        assert len(stored["attacks"]) == 2
        assert all(
            record["truth_departure"] or record["report_departure"] for record in stored["attacks"]
        )
        assert manifest.commands_injected > 0

    def test_the_manifest_carries_every_caveat(self, written: tuple[Path, AttackManifest]) -> None:
        _, manifest = written
        joined = " ".join(manifest.caveats)
        assert "MODEL of an industrial process" in joined
        assert "attacks WE designed" in joined
        assert "not evidence that PHOS is secure" in joined

    def test_the_manifest_digests_match_the_files_beside_it(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        import hashlib

        directory, manifest = written
        for entry in manifest.files:
            digest = hashlib.sha256((directory / entry.filename).read_bytes()).hexdigest()
            assert digest == entry.sha256

    def test_the_label_policy_says_what_is_and_is_not_labelled(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        _, manifest = written
        assert "recovery tail" in manifest.label_policy


class TestTheTruthFile:
    """The one output that is not for the detector."""

    def test_it_carries_the_true_state_of_every_signal(self) -> None:
        run = inject(PLANT, a_spec(), [])
        lines = truth_lines(run)
        assert len(lines) == len(run.attacked.steps) + 1
        assert lines[0].split(",")[1:] == list(run.description.signal_keys())

    def test_it_carries_no_label_column(self) -> None:
        # It is not a corpus. Giving it a label column would invite it being loaded as one, and a
        # detector that could read the true state would be detecting nothing.
        run = inject(PLANT, a_spec(), [])
        assert LABEL_COLUMN not in truth_lines(run)[0].split(",")

    def test_it_disagrees_with_the_telemetry_where_the_telemetry_lies(self) -> None:
        liar = {
            "attack_id": "liar",
            "type": "LIAR",
            "subtlety": 0.0,
            "start_hours": 2.0,
            "duration_hours": 3.0,
            "target": CLEARWELL_LEVEL,
            "reference": LEVEL_SETPOINT,
        }
        config = a_config(attacks=[liar])
        run = inject(PLANT, config.run_spec(), config.attacks)
        column = run.description.signal_keys().index(CLEARWELL_LEVEL) + 1
        published = [float(line.split(",")[column + 1]) for line in telemetry_lines(run)[241:600]]
        actual = [float(line.split(",")[column]) for line in truth_lines(run)[241:600]]
        assert max(actual) > max(published)


class TestTheHostileCorpus:
    """What a corrupted corpus records, and what it refuses to record."""

    @pytest.fixture(scope="class")
    def written(self, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, AttackManifest]:
        """Generate a poisoned corpus once for the whole class."""
        directory = tmp_path_factory.mktemp("hostile")
        config = a_config(name="test-hostile", attacks=[], hostile=[A_HOSTILE])
        return generate_attack_dataset(config, directory)

    def test_it_carries_no_attack_intervals_at_all(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        directory, manifest = written
        assert manifest.attacks == ()
        assert manifest.attacked_samples == 0
        dataset = LabelledCsvAdapter(
            path=directory / TELEMETRY_FILE,
            timestamp_column=TIMESTAMP_COLUMN,
            label_column=LABEL_COLUMN,
        ).load()
        assert dataset.attack_intervals == []

    def test_every_label_is_normal(self, written: tuple[Path, AttackManifest]) -> None:
        directory, _ = written
        rows = (directory / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()[1:]
        assert {row.split(",")[1] for row in rows} == {NORMAL_LABEL_VALUE}
        assert ATTACK_LABEL_VALUE not in {row.split(",")[1] for row in rows}

    def test_the_corruption_is_recorded_under_its_own_field(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        _, manifest = written
        assert manifest.flavour is AttackFlavour.INPUT_HOSTILE
        assert len(manifest.hostile) == 1
        assert manifest.hostile[0].flavour is AttackFlavour.INPUT_HOSTILE
        assert manifest.hostile[0].rows_affected > 0

    def test_the_label_policy_refuses_the_detection_reading(
        self, written: tuple[Path, AttackManifest]
    ) -> None:
        _, manifest = written
        assert "Nothing in this corpus is a plant attack" in manifest.label_policy


class TestDeterminism:
    """Same config, same bytes."""

    def test_two_generations_of_one_config_are_byte_identical(self, tmp_path: Path) -> None:
        config = a_config(attacks=[AN_ATTACK, A_ROGUE])
        first, _ = generate_attack_dataset(config, tmp_path / "one")
        second, _ = generate_attack_dataset(config, tmp_path / "two")
        for name in (TELEMETRY_FILE, TRUTH_FILE, TOPOLOGY_FILE, CAPTURE_FILE):
            assert (first / name).read_bytes() == (second / name).read_bytes()

    def test_a_different_seed_gives_a_different_corpus(self, tmp_path: Path) -> None:
        first, _ = generate_attack_dataset(a_config(), tmp_path / "one")
        second, _ = generate_attack_dataset(a_config(seed=99, name="other"), tmp_path / "two")
        assert (first / TELEMETRY_FILE).read_bytes() != (second / TELEMETRY_FILE).read_bytes()

    def test_the_capture_can_be_skipped(self, tmp_path: Path) -> None:
        directory, manifest = generate_attack_dataset(a_config(), tmp_path, with_capture=False)
        assert not (directory / CAPTURE_FILE).exists()
        assert CAPTURE_FILE not in {entry.filename for entry in manifest.files}

    def test_a_plant_with_no_network_writes_no_capture(self, tmp_path: Path) -> None:
        config = AttackDatasetConfig.model_validate(
            {
                **BASE,
                "name": "reactor",
                "plant_id": "batch-reactor",
                "attacks": [{**AN_ATTACK, "target": "jacket_valve_pct"}],
            }
        )
        directory, manifest = generate_attack_dataset(config, tmp_path)
        assert not (directory / CAPTURE_FILE).exists()
        assert manifest.commands_injected == 0


def test_a_run_that_holds_no_samples_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A corpus of a header and no rows scores as one in which nothing went wrong.

    Unreachable through a valid `RunSpec`, which refuses a run too short to hold a sample. Guarded
    anyway: the most expensive silence a measurement pipeline can contain is an empty corpus that
    loads without complaint.
    """
    import dataclasses

    import phos.synth.attacks.generate
    from phos.synth.attacks.generate import AttackGenerationError
    from phos.synth.attacks.inject import inject as real

    def empty(plant_id: str, spec: object, plans: object, **kwargs: object) -> object:
        produced = real(plant_id, spec, [])  # type: ignore[arg-type]
        return dataclasses.replace(
            produced, attacked=dataclasses.replace(produced.attacked, steps=())
        )

    monkeypatch.setattr(phos.synth.attacks.generate, "inject", empty)
    with pytest.raises(AttackGenerationError, match="holds no samples"):
        generate_attack_dataset(a_config(), tmp_path)
