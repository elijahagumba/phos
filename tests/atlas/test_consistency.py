"""The consistency detector is the frozen sandbox candidate, ported without changing a number.

The identity tests load ``experiments/2026-10-04-sandbox/candidate.py``, which exists only in the
lab, so they are ``lab_only``. The rest test the port on its own.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy
import pytest

from phos.atlas import consistency
from phos.atlas.consistency import (
    ScoredFile,
    TrainFile,
    detect,
    events,
    feature_components,
    feature_scores,
    fit,
)

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "experiments" / "2026-10-04-sandbox" / "candidate.py"
FROZEN_SHA256 = "7d485b7298282b6b369d55675804d3017e9f952d1353b5e673c84734720433d4"
START = 1_700_000_000.0

#: Rows of the test file where one instrument is falsified while the plant keeps moving.
LIAR = (4000, 4300)


def _plant(rows: int, seed: int, liar: tuple[int, int] | None = None) -> numpy.ndarray:
    """Five signals: a command, a lagged flow that follows it, their sum, a dead tag, noise."""
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    command = 50.0 + 20.0 * numpy.sin(2.0 * numpy.pi * t / 600.0)
    flow = 2.0 * numpy.roll(command, 10) + rng.normal(0.0, 0.5, rows)
    if liar is not None:
        start, end = liar
        flow[start:end] = flow[start]  # the instrument freezes; the command keeps moving
    level = command + flow + rng.normal(0.0, 0.5, rows)
    dead = numpy.full(rows, 3.0)
    noise = rng.normal(0.0, 1.0, rows)
    return numpy.column_stack([command, flow, level, dead, noise])


def _inputs() -> tuple[list[TrainFile], list[ScoredFile]]:
    first = _plant(6000, 1)
    second = _plant(6000, 2)
    attack = numpy.zeros(6000, dtype=bool)
    attack[5000:5100] = True
    train = [
        TrainFile(values=first, attack=numpy.zeros(6000, dtype=bool)),
        TrainFile(values=second, attack=attack),
    ]
    values = _plant(9000, 3, liar=LIAR)
    values[7000:7100, 4] += 25.0  # one reading leaves its training range
    test = [ScoredFile(time=START + numpy.arange(9000, dtype=numpy.float64), values=values)]
    return train, test


def _frozen() -> ModuleType:
    import hashlib

    data = FROZEN.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FROZEN_SHA256
    spec = importlib.util.spec_from_file_location("frozen_candidate", FROZEN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.lab_only
def test_the_port_returns_the_frozen_candidates_alert_list_exactly() -> None:
    train, test = _inputs()
    frozen = _frozen()
    expected = frozen.run(
        [{"values": f.values, "attack": f.attack} for f in train],
        [{"time": f.time, "values": f.values} for f in test],
    )
    got = detect(train, test)
    assert len(got) == len(expected) == 1
    rows, columns, scores = got[0]
    assert rows, "the fixed input must raise at least one alert"
    assert (rows, columns) == (list(expected[0][0]), list(expected[0][1]))
    assert scores == [float(score) for score in expected[0][2]]


@pytest.mark.lab_only
def test_the_ports_constants_are_the_frozen_files() -> None:
    frozen = _frozen()
    for name in (
        "LAGS",
        "FIT_STEP",
        "RIDGE",
        "RESID_QUANTILE",
        "RANGE_WEIGHT",
        "DETREND_WINDOW",
        "DETREND_STEP",
        "THRESHOLD",
        "FEATURE_GAP",
        "EVENT_WINDOW",
        "EVENT_SPAN",
        "ONSET_FRACTION",
        "ONSET_LEVEL",
        "CALIBRATION_RANK",
        "SECOND_ALERT_MIN_SEPARATION",
        "SHIFT_SECONDS",
    ):
        assert getattr(consistency, name) == getattr(frozen, name), name
    assert consistency.ALERTS_PER_SHIFT == frozen.PER_SHIFT
    assert frozen.CALIBRATION == "insample"
    assert frozen.USE_LOOP and frozen.USE_DETREND


def test_a_frozen_instrument_is_caught_by_the_loop_not_the_range() -> None:
    train, test = _inputs()
    model = fit(train)
    loop, rng = feature_components(model, test[0].values)
    start, end = LIAR
    assert float(loop[start:end, 1].max()) > consistency.THRESHOLD
    assert float(rng[start:end, 1].max()) <= consistency.THRESHOLD
    rows, _columns, _scores = detect(train, test)[0]
    assert any(start <= row < end for row in rows)


def test_feature_scores_are_the_larger_of_the_two_components() -> None:
    train, test = _inputs()
    model = fit(train)
    loop, rng = feature_components(model, test[0].values)
    scores = feature_scores(model, test[0].values)
    numpy.testing.assert_allclose(scores, numpy.maximum(loop, rng), rtol=1e-6, atol=1e-6)


def test_a_dead_signal_never_scores_on_the_loop() -> None:
    train, test = _inputs()
    model = fit(train)
    assert 3 not in model.live.tolist()
    loop, _rng = feature_components(model, test[0].values)
    assert float(numpy.abs(loop[:, 3]).max()) == 0.0


def test_one_event_gives_one_alert_per_shift_slot() -> None:
    scores = numpy.zeros((2000, 2), dtype=numpy.float32)
    scores[100:160, 0] = 5.0
    scores[120:150, 1] = 8.0
    found = events(scores)
    assert len(found) == 1
    assert found[0].score == 8.0
    assert found[0].onset == 100  # the earlier member reaches the strong level first


def test_a_fit_needs_a_training_file() -> None:
    with pytest.raises(ValueError, match="at least one training file"):
        fit([])
