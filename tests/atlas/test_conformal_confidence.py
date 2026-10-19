"""ADR 0171: explanation confidence is calibrated by the shape of the evidence behind it."""

import pytest

from phos.atlas.conformal_confidence import (
    HIGH_BOUND,
    ShapeCalibrator,
    ShapedOutcome,
    _score_seed,
    leave_one_seed_out,
    summarise,
    wilson_lower,
)
from phos.atlas.consistency_evidence import (
    COMMAND_TO_RESPONSE_MISMATCH,
    CROSS_SIGNAL_MISMATCH,
)
from phos.atlas.templates import SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
from phos.eval.build_declaration import BUILD_HELD_BACK_SEEDS

_BOTH = (COMMAND_TO_RESPONSE_MISMATCH, CROSS_SIGNAL_MISMATCH)
_CROSS = (CROSS_SIGNAL_MISMATCH,)


def _lead(
    seed: int, shape: tuple[str, ...], *, correct: bool | None, raw: float = 0.355
) -> ShapedOutcome:
    return ShapedOutcome(
        seed=seed,
        plant_id="water-treatment",
        scenario="stuck" if correct else "follow",
        lead=SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID if correct is not None else "insufficient_evidence",
        raw_confidence=raw,
        shape=shape,
        contentful=correct is not None,
        correct=correct,
    )


def test_wilson_lower_is_zero_without_data_and_refuses_impossible_counts() -> None:
    assert wilson_lower(0, 0) == 0.0
    with pytest.raises(ValueError):
        wilson_lower(4, 3)
    with pytest.raises(ValueError):
        wilson_lower(-1, 3)


def test_wilson_lower_for_a_perfect_record_depends_on_its_size() -> None:
    assert wilson_lower(33, 33) == pytest.approx(0.8957, abs=1e-4)
    assert wilson_lower(5, 5) < HIGH_BOUND


def test_an_unseen_shape_is_one_half_and_never_high() -> None:
    fitted = ShapeCalibrator.fit([_lead(97001, _BOTH, correct=True)])
    unseen = fitted.calibrate(_lead(97002, ("other",), correct=True))
    assert unseen.confidence == 0.5
    assert unseen.n == 0
    assert not unseen.high


def test_silence_is_not_counted() -> None:
    fitted = ShapeCalibrator.fit(
        [_lead(97001, (), correct=None), _lead(97001, _BOTH, correct=True)]
    )
    assert fitted.counts == {_BOTH: (1, 1)}


def test_a_perfect_shape_is_high_and_a_failing_shape_is_not() -> None:
    outcomes = [_lead(97000 + i, _BOTH, correct=True) for i in range(1, 34)]
    outcomes += [_lead(97000 + i, _CROSS, correct=False) for i in range(1, 4)]
    fitted = ShapeCalibrator.fit(outcomes)
    good = fitted.calibrate(_lead(97099, _BOTH, correct=True))
    bad = fitted.calibrate(_lead(97099, _CROSS, correct=False))
    assert good.high
    assert good.confidence == pytest.approx(34 / 35)
    assert not bad.high
    assert bad.confidence == pytest.approx(1 / 5)


def test_a_seed_is_scored_by_a_map_that_never_saw_it() -> None:
    outcomes = [
        _lead(97001, _BOTH, correct=True),
        _lead(97002, _BOTH, correct=True),
        _lead(97003, ("only-here",), correct=True),
    ]
    scored = leave_one_seed_out(outcomes)
    lonely = [lead for lead in scored if lead.outcome.seed == 97003]
    assert len(lonely) == 1
    assert lonely[0].n == 0
    assert lonely[0].confidence == 0.5


def test_summary_separates_right_from_wrong_when_shapes_do() -> None:
    outcomes = [_lead(97000 + i, _BOTH, correct=True) for i in range(1, 21)]
    outcomes += [_lead(97000 + i, _CROSS, correct=False) for i in (5, 13, 20)]
    summary = summarise(leave_one_seed_out(outcomes))
    assert summary["shared_calibrated_scores"] == []
    assert summary["shared_raw_scores"] == [0.355]
    assert summary["right"] == 20
    assert summary["high_right_share"] in (None, 1.0)


def test_a_held_back_seed_is_refused_by_the_development_scorer() -> None:
    with pytest.raises(ValueError, match="not in the development split"):
        _score_seed(BUILD_HELD_BACK_SEEDS[0], "development")


def test_the_stuck_water_lead_rests_on_the_ignored_command() -> None:
    outcomes = _score_seed(97002, "development")
    stuck = [o for o in outcomes if o.plant_id == "water-treatment" and o.scenario == "stuck"]
    assert len(stuck) == 1
    assert stuck[0].correct is True
    assert COMMAND_TO_RESPONSE_MISMATCH in stuck[0].shape
