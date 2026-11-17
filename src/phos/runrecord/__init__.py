"""The .phosrun run-record format library.

A .phosrun file is a deterministic ZIP container of one simulation or real-data
run: header, plant description, structure, timeline, labelled telemetry chunks,
optional Atlas outputs and scores, optional traffic summary/capture, and a
thumbnail.

This package never imports ``phos.atlas`` or anything under
``src/phos/atlas/``. The recorder module (under ``src/phos/referee/``) is the
only code allowed to import Atlas's public interface.

Public API:
- ``write_run(...)``: build a .phosrun from components, deterministically.
- ``read_header(path)``: read only header.json, for fast library scanning.
- ``open_run(path)``: lazy reader exposing structure, timeline, labels,
  telemetry (range queries), atlas data, scores and traffic summary.
- ``verify(path)``: check every member hash and the run_id.
- ``phos-run`` CLI: ``inspect FILE``, ``verify FILE``, ``list DIR``.
"""

from __future__ import annotations

from .format import (
    ALL_MEMBERS,
    FORMAT_NAME,
    FORMAT_VERSION_MAJOR,
    FORMAT_VERSION_MINOR,
    FORMAT_VERSION_PATCH,
    FORMAT_VERSION_STRING,
    KIND_REAL_DATA,
    KIND_SIMULATED,
    OPTIONAL_MEMBERS,
    POOL_DEV,
    POOL_PRIVATE,
    POOL_PUBLIC,
    POOL_REAL_DATA,
    POOL_RETIRED,
    REQUIRED_MEMBERS,
    TELEMETRY_CHUNK_LENGTH,
)
from .reader import RunRecord, read_header, verify
from .writer import write_run

__all__ = [
    "ALL_MEMBERS",
    "FORMAT_NAME",
    "FORMAT_VERSION_MAJOR",
    "FORMAT_VERSION_MINOR",
    "FORMAT_VERSION_PATCH",
    "FORMAT_VERSION_STRING",
    "KIND_REAL_DATA",
    "KIND_SIMULATED",
    "OPTIONAL_MEMBERS",
    "POOL_DEV",
    "POOL_PRIVATE",
    "POOL_PUBLIC",
    "POOL_REAL_DATA",
    "POOL_RETIRED",
    "REQUIRED_MEMBERS",
    "TELEMETRY_CHUNK_LENGTH",
    "RunRecord",
    "read_header",
    "verify",
    "write_run",
]
