"""The consistency detector's windows, and the one rule that scales them to a sample period.

Every window below was developed and scored on HAI, where a sample is one second, so ADR 0112
reads each as a span of seconds. `windows_for_period` converts them for a corpus whose samples
are further apart (BATADAL is hourly). At one second it returns `FROZEN_WINDOWS`, the values the
frozen candidate was scored with, so nothing scored on HAI can move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DETREND_STEP",
    "DETREND_WINDOW",
    "EVENT_SPAN",
    "EVENT_WINDOW",
    "FEATURE_GAP",
    "FIT_STEP",
    "FROZEN_WINDOWS",
    "LAGS",
    "SECOND_ALERT_MIN_SEPARATION",
    "Windows",
    "scale_windows",
    "windows_for_period",
]

#: Lags, in samples, at which every other signal predicts this one.
LAGS: Final = (0, 5, 15, 30, 60)
#: Every this-many-th training sample enters the regression.
FIT_STEP: Final = 5
#: Detrending looks back this many samples ...
DETREND_WINDOW: Final = 3600
#: ... sampled every this many.
DETREND_STEP: Final = 60
#: Gaps up to this many samples are closed inside an episode.
FEATURE_GAP: Final = 60
#: Episode onsets chaining within this many samples join one event ...
EVENT_WINDOW: Final = 300
#: ... whose member onsets span at most this many.
EVENT_SPAN: Final = 600
#: A second alert needs at least this many samples between onset and peak.
SECOND_ALERT_MIN_SEPARATION: Final = 30


@dataclass(frozen=True)
class Windows:
    """Every window the detector counts in samples. The frozen values are HAI's, at 1 s a sample.

    ADR 0112 reads each frozen window as a span of seconds, because it was developed on 1-second
    HAI, and `windows_for_period` converts it for a corpus with another sample period.
    """

    lags: tuple[int, ...]
    fit_step: int
    detrend_window: int
    detrend_step: int
    feature_gap: int
    event_window: int
    event_span: int
    second_alert_min_separation: int


#: The frozen windows, exactly as scored on HAI.
FROZEN_WINDOWS: Final = Windows(
    lags=LAGS,
    fit_step=FIT_STEP,
    detrend_window=DETREND_WINDOW,
    detrend_step=DETREND_STEP,
    feature_gap=FEATURE_GAP,
    event_window=EVENT_WINDOW,
    event_span=EVENT_SPAN,
    second_alert_min_separation=SECOND_ALERT_MIN_SEPARATION,
)


def _samples(seconds: int, period_seconds: float) -> int:
    """A positive span of seconds in samples: rounded half up, never below one sample."""
    return max(1, math.floor(seconds / period_seconds + 0.5))


def windows_for_period(period_seconds: float) -> Windows:
    """Convert the frozen windows to a corpus whose samples are ``period_seconds`` apart.

    The rule declared in ADR 0112, one rule for every corpus: each frozen window is that many
    seconds; it becomes ``max(1, floor(seconds / period + 0.5))`` samples. Lag 0 stays 0, and
    lags that land on the same sample are kept once, in order. At a period of one second this
    returns `FROZEN_WINDOWS` exactly.

    Raises:
        ValueError: If the period is not a positive number of seconds.
    """
    if not period_seconds > 0:
        raise ValueError(f"a sample period must be positive seconds, got {period_seconds!r}")
    lags: list[int] = []
    for lag in LAGS:
        scaled = 0 if lag == 0 else _samples(lag, period_seconds)
        if scaled not in lags:
            lags.append(scaled)
    return Windows(
        lags=tuple(lags),
        fit_step=_samples(FIT_STEP, period_seconds),
        detrend_window=_samples(DETREND_WINDOW, period_seconds),
        detrend_step=_samples(DETREND_STEP, period_seconds),
        feature_gap=_samples(FEATURE_GAP, period_seconds),
        event_window=_samples(EVENT_WINDOW, period_seconds),
        event_span=_samples(EVENT_SPAN, period_seconds),
        second_alert_min_separation=_samples(SECOND_ALERT_MIN_SEPARATION, period_seconds),
    )


def scale_windows(base: Windows, period_seconds: float) -> Windows:
    """Apply ADR 0112's rule to any window set written in seconds, not only the frozen one.

    Each window in ``base`` is read as that many seconds and becomes
    ``max(1, floor(seconds / period + 0.5))`` samples; lag 0 stays 0 and coinciding lags are kept
    once, in order. ``scale_windows(FROZEN_WINDOWS, p)`` equals ``windows_for_period(p)``, which
    a test checks; that function is left exactly as ADR 0112 declared it. Used by the arena
    (ADR 0120) to try other windows under the same conversion rule.

    Raises:
        ValueError: If the period is not a positive number of seconds.
    """
    if not period_seconds > 0:
        raise ValueError(f"a sample period must be positive seconds, got {period_seconds!r}")
    lags: list[int] = []
    for lag in base.lags:
        scaled = 0 if lag == 0 else _samples(lag, period_seconds)
        if scaled not in lags:
            lags.append(scaled)
    return Windows(
        lags=tuple(lags),
        fit_step=_samples(base.fit_step, period_seconds),
        detrend_window=_samples(base.detrend_window, period_seconds),
        detrend_step=_samples(base.detrend_step, period_seconds),
        feature_gap=_samples(base.feature_gap, period_seconds),
        event_window=_samples(base.event_window, period_seconds),
        event_span=_samples(base.event_span, period_seconds),
        second_alert_min_separation=_samples(base.second_alert_min_separation, period_seconds),
    )
