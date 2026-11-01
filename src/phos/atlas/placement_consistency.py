"""Place an alert at the first sample the group can point at, not one its strongest member allows.

Half A of ADR 0397, declared in ADR 0398. `phos.atlas.drift_consistency` accumulates a persistent
small departure and, fed through the frozen `phos.atlas.consistency.events`, catches **53 of 70**
attacks against the frozen engine's 32 on `phos-icssim-dev2` without losing one — and is refused
anyway, because its median detection delay is worse at every setting of its own cap (ADR 0286).
ADR 0286 says in terms that this is a property of the **placement rule**, not of the statistic.

**The defect, stated once.** `events` takes a group's highest-peak member as ``best``, computes
``level = min(best_peak, max(ONSET_LEVEL, ONSET_FRACTION * best_peak))``, and moves the alert
earlier only to a member whose *own peak* reaches that level. A member below the level is skipped
outright and cannot place the alert at all. Alone, any episode qualifies against itself, because
``level`` is clamped by ``min(best_peak, …)``. So an episode with a peak between `THRESHOLD` and
`ONSET_LEVEL` — a replay that departs sharply and briefly, say — places its own early alert until a
saturated accumulator column joins its group, and then loses the right to. On a saturated budget the
strong column is the one that wins the slot, so the alert is moved to *its* later crossing. That is
the trade ADR 0286 measured across lane 3's whole cap sweep.

**This module's rule.** The bar an episode already cleared to exist — `THRESHOLD` — is the bar that
lets it place the alert. For each group, in the frozen grouping order and with the frozen grouping
boundaries:

* the event's **score** is still its strongest member's peak, so the budget ranks the same events
  onto the same slots;
* the event's **placement** is the earliest sample at or after any member's start where that
  member's own column is at or above `THRESHOLD`, ties going to the earlier start and then the
  lower column index;
* **no level is computed from the group's peak**, which is the whole of the change.

It is called `earliest_threshold_crossing` and not "delay-aware" or "priority" on purpose. It makes
one choice — the first sample the group can point at — and it has no constant of its own to tune.

**What it does not do.** It does not edit `phos.atlas.consistency`: `events`, `budget_alerts`,
`THRESHOLD`, `ONSET_LEVEL`, `ONSET_FRACTION`, `ALERTS_PER_SHIFT`, `SHIFT_SECONDS` and the detrend
window are imported and consumed, never written. It does not edit `phos.atlas.drift_consistency` and
does not name its cap: the harness passes the augmented matrix in, so this rule is a function of a
score matrix and nothing else. The accumulator columns keep their own indices beside the per-signal
ones, so an alert still names one signal and `phos.atlas.consistency_evidence` can still attribute
it to an `ExpectedRange`.

Result name for anything this module scores: ``atlas-placement-consistency``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    THRESHOLD,
    ConsistencyEvent,
    ConsistencyModel,
    _all_episodes,
    budget_alerts,
    feature_scores,
)
from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows

__all__ = [
    "RESULT_NAME",
    "detect_with_placement",
    "earliest_crossing_events",
]

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]

#: The result name every score from this module carries.
RESULT_NAME: Final = "atlas-placement-consistency"

#: One member episode, as `phos.atlas.consistency._all_episodes` returns it.
_Member = tuple[int, int, float, int, int]


def _groups(scores: _Float32, threshold: float, windows: Windows) -> list[list[_Member]]:
    """Chain per-signal episodes into groups, on the frozen rule's own boundaries.

    The grouping is `phos.atlas.consistency.events`'s, reproduced rather than re-invented: a member
    joins the open group unless its onset is more than ``event_window`` past the previous member's
    onset or more than ``event_span`` past the group's first onset. A change to the boundaries
    would be a different rule, and this function is not the place for one.

    Args:
        scores: Rows by signals, as `phos.atlas.consistency.feature_scores` returns them.
        threshold: A score above this opens an episode.
        windows: The model's windows, for the episode gap and the two event bounds.

    Returns:
        One group per event, each a list of member episodes in onset order.
    """
    groups: list[list[_Member]] = []
    current: list[_Member] = []
    last = 0
    for episode in _all_episodes(scores, threshold, windows.feature_gap):
        if current and (
            episode[0] - last > windows.event_window
            or episode[0] - current[0][0] > windows.event_span
        ):
            groups.append(current)
            current = []
        current.append(episode)
        last = episode[0]
    if current:
        groups.append(current)
    return groups


def _crossing(scores: _Float32, members: Sequence[_Member], threshold: float) -> tuple[int, int]:
    """The earliest ``(row, column)`` at which any member of the group is above the threshold.

    Every member qualifies: an episode exists only because its column crossed the threshold, so the
    only question the rule asks is which member crosses first. Ties go to the member that started
    earlier, and then to the lower column index, so the answer does not depend on iteration order.

    Args:
        scores: Rows by signals, the matrix the group was cut from.
        members: The group's member episodes.
        threshold: The threshold the episodes were cut at.

    Returns:
        The row and column the alert goes at.

    Raises:
        ValueError: If the group is empty, which the caller cannot produce but a direct call could.
    """
    if not members:
        raise ValueError("a placement needs at least one member episode")
    best_row = -1
    best_column = -1
    for start, end, _peak, _at, _column in sorted(members, key=lambda m: (m[0], m[4])):
        hit = numpy.flatnonzero(scores[start : end + 1, _column] >= threshold)
        if hit.size == 0:
            continue
        row = start + int(hit[0])
        # Strict improvement only, over members visited earliest-start-first, then lowest-column.
        # So an equal row keeps the member reached first, which is the declared tie-break.
        if best_row < 0 or row < best_row:
            best_row, best_column = row, _column
    if best_row < 0:
        # Cannot happen for a group `_all_episodes` produced: each member's own peak is above the
        # threshold by construction. Refused rather than papered over, so a caller with a mismatched
        # matrix hears about it instead of silently receiving no alert.
        raise ValueError("no member of the group crosses the threshold at any of its own samples")
    return best_row, best_column


def earliest_crossing_events(
    scores: _Float32, threshold: float = THRESHOLD, windows: Windows = FROZEN_WINDOWS
) -> list[ConsistencyEvent]:
    """Group per-signal episodes into events and place each alert at the group's first crossing.

    The events, their members, their scores and their order are what `phos.atlas.consistency.events`
    produces. Only the placed cell differs: it is the earliest sample any member is at or above
    ``threshold``, and no onset level is derived from the group's strongest peak. See this module's
    docstring for why that is the question ADR 0286 left open.

    Args:
        scores: Rows by signals, as `phos.atlas.consistency.feature_scores` returns them.
        threshold: A score above this opens an episode, and at or above it places the alert.
        windows: The model's windows (`ConsistencyModel.windows`). HAI's by default.

    Returns:
        Events in onset order of their first member, ready for `budget_alerts` unchanged.
    """
    found: list[ConsistencyEvent] = []
    for group in _groups(scores, threshold, windows):
        peak = max(group, key=lambda episode: episode[2])
        onset, column = _crossing(scores, group, threshold)
        found.append(
            ConsistencyEvent(
                onset=int(onset),
                column=int(column),
                score=peak[2],
                peak_at=peak[3],
                peak_column=peak[4],
                members=tuple(group),
            )
        )
    return found


def detect_with_placement(
    model: ConsistencyModel,
    values: _Float64,
    time: _Float64,
    scores: _Float32 | None = None,
    windows: Windows = FROZEN_WINDOWS,
) -> tuple[list[int], list[int], list[float]]:
    """Place one file's alerts with the rule above and spend the frozen shift budget on them.

    `budget_alerts` is called exactly as the frozen engine calls it, so the eight-alerts-a-shift
    ceiling, the shift boundaries and the spare-second-alert rule are the frozen ones, unchanged.

    Args:
        model: A fitted `phos.atlas.consistency.ConsistencyModel`, for its windows.
        values: The file's readings, rows by signals.
        time: Unix seconds, one per row of ``values``.
        scores: An already-computed score matrix for ``values``, rows by signals. Omitted, the
            frozen per-signal scores are used. The harness passes lane 3's augmented matrix here,
            which keeps this module free of any dependency on that detector.
        windows: The windows the model was fit with. ``model.windows`` by default, for parity with
            `phos.atlas.consistency.detect`, which reads the model's own.

    Returns:
        ``(rows, columns, scores)``, one entry per alert.

    Raises:
        ValueError: If ``scores`` is absent and ``values`` cannot be scored, or if the matrix and
            the time axis disagree in length.
    """
    matrix = feature_scores(model, values) if scores is None else scores
    if matrix.shape[0] != time.size:
        raise ValueError(f"{matrix.shape[0]} scored rows but {time.size} timestamps")
    return budget_alerts(earliest_crossing_events(matrix, windows=windows), time, windows=windows)
