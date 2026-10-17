"""G1 baseline table: one Atlas configuration and the three checked opponents.

The configuration is fixed here and is not chosen from a score. Atlas is the public ungated
per-signal Mahalanobis model (``MahalanobisModel()``: shrinkage 0.05, joint gate off,
``emit_k`` 1.0, ``band_k`` 3.0, average-variance shrinkage). An alert is a conditional
departure of at least 3.0, the same threshold ``scripts/evaluate_atlas.py`` uses. Each
alerting feature spends its own budget slot.

The opponents are ``simple-minmax``, ``simple-steadytime`` and ``simple-histogram`` at the
published defaults (ADR 0090). Their confidence stays 0. The headline is
:func:`phos.eval.budget.recall_within_budget` with 8 alerts per 8-hour shift. That 8 is an
argument, not a new default of the function. Beside it: reference eTaPR, and eTaPR with
HAICon's pi, rho and a 180-sample tail. Alpha is recorded on ``HAICON_2020`` and is not
passed. Point-adjusted F1 is computed and is not the headline.

Nothing in this module appends ``eval_runs/log.jsonl``. Result names start with
``g1-baseline:``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy
from numpy.typing import NDArray

from phos.atlas.multivariate import MahalanobisFittedModel, MahalanobisModel
from phos.atlas.vectorise import SignalSpace
from phos.eval.batch_distillation import OPERATING_POINT_FEATURE, RECIPE_STEP_FEATURE
from phos.eval.budget import recall_within_budget
from phos.eval.etapr import HAICON_2020, REFERENCE_ETAPR, etapr_at, etapr_sample_tail
from phos.eval.point_adjust import point_adjusted_f1
from phos.eval.simple_iids import (
    DISCRETE_THRESHOLD,
    HISTOGRAM_WINDOW,
    HistogramFeature,
    RangeBound,
    SteadyFeature,
    fit_histogram,
    fit_minmax,
    fit_steadytime,
)

__all__ = [
    "ATLAS_DETECTOR",
    "CHECKED_OPPONENTS",
    "DETECTORS",
    "G1_ALERTS_PER_SHIFT",
    "G1_ATLAS_THRESHOLD",
    "G1_ENTITY",
    "HISTOGRAM_DETECTOR",
    "MINMAX_DETECTOR",
    "ROUTING_REGISTERS",
    "STEADY_DETECTOR",
    "CorpusReport",
    "DetectorScore",
    "FileScore",
    "FitFacts",
    "SeriesGrid",
    "aggregate_scores",
    "benign_matrix",
    "grid_from_columns",
    "median_period_seconds",
    "score_splits",
]

G1_ALERTS_PER_SHIFT = 8
G1_ATLAS_THRESHOLD = 3.0
G1_ENTITY = "ent_csv0000000001"
ATLAS_DETECTOR = "g1-baseline:atlas-mahalanobis"
MINMAX_DETECTOR = "g1-baseline:simple-minmax"
STEADY_DETECTOR = "g1-baseline:simple-steadytime"
HISTOGRAM_DETECTOR = "g1-baseline:simple-histogram"
DETECTORS = (ATLAS_DETECTOR, MINMAX_DETECTOR, STEADY_DETECTOR, HISTOGRAM_DETECTOR)
CHECKED_OPPONENTS = frozenset({MINMAX_DETECTOR, STEADY_DETECTOR, HISTOGRAM_DETECTOR})
ROUTING_REGISTERS = frozenset({RECIPE_STEP_FEATURE, OPERATING_POINT_FEATURE})

_Matrix = NDArray[numpy.float64]
_Flags = NDArray[numpy.bool_]


@dataclass(frozen=True)
class SeriesGrid:
    """One file as a dense numeric grid.

    ``features`` is sorted. A row is attack or unscored or neither, never both. Timestamps
    are unique and increasing. Rows with a non-finite value are omitted by the loader
    before this object exists.
    """

    timestamps: tuple[datetime, ...]
    features: tuple[str, ...]
    values: _Matrix
    attack: _Flags
    unscored: _Flags

    def __post_init__(self) -> None:
        """Reject a grid whose columns, flags or timestamps disagree."""
        n_rows = len(self.timestamps)
        if self.values.shape != (n_rows, len(self.features)):
            raise ValueError(
                f"values shape {self.values.shape} does not match "
                f"{n_rows} timestamps and {len(self.features)} features"
            )
        if self.attack.shape != (n_rows,) or self.unscored.shape != (n_rows,):
            raise ValueError("attack and unscored flags must have one entry per timestamp")
        if self.features != tuple(sorted(self.features)):
            raise ValueError("features must be sorted")
        if len(set(self.timestamps)) != n_rows:
            raise ValueError("timestamps must be unique")
        for earlier, later in zip(self.timestamps, self.timestamps[1:], strict=False):
            if earlier > later:
                raise ValueError("timestamps must be in order")
        if bool(numpy.any(self.attack & self.unscored)):
            raise ValueError("a row cannot be both attack and unscored")


@dataclass(frozen=True)
class DetectorScore:
    """One detector on one file, or the aggregate of several files.

    Attributes:
        detector: A ``g1-baseline:`` name.
        attacks: Attack windows in the denominator.
        caught: How many of those windows contain a kept alert.
        recall_within_budget: ``caught / attacks``, or 0 when there are no attacks. Headline.
        etapr_reference_f1: eTaPR F1 at the reference defaults, on the unbudgeted alert points.
        etapr_haicon_f1: eTaPR F1 at HAICon pi and rho with a 180-sample tail. Alpha is not
            an argument of that score.
        point_adjusted_f1: Reported. Not the headline.
        alerts: Feature alerts before the budget cut.
    """

    detector: str
    attacks: int
    caught: int
    recall_within_budget: float
    etapr_reference_f1: float
    etapr_haicon_f1: float
    point_adjusted_f1: float
    alerts: int


@dataclass(frozen=True)
class FileScore:
    """Every detector on one test file."""

    file: str
    scores: tuple[DetectorScore, ...]


@dataclass(frozen=True)
class FitFacts:
    """What the single fit actually saw. Not a searched parameter."""

    train_rows: int
    train_features: int
    atlas_signals: int


@dataclass(frozen=True)
class CorpusReport:
    """One corpus row of the table.

    Attributes:
        corpus: Stable corpus name.
        judges: True for the five roadmap corpora. False for distillation and Data4Cyber.
        status: ``scored``, ``reported``, or ``not_scored``.
        note: Why the row looks like this, including a sample period.
        sample_period_seconds: Median positive step of the scored files, when scored.
        declared_period_seconds: The period declared for this corpus before the run.
        files: Per-file scores. Empty when the corpus was not scored.
    """

    corpus: str
    judges: bool
    status: str
    note: str
    sample_period_seconds: float | None
    declared_period_seconds: float | None
    files: tuple[FileScore, ...]

    @property
    def scores(self) -> tuple[DetectorScore, ...]:
        """Corpus-level scores. Micro-averaged recall, attack-weighted beside-metrics."""
        return aggregate_scores(self.files)


def grid_from_columns(
    timestamps: Sequence[datetime],
    features: Sequence[str],
    values: _Matrix,
    attack: Sequence[bool],
    unscored: Sequence[bool],
) -> SeriesGrid:
    """Build a grid, sorting features and dropping rows that are not finite.

    Unscored wins over attack on the same row. The returned grid's row count can be
    shorter than ``timestamps``; the caller records how many rows were dropped.

    Raises:
        ValueError: If the columns disagree in length, or a feature is repeated.
    """
    if len(features) != len(set(features)):
        raise ValueError("a feature column is repeated")
    n_rows = len(timestamps)
    if values.shape != (n_rows, len(features)) or len(attack) != n_rows or len(unscored) != n_rows:
        raise ValueError("timestamps, values, attack and unscored must describe the same rows")
    finite = numpy.isfinite(values).all(axis=1)
    order = sorted(range(len(features)), key=lambda index: features[index])
    attack_flags = numpy.asarray(attack, dtype=numpy.bool_) & finite
    unscored_flags = numpy.asarray(unscored, dtype=numpy.bool_) & finite
    attack_flags = attack_flags & ~unscored_flags
    kept = numpy.flatnonzero(finite)
    return SeriesGrid(
        timestamps=tuple(timestamps[int(row)] for row in kept),
        features=tuple(features[index] for index in order),
        values=numpy.asarray(values[finite][:, order], dtype=numpy.float64),
        attack=attack_flags[finite],
        unscored=unscored_flags[finite],
    )


def benign_matrix(grids: Sequence[SeriesGrid]) -> tuple[tuple[str, ...], _Matrix, int]:
    """Stack attack-free, scored rows from every training file.

    Files must share one sorted feature list. Attack rows and unscored rows are left
    out of the fit. The third return is how many attack rows were excluded.

    Raises:
        ValueError: If the files disagree on features, or no benign row remains.
    """
    if not grids:
        raise ValueError("a fit needs at least one training file")
    features = grids[0].features
    parts: list[_Matrix] = []
    excluded = 0
    for grid in grids:
        if grid.features != features:
            raise ValueError("training files do not share a feature list")
        excluded += int(grid.attack.sum())
        keep = ~grid.attack & ~grid.unscored
        parts.append(grid.values[keep])
    matrix = numpy.vstack(parts) if parts else numpy.empty((0, len(features)))
    if matrix.shape[0] == 0:
        raise ValueError("training files contain no benign row")
    return features, matrix, excluded


def score_splits(
    features: Sequence[str],
    train: _Matrix,
    train_window: tuple[datetime, datetime],
    tests: Sequence[tuple[str, SeriesGrid]],
) -> tuple[FitFacts, tuple[FileScore, ...]]:
    """Fit once on ``train`` and score each test file apart.

    An attack does not cross a file. The fit window is recorded on the model and does not
    change the threshold.

    Raises:
        ValueError: If a test file's features differ from ``features``.
    """
    feature_names = tuple(features)
    atlas, facts = _fit_atlas(feature_names, train, train_window)
    opponents = _fit_opponents(feature_names, train)
    files = tuple(
        FileScore(name, _score_file(atlas, opponents, feature_names, grid)) for name, grid in tests
    )
    return facts, files


def aggregate_scores(files: Sequence[FileScore]) -> tuple[DetectorScore, ...]:
    """Micro-average recall and weight the other rates by attack count.

    A file with no attack window adds nothing to the weighted rates. Recall with no
    attacks at all is 0.
    """
    if not files:
        return ()
    names = tuple(score.detector for score in files[0].scores)
    aggregated: list[DetectorScore] = []
    for name in names:
        parts = tuple(_detector(file, name) for file in files)
        attacks = sum(part.attacks for part in parts)
        caught = sum(part.caught for part in parts)
        alerts = sum(part.alerts for part in parts)
        aggregated.append(
            DetectorScore(
                detector=name,
                attacks=attacks,
                caught=caught,
                recall_within_budget=(caught / attacks) if attacks else 0.0,
                etapr_reference_f1=_weighted(parts, "etapr_reference_f1", attacks),
                etapr_haicon_f1=_weighted(parts, "etapr_haicon_f1", attacks),
                point_adjusted_f1=_weighted(parts, "point_adjusted_f1", attacks),
                alerts=alerts,
            )
        )
    return tuple(aggregated)


def _fit_atlas(
    features: Sequence[str],
    train: _Matrix,
    window: tuple[datetime, datetime],
) -> tuple[MahalanobisFittedModel, FitFacts]:
    """The public ungated model, on a matrix instead of one observation per cell."""
    model = MahalanobisModel()
    space = SignalSpace(signals=tuple((G1_ENTITY, feature) for feature in features))
    if train.shape[0] < model.min_samples:
        fitted = model._empty()
    else:
        variable = [
            column for column in range(train.shape[1]) if float(numpy.std(train[:, column])) > 0.0
        ]
        fitted = (
            model._empty()
            if not variable
            else model._fit_joint(space.select(variable), train[:, variable], window)
        )
    if not isinstance(fitted, MahalanobisFittedModel):
        raise TypeError("ungated Mahalanobis fit did not return its own fitted type")
    facts = FitFacts(
        train_rows=int(train.shape[0]),
        train_features=len(features),
        atlas_signals=fitted.signal_space.size,
    )
    return fitted, facts


def _fit_opponents(
    features: Sequence[str], train: _Matrix
) -> tuple[dict[str, RangeBound], dict[str, SteadyFeature], dict[str, HistogramFeature]]:
    """Published defaults. A non-discrete column is absent from Steadytime and Histogram."""
    minmax: dict[str, RangeBound] = {}
    steady: dict[str, SteadyFeature] = {}
    histogram: dict[str, HistogramFeature] = {}
    for column, feature in enumerate(features):
        values = train[:, column].tolist()
        minmax[feature] = _minmax_bound(values)
        if _more_than(values, DISCRETE_THRESHOLD):
            continue
        steady_model = fit_steadytime(values)
        if steady_model is not None:
            steady[feature] = steady_model
        if len(values) >= HISTOGRAM_WINDOW:
            histogram_model = fit_histogram(values)
            if histogram_model is not None:
                histogram[feature] = histogram_model
    return minmax, steady, histogram


def _minmax_bound(values: Sequence[float]) -> RangeBound:
    """The published MinMax bound, without building a set of every analog sample.

    A column with more than ``DISCRETE_THRESHOLD`` distinct values gets half its
    range as margin. Counting stops at that threshold. The bound is the one
    ``fit_minmax`` returns.
    """
    if _more_than(values, DISCRETE_THRESHOLD):
        low = min(values)
        high = max(values)
        return RangeBound(low=low, high=high, margin=(high - low) / 2.0)
    return fit_minmax(values)


def _more_than(values: Sequence[float], limit: int) -> bool:
    """Return whether ``values`` holds more than ``limit`` distinct numbers."""
    seen: set[float] = set()
    for value in values:
        seen.add(value)
        if len(seen) > limit:
            return True
    return False


def _score_file(
    atlas: MahalanobisFittedModel,
    opponents: tuple[dict[str, RangeBound], dict[str, SteadyFeature], dict[str, HistogramFeature]],
    features: Sequence[str],
    grid: SeriesGrid,
) -> tuple[DetectorScore, ...]:
    from phos.eval.baseline_alerts import (
        _atlas_cells,
        _histogram_cells,
        _minmax_cells,
        _steady_cells,
    )

    if grid.features != tuple(features):
        raise ValueError("a test file does not share the training features")
    minmax, steady, histogram = opponents
    return (
        _score_detector(ATLAS_DETECTOR, _atlas_cells(atlas, features, grid), grid),
        _score_detector(MINMAX_DETECTOR, _minmax_cells(minmax, grid), grid),
        _score_detector(STEADY_DETECTOR, _steady_cells(steady, grid), grid),
        _score_detector(HISTOGRAM_DETECTOR, _histogram_cells(histogram, grid), grid),
    )


def _score_detector(
    detector: str, cells: Sequence[tuple[int, str, float]], grid: SeriesGrid
) -> DetectorScore:
    from phos.eval.baseline_alerts import (
        _attack_intervals,
        _caught,
        _clock,
        _clock_empty,
        _keep_top,
        _point_flags,
        _ranges,
    )

    kept = _keep_top(cells, grid.timestamps)
    intervals = _attack_intervals(grid)
    dataset = _clock(grid.timestamps[0], intervals) if grid.timestamps else _clock_empty()
    recall = recall_within_budget(kept, dataset, G1_ALERTS_PER_SHIFT)
    caught = _caught(kept, intervals)
    attacks = len(intervals)
    if attacks and abs(caught / attacks - recall) > 1e-9:
        raise RuntimeError(f"{detector} budget keep disagrees with recall_within_budget")
    truth, predicted = _point_flags(cells, grid)
    adjusted = point_adjusted_f1(truth.tolist(), predicted.tolist())
    anomaly_ranges = _ranges(truth)
    prediction_ranges = _ranges(predicted)
    reference = etapr_at(anomaly_ranges, prediction_ranges, REFERENCE_ETAPR)
    haicon = etapr_sample_tail(
        anomaly_ranges,
        prediction_ranges,
        theta_p=HAICON_2020.theta_p,
        theta_r=HAICON_2020.theta_r,
        ambiguous_samples=HAICON_2020.ambiguous_samples,
    )
    return DetectorScore(
        detector=detector,
        attacks=attacks,
        caught=caught,
        recall_within_budget=recall,
        etapr_reference_f1=reference.f1,
        etapr_haicon_f1=haicon.f1,
        point_adjusted_f1=adjusted.f1,
        alerts=len(cells),
    )


def _detector(file: FileScore, name: str) -> DetectorScore:
    found = _named(file.scores, name)
    attacks = file.scores[0].attacks
    if found.attacks != attacks:
        raise RuntimeError(f"{file.file} does not share an attack count across detectors")
    return found


def _named(scores: Sequence[DetectorScore], name: str) -> DetectorScore:
    for score in scores:
        if score.detector == name:
            return score
    raise KeyError(name)


def _weighted(parts: Sequence[DetectorScore], field: str, attacks: int) -> float:
    if attacks == 0:
        return 0.0
    total = 0.0
    for part in parts:
        value = getattr(part, field)
        if not isinstance(value, int | float):
            raise TypeError(f"{field} is not a number")
        total += float(value) * part.attacks
    return total / attacks


def median_period_seconds(timestamps: Sequence[datetime]) -> float:
    """Median positive step, in seconds. Zero when the series has no step."""
    if len(timestamps) < 2:
        return 0.0
    ordinals = numpy.asarray([stamp.timestamp() for stamp in timestamps], dtype=numpy.float64)
    deltas = numpy.diff(ordinals)
    positive = deltas[deltas > 0.0]
    if positive.size == 0:
        return 0.0
    return float(numpy.median(positive))
