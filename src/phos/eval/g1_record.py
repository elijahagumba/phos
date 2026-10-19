"""Rebuild the G1 table from a development recompute and the committed validation rows.

Development corpora are checked against the committed JSON. Validation corpora are
reprinted from that JSON. This module does not open a data file, and it returns a
table only when the rebuilt text is identical to the committed markdown.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Final, cast

from phos.eval.baseline_report import render_report
from phos.eval.baseline_table import CorpusReport, DetectorScore, FileScore

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
) -> str:
    """Return the G1 markdown when development matches and validation is reprinted.

    Development reports are rendered from ``fresh``. Validation reports are built
    from ``recorded`` and are not recomputed. The grouped section is copied from
    ``committed_markdown``. The result is returned only when it equals that
    markdown, so a caller that writes it does not change a recorded digit.

    Raises:
        RecordMismatchError: A development field differs, a validation row is not a
            scored record, or the rebuilt text would not equal the committed markdown.
    """
    problems = _validation_problems(recorded) + _development_problems(fresh, recorded)
    if problems:
        raise RecordMismatchError(problems)
    by_name = _by_corpus(recorded)
    reports = tuple(
        fresh[name] if name in DEVELOPMENT_CORPORA else _report_from_record(by_name[name])
        for name in TABLE_ORDER
    )
    heading = committed_markdown.find(GROUPED_HEADING)
    if heading < 0:
        raise RecordMismatchError(("the committed markdown has no grouped section",))
    rebuilt = _join_grouped(render_report(reports), committed_markdown[heading:])
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


def _development_problems(
    fresh: Mapping[str, CorpusReport], recorded: Sequence[Mapping[str, object]]
) -> tuple[str, ...]:
    by_name = _by_corpus(recorded)
    problems: list[str] = []
    if tuple(fresh) != DEVELOPMENT_CORPORA:
        problems.append("the recompute is not exactly the three development corpora, in order")
    for name in DEVELOPMENT_CORPORA:
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


def _validation_problems(recorded: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    names = tuple(_as_str(corpus.get("corpus"), "corpus") for corpus in recorded)
    problems: list[str] = []
    if names != TABLE_ORDER:
        problems.append("the committed corpora are not in the published order")
    by_name = _by_corpus(recorded)
    for name in VALIDATION_CORPORA:
        corpus = by_name.get(name)
        if corpus is None:
            problems.append(f"{name} is missing from the committed record")
            continue
        scores = corpus.get("scores")
        if corpus.get("status") == "not_scored" or not isinstance(scores, list) or not scores:
            problems.append(f"{name} is not a scored row in the committed record")
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


def _report_from_record(corpus: Mapping[str, object]) -> CorpusReport:
    raw_files = corpus.get("files")
    if not isinstance(raw_files, list):
        name = _as_str(corpus.get("corpus"), "corpus")
        raise RecordMismatchError((f"{name} files are not a list",))
    files: list[FileScore] = []
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise RecordMismatchError(("a file score is not an object",))
        file_name = raw.get("file")
        if not isinstance(file_name, str):
            raise RecordMismatchError(("a file name is not a string",))
        scores = tuple(_detector(row) for row in _score_rows(raw.get("scores"), file_name))
        files.append(FileScore(file_name, scores))
    return CorpusReport(
        corpus=_as_str(corpus.get("corpus"), "corpus"),
        judges=_as_bool(corpus.get("judges"), "judges"),
        status=_as_str(corpus.get("status"), "status"),
        note=_as_str(corpus.get("note"), "note"),
        sample_period_seconds=_optional_float(corpus.get("sample_period_seconds")),
        declared_period_seconds=_optional_float(corpus.get("declared_period_seconds")),
        files=tuple(files),
    )


def _score_rows(raw: object, where: str) -> tuple[tuple[object, ...], ...]:
    if not isinstance(raw, list):
        raise RecordMismatchError((f"{where} scores are not a list",))
    rows: list[tuple[object, ...]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise RecordMismatchError((f"{where} has a score that is not an object",))
        rows.append(tuple(_score_field(item, field) for field in _FIELDS))
    return tuple(rows)


def _detector(row: tuple[object, ...]) -> DetectorScore:
    detector, attacks, caught, recall, reference, haicon, adjusted, alerts = row
    return DetectorScore(
        detector=_as_str(detector, "detector"),
        attacks=_as_int(attacks, "attacks"),
        caught=_as_int(caught, "caught"),
        recall_within_budget=_as_float(recall, "recall_within_budget"),
        etapr_reference_f1=_as_float(reference, "etapr_reference_f1"),
        etapr_haicon_f1=_as_float(haicon, "etapr_haicon_f1"),
        point_adjusted_f1=_as_float(adjusted, "point_adjusted_f1"),
        alerts=_as_int(alerts, "alerts"),
    )


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


def _as_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise RecordMismatchError((f"{field} is not a boolean",))
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
