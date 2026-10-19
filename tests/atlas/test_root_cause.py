"""ADR 0172: an alert is ranked back to the signal its departure started from."""

from __future__ import annotations

from collections.abc import Mapping

import numpy
import pytest

from phos.atlas import root_cause
from phos.atlas.loop_explainer import every_sensor_subjects
from phos.atlas.root_cause import Tier, rank_root_causes, score_root_causes, upstream_of


class _Map:
    """The four things the ranking reads from a plant map, and nothing else."""

    def __init__(self, drivers: Mapping[int, tuple[int, ...]], modelled: set[int]) -> None:
        self._drivers = dict(drivers)
        self.targets = {k: object() for k in modelled}
        self.names = tuple(f"s{i}" for i in range(5))
        self.mean = numpy.zeros(5)
        self.spread = numpy.ones(5)

    def drivers_of(self, target: int) -> tuple[int, ...]:
        return self._drivers.get(target, ())


def _with_scores(monkeypatch: pytest.MonkeyPatch, scores: Mapping[int, float]) -> None:
    monkeypatch.setattr(root_cause, "_own", lambda _m, _z, k, _row: scores[k])


def test_every_ancestor_is_found_once_at_its_shortest_distance() -> None:
    model = _Map({4: (3, 2), 3: (1,), 2: (1, 0), 1: (4,)}, {1, 2, 3, 4})
    assert upstream_of(model, 4) == {3: 1, 2: 1, 1: 2, 0: 2}  # type: ignore[arg-type]


def test_a_departure_that_starts_upstream_outranks_the_alerting_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 2 is falsified; 4 is downstream of it and breaks because 2 fed it.
    model = _Map({4: (2,), 2: (0,)}, {0, 2, 4})
    _with_scores(monkeypatch, {4: 9.0, 2: 3.0, 0: 0.2})
    ranked = rank_root_causes(model, numpy.zeros((3, 5)), 2, 4)  # type: ignore[arg-type]
    assert [item.column for item in ranked] == [2, 4, 0]
    assert [item.tier for item in ranked] == [Tier.ORIGIN, Tier.INHERITED, Tier.IN_BAND]
    assert ranked[0].distance == 1


def test_within_a_tier_the_larger_departure_and_then_the_nearer_signal_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Map({4: (3, 2), 3: (1,), 2: (1,)}, {1, 2, 3, 4})
    _with_scores(monkeypatch, {4: 0.5, 3: 2.0, 2: 2.0, 1: 0.1})
    ranked = rank_root_causes(model, numpy.zeros((3, 5)), 1, 4)  # type: ignore[arg-type]
    assert [item.column for item in ranked][:2] == [2, 3]
    assert all(item.tier is Tier.ORIGIN for item in ranked[:2])


def test_a_signal_without_a_model_is_in_band(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Map({4: (0,)}, {4})
    _with_scores(monkeypatch, {4: 3.0})
    ranked = rank_root_causes(model, numpy.zeros((3, 5)), 1, 4)  # type: ignore[arg-type]
    assert ranked[0].column == 4
    assert ranked[0].tier is Tier.ORIGIN
    unmodelled = [item for item in ranked if item.column == 0]
    assert unmodelled[0].tier is Tier.IN_BAND
    assert unmodelled[0].own == 0.0


def test_one_subject_scores_and_the_counts_are_consistent() -> None:
    subject = next(s for s in every_sensor_subjects() if s.signal == "raw_turbidity_ntu")
    totals, rows = score_root_causes("development", [subject])
    assert len(rows) == 1
    assert totals.cells >= totals.on_falsified_column
    assert totals.root_in_two >= totals.root_first
    assert totals.other_column_cells == totals.cells - totals.on_falsified_column
    assert totals.root_first > totals.on_falsified_column


def test_an_unknown_split_is_refused() -> None:
    with pytest.raises(ValueError):
        score_root_causes("validation", [])
