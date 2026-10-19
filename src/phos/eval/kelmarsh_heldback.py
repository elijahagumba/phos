"""One score of Kelmarsh SCADA 2023-2024 (ADR 0174).

Train is the 2018 development zip, loaded by the round-2 path. Score is the two
held-back SCADA zips. The detector is ``atlas-v1-consistency``, unchanged. The
status-log rule is the one ADR 0165 kept from ADR 0152: a span explains an alert
when ``Service contract category`` is not ``System OK (32)``.

``which_half`` is not edited. This module passes its own window,
``[2023-01-01, 2025-01-01)``, into `parse_turbine_lines`. A timestamp on
2025-01-01 is outside, the same year-end drop ADR 0165 used for 2023-01-01.

The PMU and grid-meter archives are not that input. The one command checksums
them and reads member names plus a header line. It does not call ``detect`` on
them. Nothing here appends ``eval_runs/log.jsonl``. The counts are not a
detection claim (ADR 0143).
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.atlas.consistency import RESULT_NAME as ATLAS_SCORER
from phos.eval.build_declaration import KELMARSH_HELD_BACK_FILES
from phos.eval.kelmarsh_log import (
    SIGNAL_COLUMNS,
    TURBINES,
    FileChecksum,
    Half,
    HeldBackFileError,
    KelmarshReport,
    ScadaZip,
    StatusSpan,
    _member_turbine,
    _store,
    combine_zips,
    load_scada_zip,
    parse_status_lines,
    parse_turbine_lines,
    score_halves,
)

__all__ = [
    "HELD_BACK_SCADA",
    "METER_FILES",
    "SCORE_END",
    "SCORE_RESULT",
    "SCORE_START",
    "TRAIN_FILE",
    "DeclarationError",
    "MeterLook",
    "file_digests",
    "held_back_half",
    "held_back_names_are_the_registry",
    "inspect_meter_zip",
    "load_held_back_scada",
    "registry_checksums",
    "require_authorization",
    "score_held_back",
]

TRAIN_FILE: Final = "Kelmarsh_SCADA_2018_3084.zip"
HELD_BACK_SCADA: Final[tuple[str, ...]] = (
    "Kelmarsh_SCADA_2023_5961.zip",
    "Kelmarsh_SCADA_2024_5962.zip",
)
METER_FILES: Final[tuple[str, ...]] = (
    "Kelmarsh_PMU_4459.zip",
    "Kelmarsh_PMU_2023_2024_5968.zip",
    "Kelmarsh_Grid_Meter_4458.zip",
)
SCORE_START: Final = datetime(2023, 1, 1, tzinfo=UTC)
SCORE_END: Final = datetime(2025, 1, 1, tzinfo=UTC)
SCORE_RESULT: Final = "round-3:kelmarsh-heldback"

_HEADER_BYTES: Final = 8192


class DeclarationError(RuntimeError):
    """Raised when the committed declaration does not match the files on disk."""


class MeterLook(BaseModel):
    """What the one command records about a meter archive. The detector is not called."""

    model_config = ConfigDict(frozen=True)

    filename: str
    members: tuple[str, ...]
    header_lines: tuple[str, ...]
    scored: bool
    reason: str


def held_back_half(when: datetime) -> Half:
    """Return ``score`` on ``[2023-01-01, 2025-01-01)`` and ``outside`` otherwise.

    Args:
        when: An aware UTC timestamp.

    Returns:
        The half used only by the held-back loader.

    Raises:
        ValueError: If ``when`` is naive.
    """
    if when.tzinfo is None:
        raise ValueError("Kelmarsh timestamps are UTC")
    if SCORE_START <= when < SCORE_END:
        return "score"
    return "outside"


def require_authorization(body: Mapping[str, object]) -> None:
    """Raise before any held-back zip is opened when the declaration is not the one score.

    Args:
        body: The parsed declaration.

    Raises:
        DeclarationError: If the result name, scorer, or authorization flag is wrong,
            or a file's sha256 is still empty.
    """
    if body.get("result_name") != SCORE_RESULT:
        raise DeclarationError("result name is not the declared Kelmarsh held-back score")
    if body.get("scorer") != ATLAS_SCORER:
        raise DeclarationError("scorer is not atlas-v1-consistency")
    if body.get("authorized") is not True:
        raise DeclarationError("declaration is not authorized; sha256 is not committed")
    files = body.get("files")
    if not isinstance(files, list) or not files:
        raise DeclarationError("declaration has no files")
    for item in files:
        if not isinstance(item, dict):
            raise DeclarationError("declaration file entry is not an object")
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise DeclarationError(f"{item.get('filename')} has no committed sha256")


def file_digests(path: Path) -> tuple[int, str, str]:
    """Return size, md5, and sha256 of ``path`` without parsing it.

    Args:
        path: A zip on disk.

    Returns:
        Byte size, md5 hex, sha256 hex.
    """
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)
            sha.update(chunk)
    return size, md5.hexdigest(), sha.hexdigest()


def assert_declared_file(path: Path, checksum: FileChecksum, sha256: str) -> None:
    """Refuse a file whose size, md5, or sha256 is not the committed declaration.

    Args:
        path: The file about to be used.
        checksum: Registry name, md5, and size.
        sha256: The sha256 committed before this score.

    Raises:
        DeclarationError: If the name, size, or either digest disagrees.
    """
    if path.name != checksum.filename:
        raise DeclarationError(f"{path.name} is not {checksum.filename}")
    if not sha256 or len(sha256) != 64:
        raise DeclarationError(f"{path.name} has no committed sha256")
    size, md5, digest = file_digests(path)
    if size != checksum.size_bytes:
        raise DeclarationError(f"{path.name} is {size} bytes, registry says {checksum.size_bytes}")
    if md5 != checksum.md5:
        raise DeclarationError(f"{path.name} md5 {md5} != registry {checksum.md5}")
    if digest != sha256:
        raise DeclarationError(f"{path.name} sha256 {digest} != declaration {sha256}")


def load_held_back_scada(path: Path) -> ScadaZip:
    """Read one held-back SCADA year zip into the score half.

    PMU and grid-meter members are refused before they are read. Turbine and
    status members may be named through 1 January 2025; rows on or after that
    instant are dropped by `held_back_half`.

    Args:
        path: ``Kelmarsh_SCADA_2023_5961.zip`` or ``Kelmarsh_SCADA_2024_5962.zip``.

    Returns:
        Score buckets and status spans. The train buckets are empty.

    Raises:
        ValueError: If the zip is not one of the two SCADA years.
        HeldBackFileError: If a member is a PMU or grid-meter file.
        SchemaError: If a turbine or status member does not match the declared columns.
    """
    if path.name not in HELD_BACK_SCADA:
        raise ValueError(f"{path.name} is not a held-back Kelmarsh SCADA zip")
    scores: dict[str, tuple[list[int], list[list[float]], int]] = {}
    spans: list[StatusSpan] = []
    raw_steps = 0
    raw_steps_600 = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            base = Path(name).name
            if "PMU" in base or "Grid_Meter" in base:
                raise HeldBackFileError(f"{base} is a meter member and is not read as SCADA")
        for name in archive.namelist():
            kind = _member_turbine(name)
            if kind is None:
                continue
            role, turbine = kind
            with archive.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                if role == "data":
                    rows, dropped, steps, steps_600 = parse_turbine_lines(
                        text, half_of=held_back_half
                    )
                    raw_steps += steps
                    raw_steps_600 += steps_600
                    score_rows = [
                        (stamp, values) for stamp, values, half in rows if half == "score"
                    ]
                    _store(scores, turbine, score_rows, dropped if score_rows else 0)
                else:
                    spans.extend(parse_status_lines(text, turbine))
    return ScadaZip({}, scores, tuple(spans), raw_steps, raw_steps_600)


def inspect_meter_zip(path: Path) -> MeterLook:
    """Record member names and header lines. Do not fit or score.

    Args:
        path: One of `METER_FILES`.

    Returns:
        An unscored look. ``scored`` is always false.

    Raises:
        ValueError: If ``path`` is not a declared meter archive.
    """
    if path.name not in METER_FILES:
        raise ValueError(f"{path.name} is not a Kelmarsh meter archive")
    members: list[str] = []
    headers: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            members.append(name)
            if name.endswith("/"):
                continue
            with archive.open(name) as raw:
                sample = raw.read(_HEADER_BYTES)
            text = sample.decode("utf-8", errors="replace")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    headers.append(stripped[:240])
                    break
    joined = " ".join(headers)
    has_signals = all(column in joined for column in SIGNAL_COLUMNS)
    reason = (
        "header names the five SCADA signals; still not scored, because this command's "
        "detector input is the two SCADA year zips only"
        if has_signals
        else "not the five-signal ten-minute SCADA the status-log rule names; detect was not called"
    )
    return MeterLook(
        filename=path.name,
        members=tuple(members),
        header_lines=tuple(headers),
        scored=False,
        reason=reason,
    )


def score_held_back(
    directory: Path,
    *,
    train_checksum: FileChecksum,
    score_checksums: tuple[FileChecksum, ...],
    sha256_by_name: dict[str, str],
) -> tuple[KelmarshReport, tuple[MeterLook, ...]]:
    """Fit on 2018 and score 2023-2024 once the declaration's digests match.

    Args:
        directory: ``data/kelmarsh``.
        train_checksum: The 2018 zip's registry checksum.
        score_checksums: The two SCADA zips, then the three meter archives.
        sha256_by_name: Committed sha256 for every file this command touches,
            including the 2018 train zip.

    Returns:
        The status-log report and one unscored look per meter archive.

    Raises:
        DeclarationError: If a digest disagrees.
        IncompleteFarmError: If a turbine is missing from train or score.
    """
    assert_declared_file(directory / TRAIN_FILE, train_checksum, sha256_by_name[TRAIN_FILE])
    for item in score_checksums:
        assert_declared_file(directory / item.filename, item, sha256_by_name[item.filename])
    train_zip = load_scada_zip(directory / TRAIN_FILE, allow_year_end_label=True)
    scored = [load_held_back_scada(directory / name) for name in HELD_BACK_SCADA]
    trains, _, _ = combine_zips([train_zip], turbines=TURBINES)
    _, tests, spans = combine_zips(scored, turbines=TURBINES)
    report = score_halves(trains, tests, spans, turbines=TURBINES)
    if report.detector != ATLAS_SCORER:
        raise DeclarationError(f"scorer moved: {report.detector}")
    meters = tuple(inspect_meter_zip(directory / name) for name in METER_FILES)
    return report, meters


def registry_checksums(
    registry: Mapping[str, object], names: tuple[str, ...]
) -> dict[str, FileChecksum]:
    """Return registry checksums for ``names`` from the kelmarsh and kelmarsh-heldback entries.

    Args:
        registry: Parsed ``data/registry.json``.
        names: Filenames that must appear on one of those two entries.

    Returns:
        ``filename -> FileChecksum``.

    Raises:
        DeclarationError: If a name is missing or its checksum fields are not strings and an int.
    """
    datasets = registry.get("datasets")
    if not isinstance(datasets, list):
        raise DeclarationError("registry has no datasets list")
    found: dict[str, FileChecksum] = {}
    for item in datasets:
        if not isinstance(item, dict) or item.get("name") not in {"kelmarsh", "kelmarsh-heldback"}:
            continue
        files = item.get("files")
        if not isinstance(files, list):
            continue
        for entry in files:
            if not isinstance(entry, dict):
                continue
            filename = entry.get("filename")
            md5 = entry.get("md5")
            size = entry.get("size_bytes")
            if filename not in names:
                continue
            if (
                not isinstance(filename, str)
                or not isinstance(md5, str)
                or not isinstance(size, int)
            ):
                raise DeclarationError(f"{filename} is missing md5 or size")
            found[filename] = FileChecksum(filename=filename, md5=md5, size_bytes=size)
    missing = [name for name in names if name not in found]
    if missing:
        raise DeclarationError(f"registry is missing {missing}")
    return found


def held_back_names_are_the_registry() -> bool:
    """Return whether the five names this command uses are exactly the held-back registry set."""
    return frozenset(HELD_BACK_SCADA + METER_FILES) == frozenset(KELMARSH_HELD_BACK_FILES)
