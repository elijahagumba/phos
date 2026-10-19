"""Suggest a role and a kind for each tag, for an engineer to confirm or change (ADR 0220).

A historian export gives tag names and a sample of values. A capture table gives tag references
that were observed, marked read or write when the table says so. This package proposes, for each
tag, a role (sensor, actuator, or setpoint — the same three as `SignalRole`) and a kind (flow,
pressure, level, pump, or valve), and names the token or the statistic the proposal came from.

**A suggestion is not a declaration.** ADR 0123: a role the plant map trusts is read from
documentation, never from a name and never from the data. ``P1_FCV01D`` can suggest a valve
command. Until an engineer confirms it, that is all it is. This package does not call
`load_roles`, does not write a role file, and does not score a detector.

Kind comes only from a name token. A sample can support a role (a target that sits and then steps,
or a reading that keeps moving) when no token already named one. A capture write against a sensor
token is shown and does not replace the token. Reads alone are not a role. Writes alone do not
choose between an actuator and a setpoint.

Passive: no network calls, no agents, no subprocesses. File reading happens only in `main`.
"""

from __future__ import annotations

import argparse
import gzip
import math
import sys
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from phos.atlas.onboarding._models import (
    BRIEF_HEADER,
    MIN_SAMPLE,
    SAMPLE_ROWS,
    SUGGESTION_IS_NOT_A_DECLARATION,
    CaptureHit,
    SuggestionEvidence,
    TagKind,
    TagSample,
    TagSuggestion,
)
from phos.atlas.onboarding._names import from_name
from phos.atlas.onboarding._tables import parse_capture, parse_historian, read_csv_rows
from phos.atlas.signal_roles import SignalRole

__all__ = [
    "BRIEF_HEADER",
    "SAMPLE_ROWS",
    "SUGGESTION_IS_NOT_A_DECLARATION",
    "CaptureHit",
    "SuggestionEvidence",
    "TagKind",
    "TagSample",
    "TagSuggestion",
    "format_brief",
    "main",
    "parse_capture",
    "parse_historian",
    "read_csv_rows",
    "suggest",
]


def suggest(
    historian: Sequence[TagSample],
    capture: Sequence[CaptureHit] = (),
) -> tuple[TagSuggestion, ...]:
    """Suggest a role and a kind for every tag in the historian or the capture.

    Historian order is kept. A tag that appears only in the capture is appended in the order it
    was first referred to. A repeated historian tag keeps its first sample.

    Args:
        historian: Tag names and a sample of values. Values may be empty.
        capture: Observed tag references. May be empty.

    Returns:
        One suggestion per tag. ``role`` or ``kind`` is ``None`` when the evidence does not
        support a guess. Every suggestion carries at least one evidence item.
    """
    order: list[str] = []
    samples: dict[str, tuple[float, ...]] = {}
    for sample in historian:
        if sample.tag not in samples:
            order.append(sample.tag)
            samples[sample.tag] = sample.values
    seen: set[str] = set()
    for hit in capture:
        seen.add(hit.tag)
        if hit.tag not in samples:
            order.append(hit.tag)
            samples[hit.tag] = ()
    tally = _tally(capture)
    return tuple(_one(tag, samples[tag], tally.get(tag), tag in seen) for tag in order)


def format_brief(suggestions: Sequence[TagSuggestion]) -> str:
    """Return the suggestion list an engineer accepts or edits.

    Args:
        suggestions: The proposals from `suggest`, in the order to print them.

    Returns:
        A header, then one tab-separated line per tag: tag, role, kind, evidence.
        A blank role or kind is a cell the engineer fills in.
    """
    lines = [BRIEF_HEADER, "tag\trole\tkind\tevidence"]
    for item in suggestions:
        role = item.role.value if item.role is not None else ""
        kind = item.kind.value if item.kind is not None else ""
        evidence = item.evidence_text.replace("\t", " ").replace("\n", " ")
        lines.append(f"{item.tag}\t{role}\t{kind}\t{evidence}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print a suggestion list for a historian export and a capture table.

    Args:
        argv: Command-line arguments, excluding the program name. ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when the brief was printed, ``2`` when an input could not be read.
    """
    parser = argparse.ArgumentParser(
        description="Suggest a role and a kind for each tag. Suggestions are not declarations."
    )
    parser.add_argument("--historian", type=Path, required=True, help="CSV of tag names and values")
    parser.add_argument(
        "--capture", type=Path, required=True, help="CSV of observed tag references"
    )
    parser.add_argument("--sample-rows", type=int, default=SAMPLE_ROWS)
    parser.add_argument("--out", type=Path, default=None, help="Also write the brief to this path")
    args = parser.parse_args(argv)
    try:
        historian_rows = read_csv_rows(args.historian, max_data_rows=args.sample_rows)
        capture_rows = read_csv_rows(args.capture, max_data_rows=None)
        historian = parse_historian(historian_rows, sample_rows=args.sample_rows)
        capture = parse_capture(capture_rows)
    except (OSError, ValueError, gzip.BadGzipFile) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    brief = format_brief(suggest(historian, capture))
    sys.stdout.write(brief)
    if args.out is not None:
        args.out.write_text(brief, encoding="utf-8")
    return 0


def _one(
    tag: str,
    values: tuple[float, ...],
    counts: tuple[int, int, int] | None,
    in_capture: bool,
) -> TagSuggestion:
    kind, role, evidence = from_name(tag)
    items = list(evidence)
    stat_role, stat_item = _from_values(values)
    if role is None:
        if stat_role is not None:
            role = stat_role
        if stat_item is not None:
            items.append(stat_item)
    elif stat_role is not None and stat_item is not None:
        items.append(_statistic_beside_token(stat_role, role, stat_item))
    if in_capture and counts is not None:
        items.extend(_from_capture(role, counts))
    return TagSuggestion(tag=tag, role=role, kind=kind, evidence=tuple(items))


def _statistic_beside_token(
    stat_role: SignalRole,
    token_role: SignalRole,
    stat_item: SuggestionEvidence,
) -> SuggestionEvidence:
    if stat_role is token_role:
        return stat_item
    note = "statistic disagrees with the token; the suggestion keeps the token. "
    return SuggestionEvidence(statistic=stat_item.statistic, text=note + stat_item.text)


def _from_values(
    values: Sequence[float],
) -> tuple[SignalRole | None, SuggestionEvidence | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    count = len(finite)
    if count == 0:
        return None, None
    if count < MIN_SAMPLE:
        return None, SuggestionEvidence(
            statistic=f"n={count}",
            text=f"statistic: {count} finite values, below {MIN_SAMPLE}, so no role",
        )
    rounded = [round(value, 5) for value in finite]
    distinct = len(set(rounded))
    plateaus = sum(1 for left, right in pairwise(rounded) if left == right)
    fraction = plateaus / (count - 1)
    summary = f"{distinct} distinct values in {count} samples, plateau fraction {fraction:.2f}"
    if distinct == 1:
        return None, SuggestionEvidence(
            statistic=summary,
            text=(
                f"statistic: {summary}; a constant sample does not separate "
                "a setpoint from a stuck sensor"
            ),
        )
    if distinct <= 15 and distinct / count <= 0.05 and fraction >= 0.85:
        return SignalRole.SETPOINT, SuggestionEvidence(
            statistic=summary,
            text=f"statistic: {summary} (a target that sits, then steps)",
        )
    if distinct / count >= 0.25 and fraction < 0.50:
        return SignalRole.SENSOR, SuggestionEvidence(
            statistic=summary,
            text=f"statistic: {summary} (a reading that keeps moving)",
        )
    return None, SuggestionEvidence(
        statistic=summary,
        text=f"statistic: {summary}; not used as a role",
    )


def _from_capture(
    role: SignalRole | None,
    counts: tuple[int, int, int],
) -> tuple[SuggestionEvidence, ...]:
    reads, writes, unknown = counts
    if writes and role is SignalRole.SENSOR:
        return (
            SuggestionEvidence(
                capture=f"writes={writes}",
                text=(
                    f"capture: {writes} write references; a write contradicts a sensor token. "
                    "The suggestion keeps the token."
                ),
            ),
        )
    if writes and role is None:
        reads_text = f" and {reads} read references" if reads else " and no reads"
        return (
            SuggestionEvidence(
                capture=f"writes={writes}",
                text=(
                    f"capture: {writes} write references{reads_text}; "
                    "a write supports an actuator or a setpoint, not which one"
                ),
            ),
        )
    if reads and not writes and role is None:
        return (
            SuggestionEvidence(
                capture=f"reads={reads}",
                text=f"capture: {reads} read references and no writes; reads alone are not a role",
            ),
        )
    if unknown and not reads and not writes and role is None:
        return (
            SuggestionEvidence(
                capture=f"unknown={unknown}",
                text=(
                    f"capture: {unknown} references with no read or write access; "
                    "not used as a role"
                ),
            ),
        )
    return ()


def _tally(capture: Sequence[CaptureHit]) -> dict[str, tuple[int, int, int]]:
    reads: dict[str, int] = {}
    writes: dict[str, int] = {}
    unknown: dict[str, int] = {}
    buckets = {"read": reads, "write": writes, "unknown": unknown}
    for hit in capture:
        bucket = buckets[hit.access]
        bucket[hit.tag] = bucket.get(hit.tag, 0) + hit.count
    tags = set(reads) | set(writes) | set(unknown)
    return {tag: (reads.get(tag, 0), writes.get(tag, 0), unknown.get(tag, 0)) for tag in tags}
