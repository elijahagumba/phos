"""Tests for labelled intervals, datasets and the two dataset adapters."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.eval.datasets import (
    Dataset,
    DatasetAdapter,
    LabelledCsvAdapter,
    LabelledInterval,
    SyntheticAnomaly,
    SyntheticICSAdapter,
    default_attack_when,
)
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    """Return ``T0`` offset by ``seconds`` — keeps fixtures readable."""
    return T0 + timedelta(seconds=seconds)


def make_observation(seconds: int, value: float = 1.0) -> Observation:
    return Observation(
        id=f"obs_{seconds:012d}",
        entity_ids=["ent_000000000001"],
        feature="flow_rate",
        value=value,
        timestamp=at(seconds),
        domain=Domain.ATLAS,
    )


def make_interval(start: int, end: int, attack_type: str | None = None) -> LabelledInterval:
    return LabelledInterval(start=at(start), end=at(end), label="attack", attack_type=attack_type)


def make_dataset(
    observations: list[Observation] | None = None,
    intervals: list[LabelledInterval] | None = None,
) -> Dataset:
    return Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=[make_observation(s) for s in range(0, 3600, 60)]
        if observations is None
        else observations,
        attack_intervals=[] if intervals is None else intervals,
        source_note="hand-built fixture",
    )


# --------------------------------------------------------------------------------------------
# LabelledInterval
# --------------------------------------------------------------------------------------------


def test_interval_contains_is_inclusive_at_both_ends() -> None:
    interval = make_interval(10, 20)
    assert interval.contains(at(10))
    assert interval.contains(at(15))
    assert interval.contains(at(20))


def test_interval_excludes_timestamps_outside_it() -> None:
    interval = make_interval(10, 20)
    assert not interval.contains(at(9))
    assert not interval.contains(at(21))


def test_interval_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError, match="inverted"):
        LabelledInterval(start=at(20), end=at(10), label="attack", attack_type=None)


def test_interval_allows_a_single_instant() -> None:
    assert make_interval(10, 10).contains(at(10))


def test_interval_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_interval(10, 20).label = "other"  # type: ignore[misc]


def test_interval_round_trips_through_json() -> None:
    interval = make_interval(10, 20, attack_type="modbus_write")
    assert LabelledInterval.model_validate_json(interval.model_dump_json()) == interval


# --------------------------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------------------------


def test_dataset_rejects_out_of_order_observations() -> None:
    with pytest.raises(ValidationError, match="time-ordered"):
        make_dataset(observations=[make_observation(60), make_observation(0)])


def test_dataset_allows_simultaneous_observations() -> None:
    dataset = make_dataset(observations=[make_observation(0), make_observation(0)])
    assert len(dataset.observations) == 2


def test_dataset_duration_spans_first_to_last_observation() -> None:
    dataset = make_dataset(observations=[make_observation(0), make_observation(600)])
    assert dataset.duration() == timedelta(seconds=600)


def test_empty_dataset_has_zero_duration_and_no_attacks() -> None:
    dataset = make_dataset(observations=[])
    assert dataset.duration() == timedelta(0)
    assert dataset.normal_duration() == timedelta(0)
    assert not dataset.is_attack(T0)


def test_dataset_is_attack_consults_every_interval() -> None:
    dataset = make_dataset(intervals=[make_interval(60, 120), make_interval(600, 660)])
    assert dataset.is_attack(at(90))
    assert dataset.is_attack(at(630))
    assert not dataset.is_attack(at(300))


def test_normal_duration_subtracts_disjoint_attack_intervals() -> None:
    # Span 3540s (0..3540). Two 60s attacks -> 3420s of normal operation.
    dataset = make_dataset(intervals=[make_interval(60, 120), make_interval(600, 660)])
    assert dataset.duration() == timedelta(seconds=3540)
    assert dataset.normal_duration() == timedelta(seconds=3420)


def test_normal_duration_merges_overlapping_intervals_rather_than_double_subtracting() -> None:
    # Two intervals overlapping across 60..180 cover 120s in total, not 180s.
    dataset = make_dataset(intervals=[make_interval(60, 150), make_interval(120, 180)])
    assert dataset.normal_duration() == timedelta(seconds=3540 - 120)


def test_normal_duration_merges_abutting_intervals() -> None:
    dataset = make_dataset(intervals=[make_interval(60, 120), make_interval(120, 180)])
    assert dataset.normal_duration() == timedelta(seconds=3540 - 120)


def test_normal_duration_clamps_intervals_to_the_observed_span() -> None:
    # The interval starts before the first observation and ends after the last one.
    dataset = make_dataset(intervals=[make_interval(-600, 4200)])
    assert dataset.normal_duration() == timedelta(0)


def test_normal_duration_ignores_intervals_entirely_outside_the_span() -> None:
    dataset = make_dataset(intervals=[make_interval(7200, 7800)])
    assert dataset.normal_duration() == dataset.duration()


def test_normal_duration_is_never_negative() -> None:
    dataset = make_dataset(
        intervals=[make_interval(0, 3540), make_interval(0, 3540), make_interval(0, 3540)]
    )
    assert dataset.normal_duration() == timedelta(0)


def test_dataset_round_trips_through_json() -> None:
    dataset = make_dataset(intervals=[make_interval(60, 120)])
    assert Dataset.model_validate_json(dataset.model_dump_json()) == dataset


# --------------------------------------------------------------------------------------------
# SyntheticICSAdapter
# --------------------------------------------------------------------------------------------


def test_synthetic_adapter_satisfies_the_dataset_adapter_protocol() -> None:
    assert isinstance(SyntheticICSAdapter(n_points=10), DatasetAdapter)


def test_synthetic_adapter_is_deterministic_for_a_fixed_seed() -> None:
    first = SyntheticICSAdapter(n_points=50, seed=7).load()
    second = SyntheticICSAdapter(n_points=50, seed=7).load()
    assert first == second


def test_synthetic_adapter_differs_across_seeds() -> None:
    first = SyntheticICSAdapter(n_points=50, seed=7).load()
    second = SyntheticICSAdapter(n_points=50, seed=8).load()
    assert [o.value for o in first.observations] != [o.value for o in second.observations]


def test_synthetic_adapter_emits_evenly_spaced_ascending_timestamps() -> None:
    dataset = SyntheticICSAdapter(n_points=5, sample_interval=timedelta(seconds=30)).load()
    stamps = [o.timestamp for o in dataset.observations]
    assert len(stamps) == 5
    assert stamps == sorted(stamps)
    gaps = {b - a for a, b in pairwise(stamps)}
    assert gaps == {timedelta(seconds=30)}


def test_synthetic_adapter_labels_the_injected_anomaly_interval() -> None:
    anomaly = SyntheticAnomaly(
        start_index=10, end_index=14, magnitude=50.0, attack_type="setpoint_tamper"
    )
    dataset = SyntheticICSAdapter(n_points=40, anomaly_intervals=(anomaly,)).load()

    assert len(dataset.attack_intervals) == 1
    interval = dataset.attack_intervals[0]
    assert interval.attack_type == "setpoint_tamper"
    assert interval.start == dataset.observations[10].timestamp
    assert interval.end == dataset.observations[14].timestamp
    assert dataset.is_attack(dataset.observations[12].timestamp)
    assert not dataset.is_attack(dataset.observations[9].timestamp)


def test_synthetic_adapter_raises_the_signal_only_inside_the_anomaly() -> None:
    anomaly = SyntheticAnomaly(start_index=10, end_index=14, magnitude=50.0)
    clean = SyntheticICSAdapter(n_points=40, seed=3).load()
    dirty = SyntheticICSAdapter(n_points=40, seed=3, anomaly_intervals=(anomaly,)).load()

    for index, (before, after) in enumerate(
        zip(clean.observations, dirty.observations, strict=True)
    ):
        expected_shift = 50.0 if 10 <= index <= 14 else 0.0
        assert after.value == pytest.approx(before.value + expected_shift)


def test_synthetic_adapter_rejects_an_anomaly_beyond_the_series() -> None:
    anomaly = SyntheticAnomaly(start_index=5, end_index=99, magnitude=1.0)
    with pytest.raises(ValueError, match="outside the series"):
        SyntheticICSAdapter(n_points=10, anomaly_intervals=(anomaly,)).load()


def test_synthetic_anomaly_rejects_inverted_indices() -> None:
    with pytest.raises(ValidationError, match="inverted"):
        SyntheticAnomaly(start_index=9, end_index=2, magnitude=1.0)


def test_synthetic_adapter_rejects_a_non_positive_point_count() -> None:
    with pytest.raises(ValidationError):
        SyntheticICSAdapter(n_points=0)


# --------------------------------------------------------------------------------------------
# default_attack_when
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, False),
        (0.0, False),
        (1, True),
        (-1, True),
        ("0", False),
        ("0.0", False),
        ("1", True),
        ("", False),
        ("   ", False),
        ("attack", True),
        ("Normal", True),
    ],
)
def test_default_attack_when(value: object, expected: bool) -> None:
    assert default_attack_when(value) is expected


# --------------------------------------------------------------------------------------------
# LabelledCsvAdapter
# --------------------------------------------------------------------------------------------

CSV_FIXTURE = """timestamp,sensor_a,sensor_b,label
2026-07-28T09:00:00,10.0,1.0,0
2026-07-28T09:00:01,10.5,1.1,0
2026-07-28T09:00:02,50.0,9.9,1
2026-07-28T09:00:03,51.0,9.8,1
2026-07-28T09:00:04,10.2,1.0,0
2026-07-28T09:00:05,60.0,9.0,1
"""


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.csv"
    path.write_text(CSV_FIXTURE, encoding="utf-8")
    return path


def make_csv_adapter(path: Path, **overrides: object) -> LabelledCsvAdapter:
    kwargs: dict[str, object] = {
        "path": path,
        "name": "fixture-csv",
        "timestamp_column": "timestamp",
        "label_column": "label",
    }
    kwargs.update(overrides)
    return LabelledCsvAdapter.model_validate(kwargs)


def test_csv_adapter_satisfies_the_dataset_adapter_protocol(csv_path: Path) -> None:
    assert isinstance(make_csv_adapter(csv_path), DatasetAdapter)


def test_csv_adapter_emits_one_observation_per_row_per_value_column(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path).load()
    # 6 rows x 2 auto-detected numeric value columns (label is excluded).
    assert len(dataset.observations) == 12
    assert {o.feature for o in dataset.observations} == {"sensor_a", "sensor_b"}


def test_csv_adapter_auto_detection_excludes_timestamp_and_label_columns(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path).load()
    assert "label" not in {o.feature for o in dataset.observations}
    assert "timestamp" not in {o.feature for o in dataset.observations}


def test_csv_adapter_honours_an_explicit_value_column_subset(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path, value_columns=["sensor_a"]).load()
    assert len(dataset.observations) == 6
    assert {o.feature for o in dataset.observations} == {"sensor_a"}
    assert [o.value for o in dataset.observations] == [10.0, 10.5, 50.0, 51.0, 10.2, 60.0]


def test_csv_adapter_parses_naive_timestamps_as_utc(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path, value_columns=["sensor_a"]).load()
    assert dataset.observations[0].timestamp == datetime(2026, 7, 28, 9, 0, 0, tzinfo=UTC)
    assert dataset.observations[-1].timestamp == datetime(2026, 7, 28, 9, 0, 5, tzinfo=UTC)


def test_csv_adapter_collapses_consecutive_attack_rows_into_intervals(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path).load()
    assert len(dataset.attack_intervals) == 2

    first, second = dataset.attack_intervals
    assert (first.start, first.end) == (
        datetime(2026, 7, 28, 9, 0, 2, tzinfo=UTC),
        datetime(2026, 7, 28, 9, 0, 3, tzinfo=UTC),
    )
    # A lone attack row becomes a zero-width interval at that instant.
    assert (second.start, second.end) == (
        datetime(2026, 7, 28, 9, 0, 5, tzinfo=UTC),
        datetime(2026, 7, 28, 9, 0, 5, tzinfo=UTC),
    )


def test_csv_adapter_produces_a_sorted_dataset_from_unsorted_rows(tmp_path: Path) -> None:
    path = tmp_path / "unsorted.csv"
    path.write_text(
        "timestamp,sensor_a,label\n"
        "2026-07-28T09:00:02,3.0,1\n"
        "2026-07-28T09:00:00,1.0,0\n"
        "2026-07-28T09:00:01,2.0,0\n",
        encoding="utf-8",
    )
    dataset = make_csv_adapter(path).load()
    assert [o.value for o in dataset.observations] == [1.0, 2.0, 3.0]
    assert dataset.attack_intervals[0].start == datetime(2026, 7, 28, 9, 0, 2, tzinfo=UTC)


def test_csv_adapter_skips_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "gaps.csv"
    path.write_text(
        "timestamp,sensor_a,label\n"
        "2026-07-28T09:00:00,1.0,0\n"
        "2026-07-28T09:00:01,,0\n"
        "2026-07-28T09:00:02,3.0,0\n",
        encoding="utf-8",
    )
    dataset = make_csv_adapter(path).load()
    assert [o.value for o in dataset.observations] == [1.0, 3.0]


def test_csv_adapter_treats_a_missing_label_as_normal(tmp_path: Path) -> None:
    path = tmp_path / "missing_label.csv"
    path.write_text(
        "timestamp,sensor_a,label\n2026-07-28T09:00:00,1.0,\n2026-07-28T09:00:01,2.0,\n",
        encoding="utf-8",
    )
    assert make_csv_adapter(path).load().attack_intervals == []


def test_csv_adapter_accepts_a_custom_attack_predicate(csv_path: Path) -> None:
    # Invert the meaning of the label column: 0 marks an attack.
    dataset = make_csv_adapter(csv_path, attack_when=lambda value: value == 0).load()
    assert len(dataset.attack_intervals) == 2
    assert dataset.attack_intervals[0].start == datetime(2026, 7, 28, 9, 0, 0, tzinfo=UTC)
    assert dataset.attack_intervals[0].end == datetime(2026, 7, 28, 9, 0, 1, tzinfo=UTC)


def test_csv_adapter_names_the_columns_it_found_when_the_timestamp_column_is_missing(
    csv_path: Path,
) -> None:
    adapter = make_csv_adapter(csv_path, timestamp_column="ts")
    with pytest.raises(ValueError) as caught:
        adapter.load()
    message = str(caught.value)
    assert "ts" in message
    assert "sensor_a" in message and "sensor_b" in message and "label" in message


def test_csv_adapter_names_the_columns_it_found_when_the_label_column_is_missing(
    csv_path: Path,
) -> None:
    adapter = make_csv_adapter(csv_path, label_column="attack")
    with pytest.raises(ValueError, match="attack"):
        adapter.load()


def test_csv_adapter_names_the_columns_it_found_when_a_value_column_is_missing(
    csv_path: Path,
) -> None:
    adapter = make_csv_adapter(csv_path, value_columns=["sensor_a", "sensor_z"])
    with pytest.raises(ValueError) as caught:
        adapter.load()
    assert "sensor_z" in str(caught.value)


def test_csv_adapter_rejects_a_non_numeric_value_column_rather_than_guessing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "text.csv"
    path.write_text(
        "timestamp,mode,label\n2026-07-28T09:00:00,running,0\n2026-07-28T09:00:01,halted,0\n",
        encoding="utf-8",
    )
    adapter = make_csv_adapter(path, value_columns=["mode"])
    with pytest.raises(ValueError, match="not numeric"):
        adapter.load()


def test_csv_adapter_reports_when_no_numeric_columns_can_be_detected(tmp_path: Path) -> None:
    path = tmp_path / "no_numeric.csv"
    path.write_text(
        "timestamp,mode,label\n2026-07-28T09:00:00,running,0\n2026-07-28T09:00:01,halted,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no numeric"):
        make_csv_adapter(path).load()


def test_csv_adapter_records_provenance_on_the_dataset(csv_path: Path) -> None:
    dataset = make_csv_adapter(csv_path, source_note="HAI v1, train1.csv").load()
    assert dataset.name == "fixture-csv"
    assert dataset.source_note == "HAI v1, train1.csv"
    assert dataset.domain is Domain.ATLAS


def test_without_features_drops_the_routing_register_and_keeps_process_signals() -> None:
    process = make_observation(0, 1.0)
    register = Observation(
        id="obs_phase",
        entity_ids=["ent_000000000001"],
        feature="recipe_step",
        value=2.0,
        timestamp=at(0),
        domain=Domain.ATLAS,
    )
    dropped = make_dataset([process, register]).without_features({"recipe_step"})
    assert [item.feature for item in dropped.observations] == ["flow_rate"]
    unchanged = make_dataset([process]).without_features({"recipe_step"})
    assert unchanged.observations[0].id == process.id


# --------------------------------------------------------------------------------------------
# Unscored intervals (ADR 0082): neither attack nor normal
# --------------------------------------------------------------------------------------------


def make_unscored(start: int, end: int) -> LabelledInterval:
    return LabelledInterval(start=at(start), end=at(end), label="unscored")


def test_normal_duration_removes_unscored_time_merged_with_attack_time() -> None:
    dataset = make_dataset(intervals=[make_interval(600, 900)]).model_copy(
        update={"unscored_intervals": [make_unscored(900, 1200)]}
    )
    # Span 0..3540 s. Attack 600-900 and unscored 900-1200 abut and merge into 600-1200, so
    # 600 s are removed once, not 300 + 300 with the shared instant counted twice: 3540 - 600.
    assert dataset.normal_duration() == timedelta(seconds=2940)
    assert dataset.is_unscored(at(1000))
    assert not dataset.is_unscored(at(700))
    assert not dataset.is_attack(at(1000))


def test_csv_adapter_turns_declared_unscored_rows_into_unscored_intervals(tmp_path: Path) -> None:
    path = tmp_path / "phases.csv"
    path.write_text(
        "timestamp,label,sensor_a\n"
        "2026-07-28 09:00:00,0,1.0\n"
        "2026-07-28 09:00:01,-1,1.0\n"
        "2026-07-28 09:00:02,-1.0,1.0\n"
        "2026-07-28 09:00:03,1,9.0\n"
        "2026-07-28 09:00:04,-1,2.0\n"
        "2026-07-28 09:00:05,0,1.0\n",
        encoding="utf-8",
    )
    dataset = make_csv_adapter(path, unscored_label_values=["-1"]).load()

    second = timedelta(seconds=1)
    base = datetime(2026, 7, 28, 9, 0, 0, tzinfo=UTC)
    # "-1.0" matches the declared "-1" by value, so rows 1-2 form one unscored run.
    assert [(i.start, i.end) for i in dataset.unscored_intervals] == [
        (base + 1 * second, base + 2 * second),
        (base + 4 * second, base + 4 * second),
    ]
    assert [(i.start, i.end) for i in dataset.attack_intervals] == [
        (base + 3 * second, base + 3 * second)
    ]


def test_csv_adapter_without_the_declaration_reads_the_sentinel_as_an_attack(
    tmp_path: Path,
) -> None:
    # The trap the manifest declaration exists to close: default_attack_when calls -1 an attack.
    path = tmp_path / "phases.csv"
    path.write_text(
        "timestamp,label,sensor_a\n2026-07-28 09:00:00,0,1.0\n2026-07-28 09:00:01,-1,1.0\n",
        encoding="utf-8",
    )
    dataset = make_csv_adapter(path).load()
    assert len(dataset.attack_intervals) == 1
    assert dataset.unscored_intervals == []
