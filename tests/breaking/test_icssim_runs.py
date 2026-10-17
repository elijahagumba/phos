"""Reading PHOS's ICSSim runs (ADR 0122, ADR 0128), and the committed ICSSim role file."""

import json
from pathlib import Path

import pytest

from phos.atlas.signal_roles import SignalRole, load_roles
from phos.breaking.icssim_runs import HELD_OUT_DIRECTORY, load_run

ROLES = Path(__file__).resolve().parents[2] / "data" / "phos-icssim-dev" / "roles.toml"
TAGS = (
    "tank_input_valve_status tank_input_valve_mode tank_level_value tank_level_min "
    "tank_level_max tank_output_valve_status tank_output_valve_mode tank_output_flow_value "
    "conveyor_belt_engine_status conveyor_belt_engine_mode bottle_level_value bottle_level_max "
    "bottle_distance_to_filler_value"
).split()


def _run(root: Path, name: str = "mixed-1") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    header = "timestamp,a,b\n"
    (directory / "process.csv").write_text(header + "100.0,1,2\n101.0,1,3\n102.0,2,3\n")
    (directory / "truth.csv").write_text(header + "100.0,1,2\n101.0,1,9\n102.0,2,9\n")
    (directory / "events.json").write_text(
        json.dumps([{"kind": "liar_offset", "start": 1.0, "end": 2.0, "label": "attack"}])
    )
    (directory / "manifest.json").write_text(
        json.dumps({"scenario": "mixed", "seed": 1, "epoch": 100.0})
    )
    return directory


def test_a_run_reads_into_arrays_and_its_events_into_rows(tmp_path: Path) -> None:
    run = load_run(_run(tmp_path))
    assert run.names == ("a", "b")
    assert run.values.shape == run.truth.shape == (3, 2)
    assert run.truth[1, 1] == 9.0 and run.values[1, 1] == 3.0
    (event,) = run.events
    assert event.is_attack
    assert run.rows(event) == (1, 2)


def test_the_held_out_corpus_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="held out"):
        load_run(_run(tmp_path / HELD_OUT_DIRECTORY))


def test_icssim_roles_declare_every_tag_and_its_loops() -> None:
    roles = load_roles(ROLES, TAGS)
    assert roles.signals == tuple(TAGS)
    assert roles.role_of("tank_level_value") is SignalRole.SENSOR
    assert roles.role_of("tank_input_valve_status") is SignalRole.ACTUATOR
    assert roles.role_of("tank_level_max") is SignalRole.SETPOINT
    assert roles.without_role() == ()
    level = [loop for loop in roles.loops if loop.reading == "tank_level_value"]
    assert [loop.outputs for loop in level] == [("tank_input_valve_status",)]
    assert "bcfd1844d3f063850c69f2643f6a052bac03d8ec" in roles.source


def test_traffic_reads_into_exchanges_and_the_held_out_corpus_is_refused(tmp_path: Path) -> None:
    from phos.breaking.icssim_runs import load_exchanges

    directory = _run(tmp_path)
    (directory / "modbus.csv").write_text(
        "timestamp,client,role,plc,function,tag,value\n"
        "100.1,127.0.0.12,plc2,plc1,read,tank_output_flow_value,0.0\n"
    )
    (exchange,) = load_exchanges(directory)
    assert (exchange.client, exchange.server, exchange.function, exchange.point) == (
        "plc2",
        "plc1",
        "read",
        "tank_output_flow_value",
    )
    with pytest.raises(ValueError, match="held out"):
        load_exchanges(_run(tmp_path / HELD_OUT_DIRECTORY))


def test_only_a_write_that_changes_a_value_is_an_intervention(tmp_path: Path) -> None:
    from phos.breaking.icssim_runs import load_interventions

    directory = _run(tmp_path)
    (directory / "modbus.csv").write_text(
        "timestamp,client,role,plc,function,tag,value\n"
        "100.5,127.0.0.21,operator,plc1,write,a,1.0\n"
        "101.2,127.0.0.21,operator,plc1,write,a,4.0\n"
        "101.9,127.0.0.21,operator,plc1,read,b,3.0\n"
    )
    run = load_run(directory)
    (change,) = load_interventions(directory, run, 7)
    assert (change.file, change.row, change.point) == (7, 2, "a")
