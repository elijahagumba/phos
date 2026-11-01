"""The spent H1 agreement script stays on disk and must not be re-run.

ADR 0371 spent the look. ADR 0382 forbids running ``scripts/lane_h_code_laws.py``
again. These tests only assert the script still refuses to touch the log and
that the successor report is the one under test elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from phos.atlas.code_law.report import RESULT_NAME


def test_the_spent_script_does_not_append_log_jsonl() -> None:
    source = Path("scripts/lane_h_code_laws.py").read_text()
    assert "log.jsonl" not in source


def test_the_live_result_name_is_the_guard_form_one() -> None:
    # ADR 0382 replaced the report module for the successor command. The spent
    # script is not re-run; the live result name is the guard-form one.
    assert RESULT_NAME == "code-law:guard-form"
