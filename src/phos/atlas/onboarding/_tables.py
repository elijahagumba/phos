"""Read a historian export and a capture table. Local files only (ADR 0220)."""

from __future__ import annotations

import csv
import gzip
import math
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Final, Literal, TextIO

from phos.atlas.onboarding._models import SAMPLE_ROWS, CaptureHit, TagSample

_SKIP_COLUMNS: Final = frozenset(
    {
        "time",
        "timestamp",
        "datetime",
        "date",
        "ts",
        "attack",
        "label",
        "normal",
        "attack_p1",
        "attack_p2",
        "attack_p3",
    }
)


def parse_historian(
    rows: Iterable[Sequence[str]],
    *,
    sample_rows: int = SAMPLE_ROWS,
) -> tuple[TagSample, ...]:
    """Read a historian table into tag samples.

    A wide table has one column per tag and optional time or label columns, which are skipped.
    A long table has a ``tag`` column and a ``value`` column. Only the first ``sample_rows``
    data rows (wide) or values per tag (long) are kept.

    Args:
        rows: CSV rows, header first.
        sample_rows: How many values to keep per tag. At least 1.

    Returns:
        One sample per tag column, in header order, or in first-seen order for a long table.

    Raises:
        ValueError: If ``sample_rows`` is below 1.
    """
    if sample_rows < 1:
        raise ValueError("sample_rows must be at least 1")
    iterator = iter(rows)
    try:
        header = [cell.strip() for cell in next(iterator)]
    except StopIteration:
        return ()
    if _is_long(header):
        return _parse_long(header, iterator, sample_rows)
    return _parse_wide(header, iterator, sample_rows)


def parse_capture(rows: Iterable[Sequence[str]]) -> tuple[CaptureHit, ...]:
    """Read a capture table of observed tag references.

    Args:
        rows: CSV rows, header first. Requires a ``tag`` column. ``access`` and ``count`` are
            optional. Access may be ``read``, ``write``, ``r``, or ``w``.

    Returns:
        One hit per data row that names a tag.

    Raises:
        ValueError: If there is no ``tag`` column, or a count is not a non-negative integer.
    """
    iterator = iter(rows)
    try:
        header = [cell.strip().lower() for cell in next(iterator)]
    except StopIteration:
        return ()
    if "tag" not in header:
        raise ValueError("capture table needs a tag column")
    tag_at = header.index("tag")
    access_at = header.index("access") if "access" in header else None
    count_at = header.index("count") if "count" in header else None
    hits: list[CaptureHit] = []
    for row in iterator:
        if tag_at >= len(row) or not row[tag_at].strip():
            continue
        access: Literal["read", "write", "unknown"] = "unknown"
        if access_at is not None and access_at < len(row):
            access = _access(row[access_at])
        count = _count(row, count_at)
        hits.append(CaptureHit(tag=row[tag_at].strip(), access=access, count=count))
    return tuple(hits)


def read_csv_rows(path: Path, *, max_data_rows: int | None) -> list[list[str]]:
    """Read a CSV or ``.csv.gz`` from disk, optionally stopping after a few data rows.

    Args:
        path: Local file. No network path is fetched.
        max_data_rows: Stop once this many data rows have been read, besides the header.
            ``None`` reads the whole file.

    Returns:
        Rows, header first, each cell a string.

    Raises:
        OSError: If ``path`` cannot be read.
    """
    handle = _open_text(path)
    rows: list[list[str]] = []
    with handle:
        for row in csv.reader(handle):
            rows.append(row)
            if max_data_rows is not None and len(rows) > max_data_rows:
                break
    return rows


def _open_text(path: Path) -> TextIO:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _parse_wide(
    header: Sequence[str],
    rows: Iterator[Sequence[str]],
    sample_rows: int,
) -> tuple[TagSample, ...]:
    chosen = [
        (index, name)
        for index, name in enumerate(header)
        if name and name.lower() not in _SKIP_COLUMNS
    ]
    buckets: list[list[float]] = [[] for _ in chosen]
    taken = 0
    for row in rows:
        if taken >= sample_rows:
            break
        taken += 1
        for slot, (index, _name) in enumerate(chosen):
            if index >= len(row):
                continue
            number = _number(row[index])
            if number is not None:
                buckets[slot].append(number)
    return tuple(
        TagSample(tag=name, values=tuple(buckets[slot]))
        for slot, (_index, name) in enumerate(chosen)
    )


def _parse_long(
    header: Sequence[str],
    rows: Iterator[Sequence[str]],
    sample_rows: int,
) -> tuple[TagSample, ...]:
    lowered = [name.lower() for name in header]
    tag_at = lowered.index("tag")
    value_at = lowered.index("value")
    order: list[str] = []
    buckets: dict[str, list[float]] = {}
    for row in rows:
        if tag_at >= len(row):
            continue
        tag = row[tag_at].strip()
        if not tag:
            continue
        if tag not in buckets:
            order.append(tag)
            buckets[tag] = []
        if len(buckets[tag]) >= sample_rows:
            continue
        if value_at < len(row):
            number = _number(row[value_at])
            if number is not None:
                buckets[tag].append(number)
    return tuple(TagSample(tag=tag, values=tuple(buckets[tag])) for tag in order)


def _is_long(header: Sequence[str]) -> bool:
    lowered = {name.lower() for name in header}
    return "tag" in lowered and "value" in lowered


def _access(raw: str) -> Literal["read", "write", "unknown"]:
    token = raw.strip().lower()
    if token in {"read", "r"}:
        return "read"
    if token in {"write", "w"}:
        return "write"
    return "unknown"


def _count(row: Sequence[str], count_at: int | None) -> int:
    if count_at is None or count_at >= len(row) or not row[count_at].strip():
        return 1
    try:
        count = int(row[count_at].strip())
    except ValueError as error:
        raise ValueError(f"capture count {row[count_at]!r} is not an integer") from error
    if count < 0:
        raise ValueError("capture count must be >= 0")
    return count


def _number(cell: str) -> float | None:
    text = cell.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value
