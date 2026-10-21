"""The one clean HAI score: HAI 22.04 and 23.05, declared before it is run.

Ungrouped names stay ``g1-baseline:``. Grouped names stay ``g1-grouped:``. These two
editions are not labelled seen. The summary line "Attacks: 40 times" on HAI 23.05
test 2 is not the denominator.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from phos.eval.baseline_report import recall_comparison
from phos.eval.baseline_table import (
    ATLAS_DETECTOR,
    CHECKED_OPPONENTS,
    DETECTORS,
    ROUTING_REGISTERS,
    CorpusReport,
)
from phos.eval.grouped_rows import GROUPED_CORPORA, GroupedRow, render_grouped_section

CLEAN_CORPORA: tuple[str, ...] = ("hai-22.04", "hai-23.05")
DECLARED_FEATURES = 86
HAI_2204_TEST_ATTACKS: Mapping[str, int] = {
    "test1.csv": 7,
    "test2.csv": 17,
    "test3.csv": 10,
    "test4.csv": 24,
}
HAI_2204_ATTACKS = 58
HAI_2204_TRAIN_ATTACKS: Mapping[str, int] = {
    "train1.csv": 0,
    "train2.csv": 0,
    "train3.csv": 0,
    "train4.csv": 0,
    "train5.csv": 0,
    "train6.csv": 0,
}
HAI_2305_TEST_ATTACKS: Mapping[str, int] = {
    "hai-test1.csv": 14,
    "hai-test2.csv": 38,
}
HAI_2305_ATTACKS = 52
HAI_2305_SUMMARY_HEADER_ATTACKS = 40
HAI_2305_TRAINS: tuple[str, ...] = (
    "hai-train1.csv",
    "hai-train2.csv",
    "hai-train3.csv",
    "hai-train4.csv",
)
CLEAN_JSON_NAME = "g1-clean-hai.json"
PUBLISHED_GUARD = "| hai-20.07 | yes | g1-baseline:atlas-mahalanobis | engine | 9 | 38 |"
_NOT_SCORED_ROW = {
    "hai-22.04": "| hai-22.04 | yes | — | — | — | — | not scored |",
    "hai-23.05": "| hai-23.05 | yes | — | — | — | — | not scored |",
}
_NOT_ON_DISK = {
    "hai-22.04": (
        "hai-22.04: not scored (Git LFS pointer (ADR 0087); the CSV is not on disk). "
        "Counts as not won."
    ),
    "hai-23.05": (
        "hai-23.05: not scored (Git LFS pointer (ADR 0087); the CSV is not on disk). "
        "Counts as not won."
    ),
}
_NOTE_LINE = {
    "hai-22.04": (
        "- **hai-22.04** (not_scored): no sample period; declared 1 s. "
        "Git LFS pointer (ADR 0087); the CSV is not on disk"
    ),
    "hai-23.05": (
        "- **hai-23.05** (not_scored): no sample period; declared 1 s. "
        "Git LFS pointer (ADR 0087); the CSV is not on disk"
    ),
}
_BESIDE_ANCHOR = "| hai-21.03 | g1-baseline:simple-histogram |"
_GROUPED_SENTENCE = "HAI 22.04 and 23.05 are not scored here."
_GROUPED_REPLACEMENT = (
    "HAI 22.04 and 23.05 are the clean run, scored once, and are not labelled seen."
)


def _unscored_json(corpus: str) -> str:
    """The published ``not_scored`` object, byte for byte, including its indentation."""
    comparison = (
        f'"comparison": "{corpus}: not scored (Git LFS pointer (ADR 0087); '
        'the CSV is not on disk). Counts as not won."'
    )
    return (
        "    {\n"
        f'      "corpus": "{corpus}",\n'
        '      "judges": true,\n'
        '      "status": "not_scored",\n'
        '      "note": "Git LFS pointer (ADR 0087); the CSV is not on disk",\n'
        '      "sample_period_seconds": null,\n'
        '      "declared_period_seconds": 1.0,\n'
        f"      {comparison},\n"
        '      "scores": [],\n'
        '      "files": []\n'
        "    }"
    )


_JSON_NOT_SCORED = {corpus: _unscored_json(corpus) for corpus in CLEAN_CORPORA}


def attack_runs(flags: Sequence[bool]) -> int:
    """Count contiguous true runs. A true cell directly after a true cell extends one run."""
    count = 0
    previous = False
    for flag in flags:
        if flag and not previous:
            count += 1
        previous = bool(flag)
    return count


def features_hai_2204(columns: Sequence[str]) -> tuple[str, ...]:
    """Feature names from a HAI 22.04 header: ``timestamp``, tags, ``Attack``."""
    if not columns or columns[0] != "timestamp" or columns[-1] != "Attack":
        raise ValueError("HAI 22.04 must start with timestamp and end with Attack")
    if any(str(column).lower().startswith("attack") for column in columns[:-1]):
        raise ValueError("HAI 22.04 has one Attack column, at the end")
    features = tuple(column for column in columns[1:-1] if column not in ROUTING_REGISTERS)
    if len(features) != DECLARED_FEATURES:
        raise ValueError(f"HAI 22.04 has {len(features)} features, declared {DECLARED_FEATURES}")
    return features


def features_hai_2305(columns: Sequence[str]) -> tuple[str, ...]:
    """Feature names from a HAI 23.05 series header. There is no Attack column."""
    if not columns or columns[0] != "timestamp":
        raise ValueError("HAI 23.05 series must start with timestamp")
    lowered = {column.lower() for column in columns}
    if "attack" in lowered or "label" in lowered:
        raise ValueError("HAI 23.05 series files have no Attack column and no label column")
    features = tuple(column for column in columns[1:] if column not in ROUTING_REGISTERS)
    if len(features) != DECLARED_FEATURES:
        raise ValueError(f"HAI 23.05 has {len(features)} features, declared {DECLARED_FEATURES}")
    return features


def label_columns_hai_2305(columns: Sequence[str]) -> None:
    """Raise unless a HAI 23.05 label file is exactly ``timestamp,label``."""
    if tuple(columns) != ("timestamp", "label"):
        raise ValueError(f"HAI 23.05 labels must be timestamp,label, got {tuple(columns)}")


def declared_test_attacks(corpus: str) -> Mapping[str, int]:
    """Per-file attack-run counts the clean run must see before it fits."""
    if corpus == "hai-22.04":
        return HAI_2204_TEST_ATTACKS
    if corpus == "hai-23.05":
        return HAI_2305_TEST_ATTACKS
    raise ValueError(f"{corpus} is not in the clean run")


def assert_declared_counts(corpus: str, counted: Mapping[str, int]) -> None:
    """Raise if a file's attack runs are not the count written down before the run."""
    expected = declared_test_attacks(corpus)
    if dict(counted) != dict(expected):
        raise ValueError(f"{corpus} attack runs {dict(counted)} are not {dict(expected)}")


def splice_clean_markdown(
    text: str, reports: Sequence[CorpusReport], grouped: Sequence[GroupedRow]
) -> str:
    """Fill the two unscored placeholders. Leave every other published line in place."""
    if len(reports) != 2 or tuple(report.corpus for report in reports) != CLEAN_CORPORA:
        raise ValueError("the clean splice scores hai-22.04 then hai-23.05")
    if tuple(row.corpus for row in grouped) != CLEAN_CORPORA:
        raise ValueError("grouped rows follow the same two corpora")
    if any(row.exposure is not None for row in grouped):
        raise ValueError("the clean HAI editions are not labelled seen")
    _require_once(text, PUBLISHED_GUARD)
    updated = text
    for report in reports:
        updated = _replace_once(updated, _NOT_SCORED_ROW[report.corpus], _headline_rows(report))
        updated = _replace_once(updated, _NOT_ON_DISK[report.corpus], recall_comparison(report))
        updated = _replace_once(updated, _NOTE_LINE[report.corpus], _note_line(report))
    beside = "\n".join(_beside_row(report) for report in reports)
    updated = _insert_after_line(updated, _BESIDE_ANCHOR, beside)
    updated = _replace_once(updated, _GROUPED_SENTENCE, _GROUPED_REPLACEMENT)
    block = "\n".join(_grouped_block(row) for row in grouped)
    updated = _insert_before_line(updated, "## Grouped notes", block)
    _require_once(updated, PUBLISHED_GUARD)
    if "not on disk" in updated:
        raise ValueError("the clean splice left the not-on-disk sentence in place")
    return updated


def render_published_grouped_section(
    base: Sequence[GroupedRow], clean: Sequence[GroupedRow]
) -> str:
    """The grouped block of the G1 table, rendered from scored rows.

    ``base`` is the five corpora in `GROUPED_CORPORA`. ``clean`` is HAI 22.04
    then HAI 23.05, and neither is labelled seen. The five-corpus renderer says
    those two editions are not scored; this replaces that sentence and inserts
    their blocks before the notes. It does not read the committed markdown.

    Raises:
        ValueError: The rows are not those corpora, or a clean edition is labelled seen.
    """
    if tuple(row.corpus for row in base) != GROUPED_CORPORA:
        raise ValueError("grouped rows are not the five published corpora, in order")
    if tuple(row.corpus for row in clean) != CLEAN_CORPORA:
        raise ValueError("the clean grouped rows are not hai-22.04 then hai-23.05")
    if any(row.exposure is not None for row in clean):
        raise ValueError("the clean HAI editions are not labelled seen")
    text = render_grouped_section(base)
    if text.count(_GROUPED_SENTENCE) != 1:
        raise ValueError("the grouped renderer did not name the clean editions once")
    text = text.replace(_GROUPED_SENTENCE, _GROUPED_REPLACEMENT, 1)
    block = "\n".join(_grouped_block(row) for row in clean)
    return _insert_before_line(text, "## Grouped notes", block)


def splice_clean_json(text: str, reports: Sequence[CorpusReport]) -> str:
    """Replace the two ``not_scored`` objects. Do not reformat the rest of the file."""
    if tuple(report.corpus for report in reports) != CLEAN_CORPORA:
        raise ValueError("the clean JSON splice scores hai-22.04 then hai-23.05")
    updated = text
    for report in reports:
        updated = _replace_once(updated, _JSON_NOT_SCORED[report.corpus], _json_object(report))
    if "not on disk" in updated:
        raise ValueError("the clean JSON splice left the not-on-disk note in place")
    return updated


def _headline_rows(report: CorpusReport) -> str:
    judges = "yes" if report.judges else "no"
    lines = []
    for score in report.scores:
        checked = "engine" if score.detector == ATLAS_DETECTOR else "yes"
        if score.detector not in DETECTORS and score.detector not in CHECKED_OPPONENTS:
            raise ValueError(f"{score.detector} is not a published G1 detector")
        lines.append(
            f"| {report.corpus} | {judges} | {score.detector} | {checked} | "
            f"{score.caught} | {score.attacks} | {score.recall_within_budget:.6f} |"
        )
    return "\n".join(lines)


def _beside_row(report: CorpusReport) -> str:
    lines = []
    for score in report.scores:
        lines.append(
            f"| {report.corpus} | {score.detector} | {score.recall_within_budget:.6f} | "
            f"{score.etapr_reference_f1:.6f} | {score.etapr_haicon_f1:.6f} | "
            f"{score.point_adjusted_f1:.6f} | {score.alerts} |"
        )
    return "\n".join(lines)


def _note_line(report: CorpusReport) -> str:
    period = (
        "no sample period"
        if report.sample_period_seconds is None
        else f"measured median step {report.sample_period_seconds:.6g} s"
    )
    declared = (
        "no declared period"
        if report.declared_period_seconds is None
        else f"declared {report.declared_period_seconds:.6g} s"
    )
    return f"- **{report.corpus}** ({report.status}): {period}; {declared}. {report.note}"


def _grouped_block(row: GroupedRow) -> str:
    exposure = row.exposure if row.exposure is not None else ""
    lines = []
    for score in row.scores:
        lines.append(
            f"| {row.corpus} | {exposure} | {score.detector} | {score.caught} | "
            f"{score.attacks} | {score.recall_within_budget:.6f} |"
        )
    listed = ", ".join(row.attacks_only_grouped_atlas) or "none"
    lines.append("")
    lines.append(
        f"{row.corpus}: beyond grouping {row.beyond_grouping}. "
        f"Attacks only grouped Atlas catches: {listed}."
    )
    lines.append("")
    return "\n".join(lines)


def _json_object(report: CorpusReport) -> str:
    payload = {
        "corpus": report.corpus,
        "judges": report.judges,
        "status": report.status,
        "note": report.note,
        "sample_period_seconds": report.sample_period_seconds,
        "declared_period_seconds": report.declared_period_seconds,
        "comparison": recall_comparison(report),
        "scores": [asdict(score) for score in report.scores],
        "files": [asdict(file) for file in report.files],
    }
    dumped = json.dumps(payload, indent=2)
    return "\n".join(f"    {line}" if line else line for line in dumped.splitlines())


def _require_once(text: str, needle: str) -> None:
    if text.count(needle) != 1:
        raise ValueError(f"expected one occurrence of {needle!r}")


def _replace_once(text: str, old: str, new: str) -> str:
    _require_once(text, old)
    return text.replace(old, new, 1)


def _insert_after_line(text: str, prefix: str, block: str) -> str:
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"expected one line starting with {prefix!r}")
    index = matches[0]
    lines[index : index + 1] = [lines[index], *block.splitlines()]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _insert_before_line(text: str, exact: str, block: str) -> str:
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == exact]
    if len(matches) != 1:
        raise ValueError(f"expected one line {exact!r}")
    index = matches[0]
    lines[index:index] = [*block.splitlines(), ""]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
