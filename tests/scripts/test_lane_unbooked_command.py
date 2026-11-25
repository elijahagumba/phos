"""The unbooked-command harness joins a work order to its mode tag and scores windows.

These tests build the plant in memory. They do not open a corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.lane_unbooked_command import (
    RELEASE_VALUE,
    Cover,
    PlantEvent,
    ValveWrite,
    combine,
    read_orders,
    require_dev_corpus,
    score_plant,
)

from phos.atlas.declared_law import _MODE_RELEASE

EPOCH = 1_767_225_600.0
OUTPUT = "tank_output_valve_mode"
LEVEL = "tank_level_max"


def _event(kind: str, start: float, end: float, label: str = "attack") -> PlantEvent:
    benign = kind in {"maintenance", "setpoint"}
    return PlantEvent(kind, "benign" if benign else label, start, end)


def _write(tag: str, relative: float, value: float, role: str = "operator") -> ValveWrite:
    return ValveWrite(tag, relative, value, role)


def test_the_release_value_is_the_law_s_release_mode() -> None:
    assert RELEASE_VALUE == _MODE_RELEASE


def test_a_dev_corpus_name_is_accepted_and_any_other_name_is_refused(tmp_path: Path) -> None:
    require_dev_corpus(tmp_path / "phos-icssim-dev")
    with pytest.raises(ValueError, match="phos-icssim-dev"):
        require_dev_corpus(tmp_path / "phos-icssim-heldout")


def test_a_work_order_asset_becomes_the_output_mode_tag(tmp_path: Path) -> None:
    path = tmp_path / "work_orders.csv"
    path.write_text(
        "work_order,start,end,asset,action\n"
        "WO-1,1767225700.0,1767225800.0,tank_output_valve,planned valve service\n",
        encoding="utf-8",
    )
    assert read_orders(path, EPOCH) == (Cover(OUTPUT, 100.0, 200.0),)


def test_an_unknown_asset_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "work_orders.csv"
    path.write_text(
        "work_order,start,end,asset,action\n"
        "WO-1,1767225700.0,1767225800.0,tank_output_valve_mode,planned\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no declared mode tag"):
        read_orders(path, EPOCH)


def test_mimic_is_caught_and_genuine_maintenance_is_silent() -> None:
    events = (
        _event("mimic_maintenance", 100.0, 400.0),
        _event("maintenance", 1000.0, 1600.0),
        _event("setpoint", 2000.0, 2001.0),
        _event("replay", 3000.0, 3200.0),
        _event("rogue_command", 4000.0, 4200.0),
    )
    writes = (
        _write(OUTPUT, 100.5, 1.0),
        _write(OUTPUT, 400.2, RELEASE_VALUE),
        _write(OUTPUT, 1000.4, 1.0),
        _write(OUTPUT, 1600.2, RELEASE_VALUE),
        _write(LEVEL, 2000.1, 7.1),
        _write(OUTPUT, 3000.2, 1.0, "attacker"),
        _write("tank_input_valve_mode", 4000.2, 2.0, "attacker"),
    )
    orders = (Cover(OUTPUT, 1000.0, 1600.0),)
    score = score_plant(epoch=EPOCH, events=events, writes=writes, orders=orders)
    metrics = score.metrics()
    assert metrics["mimic_catch_rate"] == 1.0
    assert metrics["maintenance_breaks"] == 0.0
    assert metrics["setpoint_breaks"] == 0.0
    assert metrics["release_breaks"] == 0.0
    assert score.replay_caught == 1
    assert score.rogue_caught == 1
    assert score.unlabelled_breaks == 0
    assert score.breaks == 3


def test_a_release_alone_does_not_catch_mimic() -> None:
    events = (_event("mimic_maintenance", 100.0, 400.0),)
    writes = (_write(OUTPUT, 100.5, RELEASE_VALUE),)
    score = score_plant(epoch=EPOCH, events=events, writes=writes, orders=())
    assert score.metrics()["mimic_catch_rate"] == 0.0
    assert score.release_breaks == 0


def test_a_work_order_on_the_wrong_tag_counts_as_maintenance() -> None:
    events = (_event("maintenance", 1000.0, 1600.0), _event("mimic_maintenance", 100.0, 200.0))
    writes = (_write(OUTPUT, 100.2, 1.0), _write(OUTPUT, 1000.4, 1.0))
    orders = (Cover("tank_input_valve_mode", 1000.0, 1600.0),)
    score = score_plant(epoch=EPOCH, events=events, writes=writes, orders=orders)
    assert score.metrics()["maintenance_breaks"] == 1.0


def test_counts_add_and_the_rate_is_taken_on_the_total() -> None:
    first = score_plant(
        epoch=EPOCH,
        events=(_event("mimic_maintenance", 0.0, 10.0),),
        writes=(_write(OUTPUT, 1.0, 1.0),),
        orders=(),
    )
    second = score_plant(
        epoch=EPOCH,
        events=(_event("mimic_maintenance", 0.0, 10.0),),
        writes=(_write(OUTPUT, 1.0, RELEASE_VALUE),),
        orders=(),
    )
    assert combine((first, second)).metrics()["mimic_catch_rate"] == 0.5


def test_a_release_just_outside_the_window_is_not_a_break() -> None:
    score = score_plant(
        epoch=EPOCH,
        events=(_event("mimic_maintenance", 930.4, 1629.4),),
        writes=(_write(OUTPUT, 930.52, 1.0), _write(OUTPUT, 1629.435, RELEASE_VALUE)),
        orders=(),
    )
    assert score.mimic_caught == 1
    assert score.breaks == 1
    assert score.unlabelled_breaks == 0
    assert score.release_breaks == 0
