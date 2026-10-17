"""The later HAI editions' role files (ADR 0141): built from 20.07's and the manual, not by hand."""

import tomllib
from pathlib import Path

import pytest
from scripts.build_hai_roles import EDITIONS, NEW_POINTS, SOURCE, render

from phos.atlas.signal_roles import SignalRole, load_roles

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.parametrize("edition", sorted(EDITIONS))
def test_each_committed_file_is_what_the_builder_writes(edition: str) -> None:
    source = tomllib.loads(SOURCE.read_text(encoding="utf-8"))
    committed = (DATA / edition / "roles.toml").read_text(encoding="utf-8")
    assert committed == render(edition, EDITIONS[edition], source)


@pytest.mark.parametrize("edition", sorted(EDITIONS))
def test_each_file_declares_every_column_once(edition: str) -> None:
    roles = load_roles(DATA / edition / "roles.toml", EDITIONS[edition])
    assert roles.signals == EDITIONS[edition]


def test_points_shared_with_20_07_keep_its_roles() -> None:
    old = load_roles(DATA / "hai-20.07" / "roles.toml", _columns_2007())
    new = load_roles(DATA / "hai-22.04" / "roles.toml", EDITIONS["hai-22.04"])
    for signal in ("P1_LIT01", "P1_LCV01D", "P1_B3004", "P2_SIT01"):
        assert new.role_of(signal) is old.role_of(signal)
    # 20.07 reads P2_SD01 and P3_LT01; 22.04 names them as the manual does.
    assert new.role_of("P2_AutoSD") is old.role_of("P2_SD01") is SignalRole.SETPOINT
    assert new.role_of("P3_LIT01") is old.role_of("P3_LT01") is SignalRole.SENSOR


def test_points_added_after_20_07_take_their_declared_roles() -> None:
    roles = load_roles(DATA / "hai-22.04" / "roles.toml", EDITIONS["hai-22.04"])
    for signal, (role, *_rest) in NEW_POINTS.items():
        if signal in EDITIONS["hai-22.04"]:
            expected = None if role is None else SignalRole(role)
            assert roles.role_of(signal) is expected, signal


def test_a_column_the_table_does_not_name_is_never_matched_by_its_shape() -> None:
    roles = load_roles(DATA / "hai-23.05" / "roles.toml", EDITIONS["hai-23.05"])
    for signal in ("x1001_15_ASSIGN_OUT", "x1003_24_SUM_OUT", "P1_PP04D"):
        assert roles.role_of(signal) is None
    older = load_roles(DATA / "hai-21.03" / "roles.toml", EDITIONS["hai-21.03"])
    assert older.role_of("P2_ASD") is None


def test_loops_follow_the_points_each_edition_has() -> None:
    roles = load_roles(DATA / "hai-23.05" / "roles.toml", EDITIONS["hai-23.05"])
    by_name = {loop.name: loop for loop in roles.loops}
    assert by_name["P1-LC"].reading == "P1_LIT01"
    assert by_name["P1-LC"].setpoint is None  # 23.05 has no P1_B3004 column
    assert by_name["P2-SC"].setpoint == "P2_AutoSD"


def _columns_2007() -> tuple[str, ...]:
    raw = tomllib.loads((DATA / "hai-20.07" / "roles.toml").read_text(encoding="utf-8"))
    return tuple(str(p["signal"]) for p in raw["points"])
