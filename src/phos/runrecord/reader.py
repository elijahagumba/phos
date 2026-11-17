"""Reading .phosrun files: lazy, member-by-member access.

A RunRecord opens a ZIP container and reads members on demand. The header is
parsed once and cached; every other member is read only when requested.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy

from . import format as fmt


def _json_bytes_to_obj(data: bytes) -> dict[str, Any]:
    """Deserialize JSON bytes to a dict."""
    return cast(dict[str, Any], json.loads(data.decode("utf-8")))


def _jsonl_bytes_to_objs(data: bytes) -> list[dict[str, Any]]:
    """Deserialize JSON Lines bytes to a list of dicts."""
    text = data.decode("utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _npy_bytes_to_array(data: bytes) -> numpy.ndarray:
    """Deserialize .npy format bytes to a numpy array."""
    return cast(numpy.ndarray, numpy.load(io.BytesIO(data), allow_pickle=False))


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes | None:
    """Read a member by name, returning None if absent."""
    try:
        return zf.read(name)
    except KeyError:
        return None


def read_header(path: str | Path) -> dict[str, Any]:
    """Read only the header.json member, for fast library scanning.

    Args:
        path: Path to the .phosrun file.

    Returns:
        The parsed header dict.
    """
    with zipfile.ZipFile(path, "r") as zf:
        data = zf.read(fmt.MEMBER_HEADER)
    return _json_bytes_to_obj(data)


class RunRecord:
    """Lazy reader for a .phosrun file.

    Opens the ZIP once and reads members on demand. The header is parsed
    once and cached; every other member is read only when first requested
    and cached thereafter.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize a RunRecord for the given .phosrun file path."""
        self._path = Path(path)
        self._zf: zipfile.ZipFile | None = None
        self._header: dict[str, Any] | None = None
        self._plant: dict[str, Any] | None = None
        self._structure: dict[str, Any] | None = None
        self._timeline: list[dict[str, Any]] | None = None
        self._labels: list[dict[str, Any]] | None = None
        self._telemetry_index: dict[str, Any] | None = None
        self._atlas: dict[str, Any] | None = None
        self._scores: dict[str, Any] | None = None
        self._traffic: dict[str, Any] | None = None

    def __enter__(self) -> RunRecord:
        """Open the ZIP file for reading."""
        self._zf = zipfile.ZipFile(self._path, "r")
        return self

    def __exit__(self, *args: object) -> None:
        """Close the ZIP file."""
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    @property
    def _zip(self) -> zipfile.ZipFile:
        if self._zf is None:
            self._zf = zipfile.ZipFile(self._path, "r")
        return self._zf

    @property
    def header(self) -> dict[str, Any]:
        """The parsed header dict (cached after first read)."""
        if self._header is None:
            self._header = _json_bytes_to_obj(self._zip.read(fmt.MEMBER_HEADER))
        return self._header

    @property
    def path(self) -> Path:
        """The path to the .phosrun file."""
        return self._path

    @property
    def kind(self) -> str:
        """The run kind: ``"simulated"`` or ``"real_data"``."""
        return cast(str, self.header["kind"])

    @property
    def run_id(self) -> str:
        """The SHA-256 run identifier."""
        return cast(str, self.header["run_id"])

    @property
    def title(self) -> str:
        """The human-readable run title."""
        return cast(str, self.header["title"])

    @property
    def pool(self) -> str:
        """The data pool.

        One of ``"dev"``, ``"public"``, ``"private"``,
        ``"retired"``, or ``"real_data"``.
        """
        return cast(str, self.header["pool"])

    def plant(self) -> dict[str, Any]:
        """The plant descriptor dict."""
        if self._plant is None:
            self._plant = _json_bytes_to_obj(self._zip.read(fmt.MEMBER_PLANT))
        return self._plant

    def structure(self) -> dict[str, Any]:
        """The plant structure dict (nodes, edges, subsystems, layout hints)."""
        if self._structure is None:
            self._structure = _json_bytes_to_obj(self._zip.read(fmt.MEMBER_STRUCTURE))
        return self._structure

    def timeline(self) -> list[dict[str, Any]]:
        """The timeline event list."""
        if self._timeline is None:
            self._timeline = cast(
                list[dict[str, Any]],
                _json_bytes_to_obj(self._zip.read(fmt.MEMBER_TIMELINE)),
            )
        return self._timeline

    def labels(self) -> list[dict[str, Any]]:
        """The collapsed label-run list."""
        if self._labels is None:
            self._labels = cast(
                list[dict[str, Any]],
                _json_bytes_to_obj(self._zip.read(fmt.MEMBER_LABELS)),
            )
        return self._labels

    def telemetry_index(self) -> dict[str, Any]:
        """The telemetry index dict (columns, sample period, chunk map)."""
        if self._telemetry_index is None:
            self._telemetry_index = _json_bytes_to_obj(self._zip.read(fmt.MEMBER_TELEMETRY_INDEX))
        return self._telemetry_index

    def telemetry_chunk(self, chunk_index: int) -> numpy.ndarray:
        """Read one telemetry chunk as a numpy array."""
        chunk_name = fmt.TELEMETRY_CHUNK_NAME_TEMPLATE.format(index=chunk_index)
        data = self._zip.read(chunk_name)
        return _npy_bytes_to_array(data)

    def telemetry_range(
        self, tag: str, start_time: str, end_time: str
    ) -> dict[str, list[float | str]]:
        """Query telemetry for one tag within a time range.

        Uses the telemetry index to select only the chunks that overlap the
        requested range, then returns the matching samples.

        Args:
            tag: The telemetry tag (column name) to query.
            start_time: Inclusive start time (ISO format).
            end_time: Exclusive end time (ISO format).

        Returns:
            A dict with ``"timestamps"`` and ``"values"`` lists, or an empty
            dict if the tag is not found.
        """
        index = self.telemetry_index()
        columns = index["columns"]
        tag_index: int | None = next(
            (i for i, c in enumerate(columns) if c.get("tag") == tag), None
        )
        if tag_index is None:
            return {"timestamps": [], "values": []}

        sample_period = index["sample_period"]
        run_start = index["start_time"]

        run_start_dt = datetime.fromisoformat(run_start)
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        result_timestamps: list[str] = []
        result_values: list[float] = []

        for chunk_meta in index["chunks"]:
            chunk_start = datetime.fromisoformat(chunk_meta["start_time"])
            chunk_end = datetime.fromisoformat(chunk_meta["end_time"])
            if chunk_end <= start_dt or chunk_start >= end_dt:
                continue

            data = self._zip.read(chunk_meta["file"])
            array = _npy_bytes_to_array(data)

            chunk_start_offset = int((chunk_start - run_start_dt).total_seconds())
            for row_idx in range(array.shape[0]):
                sample_offset = chunk_start_offset + row_idx
                sample_dt = run_start_dt + timedelta(seconds=sample_offset * sample_period)
                if sample_dt < start_dt or sample_dt >= end_dt:
                    continue
                result_timestamps.append(sample_dt.isoformat())
                result_values.append(float(array[row_idx, tag_index]))

        return cast(
            dict[str, list[str | float]],
            {"timestamps": result_timestamps, "values": result_values},
        )

    def atlas(self) -> dict[str, Any] | None:
        """The optional Atlas detector/hypotheses/narratives data, or None."""
        if self._atlas is not None or self._atlas is False:
            return self._atlas
        detector_data = _read_member(self._zip, fmt.MEMBER_ATLAS_DETECTOR)
        if detector_data is None:
            self._atlas = None
            return None
        alerts_data = _read_member(self._zip, fmt.MEMBER_ATLAS_ALERTS)
        hypotheses_data = _read_member(self._zip, fmt.MEMBER_ATLAS_HYPOTHESES)
        narratives_data = _read_member(self._zip, fmt.MEMBER_ATLAS_NARRATIVES)
        self._atlas = {
            "detector": _json_bytes_to_obj(detector_data),
            "alerts": _jsonl_bytes_to_objs(alerts_data) if alerts_data is not None else [],
            "hypotheses": _jsonl_bytes_to_objs(hypotheses_data)
            if hypotheses_data is not None
            else [],
            "narratives": _jsonl_bytes_to_objs(narratives_data)
            if narratives_data is not None
            else [],
        }
        return self._atlas

    def scores(self) -> dict[str, Any] | None:
        """The optional per-run scores dict, or None."""
        if self._scores is not None or self._scores is False:
            return self._scores
        data = _read_member(self._zip, fmt.MEMBER_SCORES)
        if data is None:
            self._scores = None
            return None
        self._scores = _json_bytes_to_obj(data)
        return self._scores

    def traffic(self) -> dict[str, Any] | None:
        """The optional traffic summary/capture, or None."""
        if self._traffic is not None or self._traffic is False:
            return self._traffic
        summary_data = _read_member(self._zip, fmt.MEMBER_TRAFFIC_SUMMARY)
        capture_data = _read_member(self._zip, fmt.MEMBER_TRAFFIC_CAPTURE)
        if summary_data is None and capture_data is None:
            self._traffic = None
            return None
        self._traffic = {
            "summary": _json_bytes_to_obj(summary_data) if summary_data is not None else None,
            "capture": capture_data,
        }
        return self._traffic

    def thumbnail(self) -> str | None:
        """The optional SVG thumbnail content, or None."""
        data = _read_member(self._zip, fmt.MEMBER_THUMBNAIL)
        if data is None or len(data) == 0:
            return None
        return data.decode("utf-8")


def verify(path: str | Path) -> list[str]:
    """Verify a .phosrun file: every member hash and the run_id.

    Args:
        path: Path to the .phosrun file.

    Returns:
        A list of problem descriptions. Empty list means the file is valid.
    """
    problems: list[str] = []

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())

            for member in fmt.REQUIRED_MEMBERS:
                if member not in names:
                    problems.append(f"missing required member: {member}")

            try:
                header = _json_bytes_to_obj(zf.read(fmt.MEMBER_HEADER))
            except Exception as exc:
                problems.append(f"unreadable header: {exc}")
                return problems

            declared_run_id = header.get("run_id", "")
            declared_members = header.get("members", {})

            for member_name, info in declared_members.items():
                if member_name not in names:
                    problems.append(f"declared member missing: {member_name}")
                    continue
                declared_hash = info.get("sha256", "")
                declared_size = info.get("size_bytes")
                data = zf.read(member_name)
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash != declared_hash:
                    problems.append(
                        f"hash mismatch for {member_name}: "
                        f"declared {declared_hash}, actual {actual_hash}"
                    )
                if declared_size is not None and len(data) != declared_size:
                    problems.append(
                        f"size mismatch for {member_name}: "
                        f"declared {declared_size}, actual {len(data)}"
                    )

            for name in names:
                if name not in declared_members and name != fmt.MEMBER_HEADER:
                    problems.append(f"undeclared member: {name}")

            member_hashes = {
                name: info.get("sha256", "") for name, info in declared_members.items()
            }
            hash_input = "".join(
                f"{name}:{member_hashes[name]}" for name in sorted(member_hashes.keys())
            ).encode("utf-8")
            actual_run_id = hashlib.sha256(hash_input).hexdigest()
            if actual_run_id != declared_run_id:
                problems.append(
                    f"run_id mismatch: declared {declared_run_id}, actual {actual_run_id}"
                )

    except zipfile.BadZipFile as exc:
        problems.append(f"not a valid ZIP archive: {exc}")
    except Exception as exc:
        problems.append(f"verification error: {exc}")

    return problems


__all__ = [
    "RunRecord",
    "read_header",
    "verify",
]
