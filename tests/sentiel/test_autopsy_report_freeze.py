"""The CERT 6B autopsy report exists and does not rewrite precision 0.104."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "eval_runs" / "sentiel" / "6b-autopsy.md"
LOG = REPO / "eval_runs" / "log.jsonl"


def test_autopsy_report_matches_frozen_queue_split() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "autopsy:6b-top-budget" in text
    assert "True positives **5**" in text
    assert "False positives **43**" in text
    assert "0.104" in text
    assert "do not invent a subset" in text
    assert "aggregate:gaussian:peer set (34 features) (6B)" in text
    assert "not" in text.lower()


def test_experiment_log_has_no_autopsy_detector_row() -> None:
    blob = LOG.read_text(encoding="utf-8")
    assert '"detector_name":"autopsy:6b-top-budget"' not in blob
    assert '"detector_name":"aggregate:gaussian:peer set (34 features) (6B)"' not in blob
