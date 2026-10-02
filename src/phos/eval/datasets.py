"""Labelled datasets and the adapters that produce them.

Every dataset PHOS is scored against — synthetic or real, ICS or enterprise — is converted into
one shape, :class:`Dataset`, before the harness sees it. That is the whole point of this module:
the harness never learns which corpus it is scoring, so a metric computed on synthetic data and
the same metric computed on a real ICS capture mean exactly the same thing.

A :class:`Dataset` carries the observations *and* the ground truth (:class:`LabelledInterval`),
because a measurement without its labels cannot be scored. Loading is the only I/O in the
evaluation package; everything downstream is pure.
"""

import logging
from collections.abc import Callable, Collection, Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Protocol, Self, runtime_checkable

import numpy
import pandas
from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import (
    Domain,
    Observation,
    UtcDatetime,
)

__all__ = [
    "Dataset",
    "DatasetAdapter",
    "LabelledCsvAdapter",
    "LabelledInterval",
    "SyntheticAnomaly",
    "SyntheticICSAdapter",
    "default_attack_when",
]

logger = logging.getLogger(__name__)


class LabelledInterval(BaseModel):
    """A window of time that ground truth says was an attack.

    Labels are window-level rather than per-sample because that is how published IDS corpora
    label them, and because window-level truth is what an operator actually cares about: "was
    this incident caught", not "was every packet of it flagged".

    Attributes:
        start: First instant of the labelled window, UTC, inclusive.
        end: Last instant of the labelled window, UTC, inclusive.
        label: The ground-truth class, e.g. ``"attack"``.
        attack_type: Optional finer-grained type from the source corpus, e.g. ``"modbus_write"``.

    Invariants:
        ``start <= end``.
    """

    model_config = ConfigDict(frozen=True)

    start: UtcDatetime
    end: UtcDatetime
    label: str
    attack_type: str | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"interval is inverted: {self.start} > {self.end}")
        return self

    def contains(self, timestamp: datetime) -> bool:
        """Return whether ``timestamp`` falls inside the window, both bounds inclusive."""
        return self.start <= timestamp <= self.end


class Dataset(BaseModel):
    """Observations plus the ground truth needed to score a detector against them.

    Attributes:
        name: Stable identifier for the corpus, recorded in every report it produces.
        domain: Which engine's world this corpus belongs to.
        observations: Measurements in non-decreasing timestamp order.
        attack_intervals: Ground-truth attack windows. May overlap; they are merged when
            durations are computed.
        unscored_intervals: Windows ground truth calls neither attack nor normal, such as a
            perturbation's blind and recovery phases (ADR 0082). They are removed from the
            false-positive denominator, are not recall targets, and an alert inside one is
            neither a true nor a false positive. Empty for every corpus that does not declare
            them, which leaves its metrics exactly as before.
        source_note: Provenance — corpus, version, and which file or columns it came from. This
            is what makes a reported number reproducible (Constitution §3.7).

    Invariants:
        ``observations`` is time-ordered, so the first and last entries bound the corpus.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    domain: Domain
    observations: list[Observation]
    attack_intervals: list[LabelledInterval] = Field(default_factory=list)
    unscored_intervals: list[LabelledInterval] = Field(default_factory=list)
    source_note: str = ""

    @model_validator(mode="after")
    def _check_time_ordered(self) -> Self:
        stamps = [observation.timestamp for observation in self.observations]
        for earlier, later in pairwise(stamps):
            if earlier > later:
                raise ValueError(f"observations must be time-ordered; {later} follows {earlier}")
        return self

    def duration(self) -> timedelta:
        """Return the wall-clock span from the first observation to the last.

        An empty corpus spans no time.
        """
        if not self.observations:
            return timedelta(0)
        return self.observations[-1].timestamp - self.observations[0].timestamp

    def normal_duration(self) -> timedelta:
        """Return the observed span that ground truth calls normal.

        This is the denominator for the false-positive rate, so it has to be honest: attack and
        unscored intervals are clamped to the observed span and **merged** before subtraction,
        otherwise two overlapping labels would remove the same seconds twice and flatter the
        detector. Unscored time is not normal time, so it is removed too. The result is never
        negative.
        """
        if not self.observations:
            return timedelta(0)
        start = self.observations[0].timestamp
        end = self.observations[-1].timestamp

        clamped: list[tuple[datetime, datetime]] = []
        for interval in (*self.attack_intervals, *self.unscored_intervals):
            low = max(interval.start, start)
            high = min(interval.end, end)
            if low <= high:
                clamped.append((low, high))

        covered = timedelta(0)
        for low, high in _merge_spans(clamped):
            covered += high - low
        return max((end - start) - covered, timedelta(0))

    def is_attack(self, timestamp: datetime) -> bool:
        """Return whether ground truth marks ``timestamp`` as inside an attack window."""
        return any(interval.contains(timestamp) for interval in self.attack_intervals)

    def is_unscored(self, timestamp: datetime) -> bool:
        """Return whether ground truth marks ``timestamp`` as neither attack nor normal."""
        return any(interval.contains(timestamp) for interval in self.unscored_intervals)

    def without_features(self, features: Collection[str]) -> "Dataset":
        """Return this corpus with observations of ``features`` removed.

        Used so a declared routing register (a recipe step, a batch phase) can live on the
        labelled CSV for `PhaseConditionalModel` without also becoming a process signal in the
        pooled Gaussian / PCA / Mahalanobis comparison. Those models would otherwise treat the
        register as just another column and the frozen ungated rows would no longer be comparable.

        Args:
            features: Feature names to drop. Unknown names are ignored.

        Returns:
            A dataset with the same intervals and provenance, and every observation whose
            ``feature`` is not in ``features``. Time order is preserved.
        """
        skipped = frozenset(features)
        if not skipped:
            return self
        kept = [
            observation for observation in self.observations if observation.feature not in skipped
        ]
        if len(kept) == len(self.observations):
            return self
        return self.model_copy(update={"observations": kept})


def _merge_spans(spans: Sequence[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Merge overlapping and abutting ``(start, end)`` spans into a disjoint, ordered list."""
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for low, high in ordered[1:]:
        last_low, last_high = merged[-1]
        if low <= last_high:
            merged[-1] = (last_low, max(last_high, high))
        else:
            merged.append((low, high))
    return merged


@runtime_checkable
class DatasetAdapter(Protocol):
    """Converts some on-disk or generated corpus into a :class:`Dataset`.

    One method, deliberately. Adding a corpus to PHOS means writing a `load()` that maps its
    native format onto the ontology — never teaching the harness a new format.
    """

    def load(self) -> Dataset:
        """Return the corpus as a `Dataset`, labels included."""
        ...


# ------------------------------------------------------------------------------------------------
# Synthetic ICS corpus
# ------------------------------------------------------------------------------------------------

SYNTHETIC_ENTITY_ID = "ent_synthetic001"
SYNTHETIC_FEATURE = "process_value"

_SYNTHETIC_BASELINE = 100.0
_SYNTHETIC_AMPLITUDE = 5.0
_SYNTHETIC_PERIOD_POINTS = 24
_SYNTHETIC_EPOCH = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


class SyntheticAnomaly(BaseModel):
    """An anomaly to inject into the synthetic series, and the label that describes it.

    Attributes:
        start_index: First sample index of the anomaly, inclusive.
        end_index: Last sample index of the anomaly, inclusive.
        magnitude: Absolute offset added to the signal across the interval. Absolute rather than
            relative to the noise so a test can state the effect size it wants directly.
        attack_type: Recorded on the resulting `LabelledInterval`.

    Invariants:
        ``start_index <= end_index``.
    """

    model_config = ConfigDict(frozen=True)

    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    magnitude: float
    attack_type: str = "synthetic_anomaly"

    @model_validator(mode="after")
    def _check_indices(self) -> Self:
        if self.start_index > self.end_index:
            raise ValueError(f"anomaly indices are inverted: {self.start_index} > {self.end_index}")
        return self


class SyntheticICSAdapter(BaseModel):
    """Generates a deterministic periodic "process" signal with labelled anomalies injected.

    This models the defining property of an industrial environment — behaviour that repeats — so
    that "normal" is genuinely learnable and ground truth is known exactly. It is the workhorse
    for unit tests: because the anomalies are placed by hand, a metric's correct answer can be
    computed by hand too.

    The signal is ``baseline + amplitude * sin(2*pi*i / period) + noise``, with noise drawn from
    a generator seeded by ``seed``, so two adapters with equal fields produce equal datasets
    (Constitution §3.7).

    Attributes:
        n_points: Number of samples to generate.
        anomaly_intervals: Anomalies to inject, by sample index.
        seed: Seeds the noise generator.
        sample_interval: Spacing between consecutive samples.
        noise_stddev: Standard deviation of the additive gaussian noise.
        name: Dataset name recorded on the result.
    """

    model_config = ConfigDict(frozen=True)

    n_points: int = Field(default=240, ge=1)
    anomaly_intervals: tuple[SyntheticAnomaly, ...] = ()
    seed: int = 7
    sample_interval: timedelta = timedelta(seconds=30)
    noise_stddev: float = Field(default=1.0, ge=0.0)
    name: str = "synthetic-ics"

    def load(self) -> Dataset:
        """Generate the corpus.

        Raises:
            ValueError: If an anomaly's index range falls outside the generated series, which
                would silently produce an unlabelled or empty attack window.
        """
        for anomaly in self.anomaly_intervals:
            if anomaly.end_index >= self.n_points:
                raise ValueError(
                    f"anomaly [{anomaly.start_index}, {anomaly.end_index}] is outside the "
                    f"series of {self.n_points} points"
                )

        indices = numpy.arange(self.n_points)
        angle = 2.0 * numpy.pi * indices / _SYNTHETIC_PERIOD_POINTS
        values = _SYNTHETIC_BASELINE + _SYNTHETIC_AMPLITUDE * numpy.sin(angle)
        values = values + numpy.random.default_rng(self.seed).normal(
            0.0, self.noise_stddev, self.n_points
        )
        for anomaly in self.anomaly_intervals:
            values[anomaly.start_index : anomaly.end_index + 1] += anomaly.magnitude

        timestamps = [
            _SYNTHETIC_EPOCH + index * self.sample_interval for index in range(self.n_points)
        ]
        observations = [
            Observation(
                id=f"obs_syn{index:09d}",
                entity_ids=[SYNTHETIC_ENTITY_ID],
                feature=SYNTHETIC_FEATURE,
                value=float(value),
                timestamp=timestamp,
                domain=Domain.ATLAS,
                context={"generator": self.name},
            )
            for index, (timestamp, value) in enumerate(zip(timestamps, values, strict=True))
        ]
        intervals = [
            LabelledInterval(
                start=timestamps[anomaly.start_index],
                end=timestamps[anomaly.end_index],
                label="attack",
                attack_type=anomaly.attack_type,
            )
            for anomaly in self.anomaly_intervals
        ]
        return Dataset(
            name=self.name,
            domain=Domain.ATLAS,
            observations=observations,
            attack_intervals=intervals,
            source_note=(
                f"generated: n_points={self.n_points}, seed={self.seed}, "
                f"noise_stddev={self.noise_stddev}, "
                f"sample_interval={self.sample_interval.total_seconds()}s"
            ),
        )


# ------------------------------------------------------------------------------------------------
# Labelled CSV corpus (the real-dataset path)
# ------------------------------------------------------------------------------------------------


def default_attack_when(value: object) -> bool:
    """Return whether a label cell marks its row as an attack.

    The default convention across published ICS corpora is a numeric flag where zero means
    normal. Blank cells are normal. A non-numeric, non-empty string is treated as an attack
    label (corpora that name the attack in the label column), which is why a corpus whose label
    column spells out ``"normal"`` needs its own predicate.

    Missing cells never reach this function — the adapter treats them as normal before calling.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return float(text) != 0.0
        except ValueError:
            return True
    return bool(value != 0)


class LabelledCsvAdapter(BaseModel):
    """Loads a labelled CSV time-series corpus (the first real ICS path) into a `Dataset`.

    Nothing about the file is assumed. The header is introspected and any configured column that
    is absent raises an error naming the columns that *were* found, because silently guessing a
    column would silently invalidate every metric computed downstream.

    Rows are sorted by timestamp before use, and runs of consecutive attack-labelled rows are
    collapsed into one `LabelledInterval` each. Runs of rows whose label is one of
    ``unscored_label_values`` become `Dataset.unscored_intervals` the same way.

    Attributes:
        path: The CSV file.
        timestamp_column: Column holding the row timestamp. Parsed as UTC; naive values are
            interpreted as UTC rather than local time, so a run is reproducible anywhere.
        label_column: Column holding ground truth.
        value_columns: Columns to turn into observations, one `Observation` per row per column.
            ``None`` auto-detects every numeric column except the timestamp and label columns.
        attack_when: Predicate deciding whether a label cell marks an attack.
        unscored_label_values: Label cells that mark a row as neither attack nor normal, as
            text (``"-1"``). Checked before ``attack_when``, which would otherwise read a
            non-zero sentinel as an attack. Numeric cells match by value, so ``-1.0`` matches
            ``"-1"``. Empty for every corpus that declares no such rows.
        name: Dataset name recorded on the result.
        domain: Which engine's world the corpus belongs to.
        source_note: Provenance string — corpus name, version, file.
        entity_id: Entity the measurements are attributed to.
    """

    model_config = ConfigDict(frozen=True)

    path: Path
    timestamp_column: str
    label_column: str
    value_columns: list[str] | None = None
    attack_when: Callable[[object], bool] = default_attack_when
    unscored_label_values: tuple[str, ...] = ()
    name: str = "labelled-csv"
    domain: Domain = Domain.ATLAS
    source_note: str = ""
    entity_id: str = "ent_csv0000000001"

    def load(self) -> Dataset:
        """Read and convert the CSV.

        Raises:
            ValueError: If a configured column is absent, if a configured value column is not
                numeric, or if auto-detection finds no numeric columns.
        """
        frame = pandas.read_csv(self.path)
        found = [str(column) for column in frame.columns]
        self._require_column(self.timestamp_column, found)
        self._require_column(self.label_column, found)
        value_columns = self._resolve_value_columns(frame, found)

        timestamps = [
            stamp.to_pydatetime()
            for stamp in pandas.to_datetime(frame[self.timestamp_column], utc=True)
        ]
        order = sorted(range(len(timestamps)), key=timestamps.__getitem__)
        columns = {column: self._numeric_column(frame, column) for column in value_columns}

        observations: list[Observation] = []
        for position, row in enumerate(order):
            for column_index, column in enumerate(value_columns):
                value = columns[column][row]
                if numpy.isnan(value):
                    continue
                observations.append(
                    Observation(
                        id=f"obs_r{position:07d}c{column_index:02d}",
                        entity_ids=[self.entity_id],
                        feature=column,
                        value=float(value),
                        timestamp=timestamps[row],
                        domain=self.domain,
                        context={"source_column": column},
                    )
                )

        attack_intervals, unscored_intervals = self._labelled_intervals(frame, timestamps, order)
        return Dataset(
            name=self.name,
            domain=self.domain,
            observations=observations,
            attack_intervals=attack_intervals,
            unscored_intervals=unscored_intervals,
            source_note=self.source_note or f"{self.path.name}: {', '.join(value_columns)}",
        )

    def _require_column(self, column: str, found: Sequence[str]) -> None:
        """Raise a ValueError naming every column present if ``column`` is not among them."""
        if column not in found:
            raise ValueError(
                f"column {column!r} not found in {self.path}; the file has: {', '.join(found)}"
            )

    def _resolve_value_columns(self, frame: pandas.DataFrame, found: Sequence[str]) -> list[str]:
        """Return the configured value columns, or auto-detect the numeric ones."""
        if self.value_columns is not None:
            for column in self.value_columns:
                self._require_column(column, found)
            return list(self.value_columns)

        reserved = {self.timestamp_column, self.label_column}
        detected = [
            str(column)
            for column in frame.select_dtypes(include="number").columns
            if str(column) not in reserved
        ]
        if not detected:
            raise ValueError(
                f"no numeric value columns detected in {self.path}; the file has: "
                f"{', '.join(found)}. Set value_columns explicitly."
            )
        logger.debug("auto-detected value columns in %s: %s", self.path, detected)
        return detected

    def _numeric_column(self, frame: pandas.DataFrame, column: str) -> list[float]:
        """Return ``column`` coerced to floats, refusing rather than guessing at text."""
        try:
            numeric = pandas.to_numeric(frame[column], errors="raise")
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"value column {column!r} in {self.path} is not numeric: {error}"
            ) from error
        return [float(value) for value in numeric.astype(float)]

    def _labelled_intervals(
        self,
        frame: pandas.DataFrame,
        timestamps: Sequence[datetime],
        order: Sequence[int],
    ) -> tuple[list[LabelledInterval], list[LabelledInterval]]:
        """Collapse runs of consecutive same-class rows into attack and unscored intervals."""
        labels = frame[self.label_column].tolist()
        missing = [bool(flag) for flag in frame[self.label_column].isna().to_numpy()]
        unscored_keys = frozenset(_label_key(value) for value in self.unscored_label_values)

        intervals: dict[str, list[LabelledInterval]] = {"attack": [], "unscored": []}
        run_class: str | None = None
        run_start: datetime | None = None
        previous: datetime | None = None
        for row in order:
            row_class: str | None = None
            if not missing[row]:
                if unscored_keys and _label_key(labels[row]) in unscored_keys:
                    row_class = "unscored"
                elif self.attack_when(labels[row]):
                    row_class = "attack"
            if row_class != run_class:
                if run_class is not None and run_start is not None and previous is not None:
                    intervals[run_class].append(
                        LabelledInterval(start=run_start, end=previous, label=run_class)
                    )
                run_class = row_class
                run_start = timestamps[row] if row_class is not None else None
            previous = timestamps[row]
        if run_class is not None and run_start is not None and previous is not None:
            intervals[run_class].append(
                LabelledInterval(start=run_start, end=previous, label=run_class)
            )
        return intervals["attack"], intervals["unscored"]


def _label_key(value: object) -> str:
    """Return a label cell as comparable text; numeric cells compare by value, not spelling."""
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else str(number)
