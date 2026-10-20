"""The sandbox candidate look is declared here and is not executed by these tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy
from tests.lab_only import skip_if_absent

from phos.eval.baseline_table import SeriesGrid
from phos.eval.candidate_look import (
    CANDIDATE_RELATIVE,
    CANDIDATE_SHA256,
    CANDIDATE_WORKTREE,
    CLEAN_CORPORA,
    GROUPED_ATLAS,
    GROUPED_MINMAX,
    LOOK_JSON_NAME,
    OWN_GROUPING,
    SHARED_WRAPPER,
    LookRow,
    assert_candidate_bytes,
    attacks_only_candidate,
    beyond_grouped_minmax,
    cells_above,
    label_free_record,
    published_caught,
    render_look,
    sha256_bytes,
    train_record,
)

ROOT = Path(__file__).resolve().parents[2]


def test_the_candidate_bytes_are_the_frozen_file() -> None:
    """The worktree commit is not in this repo. The sha256 is the lock."""
    path = ROOT / CANDIDATE_RELATIVE
    skip_if_absent(path)
    payload = path.read_bytes()
    assert sha256_bytes(payload) == CANDIDATE_SHA256
    assert_candidate_bytes(payload)
    text = payload.decode()
    assert 'out.append(_budget(_events(scores), f["time"]))' in text
    assert "SECOND_ALERT_MIN_SEPARATION" in text
    assert CANDIDATE_WORKTREE == "6e7c665"


def test_the_look_names_the_two_clean_editions_and_the_published_counts() -> None:
    """Grouped Atlas and grouped MinMax stay the ADR 0102 fractions."""
    assert CLEAN_CORPORA == ("hai-22.04", "hai-23.05")
    assert OWN_GROUPING == "sandbox-candidate:own-grouping"
    assert SHARED_WRAPPER == "sandbox-candidate:shared-wrapper"
    assert published_caught("hai-22.04", GROUPED_ATLAS) == (5, 58)
    assert published_caught("hai-22.04", GROUPED_MINMAX) == (10, 58)
    assert published_caught("hai-23.05", GROUPED_ATLAS) == (5, 52)
    assert published_caught("hai-23.05", GROUPED_MINMAX) == (6, 52)
    assert beyond_grouped_minmax(7, 10) == -3
    assert attacks_only_candidate(("b#1", "a#0"), ("a#0",)) == ("b#1",)
    assert LOOK_JSON_NAME == "g1-candidate-look.json"


def test_cells_above_use_the_strict_frozen_comparison() -> None:
    """A score equal to the threshold is not an alert. The candidate uses ``>``."""
    scores = numpy.asarray([[1.0, 1.5], [0.0, 3.0]], dtype=numpy.float64)
    assert cells_above(scores, ("a", "b"), 1.0) == ((0, "b", 1.5), (1, "b", 3.0))


def test_a_test_record_does_not_carry_labels() -> None:
    """The frozen contract allows attack flags on train files only."""
    grid = _grid()
    assert "attack" not in label_free_record(grid)
    train = train_record(grid)
    assert train["attack"] is not None
    assert "attack" in train


def test_the_report_quotes_published_counts_and_names_exclusive_attacks() -> None:
    """A fake candidate row does not replace the published 10/58."""
    text = render_look(
        (
            LookRow("hai-22.04", GROUPED_MINMAX, 10, 58, None, None, ()),
            LookRow("hai-22.04", OWN_GROUPING, 12, 58, 0.5, 2, ("test1.csv#0",)),
        )
    )
    assert "| hai-22.04 | g1-grouped:simple-minmax | 10 | 58 | 0.172414 | published |" in text
    assert (
        "| hai-22.04 | sandbox-candidate:own-grouping | 12 | 58 | 0.206897 | 0.500000 | 2 |" in text
    )
    assert "hai-22.04 sandbox-candidate:own-grouping: test1.csv#0." in text


def test_the_look_is_on_disk() -> None:
    """The one score wrote the sidecar and did not touch the G1 table or the log."""
    payload = (ROOT / "eval_runs" / "v1" / LOOK_JSON_NAME).read_text(encoding="utf-8")
    assert '"caught": 53' in payload
    assert '"caught": 36' in payload
    assert "0.9593944845394529" in payload
    assert "0.8494745699247331" in payload
    report = (ROOT / "eval_runs" / "v1" / "g1-candidate-look.md").read_text(encoding="utf-8")
    assert "| hai-22.04 | sandbox-candidate:own-grouping | 53 | 58 |" in report
    assert "| hai-22.04 | sandbox-candidate:shared-wrapper | 53 | 58 |" in report
    assert "| hai-23.05 | sandbox-candidate:own-grouping | 36 | 52 |" in report
    assert "| hai-23.05 | g1-grouped:simple-minmax | 6 | 52 |" in report
    script = (ROOT / "scripts" / "measure_candidate_look.py").read_text(encoding="utf-8")
    assert "append_to_experiment_log" not in script
    assert "g1-baseline-table.md" not in script


def _grid() -> SeriesGrid:
    origin = datetime(2022, 1, 1, tzinfo=UTC)
    return SeriesGrid(
        timestamps=(origin, origin + timedelta(seconds=1)),
        features=("a",),
        values=numpy.ones((2, 1), dtype=numpy.float64),
        attack=numpy.array([False, True], dtype=numpy.bool_),
        unscored=numpy.array([False, False], dtype=numpy.bool_),
    )
