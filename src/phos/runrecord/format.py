"""The .phosrun file format: a deterministic ZIP container of one run.

Format name: ``phosrun``
Format version: 1.0.0 (semantic versioning, MAJOR.MINOR.PATCH)

Readers must refuse an unknown MAJOR version with a clear message.

Member layout (all text is UTF-8 JSON or JSON Lines unless stated otherwise):

Required members (every run carries these):
- header.json          provenance: format name/version, run_id, kind, title,
                       created_by, seed information, pool, caveat text,
                       plain-language summary, member hash table
- plant.json           for simulated runs: serialised PlantSpec; for real-data
                       runs: a descriptor (dataset name, tags, units, structure)
- structure.json       nodes/edges/subsystems/layout hints for the viewer
- timeline.json        every event: id, kind, type/technique, start/end,
                       affected tags/devices, layer, physical-effect flag,
                       plain-language description
- telemetry/index.json + telemetry/chunk_NNNNN.*  columnar telemetry in
                       fixed-size time chunks with min-max pyramid overview
- labels.json          collapsed label runs per timestamp range
- thumbnail.svg        deterministic drawing of plant structure

Optional members (absent when not applicable):
- atlas/detector.json   adapter name, version, configuration
- atlas/alerts.jsonl    time, tags, subsystem, severity, plain text
- atlas/hypotheses.jsonl time, ranked hypotheses with confidences,
                        supporting/contradicting evidence references
- atlas/narratives.jsonl text explanations Atlas produced
- scores.json           per-run metrics from the scorer with scorer version
- traffic/summary.json  per-interval packet counts, command writes,
                        polled registers, notable messages
- traffic/capture.pcap  optional packet capture, only below a size limit

Determinism: fixed ZIP timestamps (1980-01-01), members sorted alphabetically,
fixed ZIP_DEFLATED compression, run_id = SHA-256 over member content hashes,
no wall-clock time in the content hash.
"""

from __future__ import annotations

from typing import Final

FORMAT_NAME: Final = "phosrun"
FORMAT_VERSION_MAJOR: Final = 1
FORMAT_VERSION_MINOR: Final = 0
FORMAT_VERSION_PATCH: Final = 0
FORMAT_VERSION_STRING: Final = (
    f"{FORMAT_VERSION_MAJOR}.{FORMAT_VERSION_MINOR}.{FORMAT_VERSION_PATCH}"
)

# ZIP determinism constants.
ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)  # year, month, day, hour, minute, second
ZIP_COMPRESSION: Final = "deflated"

# Required members — every run carries these.
MEMBER_HEADER: Final = "header.json"
MEMBER_PLANT: Final = "plant.json"
MEMBER_STRUCTURE: Final = "structure.json"
MEMBER_TIMELINE: Final = "timeline.json"
MEMBER_TELEMETRY_INDEX: Final = "telemetry/index.json"
MEMBER_LABELS: Final = "labels.json"
MEMBER_THUMBNAIL: Final = "thumbnail.svg"

# Optional members — present only when applicable.
MEMBER_ATLAS_DETECTOR: Final = "atlas/detector.json"
MEMBER_ATLAS_ALERTS: Final = "atlas/alerts.jsonl"
MEMBER_ATLAS_HYPOTHESES: Final = "atlas/hypotheses.jsonl"
MEMBER_ATLAS_NARRATIVES: Final = "atlas/narratives.jsonl"
MEMBER_SCORES: Final = "scores.json"
MEMBER_TRAFFIC_SUMMARY: Final = "traffic/summary.json"
MEMBER_TRAFFIC_CAPTURE: Final = "traffic/capture.pcap"

REQUIRED_MEMBERS: Final = (
    MEMBER_HEADER,
    MEMBER_PLANT,
    MEMBER_STRUCTURE,
    MEMBER_TIMELINE,
    MEMBER_TELEMETRY_INDEX,
    MEMBER_LABELS,
    MEMBER_THUMBNAIL,
)

OPTIONAL_MEMBERS: Final = (
    MEMBER_ATLAS_DETECTOR,
    MEMBER_ATLAS_ALERTS,
    MEMBER_ATLAS_HYPOTHESES,
    MEMBER_ATLAS_NARRATIVES,
    MEMBER_SCORES,
    MEMBER_TRAFFIC_SUMMARY,
    MEMBER_TRAFFIC_CAPTURE,
)

ALL_MEMBERS: Final = REQUIRED_MEMBERS + OPTIONAL_MEMBERS

# Telemetry chunking defaults.
TELEMETRY_CHUNK_LENGTH: Final = 3600  # samples per chunk (1 hour at 1-second sampling)
TELEMETRY_ARRAY_DTYPE: Final = "float64"
TELEMETRY_CHUNK_NAME_TEMPLATE: Final = "telemetry/chunk_{index:05d}.npy"

# Kind values for header.json.
KIND_SIMULATED: Final = "simulated"
KIND_REAL_DATA: Final = "real_data"

# Pool values for header.json.
POOL_DEV: Final = "dev"
POOL_PUBLIC: Final = "public"
POOL_PRIVATE: Final = "private"
POOL_RETIRED: Final = "retired"
POOL_REAL_DATA: Final = "real_data"

__all__ = [
    "ALL_MEMBERS",
    "FORMAT_NAME",
    "FORMAT_VERSION_MAJOR",
    "FORMAT_VERSION_MINOR",
    "FORMAT_VERSION_PATCH",
    "FORMAT_VERSION_STRING",
    "KIND_REAL_DATA",
    "KIND_SIMULATED",
    "MEMBER_ATLAS_ALERTS",
    "MEMBER_ATLAS_DETECTOR",
    "MEMBER_ATLAS_HYPOTHESES",
    "MEMBER_ATLAS_NARRATIVES",
    "MEMBER_HEADER",
    "MEMBER_LABELS",
    "MEMBER_PLANT",
    "MEMBER_SCORES",
    "MEMBER_STRUCTURE",
    "MEMBER_TELEMETRY_INDEX",
    "MEMBER_THUMBNAIL",
    "MEMBER_TIMELINE",
    "MEMBER_TRAFFIC_CAPTURE",
    "MEMBER_TRAFFIC_SUMMARY",
    "OPTIONAL_MEMBERS",
    "POOL_DEV",
    "POOL_PRIVATE",
    "POOL_PUBLIC",
    "POOL_REAL_DATA",
    "POOL_RETIRED",
    "REQUIRED_MEMBERS",
    "TELEMETRY_ARRAY_DTYPE",
    "TELEMETRY_CHUNK_LENGTH",
    "TELEMETRY_CHUNK_NAME_TEMPLATE",
    "ZIP_COMPRESSION",
    "ZIP_TIMESTAMP",
]
