"""Atlas's packet and command path on the 4SICS development days (ADR 0177).

Day ``151020`` learns the command graph. Day ``151021`` is compared with it.
The third day is held back and is refused before it is opened. There are no
attack labels, so this module does not report a catch. Graph findings are
counts, not a calibrated confidence, and none is surfaced.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from phos.atlas.command_eval import default_registry
from phos.atlas.packet import (
    CaptureStats,
    CommandStreamStats,
    DeviceCommandGraph,
    MalformedFrame,
    ModbusMessage,
    UnparsedMessage,
    compare_to_graph,
    dissect_capture,
    learn_device_command_graph,
    render_graph,
)
from phos.eval.build_declaration import FOUR_SICS_DEVELOPMENT_FILES, FOUR_SICS_HELD_BACK_FILES

__all__ = [
    "LEARN_FILE",
    "RESULT_NAME",
    "SCORE_FILE",
    "FourSicsError",
    "alerts_per_hour",
    "coverage",
    "refuse_held_back",
    "score_days",
]

logger = logging.getLogger(__name__)

LEARN_FILE: Final = "4SICS-GeekLounge-151020.pcap"
SCORE_FILE: Final = "4SICS-GeekLounge-151021.pcap"
RESULT_NAME: Final = "round-3:4sics-development"
_CREDIT: Final = "https://www.netresec.com/?page=PCAP4SICS"

# Ports Atlas does not dissect. The name is the well-known assignment, not a decode.
_PORT_NAMES: Final[dict[int, str]] = {
    102: "S7comm",
    502: "Modbus",
    2222: "EtherNet/IP",
    4840: "OPC UA",
    20000: "DNP3",
    44818: "EtherNet/IP",
}


class FourSicsError(ValueError):
    """Raised when a 4SICS file is not one of the two development days."""


def refuse_held_back(filename: str) -> None:
    """Raise before a held-back 4SICS capture is opened.

    Args:
        filename: The file's final component.

    Raises:
        FourSicsError: If the name is the held-back day or is not a development day.
    """
    if filename in FOUR_SICS_HELD_BACK_FILES or "151022" in filename:
        raise FourSicsError(f"{filename} is held back and is not opened")
    if filename not in FOUR_SICS_DEVELOPMENT_FILES:
        raise FourSicsError(f"{filename} is not a 4SICS development capture")


def alerts_per_hour(findings: int, start: datetime | None, end: datetime | None) -> float | None:
    """Return findings divided by the clock from ``start`` to ``end``.

    Args:
        findings: Graph findings on the scored day.
        start: First scored timestamp.
        end: Last scored timestamp.

    Returns:
        Findings per hour, or ``None`` when the span is empty.
    """
    if start is None or end is None or end <= start or findings < 0:
        return None
    hours = (end - start) / timedelta(hours=1)
    if hours <= 0:
        return None
    return findings / hours


def coverage(path: Path) -> dict[str, object]:
    """Dissect one development capture and count what Atlas could read.

    Args:
        path: ``151020`` or ``151021``.

    Returns:
        Frame counts, decoded protocols, and undissected destination ports.

    Raises:
        FourSicsError: If the name is not a development day.
    """
    refuse_held_back(path.name)
    stats = CaptureStats()
    decoded: Counter[str] = Counter()
    malformed: Counter[str] = Counter()
    ports: Counter[str] = Counter()
    first: datetime | None = None
    last: datetime | None = None
    for item in dissect_capture(path, default_registry(), stats):
        stamp = item.timestamp
        first = stamp if first is None else min(first, stamp)
        last = stamp if last is None else max(last, stamp)
        if isinstance(item, ModbusMessage):
            decoded[item.protocol] += 1
        elif isinstance(item, UnparsedMessage):
            label = _PORT_NAMES.get(item.dst.port, "unassigned")
            ports[f"port {item.dst.port} ({label})"] += 1
        elif isinstance(item, MalformedFrame):
            malformed[item.protocol] += 1
    return {
        "filename": path.name,
        "frames_read": stats.frames_read,
        "frames_yielded": stats.frames_yielded,
        "frames_undecodable": stats.frames_undecodable,
        "frames_without_payload": stats.frames_without_payload,
        "decoded": dict(decoded),
        "malformed": dict(malformed),
        "undissected_ports": dict(ports.most_common(12)),
        "first": None if first is None else first.isoformat(),
        "last": None if last is None else last.isoformat(),
    }


def score_days(directory: Path) -> dict[str, object]:
    """Learn the graph on day one and count graph findings on day two.

    Args:
        directory: The folder that holds the two development pcaps.

    Returns:
        Coverage, the learned edges, and findings per hour. No catch count.

    Raises:
        FourSicsError: If either name is held back.
    """
    learn_path = directory / LEARN_FILE
    score_path = directory / SCORE_FILE
    refuse_held_back(learn_path.name)
    refuse_held_back(score_path.name)
    registry = default_registry()
    learn_stats = CaptureStats()
    learned_messages = list(dissect_capture(learn_path, registry, learn_stats))
    command_stats = CommandStreamStats()
    graph = learn_device_command_graph(learned_messages, command_stats)
    score_stats = CaptureStats()
    scored_messages = list(dissect_capture(score_path, registry, score_stats))
    findings = compare_to_graph(graph, scored_messages)
    stamps = [item.timestamp for item in scored_messages]
    start = min(stamps) if stamps else None
    end = max(stamps) if stamps else None
    by_feature = Counter(item.feature for item in findings)
    finding_rows = [
        {
            "feature": item.feature,
            "issuer": item.context.get("issuer_ip", ""),
            "target": item.context.get("target_ip", ""),
            "commands": item.value,
        }
        for item in findings
    ]
    return {
        "result_name": RESULT_NAME,
        "credit": _CREDIT,
        "learn": LEARN_FILE,
        "score": SCORE_FILE,
        "catches": None,
        "note": (
            "Unlabelled conference-lab traffic. Graph findings are not attacks. "
            "Hypothesis confidence is not reported. Day 151022 was not opened."
        ),
        "learn_coverage": coverage(learn_path),
        "score_coverage": coverage(score_path),
        "graph": _graph_rows(graph),
        "graph_text": render_graph(graph),
        "findings": len(findings),
        "findings_by_feature": dict(by_feature),
        "finding_rows": finding_rows,
        "alerts_per_hour": alerts_per_hour(len(findings), start, end),
        "score_span_start": None if start is None else start.isoformat(),
        "score_span_end": None if end is None else end.isoformat(),
        "learn_commands": command_stats.commands,
    }


def _graph_rows(graph: DeviceCommandGraph) -> list[dict[str, object]]:
    return [
        {
            "issuer": edge.issuer_ip,
            "target": edge.target_ip,
            "commands": edge.command_count,
            "functions": list(edge.function_codes),
        }
        for edge in graph.edges
    ]
