"""Writing .phosrun files: deterministic ZIP containers of one run.

A .phosrun file is a ZIP container whose members are sorted alphabetically,
written with fixed ZIP timestamps (1980-01-01) and ZIP_DEFLATED compression,
so writing the same run twice yields byte-identical output. The run_id is
SHA-256 over the concatenation of ``member_name:sha256`` pairs for every
member, sorted by member name. header.json's own hash is included in the
run_id computation; since header.json contains run_id itself, run_id is
computed from the header with run_id="" (placeholder), which is the hash
we just computed. This is self-consistent: changing header.json's content
changes its hash, which changes run_id.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy

from . import format as fmt


def _json_bytes(obj: object) -> bytes:
    """Serialize an object to deterministic JSON bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    """Serialize a list of dicts to JSON Lines bytes, trailing newline."""
    if not records:
        return b""
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _npy_bytes(array: numpy.ndarray) -> bytes:
    """Serialize a numpy array to .npy format bytes."""
    buffer = io.BytesIO()
    numpy.save(buffer, array, allow_pickle=False)
    return buffer.getvalue()


def _hash_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _zip_info(member_name: str) -> zipfile.ZipInfo:
    """Create a ZipInfo with a deterministic timestamp and attributes."""
    info = zipfile.ZipInfo(filename=member_name, date_time=fmt.ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def write_run(
    *,
    output: Path,
    kind: str,
    title: str,
    created_by: str,
    seed_information: dict[str, Any] | None,
    pool: str,
    model_not_reality_caveat: str | None,
    plain_language_summary: str,
    plant: dict[str, Any] | None,
    structure: dict[str, Any],
    timeline: list[dict[str, Any]],
    telemetry_chunks: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    atlas: dict[str, Any] | None = None,
    scores: dict[str, Any] | None = None,
    traffic: dict[str, Any] | None = None,
    thumbnail: str | None = None,
) -> Path:
    """Build one .phosrun file from components, deterministically.

    Args:
        output: Path to the .phosrun file to write.
        kind: ``"simulated"`` or ``"real_data"``.
        title: Human-readable title for the run.
        created_by: Tool and code version string.
        seed_information: For simulated runs: family, master_seed, child_seeds.
        pool: One of ``"dev"``, ``"public"``, ``"private"``, ``"retired"``,
            ``"real_data"``.
        model_not_reality_caveat: Caveat text for simulated runs (may be empty
            for real-data runs).
        plain_language_summary: Human-readable summary of the run.
        plant: Plant descriptor dict (simulated: serialised PlantSpec;
            real-data: dataset descriptor).
        structure: Plant structure dict (nodes, edges, subsystems, layout hints).
        timeline: List of event dicts.
        telemetry_chunks: List of telemetry chunk dicts, each with
            ``chunk_index``, ``start_time``, ``end_time``, ``data`` (numpy
            array), ``min_max`` (per-column min/max).
        labels: List of collapsed label-run dicts.
        atlas: Optional dict with ``detector``, ``alerts``, ``hypotheses``,
            ``narratives`` keys.
        scores: Optional dict of per-run metrics.
        traffic: Optional dict with ``summary`` and/or ``capture`` (bytes).
        thumbnail: Optional SVG thumbnail content string.

    Returns:
        The path to the written .phosrun file.
    """
    # Build all member byte contents except the header (which references hashes).
    member_bytes: dict[str, bytes] = {}

    member_bytes[fmt.MEMBER_PLANT] = (
        _json_bytes(plant) if plant is not None else b"{}"
    )
    member_bytes[fmt.MEMBER_STRUCTURE] = _json_bytes(structure)
    member_bytes[fmt.MEMBER_TIMELINE] = _json_bytes(timeline)
    member_bytes[fmt.MEMBER_LABELS] = _json_bytes(labels)
    member_bytes[fmt.MEMBER_THUMBNAIL] = (
        thumbnail.encode("utf-8") if thumbnail is not None else b""
    )

    # Telemetry: chunks + index.
    telemetry_member_bytes: dict[str, bytes] = {}
    telemetry_chunks_meta: list[dict[str, Any]] = []

    if telemetry_chunks:
        first_chunk = telemetry_chunks[0]
        columns = first_chunk.get("columns", [])
        sample_period = first_chunk.get("sample_period", 0.0)
        start_time = first_chunk.get("start_time", "")

        for chunk in telemetry_chunks:
            chunk_index = chunk["chunk_index"]
            chunk_name = fmt.TELEMETRY_CHUNK_NAME_TEMPLATE.format(index=chunk_index)
            data = chunk["data"]  # numpy array
            chunk_bytes = _npy_bytes(data)
            telemetry_member_bytes[chunk_name] = chunk_bytes

            telemetry_chunks_meta.append(
                {
                    "chunk_index": chunk_index,
                    "start_time": chunk["start_time"],
                    "end_time": chunk["end_time"],
                    "file": fmt.TELEMETRY_CHUNK_NAME_TEMPLATE.format(index=chunk["chunk_index"]),
                    "samples": int(chunk["data"].shape[0]),
                    "min_max": chunk["min_max"],
                }
            )

        telemetry_index = {
            "columns": columns,
            "sample_period": sample_period,
            "start_time": start_time,
            "chunk_length": fmt.TELEMETRY_CHUNK_LENGTH,
            "chunks": telemetry_chunks_meta,
        }
    else:
        telemetry_index = {
            "columns": [],
            "sample_period": 0.0,
            "start_time": "",
            "chunk_length": fmt.TELEMETRY_CHUNK_LENGTH,
            "chunks": [],
        }

    member_bytes[fmt.MEMBER_TELEMETRY_INDEX] = _json_bytes(telemetry_index)

    # Merge telemetry chunk bytes into member bytes.
    member_bytes.update(telemetry_member_bytes)

    # Add optional Atlas members.
    if atlas is not None:
        if "detector" in atlas:
            member_bytes[fmt.MEMBER_ATLAS_DETECTOR] = _json_bytes(atlas["detector"])
        if "alerts" in atlas:
            member_bytes[fmt.MEMBER_ATLAS_ALERTS] = _jsonl_bytes(atlas["alerts"])
        if "hypotheses" in atlas:
            member_bytes[fmt.MEMBER_ATLAS_HYPOTHESES] = _jsonl_bytes(
                atlas["hypotheses"]
            )
        if "narratives" in atlas:
            member_bytes[fmt.MEMBER_ATLAS_NARRATIVES] = _jsonl_bytes(
                atlas["narratives"]
            )

    # Add optional scores.
    if scores is not None:
        member_bytes[fmt.MEMBER_SCORES] = _json_bytes(scores)

    # Add optional traffic.
    if traffic is not None:
        if "summary" in traffic:
            member_bytes[fmt.MEMBER_TRAFFIC_SUMMARY] = _json_bytes(
                traffic["summary"]
            )
        capture = traffic.get("capture")
        if capture is not None:
            member_bytes[fmt.MEMBER_TRAFFIC_CAPTURE] = (
                capture if isinstance(capture, bytes) else capture.encode("utf-8")
            )

    # Compute member hashes and sizes (excluding header which references them).
    member_hashes: dict[str, str] = {}
    member_sizes: dict[str, int] = {}
    for name, data in member_bytes.items():
        member_hashes[name] = _hash_bytes(data)
        member_sizes[name] = len(data)

    # Build header.json last (it contains the member hash table).
    # First build header with empty run_id, compute its hash, add it to
    # member_hashes, then compute run_id from NON-header members only
    # (to avoid circular dependency: header contains run_id, which depends
    # on header's hash). Finally rewrite header with the real run_id and
    # update header.json's hash to match the final bytes.
    header: dict[str, Any] = {
        "format_name": fmt.FORMAT_NAME,
        "format_version": fmt.FORMAT_VERSION_STRING,
        "run_id": "",  # placeholder, filled in below
        "kind": kind,
        "title": title,
        "created_by": created_by,
        "seed_information": seed_information,
        "pool": pool,
        "model_not_reality_caveat": model_not_reality_caveat or "",
        "plain_language_summary": plain_language_summary,
        "members": {
            name: {"sha256": member_hashes[name], "size_bytes": member_sizes[name]}
            for name in sorted(member_hashes.keys())
        },
    }
    header_bytes = _json_bytes(header)

    # run_id = SHA-256 over "member_name:sha256" pairs for NON-header members only.
    # header.json contains run_id itself, so we can't include it in its own
    # hash input (circular dependency). header.json's hash is still included
    # in declared_members so that corrupting header.json is detected by verify().
    non_header_hashes = {
        name: h for name, h in member_hashes.items() if name != fmt.MEMBER_HEADER
    }
    hash_input = "".join(
        f"{name}:{non_header_hashes[name]}"
        for name in sorted(non_header_hashes.keys())
    ).encode("utf-8")
    run_id = hashlib.sha256(hash_input).hexdigest()
    header["run_id"] = run_id
    header_bytes = _json_bytes(header)

    # header.json now contains the final run_id, so update its hash.
    member_hashes[fmt.MEMBER_HEADER] = _hash_bytes(header_bytes)
    member_sizes[fmt.MEMBER_HEADER] = len(header_bytes)

    # Add header to members (with final run_id).
    member_bytes[fmt.MEMBER_HEADER] = header_bytes

    # Write ZIP deterministically: members sorted alphabetically.
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(member_bytes.keys()):
            data = member_bytes[name]
            info = _zip_info(name)
            zf.writestr(info, data)

    return output_path


__all__ = ["write_run"]
