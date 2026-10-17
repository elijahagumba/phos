"""ADR 0105 is declared here. These tests do not score HAI."""

from __future__ import annotations

import math
from pathlib import Path

import numpy

from phos.eval.candidate_checks import (
    ALERTS_PER_SHIFT,
    CANDIDATE_CAUGHT,
    CHANCE_DRAWS,
    CHANCE_SEED,
    CHECKS_JSON_NAME,
    DRIVER_SHARE_ABOVE,
    MINMAX_EVENTS_SHA256,
    NO_LOOP_SHA256,
    choose_driver,
    draw_rows,
    flagged_features,
    larger_component,
    same_alert_list,
    shift_ids,
    summarise_chance,
)
from phos.eval.candidate_look import sha256_bytes

ROOT = Path(__file__).resolve().parents[2]


def test_the_chance_summary_is_mean_linear_percentile_and_max() -> None:
    """Five draws: mean 2, the linear 95th percentile is 3.6, the max is 4."""
    summary = summarise_chance(numpy.asarray([1, 1, 2, 2, 4], dtype=numpy.int64))
    assert summary.draws == 5
    assert summary.mean_caught == 2.0
    assert math.isclose(summary.percentile_95, 3.6)
    assert summary.max_caught == 4
    assert CHANCE_DRAWS == 500
    assert CHANCE_SEED == 20261010
    assert CANDIDATE_CAUGHT == {"hai-22.04": (53, 58), "hai-23.05": (36, 52)}


def test_a_draw_takes_eight_rows_per_shift_and_a_short_shift_keeps_all() -> None:
    """Shift 0 has ten rows. Shift 1 has three. The seed fixes the choice."""
    stamps = numpy.asarray(
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 8 * 3600, 8 * 3600 + 1, 8 * 3600 + 2],
        dtype=numpy.float64,
    )
    assert list(shift_ids(stamps)) == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1]
    rng = numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED))
    chosen = draw_rows(numpy.arange(13, dtype=numpy.int64), shift_ids(stamps), rng)
    assert chosen.size == ALERTS_PER_SHIFT + 3
    assert {int(row) for row in chosen if int(row) >= 10} == {10, 11, 12}


def test_the_driver_is_the_strongest_kept_alert_and_the_range_or_the_loop() -> None:
    """A tie on score takes the earlier row. A share of 0.20 is not a flag."""
    driver = choose_driver(((4, "b", 3.0), (1, "a", 3.0), (2, "c", 1.0)))
    assert (driver.row, driver.feature) == (1, "a")
    assert larger_component(2.0, 1.0) == "range"
    assert larger_component(1.0, 2.0) == "loop"
    assert larger_component(1.0, 1.0) == "tie"
    assert flagged_features({"a": 2, "b": 1}, 10) == ()
    assert flagged_features({"a": 3}, 10) == ("a",)
    assert DRIVER_SHARE_ABOVE == 0.20


def test_the_same_alert_list_ignores_order() -> None:
    """Point-adjusted F1 saw a list. Equality is the row and the feature."""
    assert same_alert_list(((1, "b"), (0, "a")), ((0, "a"), (1, "b")))
    assert not same_alert_list(((0, "a"),), ((0, "b"),))


def test_the_checks_are_on_disk() -> None:
    """The one run wrote the sidecar and did not touch the log or the G1 table."""
    payload = (ROOT / "eval_runs" / "v1" / CHECKS_JSON_NAME).read_text(encoding="utf-8")
    assert '"mean_caught": 3.808' in payload
    assert '"mean_caught": 3.06' in payload
    assert '"feature": "P1_PCV01D"' in payload
    assert '"caught": 21' in payload
    assert '"caught": 15' in payload
    assert '"same_alert_list": false' in payload
    script = (ROOT / "scripts" / "measure_candidate_checks.py").read_text(encoding="utf-8")
    assert "append_to_experiment_log" not in script
    assert "measure_candidate_look" not in script
    assert "g1-baseline-table" not in script
    controls = ROOT / "experiments" / "2026-10-04-sandbox" / "controls"
    minmax = sha256_bytes((controls / "minmax_events" / "candidate.py").read_bytes())
    no_loop = sha256_bytes((controls / "no_loop" / "candidate.py").read_bytes())
    assert minmax == MINMAX_EVENTS_SHA256
    assert no_loop == NO_LOOP_SHA256
