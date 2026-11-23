"""The recorder: runs Atlas on a generated run through its public interface, read-only.

PART V2. This module is the *only* code allowed to import `phos.atlas`, and it feeds Atlas
telemetry and packet files only — never labels, manifests or seeds. `tests/referee/test_record.py`
pins that no `atlas` import leaks into the viewer or runrecord packages.

Usage::

    from phos.referee.record import record_atlas_on_run
    result = record_atlas_on_run(plant_dir, out_dir)

The recorder writes an `atlas/` member bundle into an existing `.phosrun` zip (or creates one
from scratch if only a corpus directory is given). It also writes the plant descriptor,
structure, timeline, and telemetry chunks needed by the viewer's run detail screen.

It is deliberately side-effect-free except for writing its own output file: it never mutates
the input corpus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy
import pandas

from phos.atlas import AtlasEngine
from phos.atlas.multivariate import MahalanobisModel
from phos.eval import LabelledCsvAdapter
from phos.models.detector import ModelDetector
from phos.ontology import Domain
from phos.reasoning import (
    CalibrationSplitPolicy,
    IsotonicCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

__all__ = [
    "atlas_evidence_from_run",
    "build_plant_descriptor",
    "build_structure",
    "build_telemetry_chunks",
    "build_timeline",
    "record_atlas_on_run",
]


def _load_telemetry(corpus_dir: Path) -> dict[str, list[float]]:
    """Load telemetry.csv as a dict of {feature: [values]} for the recorder's own accounting.

    Used only to decide which signals the corpus carries; Atlas itself reads the CSV through
    `LabelledCsvAdapter`. This function never reads labels or attack windows.
    """
    frame = pandas.read_csv(corpus_dir / "telemetry.csv")
    value_columns = [
        c for c in frame.columns if c not in ("timestamp", "label")
    ]
    return {c: frame[c].tolist() for c in value_columns}


def atlas_evidence_from_run(
    corpus_dir: Path,
    topology_path: Path | None = None,
) -> dict[str, object]:
    """Run Atlas on a generated corpus through its public interface only.

    Feeds Atlas telemetry and packet capture only — never labels, manifests or seeds. Returns
    a dict with ``detector``, ``alerts``, ``hypotheses`` and ``narratives`` keys suitable for
    writing into a ``.phosrun`` atlas member bundle.

    Args:
        corpus_dir: Directory containing ``telemetry.csv`` and ``topology.toml`` (and optionally
            ``capture.pcap``).
        topology_path: Optional override path to a topology TOML file. If omitted, the recorder
            looks for ``topology.toml`` inside ``corpus_dir``.

    Returns:
        A dict suitable for serializing into the ``atlas/`` member bundle of a ``.phosrun`` file.
        Contains ``detector`` (name and config), ``alerts`` (list of detection dicts),
        ``hypotheses`` (list of hypothesis dicts) and ``narratives`` (list of narrative dicts).

    Raises:
        FileNotFoundError: If the corpus directory lacks ``telemetry.csv``.
    """
    telemetry_path = corpus_dir / "telemetry.csv"
    if not telemetry_path.exists():
        raise FileNotFoundError(f"{corpus_dir}: no telemetry.csv — cannot run Atlas")

    # Load the corpus through the public LabelledCsvAdapter — same door a real corpus uses.
    adapter = LabelledCsvAdapter(
        path=telemetry_path,
        timestamp_column="timestamp",
        label_column="label",
        name=f"synth-{corpus_dir.name}",
        domain=Domain.ATLAS,
    )
    dataset = adapter.load()

    if len(dataset.observations) < 10:
        raise ValueError(f"{corpus_dir}: too few observations to fit Atlas")

    # Split into train/calib/test like the evaluation harness does.
    train, calib, test = train_calib_test_split(
        dataset, CalibrationSplitPolicy(train_fraction=0.5, calib_fraction=0.25)
    )

    # Fit the joint model on attack-free training data.
    fitted = MahalanobisModel().fit(train.observations)

    # Fit the isotonic calibrator on the calibration slice.
    scores, labels = scores_and_labels_from(fitted, calib)
    calibrator = IsotonicCalibrator(seed=11).fit(scores, labels)

    detector = ModelDetector(fitted=fitted)
    detections = detector.run(test)

    # Run the full engine for narratives + competing hypotheses.
    topology_path = topology_path or (corpus_dir / "topology.toml")
    from phos.atlas.topology import load_topology

    # Read the manifest to get the declared corpus name (plant_id), which is what the
    # topology's `corpus` field carries — not the directory name.
    manifest_path = corpus_dir / "manifest.json"
    corpus_name = corpus_dir.name
    if manifest_path.exists():
        import json

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            corpus_name = manifest.get("plant_id", corpus_dir.name)
        except Exception:
            pass
    subsystem_map = load_topology(
        topology_path,
        {obs.feature for obs in test.observations},
        corpus=corpus_name,
    )
    engine = AtlasEngine(
        fitted=fitted,
        calibrator=calibrator,
        subsystem_map=subsystem_map,
    )
    narratives = engine.run(test)

    # Build detector output.
    detections_out = [
        {
            "timestamp": d.timestamp.isoformat(),
            "score": d.score,
            "confidence": d.confidence,
            "entity_ids": list(d.entity_ids),
            "feature": d.feature,
        }
        for d in detections
    ]

    # Build hypothesis output from the engine's store.
    store = engine.store
    hypotheses_out: list[dict[str, object]] = []
    for hyp in store.hypotheses():
        hypotheses_out.append(
            {
                "id": hyp.id,
                "template_id": hyp.template_id,
                "confidence": hyp.confidence,
                "supporting": list(hyp.supporting),
                "contradictory": list(hyp.contradictory),
            }
        )

    # Build narrative output.
    narratives_out: list[dict[str, object]] = []
    for nar in narratives:
        narratives_out.append(
            {
                "id": nar.id,
                "title": nar.title,
                "hypothesis_ids": list(nar.hypothesis_ids),
                "confidence": nar.overall_confidence,
                "evidence_ids": list(nar.evidence_ids),
                "causal_edges": list(nar.causal_edges),
            }
        )

    return {
        "detector": {
            "name": detector.name,
            "model": "MahalanobisModel",
        },
        "alerts": detections_out,
        "hypotheses": hypotheses_out,
        "narratives": narratives_out,
    }


def load_manifest(corpus_dir: Path) -> dict[str, Any] | None:
    """Load the manifest.json from a corpus directory, if present.

    Never reads attack labels or seeds for Atlas scoring — used only to build
    viewer-facing plant/structure/timeline metadata.
    """
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception:
        return None


def build_plant_descriptor(corpus_dir: Path) -> dict[str, Any]:
    """Build a plant descriptor dict from the corpus manifest.

    Returns a dict with plant_id, label, industry, summary, units, and signals.
    Empty dict if no manifest is available.
    """
    manifest = load_manifest(corpus_dir)
    if manifest is None:
        return {}

    desc = manifest.get("description", {})
    return {
        "plant_id": desc.get("plant_id", corpus_dir.name),
        "label": desc.get("label", ""),
        "industry": desc.get("industry", ""),
        "summary": desc.get("summary", ""),
        "units": desc.get("units", []),
        "signals": desc.get("signals", []),
        "control_network": desc.get("control_network", {}),
        "write_authority": desc.get("write_authority", {}),
    }


def build_structure(corpus_dir: Path) -> dict[str, Any]:
    """Build a plant structure dict (nodes, edges) from topology.toml and manifest.

    Nodes are the declared subsystems plus control-network nodes. Edges come from
    the manifest's couplings (signal-level relationships) and control network
    blocks (which signals each PLC handles).

    Returns a dict with ``nodes`` and ``edges`` lists. Empty lists if no data.
    """
    manifest = load_manifest(corpus_dir)
    if manifest is None:
        return {"nodes": [], "edges": []}

    desc = manifest.get("description", {})
    units = desc.get("units", [])
    signals = desc.get("signals", [])
    couplings = desc.get("couplings", [])
    control_network = desc.get("control_network", {})

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Subsystem nodes from topology / manifest units.
    for unit in units:
        nodes.append(
            {
                "id": unit.get("unit_id", ""),
                "label": unit.get("label", unit.get("unit_id", "")),
                "type": "subsystem",
                "tags": [unit.get("unit_id", "")],
            }
        )

    # Control network nodes.
    for cn_node in control_network.get("nodes", []):
        nodes.append(
            {
                "id": cn_node.get("node_id", ""),
                "label": cn_node.get("label", cn_node.get("node_id", "")),
                "type": cn_node.get("role", "device"),
                "tags": [cn_node.get("role", "")],
            }
        )

    # Signal nodes (one per telemetry signal).
    for sig in signals:
        nodes.append(
            {
                "id": sig.get("key", ""),
                "label": sig.get("label", sig.get("key", "")),
                "type": sig.get("kind", "sensor").lower(),
                "tags": [sig.get("physical_unit", "")],
            }
        )

    # Coupling edges: driven <- drivers.
    for coupling in couplings:
        driven = coupling.get("driven", "")
        for driver in coupling.get("drivers", []):
            edges.append(
                {
                    "from": driver,
                    "to": driven,
                    "label": coupling.get("kind", ""),
                    "kind": coupling.get("kind", ""),
                }
            )

    # Control network block edges: PLC -> signals it handles.
    for block in control_network.get("blocks", []):
        node_id = block.get("node_id", "")
        for signal in block.get("signals", []):
            edges.append(
                {
                    "from": node_id,
                    "to": signal,
                    "label": "poll",
                    "kind": "control",
                    "writable": block.get("writable", False),
                }
            )

    return {"nodes": nodes, "edges": edges}


def build_timeline(corpus_dir: Path) -> list[dict[str, Any]]:
    """Build a timeline event list from manifest events and attacks.

    Each entry has: id, kind, type/technique, start, end, affected tags/devices,
    layer, physical_effect flag, plain-language description.

    Benign events come from manifest ``events``; attacks come from manifest
    ``attacks``. Never reads labels or truth columns for this.
    """
    manifest = load_manifest(corpus_dir)
    if manifest is None:
        return []

    timeline: list[dict[str, Any]] = []

    for i, ev in enumerate(manifest.get("events", [])):
        timeline.append(
            {
                "id": f"event-{i:04d}",
                "kind": ev.get("kind", "benign"),
                "type": ev.get("kind", "benign"),
                "start": ev.get("started_at", ""),
                "end": ev.get("ended_at", ""),
                "affected_tags": list(ev.get("writes", [])),
                "layer": "operator",
                "physical_effect": False,
                "description": ev.get("detail", ev.get("label", "")),
            }
        )

    for i, atk in enumerate(manifest.get("attacks", [])):
        timeline.append(
            {
                "id": atk.get("attack_id", f"attack-{i:04d}"),
                "kind": "attack",
                "type": atk.get("type", "rogue_command"),
                "start": atk.get("started_at", ""),
                "end": atk.get("ended_at", ""),
                "affected_tags": list(atk.get("target_signals", [])),
                "layer": "control_network",
                "physical_effect": bool(atk.get("physical_effect", False)),
                "description": atk.get("manipulation", ""),
            }
        )

    timeline.sort(key=lambda e: e.get("start", ""))
    return timeline


def build_telemetry_chunks(
    corpus_dir: Path, chunk_length: int = 3600
) -> list[dict[str, Any]]:
    """Build telemetry chunks from telemetry.csv for the viewer.

    Splits the CSV into fixed-size row chunks and returns chunk dicts with
    chunk_index, start_time, end_time, columns, data (list of rows), min_max.

    The data is kept as nested lists (not numpy) for JSON serialisation.
    """
    from phos.runrecord.format import TELEMETRY_CHUNK_LENGTH as _DEFAULT

    if chunk_length != _DEFAULT:
        chunk_length = _DEFAULT

    telemetry_path = corpus_dir / "telemetry.csv"
    if not telemetry_path.exists():
        return []

    frame = pandas.read_csv(telemetry_path)
    if frame.empty:
        return []

    time_col = "timestamp" if "timestamp" in frame.columns else frame.columns[0]
    value_cols = [c for c in frame.columns if c != time_col]

    chunks: list[dict[str, Any]] = []
    n_rows = len(frame)
    for chunk_index, start_row in enumerate(range(0, n_rows, chunk_length)):
        end_row = min(start_row + chunk_length, n_rows)
        chunk_df = frame.iloc[start_row:end_row]
        data = chunk_df[value_cols].values.tolist()
        min_max = []
        for c in value_cols:
            col_values = numpy.asarray(chunk_df[c].values, dtype="float64")
            min_max.append(
                [float(col_values.min()), float(col_values.max())]
            )
        array = numpy.array(data, dtype="float64")
        chunks.append(
            {
                "chunk_index": chunk_index,
                "start_time": str(chunk_df.iloc[0][time_col]),
                "end_time": str(chunk_df.iloc[-1][time_col]),
                "columns": value_cols,
                "sample_period": 30.0,  # 30-second sampling for synthetic corpora
                "data": array,
                "min_max": min_max,
            }
        )

    return chunks


def record_atlas_on_run(
    corpus_dir: Path,
    output: Path | None = None,
    topology_path: Path | None = None,
) -> Path:
    """Run Atlas on a generated corpus and write the result as a `.phosrun` file.

    If ``output`` is a directory, writes ``<corpus_name>.phosrun`` inside it. If ``output`` is a
    file path ending in ``.phosrun``, writes there directly. The corpus directory itself is
    never modified.

    Args:
        corpus_dir: Directory containing a generated corpus (telemetry.csv, topology.toml,
            optionally capture.pcap).
        output: Where to write the .phosrun file. Directory or file path.
        topology_path: Optional override path to a topology TOML file.

    Returns:
        The path to the written .phosrun file.
    """
    from phos.runrecord import write_run

    result = atlas_evidence_from_run(corpus_dir, topology_path=topology_path)

    out_path = Path(output) if output else Path.home() / "PHOS_runs" / "dev"
    if out_path.is_dir() or not str(out_path).endswith(".phosrun"):
        out_path = out_path / f"{corpus_dir.name}.phosrun"

    plant = build_plant_descriptor(corpus_dir)
    structure = build_structure(corpus_dir)
    timeline = build_timeline(corpus_dir)
    telemetry_chunks = build_telemetry_chunks(corpus_dir)

    write_run(
        output=out_path,
        kind="simulated",
        title=f"Atlas on {corpus_dir.name}",
        created_by="phos.referee.record 1.0",
        seed_information=None,
        pool="dev",
        model_not_reality_caveat=(
            "This run is on a simulated plant, not a real one. Results describe Atlas's "
            "behaviour on our model of a plant and are not evidence about any real plant."
        ),
        plain_language_summary=(
            f"Atlas run on the simulated plant {corpus_dir.name}; "
            f"{len(cast(list[dict[str, Any]], result.get('alerts', [])))} alerts, "
            f"{len(cast(list[dict[str, Any]], result.get('hypotheses', [])))} hypotheses, "
            f"{len(cast(list[dict[str, Any]], result.get('narratives', [])))} narratives."
        ),
        plant=plant,
        structure=structure,
        timeline=timeline,
        telemetry_chunks=telemetry_chunks,
        labels=[],
        atlas=result,
        scores=None,
        traffic=None,
        thumbnail=None,
    )

    return out_path


__all__ = [
    "atlas_evidence_from_run",
    "build_plant_descriptor",
    "build_structure",
    "build_telemetry_chunks",
    "build_timeline",
    "record_atlas_on_run",
]
