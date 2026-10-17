"""One alert per event, for every detector, from the alerts that detector already published.

The constants are the sandbox values chosen on HAI 20.07 (ADR 0096). They are seconds.
On a one-second grid a 60-second gap is the sandbox's 60-sample gap. On an hourly grid
it is still 60 seconds. This module does not score a corpus and does not add a second
alert at an event's peak.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

FEATURE_GAP_SECONDS: int = 60
EVENT_WINDOW_SECONDS: int = 300
EVENT_SPAN_SECONDS: int = 600
ONSET_FRACTION: float = 0.1
ONSET_LEVEL: float = 2.0
GROUPED_ALERTS_PER_SHIFT: int = 8

_SHIFT_SECONDS = 8 * 3600


@dataclass(frozen=True)
class _Episode:
    """One feature's merged run, scored by its strongest published alert."""

    feature: str
    onset_row: int
    peak: float
    peak_row: int
    points: tuple[tuple[int, float], ...]


def group_published_alerts(
    timestamps: Sequence[datetime],
    cells: Sequence[tuple[int, str, float]],
) -> tuple[tuple[int, str, float], ...]:
    """Return one alert per kept event.

    ``cells`` are ``(row, feature, score)`` from a detector's own published rule.
    Gaps of ``FEATURE_GAP_SECONDS`` on one feature close into an episode. Episode
    onsets within ``EVENT_WINDOW_SECONDS``, spanning at most ``EVENT_SPAN_SECONDS``,
    form one event, scored by its strongest peak. The alert is the earliest point
    in that event that reaches ``max(ONSET_LEVEL, ONSET_FRACTION * peak)`` and is
    not after the peak. Each shift keeps the strongest ``GROUPED_ALERTS_PER_SHIFT``
    events.

    Args:
        timestamps: Row clock. Index ``row`` in a cell must exist here.
        cells: Published alerts. A row the detector did not alert on is absent.

    Returns:
        ``(row, feature, event_score)`` for each kept event, ordered by row.
    """
    if not cells:
        return ()
    _require_rows(timestamps, cells)
    events = _events(_episodes(timestamps, cells), timestamps)
    return _one_per_shift(events, timestamps)


def _require_rows(timestamps: Sequence[datetime], cells: Sequence[tuple[int, str, float]]) -> None:
    limit = len(timestamps)
    for row, _feature, _score in cells:
        if row < 0 or row >= limit:
            raise ValueError(f"alert row {row} is outside a series of {limit} timestamps")


def _episodes(
    timestamps: Sequence[datetime], cells: Sequence[tuple[int, str, float]]
) -> tuple[_Episode, ...]:
    by_feature: dict[str, list[tuple[int, float]]] = {}
    for row, feature, score in cells:
        by_feature.setdefault(feature, []).append((row, score))
    episodes: list[_Episode] = []
    for feature, points in by_feature.items():
        ordered = _merge_same_row(sorted(points))
        chunk: list[tuple[int, float]] = [ordered[0]]
        for row, score in ordered[1:]:
            gap = _seconds(timestamps[row], timestamps[chunk[-1][0]])
            if gap > FEATURE_GAP_SECONDS:
                episodes.append(_episode(feature, chunk))
                chunk = []
            chunk.append((row, score))
        episodes.append(_episode(feature, chunk))
    episodes.sort(
        key=lambda episode: (timestamps[episode.onset_row], episode.onset_row, episode.feature)
    )
    return tuple(episodes)


def _merge_same_row(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    merged: list[tuple[int, float]] = []
    for row, score in points:
        if merged and merged[-1][0] == row:
            merged[-1] = (row, max(merged[-1][1], score))
        else:
            merged.append((row, score))
    return merged


def _episode(feature: str, points: list[tuple[int, float]]) -> _Episode:
    peak_row, peak = points[0]
    for row, score in points[1:]:
        if score > peak:
            peak_row, peak = row, score
    return _Episode(
        feature=feature,
        onset_row=points[0][0],
        peak=peak,
        peak_row=peak_row,
        points=tuple(points),
    )


def _events(episodes: Sequence[_Episode], timestamps: Sequence[datetime]) -> tuple[_Episode, ...]:
    """Each returned episode stands for one event: its onset row, feature and peak."""
    if not episodes:
        return ()
    groups: list[list[_Episode]] = []
    current: list[_Episode] = []
    for episode in episodes:
        if current and _breaks(current, episode, timestamps):
            groups.append(current)
            current = []
        current.append(episode)
    if current:
        groups.append(current)
    return tuple(_place(group) for group in groups)


def _breaks(current: Sequence[_Episode], episode: _Episode, timestamps: Sequence[datetime]) -> bool:
    onset = timestamps[episode.onset_row]
    previous = timestamps[current[-1].onset_row]
    first = timestamps[current[0].onset_row]
    return (
        _seconds(onset, previous) > EVENT_WINDOW_SECONDS
        or _seconds(onset, first) > EVENT_SPAN_SECONDS
    )


def _place(group: Sequence[_Episode]) -> _Episode:
    best = max(group, key=lambda episode: episode.peak)
    level = min(best.peak, max(ONSET_LEVEL, ONSET_FRACTION * best.peak))
    onset_row = best.peak_row
    feature = best.feature
    for episode in group:
        if episode.peak < level or episode.onset_row >= onset_row:
            continue
        for row, score in episode.points:
            if row >= onset_row:
                break
            if score >= level:
                onset_row = row
                feature = episode.feature
                break
    return _Episode(
        feature=feature,
        onset_row=onset_row,
        peak=best.peak,
        peak_row=best.peak_row,
        points=(),
    )


def _one_per_shift(
    events: Sequence[_Episode], timestamps: Sequence[datetime]
) -> tuple[tuple[int, str, float], ...]:
    origin = timestamps[0]
    by_shift: dict[int, list[_Episode]] = {}
    for event in events:
        shift = int(_seconds(timestamps[event.onset_row], origin) // _SHIFT_SECONDS)
        by_shift.setdefault(shift, []).append(event)
    kept: list[tuple[int, str, float]] = []
    for shift in sorted(by_shift):
        chosen = sorted(by_shift[shift], key=lambda event: (-event.peak, event.onset_row))
        kept.extend(
            (event.onset_row, event.feature, event.peak)
            for event in chosen[:GROUPED_ALERTS_PER_SHIFT]
        )
    kept.sort()
    return tuple(kept)


def _seconds(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds()
