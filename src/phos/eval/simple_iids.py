"""Reproductions of three published industrial detectors.

Wolsing, Thiemt, van Sloun, Wagner, Wehrle and Henze, "Can Industrial Intrusion Detection
Be SIMPLE?", ESORICS 2022, report these on HAI. The arithmetic follows the public code in
``ipal-ids/ipal_ids_framework`` ``ids/simple/{minmax,steadytime,histogram}.py`` (``master``,
read 2026-10-04), including the doubled range, the discrete cutoff of ten distinct values,
and Steadytime's back-dated alarm. Gradient is in the paper and is not an IDS in that tree.

These are named detectors for the harness. They are not Atlas, and they do not retune a
prior or ``EVIDENCE_STRENGTH``. ``Detection.confidence`` is 0: the score is the code's
likelihood, which is not a calibrated probability.

ADR 0090 ran the authors' ``ipal-iids`` on hai-20.07. The alert rows match these three
detectors. They do not match the paper's TPA/FPA row. The rules here were not changed to
chase that row.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.ontology.observations import Observation

__all__ = [
    "DISCRETE_THRESHOLD",
    "HISTOGRAM_WINDOW",
    "HistogramFeature",
    "RangeBound",
    "SimpleHistogram",
    "SimpleMinMax",
    "SimpleSteadytime",
    "SteadyFeature",
    "fit_histogram",
    "fit_minmax",
    "fit_steadytime",
    "histogram_alert_indexes",
    "minmax_alert_indexes",
    "steadytime_alert_indexes",
]

#: At or below this many distinct values, MinMax adds no margin and the other two run at all.
DISCRETE_THRESHOLD = 10
#: The public Histogram default. The paper says the window should match a process cycle.
HISTOGRAM_WINDOW = 100


class RangeBound(BaseModel):
    """A trained low, high, and the margin added on each side.

    Attributes:
        low: Smallest value the rule was trained on.
        high: Largest value the rule was trained on.
        margin: Half of ``high - low``, or 0 when the caller asked for no margin.
    """

    model_config = ConfigDict(frozen=True)

    low: float
    high: float
    margin: float


class SteadyFeature(BaseModel):
    """Completed-run lengths for one discrete feature.

    Attributes:
        known: Values that occurred in training.
        durations: Completed-run ``(low, high, margin)`` per value. A value with no completed
            run is absent. The public code treats that as "no data is valid".
    """

    model_config = ConfigDict(frozen=True)

    known: tuple[float, ...]
    durations: dict[float, RangeBound]


class HistogramFeature(BaseModel):
    """Per-value window-count bounds for one discrete feature.

    Attributes:
        counts: Trained minimum and maximum occurrences of each value inside a full window.
        window_size: Samples in the window these bounds were trained on.
    """

    model_config = ConfigDict(frozen=True)

    counts: dict[float, RangeBound]
    window_size: int = Field(ge=1)


def _margin(low: float, high: float) -> float:
    return (high - low) / 2.0


def _likelihood(value: float, low: float, high: float, margin: float) -> float:
    """The public overshoot, 0 inside ``[low, high]``.

    Past the raw range the distance beyond it is divided by the margin, or by 1 when the
    margin is 0. That quotient is the code's likelihood. It is not capped at 1.
    """
    if low <= value <= high:
        return 0.0
    overshoot = abs(((high + low) * 0.5) - value) - (high - low) * 0.5
    return overshoot / (1.0 if margin == 0.0 else margin)


def _by_feature(dataset: Dataset) -> dict[str, list[Observation]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in dataset.observations:
        grouped[observation.feature].append(observation)
    for rows in grouped.values():
        rows.sort(key=lambda observation: (observation.timestamp, observation.id))
    return grouped


def _detection(observation: Observation, score: float) -> Detection:
    return Detection(
        timestamp=observation.timestamp,
        score=score,
        confidence=0.0,
        entity_ids=list(observation.entity_ids),
        feature=observation.feature,
    )


def fit_minmax(
    values: Sequence[float], *, discrete_threshold: int = DISCRETE_THRESHOLD
) -> RangeBound:
    """Train one MinMax bound.

    A feature with at most ``discrete_threshold`` distinct values gets margin 0. Any other
    feature gets half its trained range, which is the paper's doubled interval.
    """
    if not values:
        raise ValueError("MinMax needs at least one training value")
    low = min(values)
    high = max(values)
    margin = 0.0 if len(set(values)) <= discrete_threshold else _margin(low, high)
    return RangeBound(low=low, high=high, margin=margin)


def minmax_alert_indexes(values: Sequence[float], bound: RangeBound) -> list[int]:
    """Indexes where the value is strictly outside ``[low - margin, high + margin]``."""
    return [
        index
        for index, value in enumerate(values)
        if value < bound.low - bound.margin or bound.high + bound.margin < value
    ]


class SimpleMinMax(BaseModel):
    """MinMax from Wolsing et al., one bound per feature.

    Fit on the benign corpus. ``run`` scores a different corpus and does not update the bounds.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "simple-minmax"
    bounds: dict[str, RangeBound]

    @classmethod
    def fit(cls, dataset: Dataset, *, discrete_threshold: int = DISCRETE_THRESHOLD) -> SimpleMinMax:
        """Learn one bound per feature from every observation in ``dataset``."""
        bounds = {
            feature: fit_minmax(
                [observation.value for observation in rows],
                discrete_threshold=discrete_threshold,
            )
            for feature, rows in _by_feature(dataset).items()
        }
        return cls(bounds=bounds)

    def run(self, dataset: Dataset) -> list[Detection]:
        """Alert where a fitted feature is outside its doubled range."""
        detections: list[Detection] = []
        for feature, rows in _by_feature(dataset).items():
            bound = self.bounds.get(feature)
            if bound is None:
                continue
            for observation in rows:
                value = observation.value
                if value < bound.low - bound.margin or bound.high + bound.margin < value:
                    detections.append(
                        _detection(
                            observation, _likelihood(value, bound.low, bound.high, bound.margin)
                        )
                    )
        detections.sort(key=lambda detection: (detection.timestamp, detection.feature or ""))
        return detections


def fit_steadytime(
    values: Sequence[float], *, discrete_threshold: int = DISCRETE_THRESHOLD
) -> SteadyFeature | None:
    """Train completed-run lengths. ``None`` when the feature is not discrete.

    A run still open at the end of training is not stored. That matches the public code,
    which records a length only when the value changes.
    """
    if not values:
        raise ValueError("Steadytime needs at least one training value")
    distinct = tuple(dict.fromkeys(values))
    if len(set(values)) > discrete_threshold:
        return None
    lengths: dict[float, list[int]] = {value: [] for value in distinct}
    current = values[0]
    length = 0
    for value in values:
        if value == current:
            length += 1
            continue
        lengths[current].append(length)
        current = value
        length = 1
    durations: dict[float, RangeBound] = {}
    for value, seen in lengths.items():
        if not seen:
            continue
        low = float(min(seen))
        high = float(max(seen))
        durations[value] = RangeBound(low=low, high=high, margin=_margin(low, high))
    return SteadyFeature(known=distinct, durations=durations)


def steadytime_alert_indexes(
    values: Sequence[float], model: SteadyFeature, *, adjust: bool = True
) -> list[int]:
    """Indexes that alert.

    With ``adjust`` (the public default) a too-short run alerts on every sample of that run,
    and a too-long run alerts only on the samples past the trained maximum. The sample that
    ended the run does not alert. Without ``adjust``, only that ending sample alerts.
    An unknown value alerts on its own sample and does not close the previous run.
    """
    alerts: set[int] = set()
    current = None
    length = 0
    start = 0
    for index, value in enumerate(values):
        if value not in model.known:
            alerts.add(index)
            current = None
            length = 0
            continue
        if current is None or value != current:
            if current is not None and length > 0:
                alerts.update(_steady_alerts(model, current, length, start, index, adjust=adjust))
            current = value
            length = 1
            start = index
            continue
        length += 1
    return sorted(alerts)


def _steady_alerts(
    model: SteadyFeature,
    value: float,
    length: int,
    start: int,
    end_index: int,
    *,
    adjust: bool,
) -> set[int]:
    bound = model.durations.get(value)
    if bound is None:
        return set()
    if bound.low - bound.margin <= length <= bound.high + bound.margin:
        return set()
    if not adjust:
        return {end_index}
    excess = length
    if length > bound.high:
        excess = length - int(bound.high)
    # Offsets [-excess, -1] relative to the sample that ended the run.
    return {
        end_index - offset for offset in range(1, int(excess) + 1) if end_index - offset >= start
    }


class SimpleSteadytime(BaseModel):
    """Steadytime from Wolsing et al. Features above the discrete cutoff are ignored."""

    model_config = ConfigDict(frozen=True)

    name: str = "simple-steadytime"
    features: dict[str, SteadyFeature]
    adjust: bool = True

    @classmethod
    def fit(
        cls, dataset: Dataset, *, discrete_threshold: int = DISCRETE_THRESHOLD
    ) -> SimpleSteadytime:
        """Learn run lengths from ``dataset``. Non-discrete features are omitted."""
        features: dict[str, SteadyFeature] = {}
        for feature, rows in _by_feature(dataset).items():
            fitted = fit_steadytime(
                [observation.value for observation in rows],
                discrete_threshold=discrete_threshold,
            )
            if fitted is not None:
                features[feature] = fitted
        return cls(features=features)

    def run(self, dataset: Dataset) -> list[Detection]:
        """Alert on runs whose length leaves the trained band, and on unseen values."""
        detections: list[Detection] = []
        for feature, rows in _by_feature(dataset).items():
            model = self.features.get(feature)
            if model is None:
                continue
            indexes = steadytime_alert_indexes(
                [observation.value for observation in rows], model, adjust=self.adjust
            )
            detections.extend(_detection(rows[index], 1.0) for index in indexes)
        detections.sort(key=lambda detection: (detection.timestamp, detection.feature or ""))
        return detections


def fit_histogram(
    values: Sequence[float],
    *,
    window_size: int = HISTOGRAM_WINDOW,
    discrete_threshold: int = DISCRETE_THRESHOLD,
) -> HistogramFeature | None:
    """Train per-value window counts. ``None`` when the feature is not discrete.

    Raises:
        ValueError: The series never fills one window, so the public code's ``min`` of an
            empty count list would fail.
    """
    if window_size < 1:
        raise ValueError("histogram window must be at least one sample")
    if not values:
        raise ValueError("Histogram needs at least one training value")
    distinct = tuple(dict.fromkeys(values))
    if len(set(values)) > discrete_threshold:
        return None
    if len(values) < window_size:
        raise ValueError("histogram window is longer than the training series")
    seen: dict[float, list[int]] = {value: [] for value in distinct}
    window: list[float] = []
    counts: dict[float, int] = dict.fromkeys(distinct, 0)
    for value in values:
        window.append(value)
        counts[value] += 1
        if len(window) > window_size:
            counts[window.pop(0)] -= 1
        if len(window) == window_size:
            for known in distinct:
                seen[known].append(counts[known])
    bounds = {
        value: RangeBound(
            low=float(min(counts_seen)),
            high=float(max(counts_seen)),
            margin=_margin(float(min(counts_seen)), float(max(counts_seen))),
        )
        for value, counts_seen in seen.items()
    }
    return HistogramFeature(counts=bounds, window_size=window_size)


def histogram_alert_indexes(
    values: Sequence[float],
    model: HistogramFeature,
    *,
    window_size: int | None = None,
) -> list[int]:
    """Indexes where an unseen value appears, or a full window leaves a trained count band.

    An unseen value alerts and is not inserted into the window, matching the public ``continue``.
    """
    size = model.window_size if window_size is None else window_size
    alerts: list[int] = []
    window: list[float] = []
    counts: dict[float, int] = dict.fromkeys(model.counts, 0)
    for index, value in enumerate(values):
        if value not in model.counts:
            alerts.append(index)
            continue
        window.append(value)
        counts[value] += 1
        if len(window) > size:
            counts[window.pop(0)] -= 1
        if len(window) < size:
            continue
        if _histogram_outside(counts, model):
            alerts.append(index)
    return alerts


def _histogram_outside(counts: dict[float, int], model: HistogramFeature) -> bool:
    for value, bound in model.counts.items():
        current = counts[value]
        if current < bound.low - bound.margin or bound.high + bound.margin < current:
            return True
    return False


class SimpleHistogram(BaseModel):
    """Histogram from Wolsing et al. Features above the discrete cutoff are ignored."""

    model_config = ConfigDict(frozen=True)

    name: str = "simple-histogram"
    features: dict[str, HistogramFeature]
    window_size: int = HISTOGRAM_WINDOW

    @classmethod
    def fit(
        cls,
        dataset: Dataset,
        *,
        window_size: int = HISTOGRAM_WINDOW,
        discrete_threshold: int = DISCRETE_THRESHOLD,
    ) -> SimpleHistogram:
        """Learn window counts from ``dataset``. Non-discrete features are omitted.

        A discrete feature shorter than ``window_size`` is omitted rather than failing the
        whole fit. ``fit_histogram`` still raises, so a single-series caller hears about it.
        """
        features: dict[str, HistogramFeature] = {}
        for feature, rows in _by_feature(dataset).items():
            values = [observation.value for observation in rows]
            if len(set(values)) > discrete_threshold or len(values) < window_size:
                continue
            fitted = fit_histogram(
                values, window_size=window_size, discrete_threshold=discrete_threshold
            )
            if fitted is not None:
                features[feature] = fitted
        return cls(features=features, window_size=window_size)

    def run(self, dataset: Dataset) -> list[Detection]:
        """Alert on an unseen discrete value, or a window whose counts leave the band."""
        detections: list[Detection] = []
        for feature, rows in _by_feature(dataset).items():
            model = self.features.get(feature)
            if model is None:
                continue
            indexes = histogram_alert_indexes([observation.value for observation in rows], model)
            detections.extend(_detection(rows[index], 1.0) for index in indexes)
        detections.sort(key=lambda detection: (detection.timestamp, detection.feature or ""))
        return detections
