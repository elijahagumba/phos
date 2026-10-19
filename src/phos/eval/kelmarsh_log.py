"""Kelmarsh development SCADA scored against the turbine's own status log (ADR 0152).

Train is 2016-2018 and score is 2019-2022, on all six turbines. Samples are ten
minutes apart, so `windows_for_period(600)` is the frozen window rule and it
collapses. A budgeted `atlas-v1-consistency` alert is explained when that
turbine's status log covers the alert time with a service-contract category
other than ``System OK (32)``.

Held-back names are refused before a zip is opened. Nothing here appends
``eval_runs/log.jsonl``. The counts are not a detection claim (ADR 0143).
Hypothesis confidence is not computed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import zipfile
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from phos.atlas.consistency import (
    RESULT_NAME,
    SHIFT_SECONDS,
    ScoredFile,
    TrainFile,
    detect,
)
from phos.atlas.consistency_windows import Windows, windows_for_period
from phos.eval.build_declaration import (
    KELMARSH_DEVELOPMENT_FILES,
    KELMARSH_HELD_BACK_FILES,
    SCORECARD,
)

__all__ = [
    "KELMARSH_CAVEAT",
    "KELMARSH_CITATION",
    "OK_SERVICE",
    "SAMPLE_SECONDS",
    "SCORE_END",
    "SCORE_START",
    "SIGNAL_COLUMNS",
    "TRAIN_START",
    "TURBINES",
    "ChecksumError",
    "FileChecksum",
    "HeldBackFileError",
    "IncompleteFarmError",
    "KelmarshReport",
    "SchemaError",
    "StatusSpan",
    "TurbineLogScore",
    "TurbineSlice",
    "build_slice",
    "development_checksums",
    "kelmarsh_scorecard",
    "load_scada_zip",
    "merged_explaining",
    "parse_status_lines",
    "parse_turbine_lines",
    "render_kelmarsh_markdown",
    "score_halves",
    "service_explains",
    "time_is_explained",
    "verify_file",
    "which_half",
]

logger = logging.getLogger(__name__)

_Float64 = NDArray[numpy.float64]
_Int64 = NDArray[numpy.int64]

KELMARSH_CAVEAT: Final = (
    "Kelmarsh development SCADA is not attack-labelled. The share of alerts the turbine's own "
    "log explains, and the false alerts per shift, are not a detection claim and are not "
    "evidence the plant map detects attacks (ADR 0143). Hypothesis confidence is not reported."
)
KELMARSH_CITATION: Final = (
    "Plumley, Charlie. Cubico Sustainable Investments wind farm data "
    "(10.5281/zenodo.16807551). CC BY 4.0."
)

SAMPLE_SECONDS: Final = 600.0
"""Greenbyte's ten-minute SCADA interval, in seconds."""

OK_SERVICE: Final = "System OK (32)"
"""The status file's own name for a running turbine. That stamp does not explain an alert."""

SIGNAL_COLUMNS: Final[tuple[str, ...]] = (
    "Wind speed (m/s)",
    "Power (kW)",
    "Rotor speed (RPM)",
    "Generator RPM (RPM)",
    "Blade angle (pitch position) A (\u00b0)",
)
"""Primary channels from the turbine CSV header.

Min, max, and standard-deviation columns stay out.
"""

TRAIN_START: Final = datetime(2016, 1, 1, tzinfo=UTC)
SCORE_START: Final = datetime(2019, 1, 1, tzinfo=UTC)
SCORE_END: Final = datetime(2023, 1, 1, tzinfo=UTC)
TURBINES: Final[tuple[str, ...]] = tuple(f"Kelmarsh {index}" for index in range(1, 7))

_DATA_NAME: Final = re.compile(r"^Turbine_Data_Kelmarsh_([1-6])_")
_STATUS_NAME: Final = re.compile(r"^Status_Kelmarsh_([1-6])_")
_MISSING: Final = frozenset({"", "NaN", "nan", "NA", "null"})
_STATUS_HEADER: Final = (
    "Timestamp start",
    "Timestamp end",
    "Status",
    "Service contract category",
    "IEC category",
)
Half = Literal["train", "score", "outside"]


class HeldBackFileError(ValueError):
    """Raised before a held-back Kelmarsh name is opened."""


class ChecksumError(ValueError):
    """Raised when a development file's size or md5 disagrees with the registry."""


class SchemaError(ValueError):
    """Raised when a development CSV does not have the declared columns."""


class IncompleteFarmError(ValueError):
    """Raised when a declared turbine is missing from train or score."""


class FileChecksum(BaseModel):
    """One development file's name, md5, and size, copied from the registry."""

    model_config = ConfigDict(frozen=True)

    filename: str
    md5: str
    size_bytes: int


@dataclass(frozen=True)
class TurbineSlice:
    """Kept rows for one turbine and one half. Time is unix seconds, ascending, deduped."""

    turbine: str
    time: _Int64
    values: _Float64
    dropped_missing: int
    clock_gaps: int
    duplicate_times: int


@dataclass(frozen=True)
class StatusSpan:
    """One status-log interval. Only ``service_category`` decides whether it explains."""

    turbine: str
    start: int
    end: int
    service_category: str


@dataclass(frozen=True)
class ScadaZip:
    """Signals and status intervals read from one development year zip."""

    trains: dict[str, tuple[list[int], list[list[float]], int]]
    scores: dict[str, tuple[list[int], list[list[float]], int]]
    spans: tuple[StatusSpan, ...]
    raw_steps: int
    raw_steps_600: int


class TurbineLogScore(BaseModel):
    """One turbine's budgeted alerts and how many the status log explains."""

    model_config = ConfigDict(frozen=True)

    turbine: str
    train_rows: int
    score_rows: int
    dropped_missing: int
    clock_gaps: int
    duplicate_times: int
    alerts: int
    explained_alerts: int
    unexplained_alerts: int
    scored_seconds: float
    shifts: float
    false_alerts_per_shift: float | None


class KelmarshReport(BaseModel):
    """The development-farm log measurement. Counts are the claim."""

    model_config = ConfigDict(frozen=True)

    measured: bool
    detector: str
    sample_seconds: float
    windows_lags: tuple[int, ...]
    detrend_window_samples: int
    signals: tuple[str, ...]
    ok_service: str
    turbines: tuple[TurbineLogScore, ...]
    alerts: int
    explained_alerts: int
    unexplained_alerts: int
    explained_share: float | None
    scored_seconds: float
    shifts: float
    false_alerts_per_shift: float | None
    caveat: str
    citation: str


def service_explains(service_category: str) -> bool:
    """Return whether a status row's service category explains an alert.

    ``System OK (32)`` is the file's running code and does not explain. Every other
    category, including an empty one, is the log naming something other than system OK.

    Args:
        service_category: The ``Service contract category`` cell, untranslated.

    Returns:
        False only for `OK_SERVICE`.
    """
    return service_category != OK_SERVICE


def which_half(when: datetime) -> Half:
    """Return train, score, or outside for one UTC timestamp.

    Train is ``[2016-01-01, 2019-01-01)``. Score is ``[2019-01-01, 2023-01-01)``.
    A timestamp on or after 2023-01-01 is outside, which keeps a held-back year out
    even if a development file mentioned it.

    Args:
        when: An aware UTC timestamp from a development CSV.

    Returns:
        The half that timestamp belongs to.
    """
    if when.tzinfo is None:
        raise ValueError("Kelmarsh timestamps are UTC")
    if TRAIN_START <= when < SCORE_START:
        return "train"
    if SCORE_START <= when < SCORE_END:
        return "score"
    return "outside"


def merged_explaining(spans: Sequence[StatusSpan], turbine: str) -> tuple[tuple[int, int], ...]:
    """Merge explaining intervals for one turbine into disjoint inclusive spans.

    Args:
        spans: Status intervals from the development zips.
        turbine: ``Kelmarsh 1`` through ``Kelmarsh 6``.

    Returns:
        ``(start, end)`` unix seconds, sorted, non-overlapping.
    """
    pieces = sorted(
        (span.start, span.end)
        for span in spans
        if span.turbine == turbine
        and span.end >= span.start
        and service_explains(span.service_category)
    )
    if not pieces:
        return ()
    merged: list[list[int]] = [[pieces[0][0], pieces[0][1]]]
    for start, end in pieces[1:]:
        if start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return tuple((item[0], item[1]) for item in merged)


def time_is_explained(when: int, merged: Sequence[tuple[int, int]]) -> bool:
    """Return whether ``when`` sits inside a merged explaining span.

    Args:
        when: Unix seconds of an alert.
        merged: The result of `merged_explaining`.

    Returns:
        True when some explaining interval covers ``when``, endpoints included.
    """
    starts = [item[0] for item in merged]
    index = bisect_right(starts, when) - 1
    if index < 0:
        return False
    start, end = merged[index]
    return start <= when <= end


def _parse_timestamp(text: str) -> datetime | None:
    try:
        parsed = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def _header_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    body = stripped[1:].strip() if stripped.startswith("#") else stripped
    if not body.startswith("Date and time"):
        return None
    return next(csv.reader([body]))


def parse_turbine_lines(
    lines: Iterable[str],
    *,
    half_of: Callable[[datetime], Half] | None = None,
) -> tuple[list[tuple[int, tuple[float, float, float, float, float], Half]], int, int, int]:
    """Parse one turbine CSV into kept rows.

    A row with any of the five signals missing is dropped, not filled with zero.
    Rows the half function calls outside are counted and dropped. The default
    half is `which_half` (ADR 0152). A caller that scores a later window passes
    its own function; `which_half` itself is unchanged (ADR 0165).

    Args:
        lines: The CSV, including Greenbyte's ``#`` preamble.
        half_of: How a timestamp becomes train, score, or outside. Defaults to
            `which_half`.

    Returns:
        Kept ``(unix, five values, half)`` rows, the missing-signal drop count,
        raw successive steps, and how many of those steps are exactly 600 seconds.

    Raises:
        SchemaError: If the declared signal columns are absent, or the file is not
            ten-minute SCADA.
    """
    classify = which_half if half_of is None else half_of
    header: list[str] | None = None
    indexes: tuple[int, int, int, int, int] | None = None
    kept: list[tuple[int, tuple[float, float, float, float, float], Half]] = []
    dropped_missing = 0
    raw_steps = 0
    raw_steps_600 = 0
    previous: int | None = None
    for line in lines:
        if header is None:
            header = _header_cells(line)
            if header is not None:
                indexes = _signal_indexes(header)
            continue
        if indexes is None:
            raise SchemaError("turbine header did not resolve")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = next(csv.reader([stripped]))
        stamped = _parse_timestamp(cells[0]) if cells else None
        if stamped is None:
            continue
        stamp = int(stamped.timestamp())
        if previous is not None:
            raw_steps += 1
            if stamp - previous == int(SAMPLE_SECONDS):
                raw_steps_600 += 1
        previous = stamp
        parsed = _five_values(cells, indexes)
        if parsed is None:
            dropped_missing += 1
            continue
        half = classify(stamped)
        if half == "outside":
            continue
        kept.append((stamp, parsed, half))
    if header is None or indexes is None:
        raise SchemaError("turbine CSV has no Date and time header")
    if raw_steps >= 10 and raw_steps_600 / raw_steps < 0.5:
        raise SchemaError(
            f"turbine CSV is not ten-minute SCADA ({raw_steps_600} of {raw_steps} steps)"
        )
    return kept, dropped_missing, raw_steps, raw_steps_600


def _signal_indexes(header: Sequence[str]) -> tuple[int, int, int, int, int]:
    found: dict[str, int] = {}
    for index, name in enumerate(header):
        if name in SIGNAL_COLUMNS and name not in found:
            found[name] = index
    missing = [name for name in SIGNAL_COLUMNS if name not in found]
    if missing:
        raise SchemaError(f"turbine CSV is missing {missing}")
    first, second, third, fourth, fifth = SIGNAL_COLUMNS
    return (found[first], found[second], found[third], found[fourth], found[fifth])


def _five_values(
    cells: Sequence[str], indexes: tuple[int, int, int, int, int]
) -> tuple[float, float, float, float, float] | None:
    parsed: list[float] = []
    for index in indexes:
        if index >= len(cells) or cells[index].strip() in _MISSING:
            return None
        try:
            parsed.append(float(cells[index]))
        except ValueError:
            return None
    one, two, three, four, five = parsed
    return (one, two, three, four, five)


def parse_status_lines(lines: Iterable[str], turbine: str) -> tuple[StatusSpan, ...]:
    """Parse one status CSV into intervals for ``turbine``.

    Args:
        lines: The status CSV, including the Greenbyte preamble.
        turbine: The turbine named by the member, ``Kelmarsh N``.

    Returns:
        Intervals with a parseable start and end. A row whose end is before its start
        is dropped.

    Raises:
        SchemaError: If the declared status columns are absent.
    """
    header: list[str] | None = None
    spans: list[StatusSpan] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or (header is None and stripped.startswith("#")):
            continue
        if header is None:
            if not stripped.startswith("Timestamp start"):
                continue
            header = next(csv.reader([stripped]))
            missing = [name for name in _STATUS_HEADER if name not in header]
            if missing:
                raise SchemaError(f"status CSV is missing {missing}")
            continue
        cells = next(csv.reader([stripped]))
        row = {
            name: cells[index] if index < len(cells) else "" for index, name in enumerate(header)
        }
        start = _parse_timestamp(row.get("Timestamp start", ""))
        end = _parse_timestamp(row.get("Timestamp end", ""))
        if start is None or end is None:
            continue
        start_unix = int(start.timestamp())
        end_unix = int(end.timestamp())
        if end_unix < start_unix:
            continue
        spans.append(
            StatusSpan(
                turbine=turbine,
                start=start_unix,
                end=end_unix,
                service_category=row.get("Service contract category", "").strip(),
            )
        )
    if header is None:
        raise SchemaError("status CSV has no Timestamp start header")
    return tuple(spans)


def build_slice(
    turbine: str,
    stamps: Sequence[int],
    columns: Sequence[Sequence[float]],
    dropped_missing: int,
) -> TurbineSlice:
    """Sort, drop duplicate timestamps, and count clock gaps that are not 600 seconds.

    After a drop, lag 1 in the collapsed window is the previous kept row, which may
    be later than ten minutes. ``clock_gaps`` counts those jumps.

    Args:
        turbine: ``Kelmarsh N``.
        stamps: Unix seconds, one per kept row, not necessarily sorted.
        columns: Five signal columns, aligned with ``stamps``.
        dropped_missing: Rows already removed because a signal was missing.

    Returns:
        One slice. Empty input yields an empty slice.
    """
    if len(columns) != len(SIGNAL_COLUMNS):
        raise SchemaError(f"{turbine} has {len(columns)} signal columns")
    if not stamps:
        empty = numpy.empty((0, len(SIGNAL_COLUMNS)), dtype=numpy.float64)
        return TurbineSlice(
            turbine, numpy.empty(0, dtype=numpy.int64), empty, dropped_missing, 0, 0
        )
    time = numpy.asarray(stamps, dtype=numpy.int64)
    values = numpy.column_stack([numpy.asarray(column, dtype=numpy.float64) for column in columns])
    order = numpy.argsort(time, kind="mergesort")
    time = time[order]
    values = values[order]
    unique = numpy.ones(time.shape[0], dtype=numpy.bool_)
    if time.shape[0] > 1:
        unique[1:] = time[1:] != time[:-1]
    duplicates = int(time.shape[0] - int(unique.sum()))
    time = time[unique]
    values = values[unique]
    gaps = 0
    if time.shape[0] > 1:
        gaps = int(numpy.count_nonzero(numpy.diff(time) != int(SAMPLE_SECONDS)))
    return TurbineSlice(turbine, time, values, dropped_missing, gaps, duplicates)


def refuse_held_back_name(filename: str) -> None:
    """Raise if ``filename`` is a held-back Kelmarsh file.

    Args:
        filename: A path's final component, not a directory.

    Raises:
        HeldBackFileError: If the name is in `KELMARSH_HELD_BACK_FILES` or is a PMU,
            grid-meter, 2023, or 2024 name.
    """
    if (
        filename in KELMARSH_HELD_BACK_FILES
        or "PMU" in filename
        or "Grid_Meter" in filename
        or "2023" in filename
        or "2024" in filename
    ):
        raise HeldBackFileError(f"{filename} is held back and is not opened")


def assert_development_zip(filename: str) -> None:
    """Raise unless ``filename`` is a declared Kelmarsh development SCADA zip.

    Args:
        filename: The zip's final component.

    Raises:
        HeldBackFileError: If the name is held back.
        ValueError: If the name is not one of the development year zips.
    """
    refuse_held_back_name(filename)
    if filename not in KELMARSH_DEVELOPMENT_FILES or not filename.endswith(".zip"):
        raise ValueError(f"{filename} is not a Kelmarsh development SCADA zip")


def verify_file(path: Path, checksum: FileChecksum) -> None:
    """Check size and md5 before a development file is used.

    The name is refused first, so a held-back path is not read.

    Args:
        path: The file on disk.
        checksum: The registry's name, md5, and size.

    Raises:
        HeldBackFileError: If the name is held back.
        ChecksumError: If the size or md5 disagrees.
        ValueError: If the names disagree.
    """
    refuse_held_back_name(path.name)
    if path.name != checksum.filename:
        raise ValueError(f"{path.name} is not {checksum.filename}")
    size = path.stat().st_size
    if size != checksum.size_bytes:
        raise ChecksumError(f"{path.name} is {size} bytes, registry says {checksum.size_bytes}")
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    if digest != checksum.md5:
        raise ChecksumError(f"{path.name} md5 {digest} != registry {checksum.md5}")


def development_checksums(registry: Mapping[str, object]) -> tuple[FileChecksum, ...]:
    """Return the kelmarsh development files' checksums. Held-back entries are not returned.

    Args:
        registry: The parsed ``data/registry.json`` object.

    Returns:
        One checksum per `KELMARSH_DEVELOPMENT_FILES` entry, registry order.

    Raises:
        ValueError: If the kelmarsh entry is missing or its file list is not the declaration.
        HeldBackFileError: If that entry names a held-back file.
    """
    datasets = registry.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("registry has no datasets list")
    entry: Mapping[str, object] | None = None
    for item in datasets:
        if isinstance(item, dict) and item.get("name") == "kelmarsh":
            entry = item
            break
    if entry is None:
        raise ValueError("registry has no kelmarsh dataset")
    files = entry.get("files")
    if not isinstance(files, list):
        raise ValueError("kelmarsh entry has no files")
    found: list[FileChecksum] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("kelmarsh file entry is not an object")
        filename = item.get("filename")
        md5 = item.get("md5")
        size = item.get("size_bytes")
        if not isinstance(filename, str) or not isinstance(md5, str) or not isinstance(size, int):
            raise ValueError("kelmarsh file entry is missing filename, md5, or size")
        refuse_held_back_name(filename)
        if filename not in KELMARSH_DEVELOPMENT_FILES:
            raise ValueError(f"{filename} is on the kelmarsh entry and is not a development file")
        found.append(FileChecksum(filename=filename, md5=md5, size_bytes=size))
    names = {item.filename for item in found}
    if names != set(KELMARSH_DEVELOPMENT_FILES):
        raise ValueError("kelmarsh registry files do not match KELMARSH_DEVELOPMENT_FILES")
    return tuple(found)


def _member_turbine(name: str) -> tuple[str, str] | None:
    base = Path(name).name
    data = _DATA_NAME.match(base)
    if data is not None:
        return "data", f"Kelmarsh {data.group(1)}"
    status = _STATUS_NAME.match(base)
    if status is not None:
        return "status", f"Kelmarsh {status.group(1)}"
    return None


def _empty_bucket() -> tuple[list[int], list[list[float]], int]:
    return ([], [[] for _ in SIGNAL_COLUMNS], 0)


def _store(
    buckets: dict[str, tuple[list[int], list[list[float]], int]],
    turbine: str,
    rows: Sequence[tuple[int, tuple[float, float, float, float, float]]],
    extra_dropped: int,
) -> None:
    """Append rows to one turbine's bucket. ``extra_dropped`` is added once."""
    stamps, columns, dropped = buckets.get(turbine, _empty_bucket())
    for stamp, values in rows:
        stamps.append(stamp)
        for index, value in enumerate(values):
            columns[index].append(value)
    if rows or extra_dropped:
        buckets[turbine] = (stamps, columns, dropped + extra_dropped)


def _refuse_member(filename: str, *, allow_year_end_label: bool) -> None:
    """Apply the held-back member rule, with ADR 0165's year-end exception."""
    if allow_year_end_label and _member_turbine(filename) is not None:
        if "PMU" in filename or "Grid_Meter" in filename or filename in KELMARSH_HELD_BACK_FILES:
            raise HeldBackFileError(f"{filename} is held back and is not opened")
        return
    refuse_held_back_name(filename)


def load_scada_zip(path: Path, *, allow_year_end_label: bool = False) -> ScadaZip:
    """Read one development year zip. Held-back names are refused before a member is read.

    Args:
        path: A zip whose name is in `KELMARSH_DEVELOPMENT_FILES`.
        allow_year_end_label: When true, a turbine or status member may be named
            through 1 January of the next year. Rows on or after 2023-01-01 are
            still dropped by `which_half`. PMU and grid-meter members stay closed.
            ADR 0165. The default keeps ADR 0152's stricter member rule.

    Returns:
        Per-turbine train and score buckets, plus status spans. The caller still
        checks the registry md5 before trusting the bytes.

    Raises:
        HeldBackFileError: If the zip name, or any member name, is held back.
        SchemaError: If a turbine or status member does not match the declared columns.
        ValueError: If the zip name is not a development year file.
    """
    assert_development_zip(path.name)
    trains: dict[str, tuple[list[int], list[list[float]], int]] = {}
    scores: dict[str, tuple[list[int], list[list[float]], int]] = {}
    spans: list[StatusSpan] = []
    raw_steps = 0
    raw_steps_600 = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            _refuse_member(Path(name).name, allow_year_end_label=allow_year_end_label)
        for name in archive.namelist():
            kind = _member_turbine(name)
            if kind is None:
                logger.info("skipping %s member %s", path.name, name)
                continue
            role, turbine = kind
            with archive.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                if role == "data":
                    rows, dropped, steps, steps_600 = parse_turbine_lines(text)
                    raw_steps += steps
                    raw_steps_600 += steps_600
                    train_rows = [
                        (stamp, values) for stamp, values, half in rows if half == "train"
                    ]
                    score_rows = [
                        (stamp, values) for stamp, values, half in rows if half == "score"
                    ]
                    # Count each dropped row once. Prefer the train half when both exist.
                    train_dropped = dropped if train_rows or not score_rows else 0
                    score_dropped = dropped if score_rows and not train_rows else 0
                    _store(trains, turbine, train_rows, train_dropped)
                    _store(scores, turbine, score_rows, score_dropped)
                else:
                    spans.extend(parse_status_lines(text, turbine))
    logger.info(
        "read %s train turbines=%s score turbines=%s spans=%s",
        path.name,
        sorted(trains),
        sorted(scores),
        len(spans),
    )
    return ScadaZip(trains, scores, tuple(spans), raw_steps, raw_steps_600)


def _combine(
    parts: Sequence[tuple[list[int], list[list[float]], int]], turbine: str
) -> TurbineSlice:
    stamps: list[int] = []
    columns: list[list[float]] = [[] for _ in SIGNAL_COLUMNS]
    dropped = 0
    for part_stamps, part_columns, part_dropped in parts:
        stamps.extend(part_stamps)
        for index, column in enumerate(part_columns):
            columns[index].extend(column)
        dropped += part_dropped
    return build_slice(turbine, stamps, columns, dropped)


def score_halves(
    trains: Mapping[str, TurbineSlice],
    tests: Mapping[str, TurbineSlice],
    spans: Sequence[StatusSpan],
    *,
    turbines: Sequence[str] = TURBINES,
) -> KelmarshReport:
    """Fit `atlas-v1-consistency` per turbine and count alerts the status log explains.

    Args:
        trains: One training slice per turbine. Attack flags are all false. Kelmarsh
            has no attack labels.
        tests: One score slice per turbine, 2019-2022.
        spans: Status intervals from the development files.
        turbines: The turbines that must all be present. The farm default is all six.

    Returns:
        Explained share and false alerts per shift. Share is ``None`` when there are
        no alerts. No hypothesis confidence is stored.

    Raises:
        IncompleteFarmError: If a required turbine is missing or has no training rows.
    """
    windows = windows_for_period(SAMPLE_SECONDS)
    missing = [
        name
        for name in turbines
        if name not in trains
        or name not in tests
        or trains[name].values.shape[0] <= max(windows.lags)
    ]
    if missing:
        raise IncompleteFarmError(f"missing train or score for {missing}")
    rows: list[TurbineLogScore] = []
    for name in turbines:
        rows.append(_score_turbine(name, trains[name], tests[name], spans, windows))
    alerts = sum(item.alerts for item in rows)
    explained = sum(item.explained_alerts for item in rows)
    unexplained = sum(item.unexplained_alerts for item in rows)
    scored_seconds = sum(item.scored_seconds for item in rows)
    shifts = scored_seconds / SHIFT_SECONDS
    share = (explained / alerts) if alerts else None
    per_shift = (unexplained / shifts) if shifts else None
    return KelmarshReport(
        measured=True,
        detector=RESULT_NAME,
        sample_seconds=SAMPLE_SECONDS,
        windows_lags=windows.lags,
        detrend_window_samples=windows.detrend_window,
        signals=SIGNAL_COLUMNS,
        ok_service=OK_SERVICE,
        turbines=tuple(rows),
        alerts=alerts,
        explained_alerts=explained,
        unexplained_alerts=unexplained,
        explained_share=share,
        scored_seconds=scored_seconds,
        shifts=shifts,
        false_alerts_per_shift=per_shift,
        caveat=KELMARSH_CAVEAT,
        citation=KELMARSH_CITATION,
    )


def _score_turbine(
    name: str,
    train: TurbineSlice,
    test: TurbineSlice,
    spans: Sequence[StatusSpan],
    windows: Windows,
) -> TurbineLogScore:
    attack = numpy.zeros(train.values.shape[0], dtype=numpy.bool_)
    found = detect(
        [TrainFile(values=train.values, attack=attack)],
        [ScoredFile(time=test.time.astype(numpy.float64), values=test.values)],
        windows,
    )[0]
    alert_rows, _columns, _rank = found
    merged = merged_explaining(spans, name)
    explained = sum(1 for row in alert_rows if time_is_explained(int(test.time[row]), merged))
    alerts = len(alert_rows)
    unexplained = alerts - explained
    scored_seconds = float(test.time[-1] - test.time[0]) if test.time.shape[0] > 1 else 0.0
    shifts = scored_seconds / SHIFT_SECONDS
    per_shift = (unexplained / shifts) if shifts else None
    return TurbineLogScore(
        turbine=name,
        train_rows=int(train.values.shape[0]),
        score_rows=int(test.values.shape[0]),
        dropped_missing=train.dropped_missing + test.dropped_missing,
        clock_gaps=train.clock_gaps + test.clock_gaps,
        duplicate_times=train.duplicate_times + test.duplicate_times,
        alerts=alerts,
        explained_alerts=explained,
        unexplained_alerts=unexplained,
        scored_seconds=scored_seconds,
        shifts=shifts,
        false_alerts_per_shift=per_shift,
    )


def kelmarsh_scorecard(report: KelmarshReport, runtime_seconds: float) -> dict[str, object]:
    """Fill `SCORECARD` for the Kelmarsh log measurement.

    Attack catches, closure margins, and calibration are unmeasured here. Kelmarsh
    has no attack labels and no work-order export. The false-alert cell is the
    unexplained budgeted alerts per shift.

    Args:
        report: The log measurement.
        runtime_seconds: Wall time of that measurement.

    Returns:
        A dict whose keys are exactly `SCORECARD`.
    """
    not_this = {"measured": False, "reason": "not this lane"}
    no_labels = {
        "measured": False,
        "reason": "Kelmarsh development SCADA has no attack labels. This is not a detection claim.",
    }
    card: dict[str, object] = {
        "catches_within_budget": no_labels,
        "margin_over_best_simple_rival": {
            "measured": False,
            "reason": (
                "The closure rival is the synthetic harness. Kelmarsh has no work-order export."
            ),
        },
        "margin_over_chance": {
            "measured": False,
            "reason": "No chance permutation is declared for the Kelmarsh log.",
        },
        "falsified_sensor_passes": not_this,
        "naming_right": not_this,
        "naming_wrong": not_this,
        "reconstruction_error": not_this,
        "maintenance_closures": {
            "measured": False,
            "reason": (
                "Kelmarsh has no work-order export. Synthetic closure is "
                "eval_runs/build/lane-b/maintenance-closure.json."
            ),
        },
        "calibration": {
            "measured": False,
            "reason": "W5 is another lane. Hypothesis confidence is not computed or shown.",
        },
        "false_alerts_per_shift": {
            "measured": True,
            "detector": report.detector,
            "value": report.false_alerts_per_shift,
            "unexplained_alerts": report.unexplained_alerts,
            "alerts": report.alerts,
            "explained_alerts": report.explained_alerts,
            "explained_share": report.explained_share,
            "shifts": report.shifts,
            "definition": (
                "Budgeted atlas-v1-consistency alerts on 2019-2022 whose time the turbine's "
                "status log does not explain, divided by scored seconds over an 8-hour shift. "
                "Explained share is explained alerts over all budgeted alerts."
            ),
        },
        "runtime": {
            "measured": True,
            "value": runtime_seconds,
            "unit": "seconds",
            "definition": "Wall time to score the Kelmarsh development halves in this report.",
        },
    }
    if tuple(card) != SCORECARD:
        raise RuntimeError(f"scorecard keys {tuple(card)} are not {SCORECARD}")
    return card


def render_kelmarsh_markdown(report: KelmarshReport) -> str:
    """Plain-English summary. No confidence is printed.

    Args:
        report: The log measurement.

    Returns:
        Markdown for the lane folder.
    """
    share = (
        "undefined, because there were no alerts"
        if report.explained_share is None
        else (f"{report.explained_alerts} of {report.alerts} ({report.explained_share:.4f})")
    )
    per_shift = (
        "undefined, because the scored clock has no duration"
        if report.false_alerts_per_shift is None
        else f"{report.false_alerts_per_shift:.4f}"
    )
    lines = [
        "# Kelmarsh development log",
        "",
        KELMARSH_CAVEAT,
        "",
        KELMARSH_CITATION,
        "",
        (
            f"Detector `{report.detector}` at a {report.sample_seconds:.0f}-second sample. "
            f"windows_for_period collapsed the lags to {report.windows_lags} and the detrend "
            f"window to {report.detrend_window_samples} samples. Those windows were not retuned."
        ),
        (
            "Train is 2016-2018. Score is 2019-2022. All six turbines are in each year file, "
            "so there is no turbine holdout."
        ),
        (
            f"A status row explains an alert when it covers that time and its service category "
            f"is not `{report.ok_service}`."
        ),
        "",
        f"Alerts the turbine's own log explains: {share}.",
        (
            f"Unexplained alerts: {report.unexplained_alerts} over {report.shifts:.4f} shifts, "
            f"{per_shift} per shift."
        ),
        "",
    ]
    for item in report.turbines:
        if item.false_alerts_per_shift is None:
            rate = "n/a"
        else:
            rate = f"{item.false_alerts_per_shift:.4f}"
        lines.append(
            f"{item.turbine}: {item.explained_alerts} of {item.alerts} explained, "
            f"{item.unexplained_alerts} unexplained, {rate} per shift, "
            f"{item.clock_gaps} clock gaps, "
            f"{item.dropped_missing} rows dropped for a missing signal."
        )
    lines.append("")
    return "\n".join(lines)


def combine_zips(
    loaded: Sequence[ScadaZip], turbines: Sequence[str] = TURBINES
) -> tuple[dict[str, TurbineSlice], dict[str, TurbineSlice], tuple[StatusSpan, ...]]:
    """Turn year zips into one train slice and one score slice per turbine.

    Args:
        loaded: Development year zips, already md5-checked.
        turbines: Turbines to build. Missing ones are simply absent; `score_halves` refuses them.

    Returns:
        Train slices, score slices, and every status span.
    """
    trains: dict[str, TurbineSlice] = {}
    tests: dict[str, TurbineSlice] = {}
    spans: list[StatusSpan] = []
    for name in turbines:
        train_parts = [item.trains[name] for item in loaded if name in item.trains]
        score_parts = [item.scores[name] for item in loaded if name in item.scores]
        if train_parts:
            trains[name] = _combine(train_parts, name)
        if score_parts:
            tests[name] = _combine(score_parts, name)
    for item in loaded:
        spans.extend(item.spans)
    return trains, tests, tuple(spans)
