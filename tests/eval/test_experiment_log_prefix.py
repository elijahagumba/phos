"""The experiment log's first 185 lines cannot change (ADR 0118).

`append_to_experiment_log` only ever appends, but nothing stopped a hand edit of an earlier line.
The first 185 lines, as they stood on 12 October 2026, are pinned by their sha256. Appending
leaves the pin true; editing, removing or reordering any pinned line breaks it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "eval_runs" / "log.jsonl"
PINNED_LINES = 185
PINNED_SHA256 = "ca7c597e4519bc2b9f19142e8d637f67be8c8774f0b0b18ed241a11e56f80461"


def test_the_pinned_prefix_of_the_experiment_log_is_unchanged() -> None:
    lines = LOG.read_bytes().split(b"\n")
    assert len(lines) > PINNED_LINES, "the log is shorter than its pinned prefix"
    prefix = b"\n".join(lines[:PINNED_LINES]) + b"\n"
    assert hashlib.sha256(prefix).hexdigest() == PINNED_SHA256
