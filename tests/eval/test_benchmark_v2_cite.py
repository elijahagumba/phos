"""Benchmark v2 cites new names and does not replace the v1 freeze."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V1 = REPO / "eval_runs" / "benchmark" / "phos-benchmark-v1.md"
V2 = REPO / "eval_runs" / "benchmark" / "phos-benchmark-v2.md"


def test_v1_freeze_still_names_the_public_rulers() -> None:
    text = V1.read_text(encoding="utf-8")
    assert "646.58" in text
    assert "18.72" in text
    assert "0.104" in text
    assert "phos-benchmark-v1" in text


def test_v2_cites_var_and_refuses_absent_corpora() -> None:
    text = V2.read_text(encoding="utf-8")
    assert "14071.07" in text
    assert "model:atlas-var1" in text
    assert "Not a rewrite of Benchmark v1" in text
    assert "REFUSED" in text
    assert "form-gated" in text or "iTrust" in text
    assert "singular" in text.lower() or "cannot invert" in text.lower()
    assert "no exclusive stem" in text.lower()
