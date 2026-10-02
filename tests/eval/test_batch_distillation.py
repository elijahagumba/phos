"""Preparation of the batch-distillation corpus into a labelled CSV.

The shipped adapter is not extended. This module is the join that ADR 0024 left outstanding:
one mixture family, fit only on experiments both label sources call clean, null tails dropped
by joining on Time, and experiments packed onto a continuous clock so the ADR 0003 denominator
does not count the voids between independent timelines as normal operation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas
import pytest

from phos.eval.batch_distillation import (
    DEFAULT_MIXTURE,
    DEFAULT_MIXTURE_DIRNAME,
    LABELS_STEM,
    LOGS_STEM,
    OPERATING_POINT_FEATURE,
    RECIPE_STEP_FEATURE,
    UNSCORED_LABEL,
    JoinSpec,
    PrepareError,
    carry_recipe_steps,
    default_join_spec,
    discover_experiments,
    find_logs_root,
    find_operation_root,
    join_experiment,
    normalise_recipe_step,
    operating_point_ordinal,
    pack_frames,
    parse_executing_steps,
    prepare_corpus,
    recipe_step_vocabulary,
    yaml_declares_anomaly,
)
from phos.eval.datasets import LabelledCsvAdapter

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "batch-distillation"
REGISTRY = REPO / "data" / "registry.json"

CLEAN_YAML = "anomalies:\n- class: None\n"
ANOMALY_YAML = "anomalies:\n  - class: Anomaly\n    id: OP001TN001A001\n"
CONFIRMED_YAML = "anomalies:\n  - class: ConfirmedAnomaly\n    id: OP014TN002A001\n"

SENSOR_HEADER = "Time,LS701,T701"
ACTUATOR_HEADER = "Time,H701,P701"
LABEL_HEADER = "Time,Label (anomaly)"


def _spec(**overrides: object) -> JoinSpec:
    fields: dict[str, object] = {
        "mixture": DEFAULT_MIXTURE,
        "mixture_dirname": DEFAULT_MIXTURE_DIRNAME,
        "labels_stem": "labels",
        "sensors_stem": "sensors",
        "actuators_stem": "actuators",
        "train_output_file": "train.csv",
        "test_output_file": "test.csv",
        "contaminated_output_file": "contaminated.csv",
        "row_stride": 1,
    }
    fields.update(overrides)
    return JoinSpec.model_validate(fields)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _experiment_tree(
    root: Path,
    *,
    mixture_dirname: str,
    operating_point: str,
    filename: str,
    sensor_body: str,
    actuator_body: str,
    label_body: str,
    yaml_text: str | None,
) -> None:
    rel = f"Operation/{mixture_dirname}/{operating_point}/{filename}"
    _write(root / "sensors" / rel, f"{SENSOR_HEADER}\n{sensor_body}")
    _write(root / "actuators" / rel, f"{ACTUATOR_HEADER}\n{actuator_body}")
    _write(root / "labels" / rel, f"{LABEL_HEADER}\n{label_body}")
    if yaml_text is not None:
        _write((root / "labels" / rel).with_suffix(".yaml"), yaml_text)


def _three_second_run(label: str, start: str = "12:00:00") -> tuple[str, str, str]:
    """Return sensor, actuator, label bodies for three consecutive seconds."""
    hour, minute, second = (int(part) for part in start.split(":"))
    sensor_rows = []
    actuator_rows = []
    label_rows = []
    for offset in range(3):
        stamp = f"{hour:02d}:{minute:02d}:{second + offset:02d}"
        sensor_rows.append(f"{stamp},1.0,{10.0 + offset}")
        actuator_rows.append(f"{stamp},5.0,{2.0 + offset}")
        label_rows.append(f"{stamp},{label}")
    return "\n".join(sensor_rows), "\n".join(actuator_rows), "\n".join(label_rows)


def test_yaml_none_is_not_an_anomaly() -> None:
    assert yaml_declares_anomaly(CLEAN_YAML) is False


def test_yaml_anomaly_and_confirmed_are_anomalies() -> None:
    assert yaml_declares_anomaly(ANOMALY_YAML) is True
    assert yaml_declares_anomaly(CONFIRMED_YAML) is True


def test_yaml_confirmed_is_not_confused_with_the_shorter_class_name() -> None:
    assert yaml_declares_anomaly("class: ConfirmedAnomaly\n") is True
    assert yaml_declares_anomaly("class: None\n") is False


def test_join_drops_null_time_tails_rather_than_turning_them_into_attacks(tmp_path: Path) -> None:
    """The ragged-file trap: extra null label rows must not become training attacks."""
    sensors, actuators, labels = _three_second_run("0")
    labels = labels + "\n,\n,"
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    spec = _spec()
    labels_root = find_operation_root(tmp_path, spec.labels_stem)
    sensors_root = find_operation_root(tmp_path, spec.sensors_stem)
    actuators_root = find_operation_root(tmp_path, spec.actuators_stem)
    experiments = discover_experiments(labels_root, spec)
    joined = join_experiment(experiments[0], spec, sensors_root, actuators_root, labels_root)
    assert len(joined) == 3
    assert int(joined["label"].sum()) == 0


def test_join_inner_join_on_time_drops_label_rows_the_sensors_do_not_have(
    tmp_path: Path,
) -> None:
    sensors, actuators, labels = _three_second_run("0")
    labels = labels + "\n12:00:03,1"
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    spec = _spec()
    joined = join_experiment(
        discover_experiments(find_operation_root(tmp_path, spec.labels_stem), spec)[0],
        spec,
        find_operation_root(tmp_path, spec.sensors_stem),
        find_operation_root(tmp_path, spec.actuators_stem),
        find_operation_root(tmp_path, spec.labels_stem),
    )
    assert len(joined) == 3
    assert int(joined["label"].sum()) == 0


def _join_labels(tmp_path: Path, label_rows: str) -> list[int]:
    """Join one four-second test experiment carrying ``label_rows`` and return its labels."""
    sensor_rows = "12:00:00,1.0,10.0\n12:00:01,1.0,11.0\n12:00:02,1.0,12.0\n12:00:03,1.0,13.0"
    actuator_rows = "12:00:00,5.0,2.0\n12:00:01,5.0,2.0\n12:00:02,5.0,2.0\n12:00:03,5.0,2.0"
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="test_anormal_experiment_001.csv",
        sensor_body=sensor_rows,
        actuator_body=actuator_rows,
        label_body=label_rows,
        yaml_text=ANOMALY_YAML,
    )
    spec = _spec()
    joined = join_experiment(
        discover_experiments(find_operation_root(tmp_path, spec.labels_stem), spec)[0],
        spec,
        find_operation_root(tmp_path, spec.sensors_stem),
        find_operation_root(tmp_path, spec.actuators_stem),
        find_operation_root(tmp_path, spec.labels_stem),
    )
    return [int(value) for value in joined["label"].tolist()]


def test_only_the_anomalous_phase_is_positive_and_blind_and_recovery_are_unscored(
    tmp_path: Path,
) -> None:
    # 0 normal, 1 blind, 2 anomalous, 3 recovery (ADR 0082).
    labels = _join_labels(tmp_path, "12:00:00,0\n12:00:01,1\n12:00:02,2\n12:00:03,3")
    assert labels == [0, UNSCORED_LABEL, 1, UNSCORED_LABEL]


def test_an_unmapped_label_class_is_refused_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(PrepareError, match="not mapped"):
        _join_labels(tmp_path, "12:00:00,0\n12:00:01,4\n12:00:02,2\n12:00:03,0")


def test_join_spec_refuses_a_class_that_is_both_positive_and_unscored() -> None:
    with pytest.raises(ValueError, match="both positive and unscored"):
        _spec(positive_label_values=(2,), unscored_label_values=(1, 2))


def test_join_spec_refuses_normal_as_a_scored_class() -> None:
    with pytest.raises(ValueError, match="class 0 is normal"):
        _spec(unscored_label_values=(0, 1))


def test_pack_inserts_a_seam_so_adjacent_experiments_do_not_merge_windows() -> None:
    spec = _spec()
    first = pandas.DataFrame(
        {
            "Time": ["12:00:00", "12:00:01", "12:00:02"],
            "LS701": [1.0, 1.0, 1.0],
            "label": [0, 0, 1],
        }
    )
    second = pandas.DataFrame(
        {
            "Time": ["13:00:00", "13:00:01", "13:00:02"],
            "LS701": [1.0, 1.0, 1.0],
            "label": [1, 0, 0],
        }
    )
    packed = pack_frames([first, second], spec)
    labels = packed["label"].tolist()
    assert labels[2] == 1
    assert labels[3] == 0
    assert labels[4] == 1
    assert packed["timestamp"].nunique() == len(packed)


def test_packed_duration_is_the_sum_of_experiments_not_a_calendar_gap(
    tmp_path: Path,
) -> None:
    for index, point in enumerate(("operating_point_001", "operating_point_002")):
        sensors, actuators, labels = _three_second_run("0", start=f"12:00:0{index}")
        _experiment_tree(
            tmp_path,
            mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
            operating_point=point,
            filename="train_normal_experiment_001.csv",
            sensor_body=sensors,
            actuator_body=actuators,
            label_body=labels,
            yaml_text=CLEAN_YAML,
        )
    result = prepare_corpus(tmp_path, _spec())
    dataset = LabelledCsvAdapter(
        path=result.train_path,
        timestamp_column="timestamp",
        label_column="label",
        name="mini-train",
    ).load()
    assert dataset.duration().total_seconds() < 60
    assert dataset.attack_intervals == []


def test_prepare_fits_only_dual_clean_train_and_ignores_other_mixtures(tmp_path: Path) -> None:
    other = "batch_dist_binary_ethanol+propan-2-ol"
    # Dual-clean train.
    sensors, actuators, labels = _three_second_run("0")
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    # CSV-clean, YAML-anomalous: must not enter the fit set.
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_002",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=ANOMALY_YAML,
    )
    # A different mixture, dual-clean: must not enter either split.
    _experiment_tree(
        tmp_path,
        mixture_dirname=other,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    # Test experiment with a perturbation.
    test_sensors, test_actuators, _ = _three_second_run("0")
    test_labels = "12:00:00,0\n12:00:01,2\n12:00:02,0"
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="test_anormal_experiment_001.csv",
        sensor_body=test_sensors,
        actuator_body=test_actuators,
        label_body=test_labels,
        yaml_text=ANOMALY_YAML,
    )
    result = prepare_corpus(tmp_path, _spec())
    assert result.n_clean_train == 1
    assert result.n_contaminated_train == 1
    assert result.n_test == 1
    train = pandas.read_csv(result.train_path)
    contaminated = pandas.read_csv(result.contaminated_path)
    test = pandas.read_csv(result.test_path)
    assert int(train["label"].sum()) == 0
    assert int(contaminated["label"].sum()) == 0
    assert int(test["label"].sum()) == 1
    dataset = LabelledCsvAdapter(
        path=result.test_path,
        timestamp_column="timestamp",
        label_column="label",
        name="mini-test",
        source_note=result.source_note,
    ).load()
    assert len(dataset.attack_intervals) == 1
    assert "perturbation" in dataset.source_note.lower()


def _strided_test_labels(tmp_path: Path, label_rows: str, stride: int) -> list[int]:
    """Prepare one six-second test experiment at ``stride`` and return its packed labels."""
    seconds = [f"12:00:0{index}" for index in range(6)]
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="test_anormal_experiment_001.csv",
        sensor_body="\n".join(f"{second},1.0,10.0" for second in seconds),
        actuator_body="\n".join(f"{second},5.0,2.0" for second in seconds),
        label_body=label_rows,
        yaml_text=ANOMALY_YAML,
    )
    result = prepare_corpus(tmp_path, _spec(row_stride=stride))
    return [int(value) for value in pandas.read_csv(result.test_path)["label"].tolist()]


def test_stride_pools_a_short_positive_run_instead_of_sampling_past_it(tmp_path: Path) -> None:
    # Sampling rows 0 and 3 would see only normal labels and erase the anomalous second.
    labels = "12:00:00,0\n12:00:01,2\n12:00:02,0\n12:00:03,0\n12:00:04,0\n12:00:05,0"
    assert _strided_test_labels(tmp_path, labels, stride=3) == [1, 0]


def test_stride_pools_a_short_unscored_run_so_its_time_is_not_normal(tmp_path: Path) -> None:
    # A two-second blind phase between samples would otherwise be counted as normal time.
    labels = "12:00:00,0\n12:00:01,0\n12:00:02,0\n12:00:03,0\n12:00:04,1\n12:00:05,0"
    assert _strided_test_labels(tmp_path, labels, stride=3) == [0, UNSCORED_LABEL]


def test_stride_pooling_prefers_positive_over_unscored_within_one_block(tmp_path: Path) -> None:
    labels = "12:00:00,1\n12:00:01,2\n12:00:02,3\n12:00:03,3\n12:00:04,0\n12:00:05,0"
    assert _strided_test_labels(tmp_path, labels, stride=3) == [1, UNSCORED_LABEL]


def test_missing_yaml_on_a_train_file_is_not_treated_as_clean(tmp_path: Path) -> None:
    sensors, actuators, labels = _three_second_run("0")
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=None,
    )
    result = prepare_corpus(tmp_path, _spec())
    assert result.n_clean_train == 0
    assert result.n_contaminated_train == 1


def test_registry_pins_the_one_mixture_and_the_conservative_fit() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = next(item for item in registry["datasets"] if item["name"] == "batch-distillation")
    assert entry["status"] == "integrated"
    join = entry["join"]
    assert join["mixture"] == DEFAULT_MIXTURE
    assert join["mixture_dirname"] == DEFAULT_MIXTURE_DIRNAME
    assert join["row_stride"] == 10
    assert entry.get("prepare") is None
    spec = default_join_spec()
    assert spec.mixture == DEFAULT_MIXTURE
    assert spec.row_stride == 10
    assert spec.labels_stem == LABELS_STEM
    assert spec.logs_stem == LOGS_STEM
    assert spec.recipe_step_column == RECIPE_STEP_FEATURE


def test_missing_archive_is_a_loud_failure(tmp_path: Path) -> None:
    with pytest.raises(PrepareError, match="no extracted archive"):
        find_operation_root(tmp_path, "labels")


def test_pack_refuses_an_empty_frame_list() -> None:
    with pytest.raises(PrepareError, match="no experiments"):
        pack_frames([], _spec())


def test_a_backwards_clock_is_refused() -> None:
    frame = pandas.DataFrame(
        {
            "Time": ["12:00:02", "12:00:01", "12:00:00"],
            "LS701": [1.0, 1.0, 1.0],
            "label": [0, 0, 0],
        }
    )
    with pytest.raises(PrepareError, match="backwards"):
        pack_frames([frame], _spec())


@pytest.mark.skipif(
    not (RAW / "raw").is_dir(),
    reason="batch-distillation payload is not on disk",
)
def test_real_payload_dual_clean_counts_match_adr_0024() -> None:
    spec = JoinSpec.model_validate(
        {
            "mixture": DEFAULT_MIXTURE,
            "mixture_dirname": DEFAULT_MIXTURE_DIRNAME,
            "labels_stem": LABELS_STEM,
            "sensors_stem": "01_Batch_Distillation_Plant_M-202210_Timeseries_Sensors",
            "actuators_stem": "02_Batch_Distillation_Plant_M-202210_Timeseries_Actuators",
            "train_output_file": "train.csv",
            "test_output_file": "test.csv",
            "contaminated_output_file": "contaminated.csv",
            "row_stride": 10,
        }
    )
    labels_root = find_operation_root(RAW, spec.labels_stem)
    experiments = discover_experiments(labels_root, spec)
    train = [item for item in experiments if item.split == "train_normal"]
    test = [item for item in experiments if item.split == "test_anormal"]
    clean = [item for item in train if not item.yaml_declares_anomaly]
    contaminated = [item for item in train if item.yaml_declares_anomaly]
    assert len(clean) == 15
    assert len(contaminated) == 13
    assert len(test) == 63


def test_operating_point_ordinal_reads_the_declared_directory_index() -> None:
    assert operating_point_ordinal("operating_point_001") == 1.0
    assert operating_point_ordinal("operating_point_035") == 35.0
    text = (
        "Time,Property,Value\n"
        "12:00:00,\tExecuting step, Druck\n"
        "12:00:01,Jump to Heat1 if PIC23 < 501 mbar (,Heat1\n"
        "12:00:02,\tExecuting step, Heat1\n"
        "12:00:03,Warning, LS702 reached limit\n"
        "12:00:04,\tExecuting step, END\n"
        ",\tExecuting step, Distillation\n"
    )
    events = parse_executing_steps(text)
    assert events == [
        ("12:00:00", "Druck"),
        ("12:00:02", "Heat1"),
        ("12:00:04", "End"),
    ]
    assert normalise_recipe_step("END") == "End"
    assert recipe_step_vocabulary(events) == ("Druck", "End", "Heat1")


def test_carry_recipe_steps_is_last_observation_carried_forward() -> None:
    events = [("12:00:01", "Heat1"), ("12:00:03", "Distillation")]
    vocabulary = recipe_step_vocabulary(events)
    carried = carry_recipe_steps(
        ["12:00:00", "12:00:01", "12:00:02", "12:00:03"],
        events,
        vocabulary,
    )
    assert carried[0] == 0.0  # no declared step yet
    assert carried[1] == 2.0  # Heat1 sorts after Distillation: Distillation=1, Heat1=2
    assert carried[2] == 2.0
    assert carried[3] == 1.0


def test_join_carries_executing_step_when_logs_are_present(tmp_path: Path) -> None:
    sensors, actuators, labels = _three_second_run("0")
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    spec = _spec()
    log_path = (
        tmp_path
        / spec.logs_stem
        / spec.mixture_dirname
        / "operating_point_001"
        / "train_normal_experiment_001.csv"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "Time,Property,Value\n"
        "12:00:00,\tExecuting step, Heat1\n"
        "12:00:02,\tExecuting step, Distillation\n",
        encoding="utf-8",
    )
    result = prepare_corpus(tmp_path, spec)
    assert result.recipe_step_names == ("Distillation", "Heat1")
    train = pandas.read_csv(result.train_path)
    assert RECIPE_STEP_FEATURE in train.columns
    steps = [float(value) for value in train[RECIPE_STEP_FEATURE].tolist() if pandas.notna(value)]
    assert steps == [2.0, 2.0, 1.0]
    assert result.n_train_recipe_step_rows == 3
    assert OPERATING_POINT_FEATURE in train.columns
    assert train[OPERATING_POINT_FEATURE].tolist() == [1.0, 1.0, 1.0]


def test_missing_operation_logs_omit_recipe_step_rather_than_inventing_one(
    tmp_path: Path,
) -> None:
    sensors, actuators, labels = _three_second_run("0")
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    result = prepare_corpus(tmp_path, _spec())
    assert result.recipe_step_names == ()
    train = pandas.read_csv(result.train_path)
    assert RECIPE_STEP_FEATURE not in train.columns
    assert OPERATING_POINT_FEATURE in train.columns
    assert find_logs_root(tmp_path, _spec()) is None


def test_ui_only_logs_do_not_become_a_phase_register(tmp_path: Path) -> None:
    """H701 new step / Selected recipe steps are operator UI, not Executing step."""
    sensors, actuators, labels = _three_second_run("0")
    _experiment_tree(
        tmp_path,
        mixture_dirname=DEFAULT_MIXTURE_DIRNAME,
        operating_point="operating_point_001",
        filename="train_normal_experiment_001.csv",
        sensor_body=sensors,
        actuator_body=actuators,
        label_body=labels,
        yaml_text=CLEAN_YAML,
    )
    spec = _spec()
    log_path = (
        tmp_path
        / spec.logs_stem
        / spec.mixture_dirname
        / "operating_point_001"
        / "train_normal_experiment_001.csv"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "Time,Property,Value\n"
        "12:00:00,H701 new step,\n"
        "12:00:01,Selected recipe steps,-\n"
        "12:00:02,Started experiment,-\n",
        encoding="utf-8",
    )
    result = prepare_corpus(tmp_path, spec)
    assert result.recipe_step_names == ()
    train = pandas.read_csv(result.train_path)
    assert RECIPE_STEP_FEATURE not in train.columns
    assert OPERATING_POINT_FEATURE in train.columns
