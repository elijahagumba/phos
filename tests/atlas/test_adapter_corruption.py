"""A corrupt or hostile plant export must be refused, not analysed.

The adapter is where real data becomes the arrays Atlas reasons over, so it is the one place a
corrupt file can enter. Before this file existed, four kinds of corruption were accepted silently:

* ``nan``, which ``float()`` accepts. A NaN reaching a consistency detector poisons every
  comparison after it, because ``nan > x`` is false for every x, so the detector goes quiet. Silence
  that looks like a clean plant is the worst outcome Atlas can produce.
* ``inf``, which makes every band comparison meaningless in the same way.
* A repeated timestamp, which makes two measurements look simultaneous.
* A timestamp that goes backwards, which makes every window, rate and duration wrong.

A fifth kind was refused but unusably: text where a number belongs produced "could not convert
string to float", naming neither the file, the line nor the column, so nobody holding the export
could find the bad cell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.atlas.icssim_adapter import read_run

HEADER = "time,tank_level,valve\n"


def _run(tmp_path: Path, body: str) -> Path:
    """Write a ``process.csv`` and return its directory.

    Args:
        tmp_path: The test's temporary directory.
        body: The rows, after the header.

    Returns:
        The directory.
    """
    directory = tmp_path / "run"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "process.csv").write_text(HEADER + body, encoding="utf-8")
    return directory


def test_a_valid_run_loads(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n1,7.0,1\n2,7.1,0\n")
    run = read_run(directory)
    assert run.values.shape == (3, 2)
    assert run.keys == ("tank_level", "valve")


@pytest.mark.parametrize("cell", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_a_non_finite_telemetry_value_is_refused(tmp_path: Path, cell: str) -> None:
    """A NaN or an infinity would silence every comparison after it without saying so."""
    directory = _run(tmp_path, f"0,6.9,1\n1,{cell},1\n")
    with pytest.raises(ValueError, match="not a finite number"):
        read_run(directory)


def test_a_non_finite_timestamp_is_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\nnan,7.0,1\n")
    with pytest.raises(ValueError, match="not a finite number"):
        read_run(directory)


def test_text_where_a_number_belongs_names_the_file_line_and_column(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n1,NOT_A_NUMBER,1\n")
    with pytest.raises(ValueError) as caught:
        read_run(directory)
    message = str(caught.value)
    assert "process.csv" in message
    assert "line 3" in message
    assert "tank_level" in message
    assert "NOT_A_NUMBER" in message


def test_an_empty_telemetry_cell_is_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n1,,1\n")
    with pytest.raises(ValueError, match="the cell is empty"):
        read_run(directory)


def test_a_repeated_timestamp_is_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n1,7.0,1\n1,7.1,1\n")
    with pytest.raises(ValueError, match="repeats"):
        read_run(directory)


def test_a_backwards_timestamp_is_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n2,7.0,1\n1,7.1,1\n")
    with pytest.raises(ValueError, match="goes backwards"):
        read_run(directory)


def test_a_short_row_is_still_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "0,6.9,1\n1,7.0\n")
    with pytest.raises(ValueError, match="fields, not"):
        read_run(directory)


def test_a_header_with_no_rows_is_refused(tmp_path: Path) -> None:
    directory = _run(tmp_path, "")
    with pytest.raises(ValueError, match="no rows"):
        read_run(directory)


def test_an_empty_file_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "empty"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "process.csv").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="is empty"):
        read_run(directory)


def test_a_column_header_is_named_instead_of_its_index(tmp_path: Path) -> None:
    """Three columns, bad in the third: the message must name the third column, not 'index 2'."""
    directory = _run(tmp_path, "0,6.9,good\n1,7.0,bad\n")
    with pytest.raises(ValueError) as caught:
        read_run(directory)
    assert "'valve'" in str(caught.value)


def test_a_real_development_run_still_loads() -> None:
    """The validation must not refuse the corpora the project actually scores.

    This is the regression that would matter most: a boundary check that rejects real plant data is
    worse than none, because it is discovered when a score fails rather than when it is written.
    """
    root = Path(__file__).resolve().parents[2]
    run = root / "data" / "phos-icssim-dev4-walk" / "normal-96801"
    if not run.is_dir():
        pytest.skip("the development corpus is not on this machine")
    loaded = read_run(run)
    assert loaded.values.shape[0] == 14401
    assert loaded.values.shape[1] == 13
