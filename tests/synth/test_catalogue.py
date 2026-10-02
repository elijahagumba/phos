"""The committed configs, which are the datasets — the payload is only their shadow.

A corpus here is defined by five numbers in a TOML file, and the file is what is committed. So the
tests that matter are: the file has to be readable into something that can only describe a real
plant, a file that is wrong has to fail where it is written rather than an hour into a generation
run, and the six committed configs have to actually cover the three plants in the way the PART
asks for — a fitting corpus and a held-out one each.
"""

from pathlib import Path

import pytest

from phos.synth.catalogue import DatasetConfig, load_config, load_configs
from phos.synth.run import PLANT_IDS

REPO_CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "synth"

VALID = """
name = "example"
plant_id = "water-treatment"
role = "train"
seed = 5
traffic_seed = 6
start = 2026-01-01T00:00:00Z
duration_hours = 2.0
sample_interval_seconds = 30.0
note = "an example"
"""


def write(directory: Path, name: str, body: str) -> Path:
    """Write a config file into ``directory`` and return its path."""
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


class TestReadingOneConfig:
    def test_reads_the_five_numbers_that_define_a_corpus(self, tmp_path: Path) -> None:
        config = load_config(write(tmp_path, "a.toml", VALID))
        assert config.plant_id == "water-treatment"
        assert config.seed == 5
        assert config.traffic_seed == 6
        spec = config.run_spec()
        assert spec.n_steps == 240
        assert spec.interval_seconds == 30.0

    def test_refuses_a_file_that_is_not_toml(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not readable as TOML"):
            load_config(write(tmp_path, "a.toml", "this is not = = toml"))

    def test_refuses_a_config_for_a_plant_that_does_not_exist(self, tmp_path: Path) -> None:
        body = VALID.replace('"water-treatment"', '"refinery"')
        with pytest.raises(ValueError, match="no plant 'refinery'"):
            load_config(write(tmp_path, "a.toml", body))

    @pytest.mark.parametrize("name", ["../escape", "a/b", "."])
    def test_refuses_a_name_that_would_be_used_as_a_path(self, tmp_path: Path, name: str) -> None:
        body = VALID.replace('name = "example"', f'name = "{name}"')
        with pytest.raises(ValueError, match="used as a directory name"):
            load_config(write(tmp_path, "a.toml", body))

    def test_refuses_a_key_it_does_not_understand_rather_than_ignoring_it(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="not a valid dataset config"):
            load_config(write(tmp_path, "a.toml", VALID + '\nattack = "yes"\n'))

    def test_refuses_a_run_with_no_duration(self, tmp_path: Path) -> None:
        body = VALID.replace("duration_hours = 2.0", "duration_hours = 0.0")
        with pytest.raises(ValueError, match="not a valid dataset config"):
            load_config(write(tmp_path, "a.toml", body))

    def test_refuses_a_sampling_interval_longer_than_the_run(self, tmp_path: Path) -> None:
        body = VALID.replace("sample_interval_seconds = 30.0", "sample_interval_seconds = 99999.0")
        with pytest.raises(ValueError, match="holds no samples"):
            load_config(write(tmp_path, "a.toml", body)).run_spec()


class TestReadingADirectory:
    def test_reads_every_config_in_filename_order(self, tmp_path: Path) -> None:
        write(tmp_path, "02-b.toml", VALID.replace('"example"', '"second"'))
        write(tmp_path, "01-a.toml", VALID.replace('"example"', '"first"'))
        assert [config.name for config in load_configs(tmp_path)] == ["first", "second"]

    def test_says_so_when_a_directory_holds_no_configs(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no dataset configs"):
            load_configs(tmp_path)

    def test_refuses_two_configs_claiming_one_dataset_name(self, tmp_path: Path) -> None:
        write(tmp_path, "01-a.toml", VALID)
        write(tmp_path, "02-b.toml", VALID.replace("seed = 5", "seed = 9"))
        with pytest.raises(ValueError, match="dataset name twice"):
            load_configs(tmp_path)


class TestTheCommittedStandardSet:
    def test_every_committed_config_is_readable(self) -> None:
        assert len(load_configs(REPO_CONFIGS)) == 6

    def test_every_plant_has_a_fitting_corpus_and_a_held_out_one(self) -> None:
        configs = load_configs(REPO_CONFIGS)
        roles = {(config.plant_id, config.role) for config in configs}
        for plant_id in PLANT_IDS:
            assert (plant_id, "train") in roles
            assert (plant_id, "holdout") in roles

    def test_the_two_corpora_for_a_plant_never_share_a_seed(self) -> None:
        by_plant: dict[str, set[int]] = {}
        for config in load_configs(REPO_CONFIGS):
            by_plant.setdefault(config.plant_id, set()).add(config.seed)
        assert all(len(seeds) == 2 for seeds in by_plant.values())

    def test_the_two_corpora_for_a_plant_never_overlap_in_time(self) -> None:
        by_plant: dict[str, list[DatasetConfig]] = {}
        for config in load_configs(REPO_CONFIGS):
            by_plant.setdefault(config.plant_id, []).append(config)
        for configs in by_plant.values():
            first, second = sorted(configs, key=lambda config: config.start)
            assert first.start + first.run_spec().duration <= second.start

    def test_every_config_says_what_it_is_for(self) -> None:
        assert all(config.note.strip() for config in load_configs(REPO_CONFIGS))
