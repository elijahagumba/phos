"""Whether a generated corpus ships its topology in the form Atlas already reads.

Two things are being checked and only one of them is mechanical. The mechanical one is that the
rendered file goes back in through `phos.atlas.topology.load_topology` and validates against the
corpus's own signal set. The other is that the declaration says what it is: a synthetic plant's
topology is exact rather than documented, which makes it *better* ground truth than any real
corpus offers and therefore something a grouping result measured against it must be qualified by.
That qualification is a string in the file, so it is asserted like anything else.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.topology import SCHEMA_VERSION, TopologyError, load_topology, render_topology
from phos.synth.plant import RunSpec
from phos.synth.plants import batch, power, water
from phos.synth.run import PLANT_IDS, build_plant, run_plant
from phos.synth.telemetry import write_csv
from phos.synth.topology import (
    SYNTHETIC_TOPOLOGY_CAVEAT,
    subsystem_map,
    subsystems,
    topology_toml,
    write_topology,
)


def short_spec() -> RunSpec:
    """Return a ten-minute run spec, which is all a topology test needs."""
    return RunSpec(
        seed=5,
        start=datetime(2026, 8, 1, tzinfo=UTC),
        duration=timedelta(minutes=10),
        sample_interval=timedelta(seconds=30),
    )


DESCRIPTIONS = {
    "water-treatment": water.WATER_DESCRIPTION,
    "power-generation": power.POWER_DESCRIPTION,
    "batch-reactor": batch.BATCH_DESCRIPTION,
}


@pytest.mark.parametrize("plant_id", list(DESCRIPTIONS))
class TestTheTopologyPartitionsThePlant:
    def test_one_subsystem_per_physical_unit(self, plant_id: str) -> None:
        description = DESCRIPTIONS[plant_id]
        assert len(subsystems(description)) == len(description.units)

    def test_every_signal_is_assigned_exactly_once(self, plant_id: str) -> None:
        description = DESCRIPTIONS[plant_id]
        assigned = [key for subsystem in subsystems(description) for key in subsystem.signals]
        assert sorted(assigned) == sorted(description.signal_keys())

    def test_the_map_validates_against_the_plants_own_signal_set(self, plant_id: str) -> None:
        description = DESCRIPTIONS[plant_id]
        mapped = subsystem_map(description)
        assert len(mapped) == len(description.units)
        for signal in description.signals:
            assert mapped.subsystem_for(signal.key).subsystem_id == signal.physical_unit

    def test_every_subsystem_declares_where_the_assignment_came_from(self, plant_id: str) -> None:
        for subsystem in subsystems(DESCRIPTIONS[plant_id]):
            assert "phos.synth.plants" in subsystem.source
            assert SYNTHETIC_TOPOLOGY_CAVEAT in subsystem.source

    def test_the_rendered_file_loads_back_through_the_unmodified_loader(
        self, plant_id: str, tmp_path: Path
    ) -> None:
        description = DESCRIPTIONS[plant_id]
        path = tmp_path / "topology.toml"
        write_topology(description, path)
        loaded = load_topology(path, description.signal_keys(), corpus=plant_id)
        assert [subsystem.subsystem_id for subsystem in loaded] == [
            unit.unit_id for unit in description.units
        ]

    def test_the_rendering_is_deterministic(self, plant_id: str) -> None:
        description = DESCRIPTIONS[plant_id]
        assert topology_toml(description) == topology_toml(description)


class TestTheFileIsAuditable:
    def test_it_declares_the_schema_version_the_loader_understands(self) -> None:
        assert f"schema_version = {SCHEMA_VERSION}" in topology_toml(water.WATER_DESCRIPTION)

    def test_it_names_the_corpus_it_describes(self) -> None:
        assert 'corpus = "water-treatment"' in topology_toml(water.WATER_DESCRIPTION)

    def test_it_says_it_is_generated_so_nobody_hand_edits_it(self) -> None:
        assert "Do not hand-edit" in topology_toml(power.POWER_DESCRIPTION)

    def test_the_loader_refuses_it_against_a_corpus_it_does_not_describe(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "topology.toml"
        write_topology(water.WATER_DESCRIPTION, path)
        with pytest.raises(TopologyError, match="declares corpus"):
            load_topology(path, water.WATER_DESCRIPTION.signal_keys(), corpus="power-generation")

    def test_it_renders_for_a_human_to_check_by_eye(self) -> None:
        listing = render_topology(subsystem_map(batch.BATCH_DESCRIPTION))
        assert "Jacketed stirred-tank reactor" in listing
        assert batch.REACTOR_TEMP in listing


class TestTheTopologyMatchesTheCorpusItShipsBeside:
    @pytest.mark.parametrize("plant_id", list(PLANT_IDS))
    def test_the_declared_signals_are_exactly_the_csv_columns(
        self, plant_id: str, tmp_path: Path
    ) -> None:
        run = run_plant(plant_id, short_spec())
        csv_path = tmp_path / "telemetry.csv"
        write_csv(run, csv_path)
        columns = set(csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")[2:])

        topology_path = tmp_path / "topology.toml"
        write_topology(run.description, topology_path)
        loaded = load_topology(topology_path, columns, corpus=plant_id)
        assert sum(len(subsystem.signals) for subsystem in loaded) == len(columns)

    def test_a_plant_still_declares_a_topology_when_it_has_no_capture(self) -> None:
        assert build_plant("batch-reactor", short_spec()).description.control_network is None
        assert len(subsystem_map(batch.BATCH_DESCRIPTION)) == 4
