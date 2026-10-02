#!/usr/bin/env python3
"""Measure Atlas's command-level detection — and refuse to, because the data does not exist.

This script is the last piece of the packet adapter, and the honest thing about it is that running
it on this repository prints a shopping list rather than a number.

**What it would do.** Given a registered corpus of industrial capture with labelled attack windows,
it learns a command baseline and a device-command graph from an attack-free stretch, fits a
calibrator on a held-out labelled slice, scores the remaining slice with both command detectors, and
reports recall, false positives per normal hour, precision, detection latency and calibration error
— the same metrics, from the same `phos.eval.evaluate`, that every sensor-path result in
``eval_runs/log.jsonl`` was produced by. Nothing about the measurement is special-cased for packets;
that is the whole point of the adapter ending in a `Dataset`.

**What it does today.** `discover_labelled_command_corpora` returns nothing, so it prints what such
a corpus must supply and exits non-zero without computing a metric. That refusal is deliberate and
tested. Session 5 (ADR 0040) opened the licence-confirmed campaign files: Data4Cyber pcapng is
readable and contains operator-shaped Modbus writes, but its labels are 1 Hz process phases, not
command-action windows. s7 `packets_dataset.parquet` is a table. 3W classes 1-9 are faults. Atlas's
claim — that reading commands separates a legitimate operator action from an attacker's identical
one — cannot be demonstrated on process-phase clocks, and producing a plausible number from a
corpus that cannot support it would be worse than producing none.

``--self-test`` runs the whole seam over a hand-built capture with a rogue write injected into it,
and prints a banner saying what that is and is not. It is a check that the plumbing carries a known
signal end to end. The rogue command was chosen and placed by the author, so its recall is a fact
about this script and not about Atlas. The capture builder below is deliberately a small local copy
of the one in ``tests/atlas/test_command_eval.py`` rather than something importable from ``src/``:
a synthetic-traffic generator is its own sub-project, and PHOS does not have one yet.

Usage::

    python scripts/evaluate_command_detection.py
    python scripts/evaluate_command_detection.py --self-test
    python scripts/evaluate_command_detection.py --no-log
"""

from __future__ import annotations

import argparse
import logging
import struct
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas import (  # noqa: E402
    COMMAND_EVIDENCE_CAVEATS,
    CommandBehaviourDetector,
    CommandCaptureAdapter,
    CommandCorpus,
    CommandGraphDetector,
    default_registry,
    discover_labelled_command_corpora,
    learn_device_command_graph,
    render_missing_corpus,
    require_labelled_intervals,
)
from phos.atlas.packet import dissect_capture  # noqa: E402
from phos.eval import (  # noqa: E402
    Dataset,
    EvalConfig,
    EvaluationReport,
    LabelledInterval,
    append_to_experiment_log,
    evaluate,
)
from phos.models import GaussianBaseline  # noqa: E402
from phos.reasoning import (  # noqa: E402
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR: Final = REPO_ROOT / "data"
SEED: Final = 11
ALERT_THRESHOLD: Final = 0.0
THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)

MECHANISM_BANNER: Final = (
    "=" * 100
    + "\nMECHANISM CHECK — NOT A DETECTION RESULT.\n"
    + "The capture below was hand-built by this script and the rogue command was placed in it "
    "deliberately,\nat a moment and with a magnitude chosen by the author. What follows shows that "
    "the pipeline carries a\nknown signal from bytes on the wire through to a scored, calibrated "
    "alert. It says nothing whatever\nabout recall on real intrusions, about the false-positive "
    "rate on a real plant, or about whether a\nconfidence from this path means what it says. "
    "Nothing here is written to the experiment log.\n" + "=" * 100
)

logger = logging.getLogger("phos.atlas.commands")


# ------------------------------------------------------------------------------------------------
# The measurement, for when there is something to measure
# ------------------------------------------------------------------------------------------------


def measure(baseline: Dataset, scored: Dataset) -> list[EvaluationReport]:
    """Score both command streams against a labelled corpus and return one report per stream.

    Args:
        baseline: An attack-free corpus to learn command behaviour from. Never scored.
        scored: The labelled corpus to report on. Split three ways so neither the model nor the
            calibrator sees the slice the numbers come from.

    Returns:
        One report for the behaviour stream and one for the graph stream, in that order. Two rather
        than one because their scores are in different units — a magnitude in learned spreads and a
        count of commands — so a single threshold sweep across both would mean nothing at either
        end.

    Raises:
        UnlabelledCommandCorpusError: If ``scored`` carries no ground truth.
        DegenerateSplitError: If the three-way split cannot produce usable slices.
    """
    require_labelled_intervals(scored)
    _, calib, test = train_calib_test_split(scored, THREE_WAY)

    fitted = GaussianBaseline(name="command-behaviour").fit(baseline.observations)
    scores, labels = scores_and_labels_from(fitted, calib)
    calibrator = IsotonicCalibrator(seed=SEED).fit(scores, labels)

    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)
    return [
        evaluate(CommandBehaviourDetector(fitted=fitted, calibrator=calibrator), test, config),
        evaluate(CommandGraphDetector(calibrator=calibrator), test, config),
    ]


def run_corpus(corpus: CommandCorpus) -> list[EvaluationReport]:
    """Learn a graph from the corpus's first capture and measure against the rest."""
    adapter = corpus.adapter()
    baseline_capture, *scored_captures = adapter.captures
    graph = learn_device_command_graph(dissect_capture(baseline_capture, default_registry()))
    logger.info(
        "%s: learned %d command relationship(s) from %s",
        corpus.name,
        len(graph.edges),
        baseline_capture.name,
    )
    baseline = CommandCaptureAdapter(
        captures=(baseline_capture,), name=f"{corpus.name}-baseline"
    ).load()
    scored = adapter.model_copy(
        update={"captures": tuple(scored_captures) or adapter.captures, "graph": graph}
    ).load()
    return measure(baseline, scored)


# ------------------------------------------------------------------------------------------------
# The self-test capture
# ------------------------------------------------------------------------------------------------

SELF_TEST_EPOCH: Final = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
HMI: Final = "10.0.0.5"
PLC: Final = "10.0.0.10"
ROGUE: Final = "10.0.0.99"


def _request(function_code: int, address: int, value: int) -> bytes:
    """Build a Modbus/TCP ADU carrying a two-field request PDU."""
    pdu = struct.pack(">BHH", function_code, address, value)
    return struct.pack(">HHHB", 0x1234, 0, len(pdu) + 1, 1) + pdu


def _frame(src: str, dst: str, payload: bytes) -> bytes:
    """Wrap ``payload`` in Ethernet / IPv4 / TCP, client port to Modbus port 502."""
    segment = struct.pack(">HHIIBBHHH", 5555, 502, 1, 1, 0x50, 0x18, 8192, 0, 0) + payload
    header = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(segment),
        1,
        0,
        64,
        6,
        0,
        bytes(int(part) for part in src.split(".")),
        bytes(int(part) for part in dst.split(".")),
    )
    return b"\xaa" * 6 + b"\xbb" * 6 + struct.pack(">H", 0x0800) + header + segment


def _write_capture(path: Path, records: Sequence[tuple[datetime, bytes]]) -> Path:
    """Write a classic libpcap file holding ``(timestamp, frame)`` records."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for stamp, raw in sorted(records, key=lambda item: item[0]):
        micros = int(stamp.timestamp() * 1_000_000)
        out += (
            struct.pack("<IIII", micros // 1_000_000, micros % 1_000_000, len(raw), len(raw)) + raw
        )
    path.write_bytes(out)
    return path


def _polling(minutes: int, start: datetime) -> list[tuple[datetime, bytes]]:
    """One read request per second from the HMI to the PLC."""
    return [
        (start + timedelta(seconds=second), _frame(HMI, PLC, _request(3, 40, 10)))
        for second in range(minutes * 60)
    ]


def self_test(workspace: Path) -> int:
    """Run the whole seam on a hand-built capture and report what it found. Returns an exit code."""
    print(MECHANISM_BANNER)

    baseline_path = _write_capture(workspace / "baseline.pcap", _polling(15, SELF_TEST_EPOCH))
    live_start = SELF_TEST_EPOCH + timedelta(hours=1)
    attack_at = live_start + timedelta(minutes=5)
    live_path = _write_capture(
        workspace / "live.pcap",
        [
            *_polling(10, live_start),
            *(
                (attack_at + timedelta(seconds=second), _frame(ROGUE, PLC, _request(6, 17, 1)))
                for second in range(5)
            ),
        ],
    )

    graph = learn_device_command_graph(dissect_capture(baseline_path, default_registry()))
    scored = CommandCaptureAdapter(
        captures=(live_path,),
        attack_intervals=(
            LabelledInterval(
                start=attack_at,
                end=attack_at + timedelta(seconds=59),
                label="attack",
                attack_type="rogue_write",
            ),
        ),
        graph=graph,
        name="self-test",
        source_note="hand-built by scripts/evaluate_command_detection.py",
    ).load()
    require_labelled_intervals(scored)

    print(
        f"\nlearned {len(graph.edges)} command relationship(s); "
        f"scored corpus holds {len(scored.observations)} observation(s) and "
        f"{len(scored.attack_intervals)} labelled window(s)"
    )

    # A calibrator built rather than fitted: the point of the self-test is the plumbing, and a
    # calibrator fitted on five hand-placed frames would be a fit to the author's own choices.
    from phos.reasoning import FittedPlattCalibrator

    calibrator = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
    detections = CommandGraphDetector(calibrator=calibrator).run(scored)
    print(f"the command graph reported {len(detections)} structural change(s):")
    for detection in detections[:5]:
        print(
            f"  {detection.timestamp.isoformat()}  {detection.feature}  "
            f"{', '.join(detection.entity_ids)}  score {detection.score:g}"
        )

    caught = any(
        interval.contains(detection.timestamp)
        for detection in detections
        for interval in scored.attack_intervals
    )
    print(
        f"\nthe injected rogue command was {'carried through to an alert' if caught else 'LOST'} — "
        "which is a statement about this pipeline, not about Atlas."
    )
    print("\n" + caveats())
    return 0 if caught else 1


# ------------------------------------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------------------------------------


def render(reports: Sequence[EvaluationReport]) -> str:
    """Render reports as a markdown table, in the shape PROGRESS.md uses."""
    header = (
        "| Corpus | Detector | Alerts | Recall | FPs | FP/normal-hr | Precision | ECE |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        f"| `{report.dataset_name}` | `{report.detector_name}` | {report.n_alerts:,} "
        f"| {report.window_recall:.2f} | {report.false_positives:,} "
        f"| {report.false_positive_rate:.2f} | {report.precision:.4f} "
        f"| {report.expected_calibration_error:.4f} |"
        for report in reports
    ]
    return "\n".join([header, *rows])


def caveats() -> str:
    """Render everything that must be read with any number this script produces."""
    return "\n".join(
        ["Read every number above with these:", *(f"  - {c}" for c in COMMAND_EVIDENCE_CAVEATS)]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the seam over a hand-built capture; prints a mechanism check, never a result",
    )
    parser.add_argument("--no-log", action="store_true", help="do not append to the experiment log")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if arguments.self_test:
        with tempfile.TemporaryDirectory(prefix="phos-command-seam-") as workspace:
            return self_test(Path(workspace))

    corpora = discover_labelled_command_corpora(DATA_DIR)
    if not corpora:
        print(render_missing_corpus())
        return 2

    reports: list[EvaluationReport] = []
    for corpus in corpora:
        try:
            reports.extend(run_corpus(corpus))
        except DegenerateSplitError as error:
            logger.warning("%s: %s", corpus.name, error)

    if not reports:
        logger.error("no registered command corpus yielded a usable split")
        return 1

    if not arguments.no_log:
        for report in reports:
            append_to_experiment_log(report)

    print("\n" + render(reports))
    print("\n" + caveats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
