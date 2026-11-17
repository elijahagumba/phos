"""Cross-subsystem synchrony detection: when physically independent units move together.

`MahalanobisModel` judges each signal against what every *other* signal implies it should read.
That is powerful, but it has a structural blind spot: when *every* signal moves together, no
single signal is anomalous relative to the rest, and the joint model sees nothing. A batch reactor
stepping through a recipe is exactly this — every tank heats and fills in unison, so the joint
model scores ordinary operation as normal even when an attacker drives the whole train off the
recipe.

This model looks one level up: at *subsystems*, not signals. It learns which pairs of subsystems
normally co-vary and which do not, then flags pairs whose observed correlation departs from the
learned baseline by more than three standard deviations. A reactor and a distribution main two
processes apart should not move in lockstep; if they suddenly do, something has coupled them — a
valve driven open that should not be, a pump forced to follow a setpoint it does not own.

It emits one `Deviation` per anomalous subsystem pair, carrying the deviation of their observed
cross-correlation from the learned baseline: "reactor temperature and distribution pressure moved
together at r=0.91, normally r=0.02."

The topology is declared, never inferred. When a `SubsystemMap` is supplied, pairs come from it
and only pairs declared in different subsystems are judged (ADR 0010: clustering by co-movement is
circular). When no map is supplied, subsystem ids are derived from signal key prefixes
(``<subsystem>.<feature>``) — a heuristic usable on synthetic corpora, not a substitute for a
declared map on real plants.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import numpy
from numpy.typing import NDArray
from pydantic import ConfigDict, Field

from phos.atlas.topology import SubsystemMap
from phos.models import BehaviouralModel, FittedModel, clamp_magnitude
from phos.ontology import Deviation, ExpectedRange, Observation, UtcDatetime

__all__ = [
    "CrossSubsystemSynchronyFittedModel",
    "CrossSubsystemSynchronyModel",
]

logger = logging.getLogger(__name__)

Matrix = NDArray[numpy.float64]

_DEFAULT_WINDOW_MINUTES: Final = 10
_DEFAULT_STEP_MINUTES: Final = 1
_DEFAULT_MIN_WINDOW_SAMPLES: Final = 5


class CrossSubsystemSynchronyFittedModel(FittedModel):
    """Learned cross-subsystem correlation baselines.

    Holds per-pair mean/stddev of Pearson correlation over sliding windows of training data,
    plus the signal columns needed to recompute subsystem aggregates at score time.

    The `FittedModel` fields `expected_ranges`, `feature_ranges` and `emit_k` are required by the
    base type but unused by this model: synchrony emits deviations keyed to subsystem pairs rather
    than per-`(entity_id, feature)` baselines. They are populated with empty/default values so the
    type checks out; scoring uses `score()` directly rather than `resolve_range()`.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    subsystem_pairs: tuple[tuple[str, str], ...]
    """Pairs of subsystem ids judged for synchrony, in sorted order."""

    pair_mean_correlation: dict[tuple[str, str], float]
    """Mean correlation each pair showed in training."""

    pair_stddev_correlation: dict[tuple[str, str], float]
    """Stddev of correlation each pair showed in training."""

    window_samples: int
    step_samples: int
    persistence_windows: int
    """Consecutive windows above threshold required before emitting a deviation.
    A persistence of 1 emits on the first anomalous window; higher values suppress
    isolated spikes while catching sustained attacks."""
    signal_columns: dict[str, list[str]]
    """Subsystem id -> signal keys that belong to it, used to recompute aggregates at score time."""

    train_start: UtcDatetime
    train_end: UtcDatetime

    expected_ranges: dict[tuple[str, str], ExpectedRange] = Field(default_factory=dict)
    feature_ranges: dict[str, ExpectedRange] = Field(default_factory=dict)
    emit_k: float = Field(default=3.0, ge=0.0)

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Score observations and return deviations for anomalously synchronous subsystem pairs.

        Re-vectorises the observations into a (n_rows x n_signals) matrix aligned by timestamp,
        aggregates each subsystem to one series, recomputes sliding-window correlations, and
        flags pairs whose observed correlation departed from its learned baseline by more than
        three standard deviations for ``persistence_windows`` consecutive windows.
        """
        deviations: list[Deviation] = []
        if not observations:
            return deviations

        # Group observations by timestamp so each row is one instant.
        by_timestamp: dict[UtcDatetime, dict[str, float]] = {}
        for obs in observations:
            by_timestamp.setdefault(obs.timestamp, {})[obs.feature] = obs.value

        ordered_ts = sorted(by_timestamp.keys())
        if len(ordered_ts) < self.window_samples:
            return deviations

        # Build the matrix: columns are all signals this model knows about, rows are timestamps.
        all_signal_keys = sorted(key for cols in self.signal_columns.values() for key in cols)
        key_to_col = {key: i for i, key in enumerate(all_signal_keys)}

        matrix = numpy.full((len(ordered_ts), len(all_signal_keys)), numpy.nan, dtype=numpy.float64)
        for row_idx, ts in enumerate(ordered_ts):
            for key, value in by_timestamp[ts].items():
                if key in key_to_col:
                    matrix[row_idx, key_to_col[key]] = value

        # Drop rows with any NaN.
        valid_rows = ~numpy.isnan(matrix).any(axis=1)
        matrix = matrix[valid_rows]
        ordered_ts = [ts for ts, keep in zip(ordered_ts, valid_rows, strict=True) if keep]

        if matrix.shape[0] < self.window_samples:
            return deviations

        # Aggregate each subsystem to one series per row: mean of its signals at that instant.
        subsystem_series: dict[str, Vector] = {}
        for sub_id, cols in self.signal_columns.items():
            if not cols:
                continue
            col_idxs = [key_to_col[k] for k in cols if k in key_to_col]
            if col_idxs:
                subsystem_series[sub_id] = matrix[:, col_idxs].mean(axis=1)

        n_windows = matrix.shape[0] - self.window_samples + 1
        # Consecutive-window counter per pair: counts how many windows in a row
        # have exceeded the threshold. Resets to zero on any non-exceeding window.
        consecutive: dict[tuple[str, str], int] = dict.fromkeys(self.subsystem_pairs, 0)
        for start in range(0, n_windows, self.step_samples):
            end = start + self.window_samples
            window_ts = ordered_ts[end - 1]  # stamp the window at its latest instant
            for sub_a, sub_b in self.subsystem_pairs:
                series_a = subsystem_series.get(sub_a)
                series_b = subsystem_series.get(sub_b)
                if series_a is None or series_b is None:
                    continue
                window_a = series_a[start:end]
                window_b = series_b[start:end]
                if window_a.std() == 0.0 or window_b.std() == 0.0:
                    consecutive[(sub_a, sub_b)] = 0
                    continue
                observed = float(numpy.corrcoef(window_a, window_b)[0, 1])
                if numpy.isnan(observed):
                    consecutive[(sub_a, sub_b)] = 0
                    continue
                pair_key = (sub_a, sub_b)
                mean = self.pair_mean_correlation[pair_key]
                stddev = self.pair_stddev_correlation[pair_key]
                if stddev == 0.0:
                    zscore = abs(observed - mean)
                else:
                    zscore = abs(observed - mean) / stddev
                if zscore < 3.0:
                    consecutive[pair_key] = 0
                    continue
                consecutive[pair_key] += 1
                if consecutive[pair_key] < self.persistence_windows:
                    continue
                magnitude = clamp_magnitude(zscore)
                deviations.append(
                    Deviation(
                        observation_id=(f"synchrony:{sub_a}:{sub_b}:{window_ts.isoformat()}"),
                        expected=ExpectedRange(
                            feature=f"synchrony:{sub_a}:{sub_b}",
                            entity_id=sub_a,
                            low=(mean - 3.0 * stddev if stddev > 0 else mean),
                            high=(mean + 3.0 * stddev if stddev > 0 else mean),
                            mean=mean,
                            stddev=stddev,
                            learned_from_window=(self.train_start, self.train_end),
                        ),
                        magnitude=magnitude,
                        timestamp=window_ts,
                    )
                )
        return deviations


Vector = NDArray[numpy.float64]


def _subsystem_ids_from_signal_keys(signal_keys: Sequence[str]) -> list[str]:
    """Derive subsystem ids from signal key prefixes (``<subsystem>.<feature>``).

    Heuristic only — usable on synthetic corpora where signal keys carry subsystem
    structure. Real deployment should supply a declared `SubsystemMap` instead.
    """
    ids: set[str] = set()
    for key in signal_keys:
        parts = key.split(".", 1)
        ids.add(parts[0] if len(parts) > 1 else key)
    return sorted(ids)


class CrossSubsystemSynchronyModel(BehaviouralModel):
    """Learns which subsystem pairs normally co-vary, and flags pairs that break that pattern.

    Fit aggregates each subsystem's signals into one series, computes sliding-window Pearson
    correlations between every declared pair, and records mean/stddev per pair. Score recomputes
    correlations over the same windows and flags pairs whose observed correlation departed by
    more than three standard deviations.

    Not a per-key model: it learns one joint relationship structure over the whole plant,
    complementing the multivariate models rather than replacing them.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str = Field(default="atlas-synchrony", min_length=1)
    window_minutes: int = Field(default=_DEFAULT_WINDOW_MINUTES, gt=0)
    step_minutes: int = Field(default=_DEFAULT_STEP_MINUTES, gt=0)
    persistence_windows: int = Field(default=3, gt=0)
    """Consecutive windows above threshold required before emitting a deviation."""
    min_window_samples: int = Field(default=_DEFAULT_MIN_WINDOW_SAMPLES, gt=0)
    subsystem_map: SubsystemMap | None = Field(
        default=None,
        description="Declared topology. When set, pairs come from it; otherwise derived "
        "from signal key prefixes (heuristic).",
    )

    def fit(self, observations: Sequence[Observation]) -> CrossSubsystemSynchronyFittedModel:
        """Learn cross-subsystem correlation baselines from attack-free training data."""
        if not observations:
            raise ValueError("no training observations; cannot learn synchrony baselines")

        # Group by timestamp.
        by_timestamp: dict[UtcDatetime, dict[str, float]] = {}
        signal_keys: set[str] = set()
        for obs in observations:
            by_timestamp.setdefault(obs.timestamp, {})[obs.feature] = obs.value
            signal_keys.add(obs.feature)

        if not by_timestamp:
            raise ValueError("no distinct timestamps in training data; cannot fit")

        ordered_ts = sorted(by_timestamp.keys())
        ordered_keys = sorted(signal_keys)
        key_to_col = {key: i for i, key in enumerate(ordered_keys)}

        matrix = numpy.full((len(ordered_ts), len(ordered_keys)), numpy.nan, dtype=numpy.float64)
        for row_idx, ts in enumerate(ordered_ts):
            for key, value in by_timestamp[ts].items():
                matrix[row_idx, key_to_col[key]] = value

        valid_rows = ~numpy.isnan(matrix).any(axis=1)
        matrix = matrix[valid_rows]
        ordered_ts = [ts for ts, keep in zip(ordered_ts, valid_rows, strict=True) if keep]

        if matrix.shape[0] < self.min_window_samples * 2:
            raise ValueError(
                f"too few valid rows ({matrix.shape[0]}) to learn synchrony baselines; "
                f"need at least {self.min_window_samples * 2}"
            )

        # Determine subsystem pairs.
        if self.subsystem_map is not None:
            subsystems = list(self.subsystem_map.subsystems)
            pairs: list[tuple[str, str]] = []
            for i, a in enumerate(subsystems):
                for b in subsystems[i + 1 :]:
                    pairs.append((a.subsystem_id, b.subsystem_id))
            # Map subsystem id -> its signal keys from the declaration.
            subsystem_to_keys: dict[str, list[str]] = {}
            for sub in subsystems:
                subsystem_to_keys[sub.subsystem_id] = sorted(sub.signals)
        else:
            subsystem_ids = _subsystem_ids_from_signal_keys(sorted(signal_keys))
            pairs = [
                (subsystem_ids[i], subsystem_ids[j])
                for i in range(len(subsystem_ids))
                for j in range(i + 1, len(subsystem_ids))
            ]
            subsystem_to_keys = {}
            for sub_id in subsystem_ids:
                subsystem_to_keys[sub_id] = sorted(
                    k for k in ordered_keys if k.startswith(f"{sub_id}.")
                )

        if not pairs:
            raise ValueError("fewer than two subsystems in training data; no pairs to learn")

        # Derive samples-per-minute from the actual timestamp spacing so the
        # minute-based window parameters work at any sampling rate.
        deltas = [
            (ordered_ts[i + 1] - ordered_ts[i]).total_seconds() for i in range(len(ordered_ts) - 1)
        ]
        median_delta = float(numpy.median(deltas)) if deltas else 1.0
        samples_per_minute = max(1, round(60.0 / median_delta))
        window_samples = max(self.min_window_samples, self.window_minutes * samples_per_minute)
        step_samples = max(1, self.step_minutes * samples_per_minute)

        pair_mean: dict[tuple[str, str], float] = {}
        pair_std: dict[tuple[str, str], float] = {}
        signal_columns: dict[str, list[str]] = {}

        for sub_a, sub_b in pairs:
            keys_a = subsystem_to_keys.get(sub_a, [])
            keys_b = subsystem_to_keys.get(sub_b, [])
            if not keys_a or not keys_b:
                continue
            signal_columns[sub_a] = keys_a
            signal_columns[sub_b] = keys_b

            cols_a = [key_to_col[k] for k in keys_a if k in key_to_col]
            cols_b = [key_to_col[k] for k in keys_b if k in key_to_col]
            if not cols_a or not cols_b:
                continue
            series_a = matrix[:, cols_a].mean(axis=1)
            series_b = matrix[:, cols_b].mean(axis=1)

            correlations: list[float] = []
            for start in range(0, matrix.shape[0] - window_samples + 1, step_samples):
                end = start + window_samples
                wa = series_a[start:end]
                wb = series_b[start:end]
                if wa.std() == 0.0 or wb.std() == 0.0:
                    continue
                c = float(numpy.corrcoef(wa, wb)[0, 1])
                if not numpy.isnan(c):
                    correlations.append(c)

            if len(correlations) < 2:
                continue
            pair_mean[(sub_a, sub_b)] = float(numpy.mean(correlations))
            pair_std[(sub_a, sub_b)] = float(numpy.std(correlations))

        if not pair_mean:
            raise ValueError(
                "no subsystem pairs yielded enough correlation windows to fit; "
                "training data may be too short or too static"
            )

        return CrossSubsystemSynchronyFittedModel(
            name=self.name,
            subsystem_pairs=tuple(sorted(pair_mean.keys())),
            pair_mean_correlation=pair_mean,
            pair_stddev_correlation=pair_std,
            window_samples=window_samples,
            step_samples=step_samples,
            persistence_windows=self.persistence_windows,
            signal_columns={
                sub: [k for k in keys if k in key_to_col] for sub, keys in signal_columns.items()
            },
            train_start=ordered_ts[0],
            train_end=ordered_ts[-1],
            expected_ranges={},
            feature_ranges={},
            emit_k=3.0,
        )

    @property
    def key(self) -> str:
        """Stable identifier for logging and experiment rows."""
        return self.name
