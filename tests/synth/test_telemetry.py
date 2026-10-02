"""Whether the generated telemetry is a corpus Atlas already knows how to read.

The claim under test is "no special-casing", and there is only one way to test it honestly: take
the file the generator writes, load it with the adapter that loads HAI and BATADAL, and then push
the result through the reshape Atlas's joint models consume. Nothing in this module constructs an
`Observation` by hand or reaches past the public loading path, because a test that did would be
testing the generator against itself.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.vectorise import SignalSpace, vectorise
from phos.eval import Dataset, DatasetAdapter, LabelledCsvAdapter
from phos.ontology import Domain
from phos.synth.plant import MODEL_NOT_REALITY_CAVEAT, RunSpec
from phos.synth.run import run_plant
from phos.synth.telemetry import (
    LABEL_COLUMN,
    NORMAL_LABEL,
    TIMESTAMP_COLUMN,
    SyntheticPlantAdapter,
    entity_id,
    observations,
    source_note,
    to_dataset,
    write_csv,
)

START = datetime(2026, 7, 1, tzinfo=UTC)


def spec(steps: int = 200, seed: int = 13) -> RunSpec:
    """Return a short run spec at thirty-second sampling."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(seconds=30) * steps,
        sample_interval=timedelta(seconds=30),
    )


class TestObservations:
    def test_one_observation_per_signal_per_sample(self) -> None:
        run = run_plant("water-treatment", spec(steps=50))
        assert len(observations(run)) == 50 * len(run.description.signals)

    def test_identifiers_are_unique_because_the_store_rejects_a_repeat(self) -> None:
        run = run_plant("water-treatment", spec(steps=120))
        produced = observations(run)
        assert len({observation.id for observation in produced}) == len(produced)

    def test_every_observation_names_the_plant_it_came_from(self) -> None:
        run = run_plant("batch-reactor", spec(steps=20))
        entity = entity_id("batch-reactor")
        for observation in observations(run):
            assert observation.entity_ids == [entity]
            assert observation.domain is Domain.ATLAS
            assert observation.context["plant"] == "batch-reactor"

    def test_the_reported_reading_is_published_and_the_true_state_is_not(self) -> None:
        run = run_plant("water-treatment", spec(steps=60))
        published = {
            (observation.timestamp, observation.feature): observation.value
            for observation in observations(run)
        }
        step = run.steps[30]
        for key, value in step.report.values.items():
            assert published[(step.timestamp, key)] == value
        differing = [
            key for key, value in step.truth.values.items() if value != step.report.values[key]
        ]
        assert differing, "the run should not have truth and report identical everywhere"

    def test_observations_come_out_in_timestamp_order_as_a_dataset_requires(self) -> None:
        produced = observations(run_plant("power-generation", spec(steps=80)))
        stamps = [observation.timestamp for observation in produced]
        assert stamps == sorted(stamps)


class TestDataset:
    def test_the_corpus_carries_no_attack_intervals_because_nothing_attacked_it(self) -> None:
        dataset = to_dataset(run_plant("water-treatment", spec(steps=60)))
        assert dataset.attack_intervals == []
        assert dataset.normal_duration() == dataset.duration()

    def test_the_name_defaults_to_the_plant_and_can_be_overridden(self) -> None:
        run = run_plant("batch-reactor", spec(steps=20))
        assert to_dataset(run).name == "synth-batch-reactor"
        assert to_dataset(run, "my-corpus").name == "my-corpus"

    def test_provenance_names_the_seed_and_carries_the_standing_caveat(self) -> None:
        run = run_plant("water-treatment", spec(steps=20, seed=4242))
        note = source_note(run.description, run.spec)
        assert "seed=4242" in note
        assert "water-treatment" in note
        assert MODEL_NOT_REALITY_CAVEAT in note
        assert MODEL_NOT_REALITY_CAVEAT in to_dataset(run).source_note


class TestTheAdapterProtocol:
    def test_the_adapter_satisfies_the_protocol_the_harness_consumes(self) -> None:
        adapter = SyntheticPlantAdapter(plant_id="water-treatment", spec=spec(steps=30))
        assert isinstance(adapter, DatasetAdapter)
        assert isinstance(adapter.load(), Dataset)

    def test_loading_twice_gives_the_same_corpus(self) -> None:
        adapter = SyntheticPlantAdapter(plant_id="power-generation", spec=spec(steps=40))
        first, second = adapter.load(), adapter.load()
        assert [o.value for o in first.observations] == [o.value for o in second.observations]

    def test_an_unknown_plant_is_refused_where_it_is_configured(self) -> None:
        with pytest.raises(ValueError, match="no plant 'refinery'"):
            SyntheticPlantAdapter(plant_id="refinery", spec=spec())

    def test_the_configured_name_reaches_the_corpus(self) -> None:
        adapter = SyntheticPlantAdapter(
            plant_id="batch-reactor", spec=spec(steps=20), name="named-corpus"
        )
        assert adapter.load().name == "named-corpus"


class TestTheCsvGoesInThroughTheDoorARealCorpusUses:
    def test_the_header_is_the_prepared_corpus_shape(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=10))
        write_csv(run, tmp_path / "telemetry.csv")
        header = (tmp_path / "telemetry.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == [
            TIMESTAMP_COLUMN,
            LABEL_COLUMN,
            *run.description.signal_keys(),
        ]

    def test_every_row_is_labelled_normal(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=40))
        write_csv(run, tmp_path / "telemetry.csv")
        rows = (tmp_path / "telemetry.csv").read_text(encoding="utf-8").splitlines()[1:]
        assert len(rows) == 40
        assert {row.split(",")[1] for row in rows} == {NORMAL_LABEL}

    def test_the_unmodified_csv_adapter_loads_it(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=120))
        path = tmp_path / "telemetry.csv"
        assert write_csv(run, path) == 120
        loaded = LabelledCsvAdapter(
            path=path, timestamp_column=TIMESTAMP_COLUMN, label_column=LABEL_COLUMN
        ).load()
        assert len(loaded.observations) == 120 * len(run.description.signals)
        assert loaded.attack_intervals == []

    def test_the_values_survive_the_round_trip_exactly(self, tmp_path: Path) -> None:
        run = run_plant("power-generation", spec(steps=60))
        path = tmp_path / "telemetry.csv"
        write_csv(run, path)
        loaded = LabelledCsvAdapter(
            path=path, timestamp_column=TIMESTAMP_COLUMN, label_column=LABEL_COLUMN
        ).load()
        by_key = {
            (observation.timestamp, observation.feature): observation.value
            for observation in loaded.observations
        }
        # Exactly the value the file holds, to the last bit: what is written is what is read, so
        # a number measured on the loaded corpus is a number about the corpus on disk.
        for step in run.steps:
            for key, value in step.report.values.items():
                assert by_key[(step.timestamp, key)] == float(f"{value:.5f}")

    def test_the_file_carries_the_precision_a_historian_would_and_no_more(
        self, tmp_path: Path
    ) -> None:
        run = run_plant("power-generation", spec(steps=20))
        write_csv(run, tmp_path / "telemetry.csv")
        cells = [
            cell
            for line in (tmp_path / "telemetry.csv").read_text(encoding="utf-8").splitlines()[1:]
            for cell in line.split(",")[2:]
        ]
        assert cells
        assert all(len(cell.split(".")[1]) == 5 for cell in cells)

    def test_the_loaded_corpus_vectorises_with_nothing_dropped(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=200))
        path = tmp_path / "telemetry.csv"
        write_csv(run, path)
        loaded = LabelledCsvAdapter(
            path=path, timestamp_column=TIMESTAMP_COLUMN, label_column=LABEL_COLUMN
        ).load()
        space = SignalSpace.from_observations(loaded.observations)
        reshaped = vectorise(loaded.observations, space)
        assert space.size == len(run.description.signals)
        assert reshaped.n_rows == 200
        assert reshaped.dropped_timestamps == 0

    def test_regenerating_the_corpus_produces_a_byte_identical_file(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a.csv", tmp_path / "b.csv"
        write_csv(run_plant("batch-reactor", spec(steps=90)), first)
        write_csv(run_plant("batch-reactor", spec(steps=90)), second)
        assert first.read_bytes() == second.read_bytes()

    def test_a_different_seed_produces_a_different_file(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a.csv", tmp_path / "b.csv"
        write_csv(run_plant("batch-reactor", spec(steps=90, seed=1)), first)
        write_csv(run_plant("batch-reactor", spec(steps=90, seed=2)), second)
        assert first.read_bytes() != second.read_bytes()
