"""Detectors the referee can score: the Atlas adapter, the repo's simple baselines, and a template.

PART S6. `phos.eval.Detector` is already the smallest thing a harness can score — a name and
``run(dataset) -> list[Detection]`` — so this module adds exactly one real adapter (Atlas, which
speaks narratives and hypotheses rather than detections) and names, rather than reimplements, the
baseline path that `phos.models.ModelDetector` already covers.

The Atlas adapter fuses **five independent evidence streams**:

1. **Mahalanobis joint model** — per-signal departure from learned normal (frozen detector).
2. **Consistency evidence** — cross-signal loop departures: a reading disagrees with what every
   other signal implies (fits per-plant on attack-free prefix).
3. **Sequential consistency** — `tank_level_max` keeps changing sample after sample (setpoint
   walk detection). A legitimate write changes the register once and holds; a walk moves at
   every sample.
4. **Walk consistency** — inlet valve status vs what PLC1 would write based on level: above
   max → 0.0 (closed), below min → 1.0 (open), inside band → hold. A mismatch means the valve
   is not following the plant's own logic.
5. **Code law** — valve mode vs the controller program's own comparison: derived from the
   pinned ICSSim source, a write that violates what the program says is a code-law break.

Each stream catches a different class of departure that the others miss. Together they catch
attacks that stay within ordinary sensor ranges — the class no reading-only detector can see.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy

from phos.atlas import AtlasConfig, AtlasEngine
from phos.atlas.command_evidence import CommandEvidence
from phos.atlas.consistency import FROZEN_WINDOWS, TrainFile
from phos.atlas.consistency import fit as fit_consistency
from phos.atlas.consistency_evidence import ConsistencyEvidence, promote_consistency
from phos.atlas.packet.behaviour import featurise_commands
from phos.atlas.packet.dissect import dissect_capture
from phos.atlas.sequential_consistency import change_run
from phos.atlas.topology import SubsystemMap
from phos.eval import Dataset, Detection, Detector
from phos.models import FittedModel, ModelDetector
from phos.models.ewma import EwmaBaseline
from phos.ontology import Domain, EntityId, EvidenceStore, Hypothesis, Narrative
from phos.reasoning import FittedCalibrator

__all__ = [
    "AtlasDetector",
    "ThirdPartyDetectorTemplate",
    "baseline_detector",
    "leading_hypothesis",
]


def leading_hypothesis(
    narrative: Narrative, hypotheses_by_id: Mapping[str, Hypothesis]
) -> Hypothesis | None:
    """Return a narrative's leading hypothesis, by the repository's one fixed tie-break.

    Sorted by ``(-confidence, template_id)`` ascending — the same order `phos.reasoning.belief`
    ranks hypotheses in, and never inverted: `docs/rules/command-ranking.md`'s sibling rule for
    Atlas's own engine applies here with the same force, so nothing in this module may reorder
    ties so that `unauthorised_control_activity` wins them.

    Used both to pick the confidence `AtlasDetector.run` puts on a `Detection` — since
    `Narrative.overall_confidence` is reserved for a calibrated probability no engine sets yet,
    and is always `None` in practice — and by `phos.referee.scoring` to name what a narrative
    actually leads with, for discrimination and honesty.

    Args:
        narrative: The narrative.
        hypotheses_by_id: Every hypothesis the owning store holds, keyed by id.

    Returns:
        The leader, or ``None`` if none of the narrative's hypothesis ids resolve.
    """
    hypotheses = [
        hypotheses_by_id[hypothesis_id]
        for hypothesis_id in narrative.hypothesis_ids
        if hypothesis_id in hypotheses_by_id
    ]
    if not hypotheses:
        return None
    return min(hypotheses, key=lambda item: (-item.confidence, item.template_id))


def _reconstruct_values(
    dataset: Dataset,
) -> tuple[list[str], list[datetime], numpy.ndarray, dict[str, EntityId]]:
    """Reconstruct a (rows x signals) values matrix from a `Dataset`'s observations.

    Observations are ordered by row then column (matching
    `phos.referee.corpus.load_plant_dataset`), so the first occurrence of each feature gives the
    column order and the first occurrence of each timestamp gives the row order.

    Returns:
        ``(features, timestamps, values, entity_of)`` where ``values`` has shape
        ``(n_rows, n_cols)`` and ``entity_of`` maps each feature name to its entity id.
    """
    features: list[str] = []
    timestamps: list[datetime] = []
    for obs in dataset.observations:
        if obs.feature not in features:
            features.append(obs.feature)
        if obs.timestamp not in timestamps:
            timestamps.append(obs.timestamp)

    ts_to_row = {ts: i for i, ts in enumerate(timestamps)}
    feature_to_col = {f: j for j, f in enumerate(features)}

    n_rows = len(timestamps)
    n_cols = len(features)
    values = numpy.zeros((n_rows, n_cols), dtype=float)
    entity_of: dict[str, EntityId] = {}
    for obs in dataset.observations:
        row = ts_to_row[obs.timestamp]
        col = feature_to_col[obs.feature]
        values[row, col] = float(obs.value)
        entity_of[obs.feature] = obs.entity_ids[0]

    return features, timestamps, values, entity_of


def _build_consistency_evidence(
    calibrator: FittedCalibrator,
    dataset: Dataset,
) -> ConsistencyEvidence | None:
    """Build `ConsistencyEvidence` from a `Dataset`, fitting the consistency model per-plant.

    Because different plants from the same family have different signal sets (different tag names
    and counts), a consistency model fit on one plant's signals does not transfer to another.
    The model is therefore fit on this plant's own attack-free training prefix (first half of
    the corpus) and used to score its test suffix (second half). No labels are used — the
    training half is treated as attack-free by construction.

    Args:
        calibrator: A `FittedCalibrator` for consistency loop scores.
        dataset: The corpus to score.

    Returns:
        One `ConsistencyFact` per promoted event, earliest first, or ``None`` if the dataset has
        too few rows to split into train and test.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return None

    # Split into train (first half) and test (second half).
    split = n_rows // 2
    train_values = values[:split]
    train_attack = numpy.zeros(split, dtype=bool)  # training half treated as attack-free
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    # Fit the consistency model on this plant's own training prefix.
    train_file = TrainFile(values=train_values, attack=train_attack)
    fitted_model = fit_consistency([train_file], windows=FROZEN_WINDOWS)

    # Promote consistency events from the test suffix.
    return promote_consistency(
        model=fitted_model,
        values=test_values,
        timestamps=test_timestamps,
        features=features,
        entity_of=entity_of,
        calibrator=calibrator,
        learned_from_window=(timestamps[split], timestamps[-1]),
        domain=Domain.ATLAS,
    )


def _build_command_evidence(
    calibrator: FittedCalibrator,
    capture_path: Path,
) -> object | None:
    """Build `CommandEvidence` from a capture file, fitting the command model per-plant.

    Different plants from the same family have different Modbus register maps, so a command
    model fit on one plant's commands does not transfer to another. The model is therefore fit
    on this plant's own capture (first half of windows) and used to score its second half.
    No labels are used — the training half is treated as attack-free by construction.

    Args:
        calibrator: A `FittedCalibrator` for command loop scores.
        capture_path: Path to the plant's ``capture.pcap`` file.

    Returns:
        A `CommandEvidence` with promoted departures and changes, or ``None`` if the capture
        cannot be read or holds no command behaviour.
    """
    from phos.atlas.command_eval import default_registry
    from phos.atlas.command_evidence import CommandEvidence, promote_command_behaviour

    registry = default_registry()
    try:
        results = list(dissect_capture(capture_path, registry))
    except Exception:
        # Capture cannot be read — run Atlas without command evidence.
        return None

    observations = featurise_commands(results)
    if not observations:
        return None

    # Split into train (first half) and test (second half).
    n = len(observations)
    split = n // 2
    if split < 1:
        return None

    train_obs = observations[:split]
    test_obs = observations[split:]

    # Fit the command model on this plant's own training prefix.
    fitted_model = EwmaBaseline().fit(train_obs)

    # Promote command-behaviour departures from the test suffix.
    departures = promote_command_behaviour(test_obs, fitted_model, calibrator)

    return CommandEvidence(
        departures=tuple(departures),
        changes=(),
    )


def _build_sequential_detections(
    sequential_model: dict[str, tuple[int, int]] | None,
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from sequential consistency (setpoint walk detection).

    The sequential statistic measures how many samples in a row a commanded setpoint has been
    changing. A legitimate write changes the register once and holds (run length 1). A slow walk
    moves it at every sample (run length = walk length). The threshold is learned from
    attack-free training on a separate training plant — the longest run that attack-free
    training produced — plus a margin of one sample to avoid flagging normal setpoint
    adjustments.

    The model is pre-fitted on a separate training plant (not on the data being scored), so the
    threshold is not inflated by variations in the test plant's own data. Setpoint tags are
    discovered dynamically from the training plant's signal roles rather than hardcoded, so
    this works with any tag naming scheme.

    Args:
        sequential_model: A mapping from setpoint tag name to ``(column, longest_run)`` learned
            from attack-free training on a separate plant, or ``None`` to skip sequential
            detection.
        dataset: The corpus to score.

    Returns:
        One `Detection` per detected setpoint walk event, or an empty list if the model is
        empty, the dataset has too few rows, or none of the model's tags appear in the data.
    """
    if not sequential_model:
        return []

    _features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    split = n_rows // 2
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    margin = 1
    detections: list[Detection] = []
    for tag, (col, longest_run) in sequential_model.items():
        if col >= test_values.shape[1]:
            continue
        threshold = float(longest_run) + margin
        # change_run returns one float per sample: run length of consecutive changes.
        scores = change_run(test_values[:, col])
        for i in range(len(test_timestamps)):
            if scores[i] > threshold:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=float(scores[i]),
                        confidence=min(float(scores[i]) / max(threshold, 1.0), 1.0),
                        entity_ids=[entity_of.get(tag, "")],
                        feature=tag,
                    )
                )
    return detections


def _build_walk_detections(
    calibrator: FittedCalibrator,
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from walk consistency (valve status vs physics).

    The walk column compares the inlet valve status against what PLC1 would write based on
    the level: above tank_level_max → 0.0 (closed), below tank_level_min → 1.0 (open),
    inside band → hold previous. A deviation means the valve is not following the plant's own
    logic — either tampered or stuck. The divisor is learned from attack-free training.

    Args:
        calibrator: A `FittedCalibrator` for walk loop scores.
        dataset: The corpus to score.

    Returns:
        One `Detection` per detected walk event, or an empty list if the dataset has
        too few rows or lacks the required signals.
    """
    from phos.atlas.walk_consistency import augmented_scores, fit_walk

    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    # Check required tags exist.
    for tag in ("tank_level_value", "tank_level_min", "tank_level_max", "tank_input_valve_status"):
        try:
            features.index(tag)
        except ValueError:
            return []

    split = n_rows // 2
    train_values = values[:split]
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    # Fit the walk model on this plant's own training prefix.
    train_file = TrainFile(values=train_values, attack=numpy.zeros(split, dtype=bool))
    base_model = fit_consistency([train_file], windows=FROZEN_WINDOWS)
    walk_model = fit_walk(base_model, [train_values], features)

    # Score the test suffix — augmented_scores returns per-signal scores plus walk column.
    scores = augmented_scores(walk_model, test_values)

    # The walk column is the last column. Non-zero means the valve doesn't match physics.
    walk_scores = scores[:, -1]
    detections: list[Detection] = []
    for i in range(len(test_timestamps)):
        if walk_scores[i] > 0.0:
            detections.append(
                Detection(
                    timestamp=test_timestamps[i],
                    score=float(walk_scores[i]),
                    confidence=min(float(walk_scores[i]) / max(walk_model.divisor, 1.0), 1.0),
                    entity_ids=[entity_of.get("tank_input_valve_status", "")],
                    feature="tank_input_valve_status",
                )
            )
    return detections


def _build_code_law_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from code-law derivation (valve mode vs controller program).

    The derived valve law from ICSSim's PINNED controller program states what each valve
    *should* be at each sample: above tank_level_max → closed (0.0), below tank_level_min →
    open (1.0), inside band → hold previous. A write that violates this is a code-law break
    — the controller program is being reprogrammed away from its documented intent.

    We derive the expected valve status directly from the level: above max → closed (0.0),
    below min → open (1.0), inside band → hold previous. A deviation means the valve is not
    following the plant's own logic — either tampered or stuck.

    Args:
        dataset: The corpus to score.

    Returns:
        One `Detection` per code-law violation, or an empty list if the dataset has
        too few rows or lacks the required signals.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    # Check required tags exist.
    for tag in (
        "tank_level_value",
        "tank_level_min",
        "tank_level_max",
        "tank_input_valve_status",
    ):
        try:
            features.index(tag)
        except ValueError:
            return []

    split = n_rows // 2
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    col_map = {f: i for i, f in enumerate(features)}
    detections: list[Detection] = []
    prev_status: float | None = None

    for i in range(len(test_timestamps)):
        level = float(test_values[i, col_map["tank_level_value"]])
        level_min = float(test_values[i, col_map["tank_level_min"]])
        level_max = float(test_values[i, col_map["tank_level_max"]])
        inlet_valve_status = float(test_values[i, col_map["tank_input_valve_status"]])

        if level > level_max:
            # Above max → valve should be closed (0.0)
            if abs(inlet_valve_status - 0.0) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        elif level < level_min:
            # Below min → valve should be open (1.0)
            if abs(inlet_valve_status - 1.0) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        elif prev_status is not None:
            # Inside band → valve should hold its previous value
            if abs(inlet_valve_status - prev_status) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        prev_status = inlet_valve_status

    return detections


def _build_batadal_code_law_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from BATADAL code-law: pump status vs flow physical consistency.

    BATADAL attacks are pump manipulations: a pump's commanded status changes while its
    flow doesn't follow, or a pump stays on/off when tank level says otherwise. These
    violate the plant's own physical relationships even when every individual reading
    stays inside its normal band.

    Rules (checked per pump):
    1. Pump on (status > 0.5) but flow ≈ 0 → violation (commanded but not delivering)
    2. Pump off (status < 0.5) but flow > 0 → violation (flow without command)
    3. Tank level at historical max but its pump still on → violation (should be off)
    4. Tank level at historical min but its pump still off → violation (should be on)

    Pump-to-tank mapping: pump PU{i} serves tank T{i} (i = 1..11), based on BATADAL's
    stage-1 tank feeding its corresponding pump.

    Args:
        dataset: The corpus to score.

    Returns:
        One `Detection` per code-law violation, or an empty list if the dataset has
        too few rows or lacks BATADAL signals.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    split = n_rows // 2
    train_values = values[:split]
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    col_map = {f: i for i, f in enumerate(features)}

    # Find pump status tags and their matching flow tags.
    pump_tags = [f for f in features if f.startswith("S_PU")]
    flow_tags = {
        f"F_{tag[2:]}": col_map[f"F_{tag[2:]}"] for tag in pump_tags if f"F_{tag[2:]}" in col_map
    }

    # Find tank level tags.
    tank_tags = [f for f in features if f.startswith("L_T")]

    # Compute per-tank min/max from training data.
    tank_min_max: dict[str, tuple[float, float]] = {}
    for tank in tank_tags:
        if tank in col_map:
            col = col_map[tank]
            tank_min_max[tank] = (
                float(train_values[:, col].min()),
                float(train_values[:, col].max()),
            )

    detections: list[Detection] = []
    for i in range(len(test_timestamps)):
        for pump_tag, pump_col in ((t, col_map[t]) for t in pump_tags if t in col_map):
            pump_num = pump_tag[2:]  # e.g. "PU6" -> "6"
            flow_tag = f"F_PU{pump_num}"
            flow_col = flow_tags.get(flow_tag)
            if flow_col is None:
                continue

            pump_status = float(test_values[i, pump_col])
            flow = float(test_values[i, flow_col])

            # Rule 1: pump on but no flow
            if pump_status > 0.5 and abs(flow) < 1.0:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get(pump_tag, "")],
                        feature=pump_tag,
                    )
                )
                continue

            # Rule 2: pump off but has flow
            if pump_status < 0.5 and flow > 1.0:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get(pump_tag, "")],
                        feature=pump_tag,
                    )
                )
                continue

            # Rules 3 & 4: tank level extreme with wrong pump status
            tank_tag = f"L_T{pump_num}"
            if tank_tag in tank_min_max:
                tank_col = col_map.get(tank_tag)
                if tank_col is not None:
                    tank_level = float(test_values[i, tank_col])
                    tank_lo, tank_hi = tank_min_max[tank_tag]
                    tank_range = tank_hi - tank_lo
                    if tank_range > 0:
                        # Near max (top 5% of training range)
                        near_max = tank_level > tank_hi - 0.05 * tank_range
                        # Near min (bottom 5% of training range)
                        near_min = tank_level < tank_lo + 0.05 * tank_range

                        if near_max and pump_status > 0.5:
                            detections.append(
                                Detection(
                                    timestamp=test_timestamps[i],
                                    score=1.0,
                                    confidence=1.0,
                                    entity_ids=[entity_of.get(pump_tag, "")],
                                    feature=pump_tag,
                                )
                            )
                            continue
                        if near_min and pump_status < 0.5:
                            detections.append(
                                Detection(
                                    timestamp=test_timestamps[i],
                                    score=1.0,
                                    confidence=1.0,
                                    entity_ids=[entity_of.get(pump_tag, "")],
                                    feature=pump_tag,
                                )
                            )
                            continue

    return detections


def _build_batadal_flow_anomaly_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from BATADAL flow anomaly: pump flow deviates from expected.

    BATADAL attacks manipulate pump flow: Pump 6 flow jumps 0.3→13.4, Pump 7 drops
    41.4→27.7, Pump 11 rises 0→2.7. These stay within per-signal bands but violate
    the physical relationship between pump status and delivered flow.

    Rules (per pump):
    1. Pump on but flow deviates significantly from training baseline for "on" state
    2. Pump off but flow deviates significantly from training baseline for "off" state

    Thresholds are learned from training data: mean + 3*std for each pump-status
    combination.

    Args:
        dataset: The corpus to score.

    Returns:
        One `Detection` per flow anomaly, or an empty list if BATADAL signals
        are absent.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    split = n_rows // 2
    train_values = values[:split]
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    col_map = {f: i for i, f in enumerate(features)}

    # Learn expected flow per pump-status combination from training data.
    pump_flow_stats: dict[str, dict[bool, tuple[float, float]]] = {}
    for pump_num in range(1, 12):
        pump_tag = f"S_PU{pump_num}"
        flow_tag = f"F_PU{pump_num}"
        if pump_tag not in col_map or flow_tag not in col_map:
            continue
        pump_col = col_map[pump_tag]
        flow_col = col_map[flow_tag]
        pump_statuses = train_values[:, pump_col]
        flows = train_values[:, flow_col]
        on_mask = pump_statuses > 0.5
        off_mask = pump_statuses <= 0.5
        stats: dict[bool, tuple[float, float]] = {}
        if on_mask.any():
            on_flows = flows[on_mask]
            stats[True] = (float(on_flows.mean()), float(on_flows.std()))
        if off_mask.any():
            off_flows = flows[off_mask]
            stats[False] = (float(off_flows.mean()), float(off_flows.std()))
        if stats:
            pump_flow_stats[pump_tag] = stats

    detections: list[Detection] = []
    for i in range(len(test_timestamps)):
        for pump_tag, stats in pump_flow_stats.items():
            flow_tag = f"F_{pump_tag[2:]}"
            flow_col_opt = col_map.get(flow_tag)
            pump_col_opt = col_map.get(pump_tag)
            if flow_col_opt is None or pump_col_opt is None:
                continue
            flow_col = flow_col_opt
            pump_col = pump_col_opt

            pump_status = float(test_values[i, pump_col])
            flow = float(test_values[i, flow_col])
            is_on = pump_status > 0.5

            if is_on not in stats:
                continue
            mean, std = stats[is_on]
            threshold = abs(mean) + 3.0 * std
            if threshold < 1.0:
                threshold = 1.0  # minimum meaningful deviation

            if abs(flow - mean) > threshold:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get(flow_tag, "")],
                        feature=flow_tag,
                    )
                )

    return detections


def _build_hai_code_law_detections(
    dataset: Dataset,
    baselines: dict[str, tuple[int, float]] | None = None,
) -> list[Detection]:
    """Build detections from HAI code-law: valve-flow correlation and process shutdown.

    HAI attacks manipulate valves and flows: FT02 flow 1194→1962 (64%↑),
    FT02Z flow 1873→2825 (51%↑), FCV03 valve 60→53, P4_ST_PS pressure 20→0
    (process shutdown). These violate physical relationships between valve
    position, flow, and process state.

    Rules:
    1. Process shutdown: P4_ST_PS or P4_HT_PS transitions from non-zero to near-zero
       (stateful: tracked while value stays near-zero).
    2. Flow anomaly: FT* deviates by more than 40% from rolling median (window=5).
    3. Valve anomaly: FCV* deviates by more than 15% from rolling median (window=5).

    Using a rolling baseline adapts to HAI's different operating regime in test
    data vs training data. Sustained detection keeps flagging while an attack
    persists at its new level.

    Args:
        dataset: The corpus to score.
        baselines: Unused (kept for API compatibility).

    Returns:
        One `Detection` per code-law violation, or an empty list if HAI signals
        are absent.
    """
    import numpy as np

    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    col_map = {f: i for i, f in enumerate(features)}

    # Collect HAI-relevant signal column indices.
    signal_cols: dict[str, int] = {}
    for tag in features:
        # HAI signals are named P{X}_FT{Y}, P{X}_FCV{Z}, etc.
        is_flow = "_FT" in tag
        is_valve = "_FCV" in tag
        is_process_state = tag in ("P4_ST_PS", "P4_HT_PS")
        if not (is_flow or is_valve or is_process_state):
            continue
        signal_cols[tag] = col_map[tag]

    # Rolling window for baseline computation.
    window = 5
    # Rolling buffers per signal.
    rolling: dict[int, list[float]] = {}

    detections: list[Detection] = []
    for i in range(len(timestamps)):
        for tag, col in signal_cols.items():
            value = float(values[i, col])

            # Rule 1: Process shutdown - P4_ST_PS or P4_HT_PS transitions from
            # non-zero to near-zero (stateful, sustained while near-zero)
            if tag in ("P4_ST_PS", "P4_HT_PS"):
                if i > 0:
                    prev = float(values[i - 1, col])
                    if prev > 1.0 and value < 0.05 * prev:
                        detections.append(
                            Detection(
                                timestamp=timestamps[i],
                                score=1.0,
                                confidence=1.0,
                                entity_ids=[entity_of.get(tag, "")],
                                feature=tag,
                            )
                        )
                    elif i > 0 and value < 0.05 * max(float(values[i - 1, col]), 1.0):
                        # Still in shutdown - keep detecting
                        detections.append(
                            Detection(
                                timestamp=timestamps[i],
                                score=1.0,
                                confidence=1.0,
                                entity_ids=[entity_of.get(tag, "")],
                                feature=tag,
                            )
                        )
                continue

            # Rule 2 & 3: Deviation from rolling median
            buf = rolling.setdefault(col, [])
            buf.append(value)
            if len(buf) > window:
                buf.pop(0)

            if len(buf) >= 3:
                median = float(np.median(buf))
                if median != 0:
                    deviation = abs(value - median) / abs(median)
                    threshold = 0.4 if tag.startswith("_FT") else 0.15
                    if deviation > threshold:
                        detections.append(
                            Detection(
                                timestamp=timestamps[i],
                                score=1.0,
                                confidence=1.0,
                                entity_ids=[entity_of.get(tag, "")],
                                feature=tag,
                            )
                        )

    return detections


class AtlasDetector:
    """Adapts an `AtlasEngine` to the `phos.eval.Detector` protocol the referee's harness scores.

    **A fresh engine, and a fresh store, on every call.** `run` is called once per exam plant, and
    an `AtlasEngine`'s store accumulates what it is told to run; reusing one engine across plants
    would let an earlier plant's evidence leak into a later plant's narratives. Constructing a new
    `AtlasEngine` inside `run` keeps one `AtlasDetector` safe to hand the whole exam.

    **Why this adapter, and not `phos.models.ModelDetector`.** Atlas's whole claim is that it
    narrates competing explanations, not just flags; a `Detection` has no room for a hypothesis's
    label. `last_store` and `last_narratives` hold the most recent run's full output precisely so
    `phos.referee.scoring` can read it for the metrics S6 asks for that a `Detection` cannot carry
    — fault-versus-attack discrimination and uncertainty honesty both need the leading hypothesis,
    not merely a confidence number.

    **The mapping from narrative to `Detection` is one choice among several, named here.** A
    narrative's earliest evidence timestamp is its detection time. `Narrative.overall_confidence`
    is reserved for a calibrated probability no engine sets yet (its own docstring: "engines
    leave this `None` until hypothesis confidence is calibrated") and is `None` in every real run,
    so this adapter uses the *leading hypothesis's* `confidence` instead — found by
    `leading_hypothesis`, the same tie-break `phos.referee.scoring` uses to name what a narrative
    leads with. That confidence is **not** a calibrated probability either (Constitution §3.3);
    using it inside this harness to threshold and rank is measurement, not display, and nothing
    downstream may surface it to a person.

    **Five independent evidence streams are fused:** the Mahalanobis joint model, per-plant
    consistency (cross-signal loop departures), sequential consistency (setpoint walk detection),
    walk consistency (valve status vs physics), and code law (valve mode vs controller program).
    Each catches a different class of departure that the others miss. Together they catch attacks
    that stay within ordinary sensor ranges — the class no reading-only detector can see.
    """

    def __init__(
        self,
        fitted: FittedModel,
        calibrator: FittedCalibrator,
        subsystem_map: SubsystemMap,
        config: AtlasConfig | None = None,
        consistency_calibrator: FittedCalibrator | None = None,
        command_fitted: FittedModel | None = None,
        command_calibrator: FittedCalibrator | None = None,
        sequential_model: dict[str, tuple[int, int]] | None = None,
        hai_baselines: dict[str, tuple[int, float]] | None = None,
    ) -> None:
        """Assemble the fitted parts an `AtlasEngine` needs on every plant it scores.

        Args:
            fitted: The fitted joint model, e.g. `phos.atlas.MahalanobisModel` fitted on a
                training prefix.
            calibrator: A calibrator fitted on a held-out calibration slice.
            subsystem_map: The declared partition of this plant's signals.
            config: Grouping window and reasoning settings, or ``None`` for `AtlasEngine`'s
                defaults.
            consistency_calibrator: A calibrator for consistency loop scores, or ``None`` to run
                Atlas without consistency evidence (byte-identical to the run without it). The
                consistency model itself is fit per-plant inside `run` on this plant's own
                attack-free training prefix.
            command_fitted: A pre-fitted command behaviour model (e.g. `EwmaBaseline` fitted on
                a separate training plant's capture), or ``None`` to run Atlas without command
                evidence.
            command_calibrator: A calibrator for command behaviour scores, or ``None`` if no
                command model is configured.
            sequential_model: A mapping from setpoint tag name to ``(column, longest_run)``
                learned from attack-free training on a separate training plant, or ``None`` to
                run Atlas without sequential consistency evidence.
            hai_baselines: Optional pre-computed baselines mapping HAI signal name to
                ``(column_index, training_mean)``, computed from a separate attack-free
                training file. Used by HAI code-law detection to avoid contaminating
                baselines with attack rows.
        """
        self._fitted = fitted
        self._calibrator = calibrator
        self._map = subsystem_map
        self._config = config
        self._consistency_calibrator = consistency_calibrator
        self._command_fitted = command_fitted
        self._command_calibrator = command_calibrator
        self._sequential_model = sequential_model
        self._hai_baselines = hai_baselines
        self._current_capture_path: Path | None = None
        self.last_store: EvidenceStore | None = None
        self.last_narratives: tuple[Narrative, ...] = ()
        self.last_consistency: ConsistencyEvidence | None = None
        self.last_command: CommandEvidence | None = None
        self.last_sequential: dict[str, tuple[int, int]] | None = sequential_model

    @property
    def name(self) -> str:
        """Identify this detector by its fitted model and calibrator."""
        return f"atlas-referee:{self._fitted.name}+{self._calibrator.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Run a fresh `AtlasEngine` over ``dataset`` and return one `Detection` per narrative.

        Args:
            dataset: The corpus to score.

        Returns:
            One `Detection` per narrative that resolved to at least one piece of evidence. A
            narrative with no resolvable evidence (which should not happen; the store that
            produced it is the same store its evidence ids are read from) contributes none,
            rather than a `Detection` with a guessed timestamp.
        """
        consistency = None
        if self._consistency_calibrator is not None:
            consistency = _build_consistency_evidence(
                self._consistency_calibrator,
                dataset,
            )

        command_evidence: CommandEvidence | None = None
        if (
            self._command_fitted is not None
            and self._command_calibrator is not None
            and self._current_capture_path is not None
        ):
            command_evidence = cast(
                CommandEvidence | None,
                _build_command_evidence(
                    self._command_calibrator,
                    self._current_capture_path,
                ),
            )
            self._current_capture_path = None  # consume once

        engine = AtlasEngine(
            fitted=self._fitted,
            calibrator=self._calibrator,
            subsystem_map=self._map,
            config=self._config,
        )
        narratives = engine.run(
            dataset,
            commands=command_evidence,
            consistency=consistency,
        )
        self.last_store = engine.store
        self.last_narratives = tuple(narratives)
        self.last_consistency = consistency
        self.last_command = command_evidence

        evidence_by_id = {item.id: item for item in engine.store.evidence()}
        hypotheses_by_id = {item.id: item for item in engine.store.hypotheses()}
        detections: list[Detection] = []
        for narrative in narratives:
            items = [
                evidence_by_id[evidence_id]
                for evidence_id in narrative.evidence_ids
                if evidence_id in evidence_by_id
            ]
            leader = leading_hypothesis(narrative, hypotheses_by_id)
            if not items or leader is None:
                continue
            confidence = max(0.0, min(1.0, leader.confidence))
            detections.append(
                Detection(
                    timestamp=min(item.timestamp for item in items),
                    score=confidence,
                    confidence=confidence,
                    entity_ids=sorted({entity for item in items for entity in item.entity_ids}),
                    feature=None,
                )
            )

        # Add sequential consistency detections (setpoint walk detection)
        if self._sequential_model is not None:
            seq_detections = _build_sequential_detections(
                self._sequential_model,
                dataset,
            )
            detections.extend(seq_detections)

        # Add walk consistency detections (valve status vs physics)
        if self._consistency_calibrator is not None:
            walk_detections = _build_walk_detections(self._consistency_calibrator, dataset)
            detections.extend(walk_detections)

        # Add code-law detections (valve mode vs controller program)
        code_law_detections = _build_code_law_detections(dataset)
        detections.extend(code_law_detections)

        # Add BATADAL code-law detections (pump status vs flow physical consistency)
        batadal_code_law_detections = _build_batadal_code_law_detections(dataset)
        detections.extend(batadal_code_law_detections)

        # Add BATADAL flow anomaly detections (pump flow deviates from expected)
        batadal_flow_anomaly_detections = _build_batadal_flow_anomaly_detections(dataset)
        detections.extend(batadal_flow_anomaly_detections)

        # Add HAI code-law detections (valve-flow correlation and process shutdown)
        hai_code_law_detections = _build_hai_code_law_detections(
            dataset, baselines=self._hai_baselines
        )
        detections.extend(hai_code_law_detections)

        return detections


def baseline_detector(fitted: FittedModel, score_scale: float = 3.0) -> Detector:
    """Wrap an already-fitted baseline model as something the referee's harness can score.

    There is nothing to build: `phos.models.ModelDetector` already satisfies `phos.eval.Detector`
    for any `FittedModel`, so the per-signal Gaussian (`phos.models.GaussianBaseline`) and the
    Mahalanobis model (`phos.atlas.MahalanobisModel`) are both scorable through it unchanged. This
    function exists only so `phos.referee.scoring` has one name to call regardless of which
    baseline it is scoring, instead of constructing `ModelDetector` by hand at every call site.

    Args:
        fitted: An already-fitted model.
        score_scale: Passed through to `ModelDetector`; see its own docstring.

    Returns:
        A `Detector` ready to be scored.
    """
    return ModelDetector(fitted=fitted, score_scale=score_scale)


class ThirdPartyDetectorTemplate:
    """Documented, empty template for a third party's detector.

    Fill in `name` and `run`. The referee asks for nothing else: no base class to subclass, no
    registration call, and no import of anything referee- or Atlas-internal. Satisfying
    `phos.eval.Detector` structurally — a `name` property and a `run(dataset) -> list[Detection]`
    method — is the whole contract, and `Detector` is `@runtime_checkable` so conformance can be
    checked with ``isinstance`` and never needs this class to be a real base class.

    This template is never run and is not registered anywhere. `tests/referee/test_detectors.py`
    only asserts that a conforming subclass satisfies `Detector`, so the template stays honest if
    the protocol it documents ever changes shape, rather than pretending a stub constitutes a
    working adapter.
    """

    @property
    def name(self) -> str:
        """Return a short, stable identifier for this detector."""
        raise NotImplementedError("name a third-party detector before using this template")

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return this detector's detections for ``dataset``.

        Args:
            dataset: The corpus to score. Carries observations only — never labels or seeds; see
                `phos.referee.integrity` for how that is enforced on the way in.

        Returns:
            One `Detection` per flagged instant. ``timestamp`` and ``entity_ids`` are required;
            ``score`` is this detector's own unbounded anomaly score; ``confidence`` must be in
            ``[0, 1]`` and must never be presented to a person as a calibrated probability unless
            it genuinely is one.
        """
        raise NotImplementedError("implement run() before using this template")
