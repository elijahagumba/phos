"""Declared operating modes for Kelmarsh, scored with the frozen detector (ADR 0166).

Idle, curtailment, startup, shutdown, and running are labels on the five
signals. Each contiguous run is handed to ``phos.atlas.consistency.detect``.
That function is not edited. A one-row run is skipped because lag 1 needs a
neighbour.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import SHIFT_SECONDS, ScoredFile, TrainFile, detect
from phos.atlas.consistency_windows import Windows, windows_for_period
from phos.eval.kelmarsh_log import (
    KELMARSH_CAVEAT,
    KELMARSH_CITATION,
    OK_SERVICE,
    SAMPLE_SECONDS,
    SIGNAL_COLUMNS,
    KelmarshReport,
    StatusSpan,
    TurbineLogScore,
    TurbineSlice,
    merged_explaining,
    time_is_explained,
)

__all__ = [
    "CURTAIL_PITCH_DEG",
    "CURTAIL_POWER_KW",
    "CURTAIL_WIND_MS",
    "IDLE_POWER_KW",
    "IDLE_ROTOR_RPM",
    "MODE_RESULT",
    "TRANSITION_SAMPLES",
    "label_modes",
    "score_modes",
]

IDLE_POWER_KW: float = 0.0
IDLE_ROTOR_RPM: float = 1.0
CURTAIL_PITCH_DEG: float = 5.0
CURTAIL_WIND_MS: float = 6.0
CURTAIL_POWER_KW: float = 1800.0
TRANSITION_SAMPLES: int = 3
MODE_RESULT: str = "lane-b-dev:kelmarsh-modes"

_IDLE = 0
_RUNNING = 1
_CURTAIL = 2
_STARTUP = 3
_SHUTDOWN = 4
_POWER = 1
_ROTOR = 2
_WIND = 0
_PITCH = 4


def label_modes(values: NDArray[numpy.float64]) -> NDArray[numpy.int8]:
    """Return one declared mode code per row.

    Args:
        values: Shape ``(n, 5)`` in `SIGNAL_COLUMNS` order.

    Returns:
        Codes: idle 0, running 1, curtailment 2, startup 3, shutdown 4.

    Raises:
        ValueError: If ``values`` is not five columns.
    """
    if values.ndim != 2 or values.shape[1] != 5:
        raise ValueError(f"expected (n, 5) signals, got {values.shape}")
    n = values.shape[0]
    labels = numpy.full(n, _RUNNING, dtype=numpy.int8)
    if n == 0:
        return labels
    idle = (values[:, _POWER] <= IDLE_POWER_KW) & (values[:, _ROTOR] < IDLE_ROTOR_RPM)
    curtail = (
        ~idle
        & (values[:, _PITCH] >= CURTAIL_PITCH_DEG)
        & (values[:, _WIND] >= CURTAIL_WIND_MS)
        & (values[:, _POWER] < CURTAIL_POWER_KW)
    )
    labels[idle] = _IDLE
    labels[curtail] = _CURTAIL
    if n == 1:
        return labels
    leave = numpy.flatnonzero(idle[:-1] & ~idle[1:])
    enter = numpy.flatnonzero(~idle[:-1] & idle[1:])
    for index in leave:
        stop = min(n, int(index) + 1 + TRANSITION_SAMPLES)
        for row in range(int(index) + 1, stop):
            if labels[row] != _IDLE:
                labels[row] = _STARTUP
    for index in enter:
        start = max(0, int(index) + 1 - TRANSITION_SAMPLES)
        for row in range(start, int(index) + 1):
            if labels[row] not in (_IDLE, _STARTUP):
                labels[row] = _SHUTDOWN
    return labels


def _runs(labels: NDArray[numpy.int8]) -> list[tuple[int, int, int]]:
    """Return ``(mode, start, end)`` for runs longer than one row."""
    found: list[tuple[int, int, int]] = []
    start = 0
    n = int(labels.shape[0])
    for index in range(1, n + 1):
        if index == n or labels[index] != labels[start]:
            if index - start > 1:
                found.append((int(labels[start]), start, index))
            start = index
    return found


def score_modes(
    trains: Mapping[str, TurbineSlice],
    tests: Mapping[str, TurbineSlice],
    spans: Sequence[StatusSpan],
    *,
    turbines: Sequence[str],
) -> KelmarshReport:
    """Score each declared mode with the frozen detector and the status log.

    Args:
        trains: One 2018 slice per turbine.
        tests: One 2019-2022 slice per turbine.
        spans: Status intervals from the scored zips.
        turbines: Turbines that must all be present.

    Returns:
        The same report shape as the pooled log score, under `MODE_RESULT`.

    Raises:
        IncompleteFarmError: If a turbine slice is missing.
    """
    from phos.eval.kelmarsh_log import IncompleteFarmError

    windows = windows_for_period(SAMPLE_SECONDS)
    missing = [name for name in turbines if name not in trains or name not in tests]
    if missing:
        raise IncompleteFarmError(f"missing train or score for {missing}")
    rows: list[TurbineLogScore] = []
    for name in turbines:
        rows.append(_score_one(name, trains[name], tests[name], spans, windows))
    alerts = sum(item.alerts for item in rows)
    explained = sum(item.explained_alerts for item in rows)
    unexplained = sum(item.unexplained_alerts for item in rows)
    scored_seconds = sum(item.scored_seconds for item in rows)
    shifts = scored_seconds / SHIFT_SECONDS
    return KelmarshReport(
        measured=True,
        detector=MODE_RESULT,
        sample_seconds=SAMPLE_SECONDS,
        windows_lags=windows.lags,
        detrend_window_samples=windows.detrend_window,
        signals=SIGNAL_COLUMNS,
        ok_service=OK_SERVICE,
        turbines=tuple(rows),
        alerts=alerts,
        explained_alerts=explained,
        unexplained_alerts=unexplained,
        explained_share=(explained / alerts) if alerts else None,
        scored_seconds=scored_seconds,
        shifts=shifts,
        false_alerts_per_shift=(unexplained / shifts) if shifts else None,
        caveat=KELMARSH_CAVEAT,
        citation=KELMARSH_CITATION,
    )


def _score_one(
    name: str,
    train: TurbineSlice,
    test: TurbineSlice,
    spans: Sequence[StatusSpan],
    windows: Windows,
) -> TurbineLogScore:
    train_labels = label_modes(train.values)
    test_labels = label_modes(test.values)
    train_runs: dict[int, list[TrainFile]] = defaultdict(list)
    for mode, start, end in _runs(train_labels):
        chunk = train.values[start:end]
        flags = numpy.zeros(chunk.shape[0], dtype=numpy.bool_)
        train_runs[mode].append(TrainFile(values=chunk, attack=flags))
    alert_rows: set[int] = set()
    for mode, files in train_runs.items():
        scored: list[ScoredFile] = []
        maps: list[NDArray[numpy.int64]] = []
        for test_mode, start, end in _runs(test_labels):
            if test_mode != mode:
                continue
            scored.append(
                ScoredFile(
                    time=test.time[start:end].astype(numpy.float64),
                    values=test.values[start:end],
                )
            )
            maps.append(numpy.arange(start, end, dtype=numpy.int64))
        if not scored:
            continue
        found = detect(files, scored, windows)
        for (rows, _columns, _scores), index_map in zip(found, maps, strict=True):
            for row in rows:
                alert_rows.add(int(index_map[int(row)]))
    merged = merged_explaining(spans, name)
    explained = sum(1 for row in alert_rows if time_is_explained(int(test.time[row]), merged))
    alerts = len(alert_rows)
    unexplained = alerts - explained
    scored_seconds = float(test.time[-1] - test.time[0]) if test.time.shape[0] > 1 else 0.0
    shifts = scored_seconds / SHIFT_SECONDS
    return TurbineLogScore(
        turbine=name,
        train_rows=int(train.values.shape[0]),
        score_rows=int(test.values.shape[0]),
        dropped_missing=train.dropped_missing + test.dropped_missing,
        clock_gaps=train.clock_gaps + test.clock_gaps,
        duplicate_times=train.duplicate_times + test.duplicate_times,
        alerts=alerts,
        explained_alerts=explained,
        unexplained_alerts=unexplained,
        scored_seconds=scored_seconds,
        shifts=shifts,
        false_alerts_per_shift=(unexplained / shifts) if shifts else None,
    )
