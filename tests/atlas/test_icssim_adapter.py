"""A run's two files become a telemetry matrix and a command matrix that line up."""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest

from phos.atlas.icssim_adapter import Command, commanded, read_run, read_traffic

_PROCESS = (
    "timestamp,tank_level_value,tank_output_valve_mode\n"
    "100.0,1.5,3.0\n"
    "101.0,1.6,3.0\n"
    "102.0,1.7,2.0\n"
    "103.0,1.8,2.0\n"
)

_TRAFFIC = (
    "timestamp,client,role,plc,function,tag,value\n"
    "100.2,127.0.0.11,plc1,plc1,read,tank_level_value,1.5\n"
    "101.5,127.0.0.21,operator,plc1,write,tank_output_valve_mode,2.0\n"
    "102.5,127.0.0.66,attacker,plc1,write,tank_level_value,9.0\n"
    "103.1,127.0.0.21,operator,plc1,write,not_a_column,7.0\n"
)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    (tmp_path / "process.csv").write_text(_PROCESS)
    (tmp_path / "modbus.csv").write_text(_TRAFFIC)
    return tmp_path


def test_the_telemetry_becomes_rows_by_signals(run_dir: Path) -> None:
    run = read_run(run_dir)
    assert run.keys == ("tank_level_value", "tank_output_valve_mode")
    assert run.values.shape == (4, 2)
    numpy.testing.assert_allclose(run.values[:, 0], [1.5, 1.6, 1.7, 1.8])
    numpy.testing.assert_allclose(run.times, [100.0, 101.0, 102.0, 103.0])


def test_polls_are_dropped_and_writes_are_kept(run_dir: Path) -> None:
    """Reads are the overwhelming majority and carry no command."""
    writes = read_traffic(run_dir)
    assert [item.tag for item in writes] == [
        "tank_output_valve_mode",
        "tank_level_value",
        "not_a_column",
    ]
    assert all(item.role in {"operator", "attacker"} for item in writes)


def test_every_message_is_kept_when_asked(run_dir: Path) -> None:
    assert len(read_traffic(run_dir, writes_only=False)) == 4


def test_the_function_is_carried(run_dir: Path) -> None:
    """Lane 1 needs reads as well as writes, so the function travels with the message."""
    every = read_traffic(run_dir, writes_only=False)
    assert [item.function for item in every] == ["read", "write", "write", "write"]


def test_the_station_that_wrote_is_carried(run_dir: Path) -> None:
    """Attribution by role is the whole reason this corpus exists."""
    writes = read_traffic(run_dir)
    attacker = [item for item in writes if item.role == "attacker"]
    assert len(attacker) == 1
    assert attacker[0].tag == "tank_level_value"
    assert attacker[0].value == 9.0


def test_a_command_holds_from_the_first_sample_at_or_after_it(run_dir: Path) -> None:
    run = read_run(run_dir)
    matrix = commanded(read_traffic(run_dir), run.keys, run.times)
    mode = matrix[:, 1]
    assert numpy.isnan(mode[0])
    assert numpy.isnan(mode[1])
    numpy.testing.assert_allclose(mode[2:], [2.0, 2.0])


def test_a_signal_never_commanded_stays_absent(run_dir: Path) -> None:
    """NaN rather than zero: a caller must tell 'commanded to zero' from 'never commanded'."""
    run = read_run(run_dir)
    only_reads = tuple(item for item in read_traffic(run_dir) if item.role == "operator")
    matrix = commanded(only_reads, run.keys, run.times)
    assert numpy.isnan(matrix[:, 0]).all()


def test_a_tag_that_is_not_a_signal_is_ignored(run_dir: Path) -> None:
    run = read_run(run_dir)
    matrix = commanded(read_traffic(run_dir), run.keys, run.times)
    assert matrix.shape == (4, 2)


def test_commands_out_of_order_still_land_in_time_order(run_dir: Path) -> None:
    run = read_run(run_dir)
    jumbled = (
        Command(at=103.0, role="operator", function="write", tag="tank_level_value", value=5.0),
        Command(at=101.0, role="operator", function="write", tag="tank_level_value", value=4.0),
    )
    matrix = commanded(jumbled, run.keys, run.times)
    numpy.testing.assert_allclose(matrix[1:, 0], [4.0, 4.0, 5.0])


def test_a_command_after_the_last_sample_changes_nothing(run_dir: Path) -> None:
    run = read_run(run_dir)
    late = (
        Command(at=999.0, role="attacker", function="write", tag="tank_level_value", value=1.0),
    )
    assert numpy.isnan(commanded(late, run.keys, run.times)).all()


def test_a_header_with_no_rows_is_refused(tmp_path: Path) -> None:
    (tmp_path / "process.csv").write_text("timestamp,a\n")
    with pytest.raises(ValueError, match="header and no rows"):
        read_run(tmp_path)


def test_a_short_row_is_refused_with_its_line(tmp_path: Path) -> None:
    (tmp_path / "process.csv").write_text("timestamp,a,b\n1.0,2.0\n")
    with pytest.raises(ValueError, match="line 2"):
        read_run(tmp_path)
