"""Diagnose the HAI 20.07 queue. This is not a ranker.

It loads only ``data/hai-20.07``, fits the frozen champion, and counts three
orderings of that same alert list: the champion's score, one shuffle inside
each shift from ``numpy.random.default_rng(97651)``, and an oracle that
stable-partitions true alerts ahead of benign alerts inside each shift. It
does not add or remove an alert, and it does not open a validation corpus.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy
from numpy.random import Generator
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
# The worktree, not the editable install in the shared venv (that install points at main).
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.measure_baseline_table import (  # noqa: E402
    DECLARED_PERIOD_SECONDS,
    _read_hai,
)

from phos.atlas.consistency import (  # noqa: E402
    THRESHOLD,
    TrainFile,
    feature_components,
    feature_scores,
    fit,
)
from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH  # noqa: E402
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.atlas.grouping import SUBSYSTEM_EVENT_MARKER  # noqa: E402
from phos.atlas.templates import (  # noqa: E402
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    atlas_library,
)
from phos.eval.baseline_alerts import _attack_intervals  # noqa: E402
from phos.eval.baseline_table import SeriesGrid  # noqa: E402
from phos.eval.budget import OPERATOR_SHIFT, recall_within_budget  # noqa: E402
from phos.eval.datasets import Dataset, LabelledInterval  # noqa: E402
from phos.eval.detectors import Detection  # noqa: E402
from phos.eval.metrics import window_recall  # noqa: E402
from phos.eval.queue_rank import AttackRank, AttackSpan, QueueAlert, rank_attacks  # noqa: E402
from phos.ontology import (  # noqa: E402
    Domain,
    Evidence,
    EvidenceKind,
    FacetKind,
    InMemoryEvidenceStore,
    Observation,
)
from phos.reasoning import ReasoningEngine  # noqa: E402
from phos.reasoning.templates import (  # noqa: E402
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    TemplateLibrary,
)

logger = logging.getLogger(__name__)

CORPUS = "hai-20.07"
RANDOM_SEED = 97651
ALERTS_PER_SHIFT = 8
DIRECTORY = ROOT / "data" / CORPUS
TRAINS = ("train1.csv.gz", "train2.csv.gz")
TESTS = ("test1.csv.gz", "test2.csv.gz")
OUT = ROOT / "eval_runs" / "build" / "d" / "queue" / "diagnosis.json"
FORBIDDEN = ("hai-21", "hai-22", "hai-23", "batadal")
INNOCENT = frozenset(
    {
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        PROCESS_DISTURBANCE_TEMPLATE_ID,
    }
)
_LIBRARY: TemplateLibrary = atlas_library()
_Float32 = NDArray[numpy.float32]


@dataclass(frozen=True)
class DiagAlert:
    """One champion alert, with the facts the taxonomy reads off it."""

    input_order: int
    timestamp: datetime
    champion_score: float
    onset_signal: str
    onset_unit: str
    member_columns: tuple[str, ...]
    member_units: tuple[str, ...]
    is_true: bool
    witness_disagreement: bool
    moved_together: bool
    familiar: bool
    onset_seen_in_training: bool
    members_seen_in_training: int
    strong_innocent: tuple[str, ...]
    lead: str

    @property
    def column_set(self) -> frozenset[str]:
        """The member columns, ignoring order."""
        return frozenset(self.member_columns)

    @property
    def shape(self) -> str:
        """Witness disagreement, a broad co-movement, or a small range departure."""
        if self.witness_disagreement:
            return "witness"
        if self.moved_together:
            return "together"
        return "local_range"


@dataclass(frozen=True)
class FileAlerts:
    """One test file's alerts, attack windows, and shift origin."""

    name: str
    origin: datetime
    spans: tuple[AttackSpan, ...]
    intervals: tuple[LabelledInterval, ...]
    alerts: tuple[DiagAlert, ...]


def main() -> None:
    """Fit HAI 20.07, write the three orderings and the blocking-alert taxonomy."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # The belief update logs uncalibrated confidences. This diagnosis does not report them.
    logging.getLogger("phos.reasoning").setLevel(logging.ERROR)
    _refuse_forbidden(DIRECTORY)
    period = DECLARED_PERIOD_SECONDS[CORPUS]
    windows = windows_for_period(period)
    trains = tuple(_load(name) for name in TRAINS)
    if len({grid.features for grid in trains}) != 1:
        raise SystemExit("HAI 20.07 training files do not share one column set")
    logger.info("fitting %s", CORPUS)
    model = fit(
        [
            TrainFile(values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_))
            for grid in trains
        ],
        windows,
    )
    familiar = _training_column_sets(model, trains)
    del trains
    seen = frozenset().union(*familiar) if familiar else frozenset()
    files = tuple(_score_file(name, model, familiar, seen) for name in TESTS)
    generator = numpy.random.default_rng(RANDOM_SEED)
    random_scores = {file.name: _random_scores(file, generator) for file in files}
    oracle_scores = {file.name: _oracle_scores(file) for file in files}
    champion_scores = {file.name: _champion_scores(file) for file in files}
    champion = _score_order(files, champion_scores)
    random_order = _score_order(files, random_scores)
    oracle = _score_order(files, oracle_scores)
    _check_recall(files)
    payload = {
        "corpus": CORPUS,
        "detector": "atlas-v1-consistency",
        "random_seed": RANDOM_SEED,
        "recorded_champion_passes": 19,
        "recorded_attacks": 38,
        "champion_reproduced": champion["passes"] == 19 and champion["attacks"] == 38,
        "training_normal_column_sets": len(familiar),
        "a3": {"champion": champion, "random": random_order, "oracle": oracle},
        "recall_within_8": {
            "champion": _recall(files, champion_scores),
            "random": _recall(files, random_scores),
            "oracle": _recall(files, oracle_scores),
        },
        "taxonomy": _taxonomy(files),
        "queues": _queues(files),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "champion %s/%s reproduced=%s random %s/%s oracle %s/%s",
        champion["passes"],
        champion["attacks"],
        payload["champion_reproduced"],
        random_order["passes"],
        random_order["attacks"],
        oracle["passes"],
        oracle["attacks"],
    )
    logger.info("wrote %s", OUT)


def _refuse_forbidden(path: Path) -> None:
    text = str(path)
    if any(token in text for token in FORBIDDEN):
        raise SystemExit(f"refusing to open {path}")


def _load(name: str) -> SeriesGrid:
    path = DIRECTORY / name
    _refuse_forbidden(path)
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    grid = _read_hai(path, ";")
    if not grid.timestamps or grid.timestamps[0].tzinfo is None:
        raise SystemExit(f"{name} has no timezone-aware clock")
    return grid


def _training_column_sets(model: object, trains: Sequence[SeriesGrid]) -> frozenset[frozenset[str]]:
    from phos.atlas.consistency import ConsistencyEvent

    found: set[frozenset[str]] = set()
    for grid in trains:
        for event in events_typed(model, grid):
            if not isinstance(event, ConsistencyEvent):
                raise TypeError("expected a ConsistencyEvent")
            if bool(grid.attack[event.onset]):
                continue
            found.add(frozenset(grid.features[member[4]] for member in event.members))
    logger.info("training-normal column sets: %d", len(found))
    return frozenset(found)


def _score_file(
    name: str,
    model: object,
    familiar: frozenset[frozenset[str]],
    seen: frozenset[str],
) -> FileAlerts:
    from phos.atlas.consistency import ConsistencyModel

    grid = _load(name)
    if not isinstance(model, ConsistencyModel):
        raise TypeError("diagnosis scores only a ConsistencyModel")
    loop, rng = feature_components(model, grid.values)
    found = events_typed(model, grid)
    intervals = tuple(_attack_intervals(grid))
    spans = tuple(
        AttackSpan(f"{name}#{index}", interval.start, interval.end)
        for index, interval in enumerate(intervals)
    )
    alerts = tuple(
        _alert(order, event, grid, loop, rng, intervals, familiar, seen)
        for order, event in enumerate(found)
    )
    logger.info("%s alerts=%d attacks=%d", name, len(alerts), len(spans))
    return FileAlerts(name, grid.timestamps[0], spans, intervals, alerts)


def events_typed(model: object, grid: SeriesGrid) -> list[object]:
    """Typed wrapper so the event list stays a list of consistency events."""
    from phos.atlas.consistency import ConsistencyModel, events

    if not isinstance(model, ConsistencyModel):
        raise TypeError("diagnosis scores only a ConsistencyModel")
    return list(events(feature_scores(model, grid.values), windows=model.windows))


def _alert(
    order: int,
    event: object,
    grid: SeriesGrid,
    loop: _Float32,
    rng: _Float32,
    intervals: Sequence[LabelledInterval],
    familiar: frozenset[frozenset[str]],
    seen: frozenset[str],
) -> DiagAlert:
    from phos.atlas.consistency import ConsistencyEvent

    if not isinstance(event, ConsistencyEvent):
        raise TypeError("expected a ConsistencyEvent")
    columns = tuple(sorted({grid.features[member[4]] for member in event.members}))
    units = tuple(sorted({_unit(column) for column in columns}))
    onset_signal = grid.features[event.column]
    loop_score = float(loop[event.onset, event.column])
    range_score = float(rng[event.onset, event.column])
    witness = loop_score > THRESHOLD and loop_score >= range_score
    stamp = grid.timestamps[event.onset]
    column_set = frozenset(columns)
    lead, strong = _explanation(stamp, columns, onset_signal, witness)
    return DiagAlert(
        input_order=order,
        timestamp=stamp,
        champion_score=float(event.score),
        onset_signal=onset_signal,
        onset_unit=_unit(onset_signal),
        member_columns=columns,
        member_units=units,
        is_true=any(interval.contains(stamp) for interval in intervals),
        witness_disagreement=witness,
        moved_together=len(columns) >= 3 and not witness,
        familiar=column_set in familiar,
        onset_seen_in_training=onset_signal in seen,
        members_seen_in_training=sum(1 for column in columns if column in seen),
        strong_innocent=strong,
        lead=lead,
    )


def _unit(column: str) -> str:
    return column.split("_", 1)[0]


_EXPLAIN_CACHE: dict[tuple[tuple[str, ...], str, bool], tuple[str, tuple[str, ...]]] = {}


def _explanation(
    stamp: datetime, columns: Sequence[str], onset_signal: str, witness: bool
) -> tuple[str, tuple[str, ...]]:
    """Return the lead template and the innocent templates this alert supports cleanly.

    Each fact is weighed at weight 1. That is a structural probe of which
    explanations the evidence shape supports. It is not a calibrated confidence,
    and this function does not return a confidence. The same column set and
    witness flag always produce the same set, so the probe is cached.
    """
    key = (tuple(columns), onset_signal, witness)
    cached = _EXPLAIN_CACHE.get(key)
    if cached is not None:
        return cached
    facts = [
        Evidence(
            kind=EvidenceKind.DEVIATION,
            source_id=f"{SUBSYSTEM_EVENT_MARKER}diagnosis",
            entity_ids=list(columns),
            timestamp=stamp,
            domain=Domain.ATLAS,
            weight=1.0,
            summary="diagnosis breadth",
        )
    ]
    if witness:
        facts.append(
            Evidence(
                kind=EvidenceKind.DEVIATION,
                source_id="diagnosis-consistency",
                entity_ids=[onset_signal],
                timestamp=stamp,
                domain=Domain.ATLAS,
                weight=1.0,
                summary="diagnosis cross-signal mismatch",
                facet_kind=FacetKind.CONSISTENCY,
                facet=CROSS_SIGNAL_MISMATCH,
            )
        )
    engine = ReasoningEngine(_LIBRARY, InMemoryEvidenceStore())
    engine.ingest(facts)
    ranked = engine.competing(Domain.ATLAS)
    lead = ranked[0].template_id if ranked else INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    strong = tuple(
        sorted(
            hypothesis.template_id
            for hypothesis in ranked
            if hypothesis.template_id in INNOCENT
            and hypothesis.supporting
            and not hypothesis.contradictory
        )
    )
    _EXPLAIN_CACHE[key] = (lead, strong)
    return lead, strong


def _by_shift(alerts: Sequence[DiagAlert], origin: datetime) -> dict[int, tuple[DiagAlert, ...]]:
    grouped: dict[int, list[DiagAlert]] = {}
    for alert in alerts:
        grouped.setdefault(_shift_index(alert.timestamp, origin), []).append(alert)
    return {index: tuple(group) for index, group in grouped.items()}


def _shift_index(stamp: datetime, origin: datetime) -> int:
    return (stamp - origin) // OPERATOR_SHIFT


def _champion_scores(file: FileAlerts) -> dict[int, float]:
    return {alert.input_order: alert.champion_score for alert in file.alerts}


def _random_scores(file: FileAlerts, generator: Generator) -> dict[int, float]:
    """Shuffle detector order inside each shift. One generator, shifts in index order."""
    scores: dict[int, float] = {}
    for index in sorted(_by_shift(file.alerts, file.origin)):
        group = list(_by_shift(file.alerts, file.origin)[index])
        group.sort(key=lambda alert: alert.input_order)
        order = numpy.arange(len(group), dtype=numpy.int64)
        generator.shuffle(order)
        shuffled = [group[int(item)] for item in order.tolist()]
        scores.update(_descending(shuffled))
    return scores


def _oracle_scores(file: FileAlerts) -> dict[int, float]:
    """Stable-partition the champion order: true alerts, then benign alerts."""
    scores: dict[int, float] = {}
    for group in _by_shift(file.alerts, file.origin).values():
        ordered = sorted(
            group,
            key=lambda alert: (-alert.champion_score, alert.timestamp, alert.input_order),
        )
        partitioned = [alert for alert in ordered if alert.is_true] + [
            alert for alert in ordered if not alert.is_true
        ]
        scores.update(_descending(partitioned))
    return scores


def _descending(ordered: Sequence[DiagAlert]) -> dict[int, float]:
    count = len(ordered)
    return {alert.input_order: float(count - position) for position, alert in enumerate(ordered)}


def _score_order(
    files: Sequence[FileAlerts], scores: Mapping[str, Mapping[int, float]]
) -> dict[str, object]:
    ranks: list[dict[str, object]] = []
    for file in files:
        file_scores = scores[file.name]
        alerts = [
            QueueAlert(alert.timestamp, float(file_scores[alert.input_order]), alert.input_order)
            for alert in file.alerts
        ]
        for rank in rank_attacks(alerts, file.spans, origin=file.origin):
            ranks.append(_rank_row(file.name, rank))
    passes = sum(1 for rank in ranks if rank["passed"] is True)
    return {"passes": passes, "attacks": len(ranks), "ranks": ranks}


def _rank_row(name: str, rank: AttackRank) -> dict[str, object]:
    return {
        "id": rank.attack_id,
        "file": name,
        "passed": rank.passed,
        "rank": rank.rank,
        "queue_length": rank.queue_length,
        "top_slots": rank.top_slots,
        "shift_index": rank.shift_index,
    }


def _recall(
    files: Sequence[FileAlerts], scores: Mapping[str, Mapping[int, float]]
) -> dict[str, object]:
    caught = 0
    attacks = 0
    for file in files:
        kept = _keep(file, scores[file.name])
        attacks += len(file.intervals)
        caught += sum(
            1
            for interval in file.intervals
            if any(interval.start <= alert.timestamp <= interval.end for alert in kept)
        )
    return {
        "caught": caught,
        "attacks": attacks,
        "recall": 0.0 if attacks == 0 else caught / attacks,
    }


def _keep(file: FileAlerts, scores: Mapping[int, float]) -> tuple[Detection, ...]:
    grouped: dict[int, list[tuple[int, Detection]]] = {}
    for alert in file.alerts:
        detection = Detection(
            timestamp=alert.timestamp,
            score=float(scores[alert.input_order]),
            confidence=0.0,
            entity_ids=["diagnosis"],
            feature=alert.onset_signal,
        )
        grouped.setdefault(_shift_index(alert.timestamp, file.origin), []).append(
            (alert.input_order, detection)
        )
    kept: list[Detection] = []
    for group in grouped.values():
        group.sort(key=lambda item: (-item[1].score, item[1].timestamp, item[0]))
        kept.extend(detection for _, detection in group[:ALERTS_PER_SHIFT])
    return tuple(kept)


def _check_recall(files: Sequence[FileAlerts]) -> None:
    """The hand-rolled keep must match ``recall_within_budget`` on the champion scores."""
    for file in files:
        detections = [
            Detection(
                timestamp=alert.timestamp,
                score=alert.champion_score,
                confidence=0.0,
                entity_ids=["diagnosis"],
                feature=alert.onset_signal,
            )
            for alert in file.alerts
        ]
        dataset = Dataset(
            name=file.name,
            domain=Domain.ATLAS,
            observations=[
                Observation(
                    entity_ids=["diagnosis"],
                    feature="clock",
                    value=0.0,
                    timestamp=file.origin,
                    domain=Domain.ATLAS,
                )
            ],
            attack_intervals=list(file.intervals),
            source_note="hai-20.07 queue diagnosis clock",
        )
        official = recall_within_budget(detections, dataset, ALERTS_PER_SHIFT)
        kept = _keep(file, _champion_scores(file))
        mine = window_recall(kept, file.intervals)
        if official != mine:
            raise SystemExit(f"{file.name} recall {mine} does not match the harness {official}")


def _queues(files: Sequence[FileAlerts]) -> list[dict[str, object]]:
    """Champion order of every alert. Positions are 1-based inside the shift."""
    rows: list[dict[str, object]] = []
    for file in files:
        for shift, group in sorted(_by_shift(file.alerts, file.origin).items()):
            ordered = sorted(
                group,
                key=lambda alert: (-alert.champion_score, alert.timestamp, alert.input_order),
            )
            for position, alert in enumerate(ordered, start=1):
                rows.append(
                    {
                        "file": file.name,
                        "shift": shift,
                        "position": position,
                        "true": alert.is_true,
                        "signal": alert.onset_signal,
                        "unit": alert.onset_unit,
                        "members": len(alert.member_columns),
                        "shape": alert.shape,
                        "familiar": alert.familiar,
                        "onset_seen_in_training": alert.onset_seen_in_training,
                        "members_seen_in_training": alert.members_seen_in_training,
                        "strong": list(alert.strong_innocent),
                        "lead": alert.lead,
                    }
                )
    return rows


def _taxonomy(files: Sequence[FileAlerts]) -> dict[str, object]:
    blocking: list[DiagAlert] = []
    outranked_true: list[DiagAlert] = []
    all_true: list[DiagAlert] = []
    all_benign: list[DiagAlert] = []
    for file in files:
        all_true.extend(alert for alert in file.alerts if alert.is_true)
        all_benign.extend(alert for alert in file.alerts if not alert.is_true)
        for group in _by_shift(file.alerts, file.origin).values():
            ordered = sorted(
                group, key=lambda alert: (-alert.champion_score, alert.timestamp, alert.input_order)
            )
            last_true = max(
                (index for index, alert in enumerate(ordered) if alert.is_true),
                default=-1,
            )
            if last_true < 0:
                continue
            blocking.extend(alert for alert in ordered[:last_true] if not alert.is_true)
            seen_benign = False
            for alert in ordered:
                if not alert.is_true:
                    seen_benign = True
                elif seen_benign:
                    outranked_true.append(alert)
    return {
        "blocking_benign": _bucket(blocking),
        "outranked_true": _bucket(outranked_true),
        "all_true": _bucket(all_true),
        "all_benign": _bucket(all_benign),
    }


def _bucket(alerts: Sequence[DiagAlert]) -> dict[str, object]:
    units: Counter[str] = Counter(alert.onset_unit for alert in alerts)
    signals: Counter[str] = Counter(alert.onset_signal for alert in alerts)
    sets: Counter[str] = Counter(",".join(alert.member_columns) for alert in alerts)
    leads: Counter[str] = Counter(alert.lead for alert in alerts)
    strong_names: Counter[str] = Counter(name for alert in alerts for name in alert.strong_innocent)
    cells: Counter[str] = Counter(
        f"{alert.shape}|familiar={alert.familiar}|strong={bool(alert.strong_innocent)}"
        for alert in alerts
    )
    return {
        "count": len(alerts),
        "familiar": sum(1 for alert in alerts if alert.familiar),
        "onset_seen_in_training": sum(1 for alert in alerts if alert.onset_seen_in_training),
        "strong_innocent": sum(1 for alert in alerts if alert.strong_innocent),
        "witness": sum(1 for alert in alerts if alert.witness_disagreement),
        "together": sum(1 for alert in alerts if alert.moved_together),
        "local_range": sum(1 for alert in alerts if alert.shape == "local_range"),
        "onset_units": dict(units.most_common()),
        "onset_signals": dict(signals.most_common(20)),
        "member_sets": dict(sets.most_common(15)),
        "leads": dict(leads),
        "strong_templates": dict(strong_names),
        "cells": dict(cells),
    }


if __name__ == "__main__":
    main()
