"""New engine-week log names must not collide with frozen public rows."""

from __future__ import annotations

from pathlib import Path

from scripts.evaluate_atlas import correlation_contenders, var_contenders

from phos.sentiel.autopsy import (
    AUTOPSY_DETECTOR_NAME,
    FROZEN_SIX_B_DETECTOR_NAME,
    named_subset_detector_name,
)

_REPO = Path(__file__).resolve().parents[2]

_FROZEN_ATLAS = "atlas-mahalanobis"
_FROZEN_SENTIEL = "aggregate:gaussian:peer set (34 features)"


def test_var_and_correlation_names_are_not_the_public_mahalanobis_row() -> None:
    assert var_contenders()[0].name != _FROZEN_ATLAS
    assert correlation_contenders()[0].name != _FROZEN_ATLAS
    assert "model:" + var_contenders()[0].name != "model:atlas-mahalanobis"


def test_autopsy_name_is_not_the_public_six_b_row() -> None:
    # `str(...)` for the same reason as in tests/sentiel/test_autopsy.py: the two names are
    # `Final` literals, so mypy calls the comparison non-overlapping. The pin stays (ADR 0065).
    assert str(AUTOPSY_DETECTOR_NAME) != str(FROZEN_SIX_B_DETECTOR_NAME)
    assert _FROZEN_SENTIEL not in AUTOPSY_DETECTOR_NAME
    assert AUTOPSY_DETECTOR_NAME.startswith("autopsy:")


def test_named_subset_and_autopsy_script_cannot_rewrite_six_b() -> None:
    assert named_subset_detector_name("http_count") != FROZEN_SIX_B_DETECTOR_NAME
    script = (_REPO / "scripts" / "autopsy_sentiel_6b.py").read_text(encoding="utf-8")
    assert "append_to_experiment_log" not in script


def test_correlation_refuse_is_on_disk_and_unlogged() -> None:
    refuse = (_REPO / "eval_runs" / "atlas" / "hai-correlation-refuse.md").read_text(
        encoding="utf-8"
    )
    assert "singular" in refuse.lower()
    assert "646.58" in refuse
    log = (_REPO / "eval_runs" / "log.jsonl").read_text(encoding="utf-8")
    assert '"detector_name":"model:atlas-mahalanobis-correlation"' not in log
