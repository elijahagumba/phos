"""Grouped rows sit beside the published scores. These tests score no HAI file."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy

from phos.eval.baseline_table import (
    ATLAS_DETECTOR,
    HISTOGRAM_DETECTOR,
    MINMAX_DETECTOR,
    STEADY_DETECTOR,
    SeriesGrid,
)
from phos.eval.grouped_rows import (
    GROUPED_ATLAS,
    GROUPED_CORPORA,
    GROUPED_HISTOGRAM,
    GROUPED_MINMAX,
    GROUPED_STEADY,
    attacks_only_grouped_atlas,
    beyond_grouping,
    exposure_of,
    score_grouped_cells,
)


def test_the_grouped_corpora_leave_out_the_clean_hai_editions() -> None:
    """22.04 and 23.05 are scored once, later, not in this pass."""
    assert "hai-22.04" not in GROUPED_CORPORA
    assert "hai-23.05" not in GROUPED_CORPORA
    assert GROUPED_CORPORA == (
        "hai-20.07",
        "hai-21.03",
        "batadal",
        "batch-distillation",
        "data4cyber",
    )


def test_only_the_sandbox_corpora_are_seen() -> None:
    assert exposure_of("hai-20.07") == "seen"
    assert exposure_of("hai-21.03") == "seen"
    assert exposure_of("batadal") is None
    assert exposure_of("data4cyber") is None


def test_beyond_grouping_is_the_signed_gap_in_catches() -> None:
    assert beyond_grouping(5, (6, 4, 3)) == -1
    assert beyond_grouping(9, (3, 2, 2)) == 6


def test_attacks_only_grouped_atlas_catches_are_listed() -> None:
    exclusive = attacks_only_grouped_atlas(
        ("a#0", "a#1", "b#0"),
        (("a#1", "b#2"), ("a#0",)),
    )
    assert exclusive == ("b#0",)


def test_published_cells_become_grouped_names_and_one_event() -> None:
    """Ten consecutive alerts are one event, so the budget keeps one."""
    origin = datetime(2021, 1, 1, tzinfo=UTC)
    stamps = tuple(origin + timedelta(seconds=index) for index in range(20))
    attack = numpy.zeros(20, dtype=numpy.bool_)
    attack[0:12] = True
    grid = SeriesGrid(
        timestamps=stamps,
        features=("flow",),
        values=numpy.zeros((20, 1)),
        attack=attack,
        unscored=numpy.zeros(20, dtype=numpy.bool_),
    )
    cells = tuple((row, "flow", 5.0) for row in range(10))
    published = {
        ATLAS_DETECTOR: cells,
        MINMAX_DETECTOR: ((0, "flow", 1.5),),
        STEADY_DETECTOR: (),
        HISTOGRAM_DETECTOR: (),
    }
    scores, caught = score_grouped_cells(grid, "test.csv", published)
    by_name = {score.detector: score for score in scores}
    assert by_name[GROUPED_ATLAS].caught == 1
    assert by_name[GROUPED_ATLAS].alerts == 1
    assert by_name[GROUPED_MINMAX].caught == 1
    assert by_name[GROUPED_STEADY].caught == 0
    assert by_name[GROUPED_HISTOGRAM].alerts == 0
    assert caught[GROUPED_ATLAS] == ("test.csv#0",)
    assert (
        beyond_grouping(
            by_name[GROUPED_ATLAS].caught,
            (
                by_name[GROUPED_MINMAX].caught,
                by_name[GROUPED_STEADY].caught,
                by_name[GROUPED_HISTOGRAM].caught,
            ),
        )
        == 0
    )
    assert (
        attacks_only_grouped_atlas(
            caught[GROUPED_ATLAS],
            (caught[GROUPED_MINMAX], caught[GROUPED_STEADY], caught[GROUPED_HISTOGRAM]),
        )
        == ()
    )


def test_the_grouped_section_names_seen_and_does_not_score_later_hai() -> None:
    from phos.eval.baseline_table import DetectorScore
    from phos.eval.grouped_rows import GroupedRow, render_grouped_section

    score = DetectorScore(
        detector=GROUPED_ATLAS,
        attacks=2,
        caught=1,
        recall_within_budget=0.5,
        etapr_reference_f1=0.0,
        etapr_haicon_f1=0.0,
        point_adjusted_f1=0.0,
        alerts=1,
    )
    text = render_grouped_section(
        (
            GroupedRow(
                corpus="hai-20.07",
                exposure="seen",
                scores=(score,),
                beyond_grouping=-1,
                attacks_only_grouped_atlas=("test1.csv#0",),
                note="same fit",
            ),
        )
    )
    assert "| hai-20.07 | seen | g1-grouped:atlas-mahalanobis | 1 | 2 | 0.500000 |" in text
    assert "beyond grouping -1" in text
    assert "test1.csv#0" in text
    assert "HAI 22.04 and 23.05 are not scored here" in text
