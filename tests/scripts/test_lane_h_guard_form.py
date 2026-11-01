"""The H1 guard-form report renderer, exercised without running the declared score.

ADR 0382's command reads the pinned ICSSim checkout. That run is the declared
score and it is not run here: these tests render the report from a law derived
out of the fixtures, so the one look stays unspent.
"""

from __future__ import annotations

from pathlib import Path

from scripts.lane_h_guard_form import DEFAULT_REPORT, main
from tests.atlas.code_law.fixtures import CONFIGS_TEXT, DEVICE_TEXT, PLC1_TEXT

from phos.atlas.code_law import (
    RefusalReason,
    SourceRefusal,
    check_agreement,
    derive_valve_law,
    pinned_source_from_text,
)
from phos.atlas.code_law.report import RESULT_NAME, refusal_markdown, report_markdown

SCORE_WORDS = ("confidence", "probability", "weight", "magnitude", "score")
RATE_WORDS = ("recall", "false-positive", "percentage", "coverage", "precision")


def _report() -> str:
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=PLC1_TEXT, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.law is not None
    return report_markdown(derivation.law, check_agreement(derivation.law))


def test_the_report_names_the_declared_result() -> None:
    assert RESULT_NAME == "code-law:guard-form"
    assert _report().startswith(f"# {RESULT_NAME}")


def test_the_default_report_path_is_the_declared_one() -> None:
    assert DEFAULT_REPORT.name == "h1-guard-form.md"
    assert "lane-h" in str(DEFAULT_REPORT)


def test_the_report_states_every_bar_as_met_or_not_met() -> None:
    report = _report()
    for name in (
        "literal agreement, quoted from the source node",
        "comparison agreement on both sides",
        "guard comparison is on the guard's form",
        "forced actuator writes at modes 1 and 2 are a stated fact",
        "every disagreement on the extended enumeration is listed, with a certificate",
        "certificate shape",
        "the tree stays green",
    ):
        assert name in report
    assert "not met" in report


def test_the_report_quotes_the_source_literal_text() -> None:
    report = _report()
    assert "`0`" in report
    assert "`1`" in report
    assert "`3`" in report
    assert "`1.0`" in report


def test_the_report_lists_forced_writes() -> None:
    report = _report()
    assert "forced actuator writes" in report.casefold() or "Forced actuator" in report


def test_the_report_lists_disagreements() -> None:
    report = _report()
    assert "disagreement" in report.casefold()
    assert "- none" not in report.split("## Enumerated disagreements")[1][:200]


def test_the_report_quotes_the_files_and_digests_it_read() -> None:
    report = _report()
    for relative in ("src/PLC1.py", "src/Configs.py", "src/ics_sim/Device.py"):
        assert relative in report
    assert "sha256" in report


def test_the_report_carries_no_score_word() -> None:
    folded = _report().casefold()
    for word in SCORE_WORDS:
        assert word not in folded


def test_the_report_carries_no_rate_word() -> None:
    folded = _report().casefold()
    for word in RATE_WORDS:
        assert word not in folded


def test_the_report_says_the_source_was_not_executed() -> None:
    report = _report()
    assert "not imported, executed or simulated" in report
    assert "roles.toml` was not read" in report


def test_a_refused_run_is_written_out_in_the_same_shape() -> None:
    refusal = refusal_markdown(
        [
            SourceRefusal(
                relative="src/PLC1.py",
                reason=RefusalReason.DIGEST_MISMATCH,
                expected="a" * 64,
                found="b" * 64,
            )
        ]
    )
    assert refusal.startswith(f"# {RESULT_NAME} - refused")
    assert "digest mismatch" in refusal
    assert "No bar was evaluated" in refusal
    for word in SCORE_WORDS:
        assert word not in refusal.casefold()


def test_main_refuses_a_missing_checkout(tmp_path: Path) -> None:
    out = tmp_path / "h1-guard-form.md"
    status = main(["--icssim", str(tmp_path / "missing"), "--out", str(out)])
    assert status == 1
    assert out.is_file()
    assert "refused" in out.read_text().casefold()


def test_the_script_does_not_append_log_jsonl() -> None:
    # The module never names log.jsonl. A regression that wrote to it would
    # have to import or open that path.
    source = Path("scripts/lane_h_guard_form.py").read_text()
    assert "log.jsonl" not in source
