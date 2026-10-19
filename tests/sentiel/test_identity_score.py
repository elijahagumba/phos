"""The empty identity register scores zeros. The fixture is not CERT."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from phos.sentiel.identity_score import (
    EMPTY_REGISTER_SHA256,
    score_traces,
    summarise_identity,
)
from phos.sentiel.named_counterparties import DeclaredIdentities, register_sha256
from phos.sentiel.traces import EntityDayTrace


def _trace() -> EntityDayTrace:
    return EntityDayTrace(
        user_id="A",
        day=datetime(2010, 7, 1, tzinfo=UTC),
        hosts=("wikileaks.org",),
        recipients=("home@example.com",),
        pcs=("PC-1",),
    )


def test_an_empty_register_scores_zeros_on_named_counterparties() -> None:
    summary = summarise_identity(score_traces([_trace()], DeclaredIdentities()))
    assert summary["all_zero"] is True
    assert summary["register_sha256"] == EMPTY_REGISTER_SHA256
    features = summary["features"]
    assert isinstance(features, dict)
    for row in features.values():
        assert isinstance(row, dict)
        assert row["sum"] == 0.0
        assert row["max"] == 0.0


def test_a_declared_host_is_counted_when_the_register_names_it() -> None:
    register = DeclaredIdentities(hosts=frozenset({"wikileaks.org"}))
    summary = summarise_identity(score_traces([_trace()], register))
    features = summary["features"]
    assert isinstance(features, dict)
    hosts = features["declared_host_count"]
    assert isinstance(hosts, dict)
    assert hosts["sum"] == 1.0
    assert summary["register_sha256"] == register_sha256(register)
    assert summary["all_zero"] is False


def test_an_existing_identity_result_is_not_scored_again(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "s2.json"
    out.write_text("{}\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "score_identity_features.py"),
            "--release",
            "r3.1",
            "--out",
            str(out),
            "--data-dir",
            str(tmp_path / "missing"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert out.read_text(encoding="utf-8") == "{}\n"
