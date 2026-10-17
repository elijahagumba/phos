"""Explanation confidence is charted and not shown as a probability (ADR 0162)."""

import pytest

from phos.atlas.explanation_calibration import (
    HIGH_CONFIDENCE,
    ExplanationOutcome,
    _report,
    _score_seed,
    expected_calibration_error,
    map_is_flat,
    reliability_bins,
    reliability_svg,
    score_calibration,
    scorecard_numbers,
)
from phos.atlas.templates import SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
from phos.eval.build_declaration import BUILD_HELD_BACK_SEEDS


def _outcome(confidence: float, *, correct: bool, scenario: str = "stuck") -> ExplanationOutcome:
    return ExplanationOutcome(
        seed=97002,
        plant_id="water-treatment",
        scenario=scenario,
        lead=SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        confidence=confidence,
        contentful=True,
        correct=correct,
        n_evidence=2,
    )


def test_a_reliability_bin_is_the_observed_frequency() -> None:
    """Two right leads and one wrong lead in the same bin observe two thirds."""
    outcomes = (
        _outcome(0.35, correct=True),
        _outcome(0.36, correct=True),
        _outcome(0.37, correct=False, scenario="follow"),
        ExplanationOutcome(
            seed=97002,
            plant_id="water-treatment",
            scenario="quiet",
            lead="insufficient_evidence",
            confidence=0.3,
            contentful=False,
            correct=None,
            n_evidence=0,
        ),
    )
    bins = reliability_bins(outcomes)
    occupied = [item for item in bins if item.count]
    assert len(occupied) == 1
    assert occupied[0].count == 3
    assert occupied[0].correct == 2
    assert occupied[0].observed == pytest.approx(2 / 3)
    error = expected_calibration_error(bins)
    assert error is not None
    assert occupied[0].mean_confidence is not None
    assert error == pytest.approx(abs(2 / 3 - occupied[0].mean_confidence))


def test_a_flat_map_is_not_a_ranking() -> None:
    """A band narrower than the frozen span is a base rate."""
    assert map_is_flat((0.916, 0.917))
    assert not map_is_flat((0.2, 0.9))
    with pytest.raises(ValueError, match="span"):
        map_is_flat((0.1, 0.2), span=0.0)


def test_the_chart_names_the_observed_frequency() -> None:
    """The diagram is reconstructable from the bin it draws."""
    bins = reliability_bins((_outcome(0.35, correct=True),))
    drawing = reliability_svg(bins)
    assert "observed=1.000" in drawing
    assert "n=1" in drawing
    assert drawing.startswith("<svg")
    assert drawing.endswith("</svg>")


def test_the_scorecard_does_not_publish_a_calibration() -> None:
    """``calibration`` stays unset when the probability is not surfaced."""
    report = score_calibration("development")
    numbers = scorecard_numbers(report)
    assert numbers["calibration"] is None
    assert report.surfaced is False
    assert report.raw_high_confidence == 0
    assert report.contentful_correct > 0
    assert report.contentful > report.contentful_correct
    assert report.map_flat
    assert report.platt_low is not None
    assert report.platt_high is not None
    assert report.platt_high - report.platt_low < 0.05
    assert report.expected_calibration_error is not None
    assert report.expected_calibration_error > 0.4
    assert all(item.confidence < HIGH_CONFIDENCE for item in report.outcomes)
    assert report.as_dict()["user_facing_probability"] is None


def test_held_back_labels_do_not_fit_a_map() -> None:
    """A chart can be drawn without training Platt on the pairs it charts."""
    report = _report("held-back", (_outcome(0.35, correct=True),), fit_platt=False)
    assert report.platt_coefficient is None
    assert report.platt_low is None
    assert report.map_flat
    assert report.surfaced is False
    assert report.bins[1].count == 1


def test_a_seed_outside_the_split_is_refused_before_a_plant_is_built() -> None:
    """Held-back seeds are not a development calibration."""
    with pytest.raises(ValueError, match="not in the development split"):
        _score_seed(BUILD_HELD_BACK_SEEDS[0], "development")


def test_one_development_seed_leads_with_the_sensor_fault_on_the_stuck_run() -> None:
    """Seed 97002's stuck water lead is the sensor fault, under the high-confidence line."""
    outcomes = _score_seed(97002, "development")
    stuck = [
        item for item in outcomes if item.plant_id == "water-treatment" and item.scenario == "stuck"
    ]
    assert len(stuck) == 1
    assert stuck[0].lead == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    assert stuck[0].correct is True
    assert stuck[0].confidence < HIGH_CONFIDENCE
