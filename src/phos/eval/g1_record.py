"""Rebuild the G1 table from a recompute of every corpus.

Every corpus in the published order is checked against the committed JSON. This
module does not open a data file. It returns a table only when the rebuilt text
is identical to the committed markdown. The grouped section is the block the
caller rendered from the files. This module does not copy it out of the
committed markdown.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Final, cast

from phos.eval.baseline_report import render_report
from phos.eval.baseline_table import CorpusReport, DetectorScore

DEVELOPMENT_CORPORA: Final[tuple[str, ...]] = (
    "hai-20.07",
    "batch-distillation",
    "data4cyber",
)
VALIDATION_CORPORA: Final[tuple[str, ...]] = (
    "hai-21.03",
    "hai-22.04",
    "hai-23.05",
    "batadal",
)
TABLE_ORDER: Final[tuple[str, ...]] = (
    "hai-20.07",
    "hai-21.03",
    "hai-22.04",
    "hai-23.05",
    "batadal",
    "batch-distillation",
    "data4cyber",
)
GROUPED_HEADING: Final = "## Grouped rows"
_FIELDS: Final[tuple[str, ...]] = (
    "detector",
    "attacks",
    "caught",
    "recall_within_budget",
    "etapr_reference_f1",
    "etapr_haicon_f1",
    "point_adjusted_f1",
    "alerts",
)
_HEADER: Final[tuple[str, ...]] = (
    "judges",
    "status",
    "note",
    "sample_period_seconds",
    "declared_period_seconds",
)


class RecordMismatchError(Exception):
    """The recompute does not match the committed record, or the record cannot be reprinted."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        """Store one line per difference. The message is those lines joined."""
        self.problems = problems
        super().__init__("\n".join(problems))


def corpora_from_json(text: str) -> tuple[Mapping[str, object], ...]:
    """The ``corpora`` array of a committed G1 JSON document.

    Raises:
        RecordMismatchError: The text is not that document.
    """
    loaded = cast(object, json.loads(text))
    if not isinstance(loaded, dict):
        raise RecordMismatchError(("the committed JSON is not an object",))
    raw = loaded.get("corpora")
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise RecordMismatchError(("the committed JSON has no corpora array",))
    corpora = tuple(cast(Mapping[str, object], item) for item in raw)
    return corpora


def rebuild_markdown(
    committed_markdown: str,
    recorded: Sequence[Mapping[str, object]],
    fresh: Mapping[str, CorpusReport],
    grouped_section: str,
) -> str:
    """Return the G1 markdown when the recompute matches the committed record.

    ``fresh`` must contain every corpus in `TABLE_ORDER`. Each report is compared
    with the committed JSON. ``grouped_section`` is the grouped block rendered
    from the files, starting at the grouped heading. The committed markdown is
    the comparison, not the source of that block. The result is returned only
    when it equals that markdown, so a caller that writes it does not change a
    recorded digit.

    Raises:
        RecordMismatchError: A corpus was not recomputed, a field differs, the
            grouped section was not rendered, or the rebuilt text would not equal
            the committed markdown.
    """
    problems = _recompute_problems(fresh, recorded)
    if problems:
        raise RecordMismatchError(problems)
    if not grouped_section.startswith(GROUPED_HEADING):
        raise RecordMismatchError(("the rendered grouped section has no grouped heading",))
    reports = tuple(fresh[name] for name in TABLE_ORDER)
    rebuilt = _join_grouped(render_report(reports), grouped_section)
    if rebuilt != committed_markdown:
        raise RecordMismatchError(
            (
                "rebuilding the table would change the committed markdown; "
                + _first_line_diff(rebuilt, committed_markdown),
            )
        )
    return rebuilt


def _join_grouped(rendered: str, grouped: str) -> str:
    """Place one blank line between the rendered headline and the grouped section."""
    if rendered.endswith("\n"):
        return rendered + "\n" + grouped
    return rendered + "\n\n" + grouped


def _recompute_problems(
    fresh: Mapping[str, CorpusReport], recorded: Sequence[Mapping[str, object]]
) -> tuple[str, ...]:
    names = tuple(_as_str(corpus.get("corpus"), "corpus") for corpus in recorded)
    problems: list[str] = []
    if names != TABLE_ORDER:
        problems.append("the committed corpora are not in the published order")
    if tuple(fresh) != TABLE_ORDER:
        problems.append("the recompute is not every published corpus, in order")
    by_name = _by_corpus(recorded)
    for name in TABLE_ORDER:
        report = fresh.get(name)
        corpus = by_name.get(name)
        if report is None:
            problems.append(f"{name} was not recomputed")
            continue
        if corpus is None:
            problems.append(f"{name} is missing from the committed record")
            continue
        problems.extend(_compare_corpus(name, report, corpus))
    return tuple(problems)


def _compare_corpus(
    name: str, fresh: CorpusReport, recorded: Mapping[str, object]
) -> tuple[str, ...]:
    problems: list[str] = []
    for field in _HEADER:
        got = getattr(fresh, field)
        expected = recorded.get(field)
        if got != expected:
            problems.append(f"{name} {field} is {got!r}; the record has {expected!r}")
    problems.extend(_compare_scores(f"{name} corpus", tuple(fresh.scores), recorded.get("scores")))
    raw_files = recorded.get("files")
    if not isinstance(raw_files, list):
        problems.append(f"{name} files are not a list in the record")
        return tuple(problems)
    if len(raw_files) != len(fresh.files):
        problems.append(f"{name} has {len(fresh.files)} files; the record has {len(raw_files)}")
        return tuple(problems)
    for fresh_file, raw in zip(fresh.files, raw_files, strict=True):
        if not isinstance(raw, dict):
            problems.append(f"{name} has a file record that is not an object")
            continue
        file_name = raw.get("file")
        if file_name != fresh_file.file:
            problems.append(f"{name} file {fresh_file.file!r} is {file_name!r} in the record")
        problems.extend(
            _compare_scores(
                f"{name} {fresh_file.file}",
                fresh_file.scores,
                raw.get("scores"),
            )
        )
    return tuple(problems)


def _compare_scores(
    where: str, fresh: Sequence[DetectorScore], recorded: object
) -> tuple[str, ...]:
    try:
        expected = _score_rows(recorded, where)
    except RecordMismatchError as error:
        return error.problems
    got = tuple(_from_detector(score) for score in fresh)
    if got == expected:
        return ()
    if len(got) != len(expected):
        return (f"{where} has {len(got)} detectors; the record has {len(expected)}",)
    problems: list[str] = []
    for index, (left, right) in enumerate(zip(got, expected, strict=True)):
        for field, fresh_value, recorded_value in zip(_FIELDS, left, right, strict=True):
            if fresh_value != recorded_value:
                problems.append(
                    f"{where} detector {index} {field} is {fresh_value!r}; "
                    f"the record has {recorded_value!r}"
                )
    return tuple(problems)


def _score_rows(raw: object, where: str) -> tuple[tuple[object, ...], ...]:
    if not isinstance(raw, list):
        raise RecordMismatchError((f"{where} scores are not a list",))
    rows: list[tuple[object, ...]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise RecordMismatchError((f"{where} has a score that is not an object",))
        rows.append(tuple(_score_field(item, field) for field in _FIELDS))
    return tuple(rows)


def _from_detector(score: DetectorScore) -> tuple[object, ...]:
    return (
        score.detector,
        score.attacks,
        score.caught,
        score.recall_within_budget,
        score.etapr_reference_f1,
        score.etapr_haicon_f1,
        score.point_adjusted_f1,
        score.alerts,
    )


def _score_field(raw: Mapping[str, object], field: str) -> object:
    if field not in raw:
        raise RecordMismatchError((f"a score is missing {field}",))
    value = raw[field]
    if field == "detector":
        return _as_str(value, field)
    if field in {"attacks", "caught", "alerts"}:
        return _as_int(value, field)
    return _as_float(value, field)


def _by_corpus(recorded: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    return {_as_str(corpus.get("corpus"), "corpus"): corpus for corpus in recorded}


def _as_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise RecordMismatchError((f"{field} is not a string",))
    return value


def _as_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordMismatchError((f"{field} is not an integer",))
    return value


def _as_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RecordMismatchError((f"{field} is not a number",))
    return float(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _as_float(value, "period")


def _first_line_diff(rebuilt: str, committed: str) -> str:
    rebuilt_lines = rebuilt.splitlines()
    committed_lines = committed.splitlines()
    for number, pair in enumerate(zip(rebuilt_lines, committed_lines, strict=False), start=1):
        if pair[0] != pair[1]:
            return f"the first different line is {number}"
    return f"the line counts are {len(rebuilt_lines)} and {len(committed_lines)}"
