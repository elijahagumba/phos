"""ADR 0174: the held-back window is not the development window, and meters are not scored."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.eval.kelmarsh_heldback import (
    HELD_BACK_SCADA,
    METER_FILES,
    SCORE_RESULT,
    DeclarationError,
    held_back_half,
    held_back_names_are_the_registry,
    inspect_meter_zip,
    load_held_back_scada,
    require_authorization,
)
from phos.eval.kelmarsh_log import SIGNAL_COLUMNS, parse_turbine_lines, which_half

_HEADER = "Date and time," + ",".join(SIGNAL_COLUMNS)


def _row(stamp: str, value: str = "1") -> str:
    return f"{stamp}," + ",".join([value] * len(SIGNAL_COLUMNS))


def test_which_half_still_drops_2023_and_the_held_back_window_keeps_it() -> None:
    assert which_half(datetime(2023, 6, 1, tzinfo=UTC)) == "outside"
    assert held_back_half(datetime(2022, 12, 31, tzinfo=UTC)) == "outside"
    assert held_back_half(datetime(2023, 1, 1, tzinfo=UTC)) == "score"
    assert held_back_half(datetime(2024, 12, 31, 23, 50, tzinfo=UTC)) == "score"
    assert held_back_half(datetime(2025, 1, 1, tzinfo=UTC)) == "outside"
    lines = [
        _HEADER,
        _row("2019-06-01 00:00:00"),
        _row("2023-06-01 00:10:00"),
        _row("2025-01-01 00:00:00"),
    ]
    kept, _, _, _ = parse_turbine_lines(lines, half_of=held_back_half)
    assert len(kept) == 1
    assert kept[0][2] == "score"


def test_authorization_blocks_an_empty_sha256() -> None:
    with pytest.raises(DeclarationError, match="not authorized"):
        require_authorization(
            {
                "result_name": SCORE_RESULT,
                "scorer": "atlas-v1-consistency",
                "authorized": False,
                "files": [{"filename": "x", "sha256": None}],
            }
        )


def test_held_back_names_are_the_five_registry_files() -> None:
    assert held_back_names_are_the_registry()
    assert HELD_BACK_SCADA[0].startswith("Kelmarsh_SCADA_2023")
    assert "PMU" in METER_FILES[0]


def test_loader_keeps_a_2023_row_and_refuses_a_meter_member(tmp_path: Path) -> None:
    scada = tmp_path / HELD_BACK_SCADA[0]
    member = "Turbine_Data_Kelmarsh_1_2023-01-01_-_2024-01-01.csv"
    body = _HEADER + "\n" + _row("2023-01-01 00:00:00") + "\n" + _row("2023-01-01 00:10:00") + "\n"
    status = (
        "Timestamp start,Timestamp end,Status,Service contract category,IEC category\n"
        "2023-01-01 00:00:00,2023-01-01 01:00:00,stop,Manual stop,x\n"
    )
    with zipfile.ZipFile(scada, "w") as archive:
        archive.writestr(member, body)
        archive.writestr("Status_Kelmarsh_1_2023.csv", status)
    loaded = load_held_back_scada(scada)
    assert "Kelmarsh 1" in loaded.scores
    assert loaded.trains == {}
    assert loaded.spans[0].service_category == "Manual stop"

    poisoned = tmp_path / HELD_BACK_SCADA[1]
    with zipfile.ZipFile(poisoned, "w") as archive:
        archive.writestr("Kelmarsh_PMU_inside.csv", "x")
    with pytest.raises(Exception, match="meter member"):
        load_held_back_scada(poisoned)


def test_meter_look_does_not_score(tmp_path: Path) -> None:
    path = tmp_path / METER_FILES[2]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("grid.csv", "time,kWh\n2023-01-01,1\n")
    look = inspect_meter_zip(path)
    assert look.scored is False
    assert "detect was not called" in look.reason
    assert look.header_lines == ("time,kWh",)


def test_default_parser_still_uses_which_half() -> None:
    lines = io.StringIO(_HEADER + "\n" + _row("2023-06-01 00:00:00") + "\n")
    kept, _, _, _ = parse_turbine_lines(lines)
    assert kept == []
