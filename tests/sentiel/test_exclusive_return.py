"""Exclusive-host returns: a repeat visit counts only while the host is still one user's."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.sentiel.exclusive_return import SCORER_NAME, HostDay, exclusive_return_scores


def _day(user: str, hosts: tuple[str, ...], day: int, month: int = 1) -> HostDay:
    return HostDay(user, datetime(2010, month, day, tzinfo=UTC), hosts)


def test_scorer_name_is_not_the_frozen_row() -> None:
    assert SCORER_NAME == "exclusive-host-return"
    assert "6B" not in SCORER_NAME
    assert "aggregate" not in SCORER_NAME


def test_first_visit_scores_nothing_and_the_return_scores_one() -> None:
    scores = exclusive_return_scores(
        (
            _day("A", ("only.example",), 1),
            _day("A", ("only.example",), 2),
        )
    )
    assert scores == (0, 1)


def test_someone_else_on_an_earlier_day_blocks_the_return() -> None:
    scores = exclusive_return_scores(
        (
            _day("B", ("shared.example",), 1),
            _day("A", ("shared.example",), 2),
            _day("A", ("shared.example",), 3),
        )
    )
    assert scores == (0, 0, 0)


def test_a_same_day_visitor_neither_adds_nor_removes_a_point() -> None:
    first = (
        _day("A", ("only.example",), 1),
        _day("A", ("only.example",), 2),
        _day("B", ("only.example",), 2),
    )
    reversed_same_day = (
        _day("A", ("only.example",), 1),
        _day("B", ("only.example",), 2),
        _day("A", ("only.example",), 2),
    )
    assert exclusive_return_scores(first) == (0, 1, 0)
    assert exclusive_return_scores(reversed_same_day) == (0, 0, 1)


def test_two_exclusive_hosts_score_two_and_duplicates_count_once() -> None:
    scores = exclusive_return_scores(
        (
            _day("A", ("one.example", "two.example"), 1),
            _day("A", ("one.example", "one.example", "two.example", ""), 2),
        )
    )
    assert scores == (0, 2)


def test_a_later_other_user_does_not_rewrite_an_earlier_return() -> None:
    scores = exclusive_return_scores(
        (
            _day("A", ("only.example",), 1),
            _day("A", ("only.example",), 2),
            _day("B", ("only.example",), 3),
            _day("A", ("only.example",), 4),
        )
    )
    assert scores == (0, 1, 0, 0)


def test_days_out_of_order_are_refused() -> None:
    with pytest.raises(ValueError, match="non-decreasing"):
        exclusive_return_scores(
            (
                _day("A", ("only.example",), 2),
                _day("A", ("only.example",), 1),
            )
        )


def test_no_hosts_scores_zero() -> None:
    assert exclusive_return_scores((_day("A", (), 1),)) == (0,)


def test_r42_command_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "exclusive-host-return-r42.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "score_exclusive_host_return.py"),
            "--release",
            "r4.2",
            "--out",
            str(out),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    text = (completed.stdout + completed.stderr).lower()
    assert completed.returncode == 2
    assert not out.exists()
    assert "held out" in text
    assert "exclusive-host-return:cert-r4.2@48" in completed.stdout + completed.stderr


def _host_day(user: str, day: int, *hosts: str) -> HostDay:
    return HostDay(user, datetime(2010, 8, day, tzinfo=UTC), tuple(hosts))


def test_zero_scores_are_never_alerts_even_when_ties_would_fill_the_budget() -> None:
    from typing import NamedTuple

    from phos.sentiel.exclusive_return import alerting

    class Row(NamedTuple):
        user_id: str
        score: float

    ranked = [Row("a", 2.0), Row("b", 1.0), Row("c", 0.0), Row("d", 0.0)]
    assert [r.user_id for r in alerting(ranked, budget=48)] == ["a", "b"]
    assert [r.user_id for r in alerting(ranked, budget=1)] == ["a"]


def test_single_user_hosts_are_counted_per_owner() -> None:
    from phos.sentiel.exclusive_return import single_user_host_owners

    days = [
        _host_day("ann", 1, "shared.com", "ann-only.com"),
        _host_day("bob", 1, "shared.com"),
        _host_day("bob", 2, "bob-only.com", "bob-too.com"),
    ]
    assert single_user_host_owners(days) == {"ann": 1, "bob": 2}
