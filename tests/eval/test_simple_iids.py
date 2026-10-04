"""Hand-worked checks for the three SIMPLE detectors that still have public code.

Wolsing, Thiemt, van Sloun, Wagner, Wehrle and Henze, "Can Industrial Intrusion Detection
Be SIMPLE?", ESORICS 2022. The rules below are the ones in ipal-ids/ipal_ids_framework
``ids/simple/{minmax,steadytime,histogram}.py`` on ``master``, read 2026-10-04. The paper's
Gradient IDS is not in that tree.

Expected alerts are worked out in the comments. Nothing here is a comparison with Atlas,
and nothing is scored against the draft pass criteria.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.eval.datasets import Dataset
from phos.eval.simple_iids import (
    HISTOGRAM_WINDOW,
    SimpleHistogram,
    SimpleMinMax,
    SimpleSteadytime,
    fit_histogram,
    fit_minmax,
    fit_steadytime,
    histogram_alert_indexes,
    minmax_alert_indexes,
    steadytime_alert_indexes,
)
from phos.ontology import Domain, Observation

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _series(feature: str, values: list[float]) -> list[Observation]:
    return [
        Observation(
            id=f"obs_{feature}_{index:012d}",
            entity_ids=["ent_000000000001"],
            feature=feature,
            value=value,
            timestamp=T0 + timedelta(seconds=index),
            domain=Domain.ATLAS,
        )
        for index, value in enumerate(values)
    ]


def _dataset(name: str, observations: list[Observation]) -> Dataset:
    return Dataset(
        name=name,
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        source_note="hand-worked SIMPLE example",
    )


def test_minmax_doubles_a_continuous_range_and_does_not_pad_a_discrete_one() -> None:
    # Eleven distinct values: above the discrete cutoff of 10. Range [0, 10], margin 5.
    # The alert line is [-5, 15]. The endpoints of that line do not alert.
    continuous = fit_minmax([float(value) for value in range(11)])
    assert continuous.margin == pytest.approx(5.0)
    assert minmax_alert_indexes([0.0, 10.0, -5.0, 15.0, -5.1, 15.1], continuous) == [4, 5]
    # Two distinct values: margin is 0, so the trained endpoints are the alert line.
    discrete = fit_minmax([0.0, 1.0, 0.0, 1.0])
    assert discrete.margin == 0.0
    assert minmax_alert_indexes([0.0, 1.0, 2.0], discrete) == [2]


def test_minmax_score_matches_the_public_overshoot() -> None:
    # value 16, trained [0, 10], margin 5.
    # overshoot = |5 - 16| - 5 = 6, divided by the margin, is 1.2.
    bound = fit_minmax([float(value) for value in range(11)])
    model = SimpleMinMax.fit(_dataset("train", _series("flow", [float(v) for v in range(11)])))
    alerts = model.run(_dataset("live", _series("flow", [16.0])))
    assert len(alerts) == 1
    assert alerts[0].score == pytest.approx(1.2)
    assert alerts[0].feature == "flow"
    assert bound.low == 0.0


def test_steadytime_alerts_on_a_completed_run_that_leaves_the_trained_length() -> None:
    # Train 0 x5, 1 x5, 0 x5. The final run is not stored. Both values have length [5, 5].
    # A run of four 0s, then a 1, is outside that length. With adjust on (the public
    # default) the four samples of the short run alert, and the sample that ended the run
    # does not.
    trained = fit_steadytime([0.0] * 5 + [1.0] * 5 + [0.0] * 5)
    assert trained is not None
    assert steadytime_alert_indexes([0.0] * 4 + [1.0], trained) == [0, 1, 2, 3]
    assert steadytime_alert_indexes([0.0] * 5 + [1.0], trained) == []
    # A value whose runs never finished during training has no bound, so a later run of it
    # does not alert. 0 completed once. 1 never completed.
    unfinished = fit_steadytime([0.0] * 3 + [1.0] * 3)
    assert unfinished is not None
    assert steadytime_alert_indexes([1.0] * 9 + [0.0], unfinished) == []


def test_steadytime_alerts_immediately_on_a_value_training_never_saw() -> None:
    trained = fit_steadytime([0.0] * 5 + [1.0] * 5 + [0.0] * 5)
    assert trained is not None
    assert steadytime_alert_indexes([2.0], trained) == [0]


def test_histogram_alerts_when_a_window_count_leaves_the_trained_band() -> None:
    # Windows of 3 over 0,1,0,1,0,1. Counts of 0 are only 1 or 2, margin 0.5,
    # so a count of 3 (three zeros) is past the band. The window is not full until index 2.
    trained = fit_histogram([0.0, 1.0, 0.0, 1.0, 0.0, 1.0], window_size=3)
    assert trained is not None
    assert histogram_alert_indexes([0.0, 0.0, 0.0], trained, window_size=3) == [2]
    # An unseen value alerts on its own sample and is not fed into the window.
    assert histogram_alert_indexes([2.0, 0.0, 1.0, 0.0], trained, window_size=3) == [0]


def test_a_feature_with_too_many_distinct_values_is_left_alone() -> None:
    values = [float(value) for value in range(11)]
    assert fit_steadytime(values) is None
    assert fit_histogram(values, window_size=3) is None
    steady = SimpleSteadytime.fit(_dataset("train", _series("flow", values)))
    assert steady.run(_dataset("live", _series("flow", [100.0]))) == []


def test_detector_names_are_the_published_method_names() -> None:
    train = _dataset("train", _series("flow", [0.0, 1.0]))
    assert SimpleMinMax.fit(train).name == "simple-minmax"
    assert SimpleSteadytime.fit(train).name == "simple-steadytime"
    assert SimpleHistogram.fit(train).name == "simple-histogram"
    assert HISTOGRAM_WINDOW == 100


def test_histogram_refuses_a_series_shorter_than_its_window() -> None:
    with pytest.raises(ValueError, match="window"):
        fit_histogram([0.0, 1.0, 0.0], window_size=100)
