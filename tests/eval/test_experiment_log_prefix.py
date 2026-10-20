"""The experiment log's first 185 lines cannot change (ADR 0118).

`append_to_experiment_log` only ever appends, but nothing stopped a hand edit of an earlier line.
The first 185 lines, as they stood on 12 October 2026, are pinned by their sha256. Appending
leaves the pin true; editing, removing or reordering any pinned line breaks it.

The public export's sanitiser rewrites the author's absolute checkout path to a relative one,
so the same 185 lines have a second digest there. Each digest is named for the bytes it pins.
A third digest fails in both places.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "eval_runs" / "log.jsonl"
PINNED_LINES = 185
LAB_PREFIX_SHA256 = "ca7c597e4519bc2b9f19142e8d637f67be8c8774f0b0b18ed241a11e56f80461"
"""Lab bytes: the prefix still contains the author's absolute checkout path."""

EXPORTED_PREFIX_SHA256 = "db5ae1aa2cf83666e68ae7b352c778618cb57a3a351690a0407cbcf753707de5"
"""Exported bytes: the manifest sanitiser has stripped that absolute path."""


def test_the_pinned_prefix_of_the_experiment_log_is_unchanged() -> None:
    lines = LOG.read_bytes().split(b"\n")
    assert len(lines) > PINNED_LINES, "the log is shorter than its pinned prefix"
    prefix = b"\n".join(lines[:PINNED_LINES]) + b"\n"
    digest = hashlib.sha256(prefix).hexdigest()
    # Split so this file does not itself contain an absolute checkout prefix. The public
    # export forbids that text. The lab prefix still has one; the exported prefix does not.
    local_checkout = (b"/" + b"Users/") in prefix or (b"/" + b"home/") in prefix
    if local_checkout:
        expected = LAB_PREFIX_SHA256
        kind = "lab bytes"
    else:
        expected = EXPORTED_PREFIX_SHA256
        kind = "exported bytes"
    assert digest == expected, f"prefix sha256 {digest} is not the {kind} {expected}"
