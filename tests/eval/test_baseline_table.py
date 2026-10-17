"""The G1 configuration, pinned before any corpus score.

The matrix path has to raise the same alerts as ``ModelDetector`` at threshold 3.0.
The three opponents have to raise the same alerts as their ``run`` methods. The heap
has to keep the same windows as ``recall_within_budget``. No file in ``data/`` is read.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy

from phos.atlas.multivariate import MahalanobisModel, ShrinkageTarget
from phos.eval.baseline_alerts import (
    _atlas_cells,
    _histogram_cells,
    _minmax_cells,
    _steady_cells,
    kept_matches_full_list,
)
from phos.eval.baseline_report import recall_comparison, render_report
from phos.eval.baseline_table import (
    ATLAS_DETECTOR,
    CHECKED_OPPONENTS,
    DETECTORS,
    G1_ALERTS_PER_SHIFT,
    G1_ATLAS_THRESHOLD,
    G1_ENTITY,
    HISTOGRAM_DETECTOR,
    MINMAX_DETECTOR,
    STEADY_DETECTOR,
    CorpusReport,
    DetectorScore,
    FileScore,
    SeriesGrid,
    _fit_atlas,
    _minmax_bound,
    grid_from_columns,
    score_splits,
)
from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.eval.simple_iids import SimpleHistogram, SimpleMinMax, SimpleSteadytime, fit_minmax
from phos.models.detector import ModelDetector
from phos.ontology import Domain, Observation

_START = datetime(2020, 1, 1, tzinfo=UTC)


def test_minmax_bound_matches_the_published_function() -> None:
    discrete = [0.0, 1.0, 0.0, 1.0]
    analog = [float(value) for value in numpy.linspace(0.0, 1.0, 30)]
    assert _minmax_bound(discrete) == fit_minmax(discrete)
    assert _minmax_bound(analog) == fit_minmax(analog)


def test_atlas_configuration_is_the_public_ungated_model() -> None:
    model = MahalanobisModel()
    assert model.shrinkage == 0.05
    assert model.shrinkage_target is ShrinkageTarget.AVERAGE_VARIANCE
    assert model.joint_k == 0.0
    assert model.adaptive_joint_quantile is None
    assert model.emit_k == 1.0
    assert model.band_k == 3.0
    assert G1_ATLAS_THRESHOLD == 3.0
    assert G1_ALERTS_PER_SHIFT == 8
    assert all(name.startswith("g1-baseline:") for name in DETECTORS)
    assert CHECKED_OPPONENTS == frozenset({MINMAX_DETECTOR, STEADY_DETECTOR, HISTOGRAM_DETECTOR})


def test_matrix_path_matches_model_detector_at_the_public_threshold() -> None:
    rng = numpy.random.default_rng(11)
    train = rng.normal(size=(40, 3))
    train[:, 1] = train[:, 0] + 0.01 * rng.normal(size=40)
    train[:, 2] = 0.5 * train[:, 0] + 0.01 * rng.normal(size=40)
    test = rng.normal(size=(12, 3))
    test[:, 1] = test[:, 0] + 0.01 * rng.normal(size=12)
    test[:, 2] = 0.5 * test[:, 0] + 0.01 * rng.normal(size=12)
    test[-1, 0] = 80.0
    features = ("flow", "pressure", "valve")
    train_times = _times(0, 40)
    test_times = _times(100, 12)
    train_obs = _observations(train_times, features, train)
    test_obs = _observations(test_times, features, test)
    fitted_model = MahalanobisModel().fit(train_obs)
    detected = {
        (detection.timestamp, detection.feature, detection.score)
        for detection in ModelDetector(fitted=fitted_model).run(
            Dataset(name="g1-test", domain=Domain.ATLAS, observations=test_obs)
        )
        if detection.score >= G1_ATLAS_THRESHOLD
    }
    fitted, _facts = _fit_atlas(features, train, (train_times[0], train_times[-1]))
    grid = grid_from_columns(test_times, list(features), test, [False] * 12, [False] * 12)
    cells = {
        (grid.timestamps[row], feature, magnitude)
        for row, feature, magnitude in _atlas_cells(fitted, features, grid)
    }
    assert detected
    detected_keys = set()
    for stamp, feature, _score in detected:
        assert feature is not None
        detected_keys.add((stamp, feature))
    assert {(stamp, feature) for stamp, feature, _score in cells} == detected_keys
    by_cell = {(stamp, feature): score for stamp, feature, score in cells}
    for stamp, feature, score in detected:
        assert feature is not None
        assert abs(by_cell[(stamp, feature)] - score) < 1e-9


def test_opponent_cells_match_their_run_methods() -> None:
    features = ("flow", "valve")
    train = numpy.column_stack(
        [
            numpy.linspace(0.0, 10.0, 120),
            numpy.array([0.0, 1.0] * 60),
        ]
    )
    test = numpy.column_stack(
        [
            numpy.array([5.0] * 19 + [100.0]),
            numpy.array([0.0] * 15 + [2.0] * 5),
        ]
    )
    train_times = _times(0, 120)
    test_times = _times(1000, 20)
    train_set = Dataset(
        name="train",
        domain=Domain.ATLAS,
        observations=_observations(train_times, features, train),
    )
    test_set = Dataset(
        name="test",
        domain=Domain.ATLAS,
        observations=_observations(test_times, features, test),
    )
    grid = grid_from_columns(test_times, list(features), test, [False] * 20, [False] * 20)
    minmax = SimpleMinMax.fit(train_set)
    _assert_same(minmax.run(test_set), _minmax_cells(minmax.bounds, grid), grid)
    steady = SimpleSteadytime.fit(train_set)
    _assert_same(steady.run(test_set), _steady_cells(steady.features, grid), grid)
    histogram = SimpleHistogram.fit(train_set)
    _assert_same(histogram.run(test_set), _histogram_cells(histogram.features, grid), grid)


def test_heap_keeps_the_same_windows_as_the_budget_function() -> None:
    times = _times(0, 12)
    attack = [False] * 12
    attack[1] = True
    attack[11] = True
    grid = grid_from_columns(times, ["flow"], numpy.zeros((12, 1)), attack, [False] * 12)
    cells = [(row, "flow", float(row)) for row in range(12)]
    assert kept_matches_full_list(cells, grid)


def test_unscored_rows_leave_the_point_index_and_do_not_count_as_attacks() -> None:
    times = _times(0, 4)
    values = numpy.array([[0.0], [0.0], [0.0], [50.0]])
    grid = grid_from_columns(
        times,
        ["flow"],
        values,
        [False, True, False, True],
        [False, False, True, False],
    )
    train = numpy.array([[float(row)] for row in range(10)])
    _facts, files = score_splits(("flow",), train, (times[0], times[0]), [("file", grid)])
    atlas = files[0].scores[0]
    assert atlas.attacks == 2
    assert atlas.detector == ATLAS_DETECTOR


def test_render_leads_with_recall_and_records_where_atlas_is_below() -> None:
    beaten = _report("hai-20.07", True, "scored", atlas_caught=1, opponent_caught=3)
    missed = _report("hai-22.04", True, "not_scored", atlas_caught=0, opponent_caught=0)
    text = render_report((beaten, missed))
    first_table = text.split("## Beside the headline", maxsplit=1)[0]
    recall_table = first_table.split("## Recall within budget", maxsplit=1)[1]
    assert "Recall within budget" in recall_table
    assert "Point-adjusted F1" not in recall_table
    assert "not the headline" in text
    assert "alpha is not an argument" in text
    assert "pi=0.7" in text
    assert "180 samples" in text
    assert "not scored" in recall_comparison(missed)
    assert "not won" in recall_comparison(missed)
    assert "below" in recall_comparison(beaten)


def test_the_command_does_not_append_the_experiment_log() -> None:
    source = Path("scripts/measure_baseline_table.py").read_text()
    assert "append_to_experiment_log" not in source
    assert "log.jsonl" not in source


def _times(start: int, count: int) -> tuple[datetime, ...]:
    return tuple(_START + timedelta(seconds=start + offset) for offset in range(count))


def _observations(
    timestamps: tuple[datetime, ...],
    features: tuple[str, ...],
    matrix: numpy.ndarray,
) -> list[Observation]:
    observations: list[Observation] = []
    for row, stamp in enumerate(timestamps):
        for column, feature in enumerate(features):
            observations.append(
                Observation(
                    id=f"obs_{row:04d}_{column:02d}",
                    entity_ids=[G1_ENTITY],
                    feature=feature,
                    value=float(matrix[row, column]),
                    timestamp=stamp,
                    domain=Domain.ATLAS,
                )
            )
    return observations


def _assert_same(
    detections: list[Detection],
    cells: list[tuple[int, str, float]],
    grid: SeriesGrid,
) -> None:
    from_run = {(item.timestamp, item.feature, item.score) for item in detections}
    from_cells = {(grid.timestamps[row], feature, score) for row, feature, score in cells}
    assert from_run == from_cells


def _report(
    corpus: str,
    judges: bool,
    status: str,
    *,
    atlas_caught: int,
    opponent_caught: int,
) -> CorpusReport:
    attacks = 4 if status == "scored" else 0
    files: tuple[FileScore, ...] = ()
    if status == "scored":
        files = (
            FileScore(
                file="test",
                scores=tuple(
                    DetectorScore(
                        detector=name,
                        attacks=attacks,
                        caught=atlas_caught if name == ATLAS_DETECTOR else opponent_caught,
                        recall_within_budget=0.0,
                        etapr_reference_f1=0.0,
                        etapr_haicon_f1=0.0,
                        point_adjusted_f1=0.0,
                        alerts=1,
                    )
                    for name in DETECTORS
                ),
            ),
        )
    return CorpusReport(
        corpus=corpus,
        judges=judges,
        status=status,
        note="Git LFS pointer" if status == "not_scored" else "hand",
        sample_period_seconds=None,
        declared_period_seconds=1.0,
        files=files,
    )
