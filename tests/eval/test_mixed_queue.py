"""ADR 0231's generator, checked before any plant is built."""

from __future__ import annotations

from datetime import timedelta

from phos.eval.build_declaration import QUEUE_DEVELOPMENT_SEEDS, QUEUE_HELD_BACK_SEEDS
from phos.eval.mixed_queue import (
    ATTACK_HOURS,
    JOBS,
    QUIET_TRAIN_HOURS,
    QUIET_TRAIN_SEED,
    SHIFT_HOURS,
    WORK_ORDER_HOURS,
    attack_window,
    hold_value,
    job_for_seed,
    run_spec,
    work_order_for,
)


def test_the_two_batches_start_on_water_and_then_cycle() -> None:
    assert job_for_seed(97651).plant_id == "water-treatment"
    assert job_for_seed(97652).plant_id == "power-generation"
    assert job_for_seed(97653).plant_id == "batch-reactor"
    assert job_for_seed(97654).plant_id == "water-treatment"
    assert job_for_seed(97601).plant_id == "water-treatment"
    assert job_for_seed(97602).sample_seconds == 10
    assert job_for_seed(97603).sensor == "reactor_temp_c"
    assert job_for_seed(97603).asset_id == "reactor"
    assert {job.sample_seconds for job in JOBS} == {30, 10, 60}


def test_quiet_train_is_seed_97001_and_the_shift_is_eight_hours() -> None:
    assert QUIET_TRAIN_SEED == 97001
    assert QUIET_TRAIN_SEED not in QUEUE_DEVELOPMENT_SEEDS
    assert QUIET_TRAIN_SEED not in QUEUE_HELD_BACK_SEEDS
    assert QUIET_TRAIN_HOURS == 24
    assert SHIFT_HOURS == 8


def test_the_work_order_does_not_overlap_the_hold() -> None:
    spec = run_spec(97651, 30, hours=SHIFT_HOURS)
    order = work_order_for(97651, spec, "intake")
    window = attack_window(spec)
    assert order.order_id == "WO-97651"
    assert order.sanctioning
    assert order.asset_id == "intake"
    assert order.end < window.start
    assert (order.start - spec.start) == timedelta(hours=WORK_ORDER_HOURS[0])
    assert (window.end - spec.start) == timedelta(hours=ATTACK_HOURS[1])
    assert window.contains(spec.start + timedelta(hours=6))
    assert not window.contains(spec.start + timedelta(hours=8))
    assert not window.contains(order.end)


def test_the_held_reading_is_nine_tenths_of_the_span() -> None:
    assert hold_value(0.0, 10.0) == 9.0


def test_a_seed_outside_the_batches_is_refused() -> None:
    try:
        job_for_seed(97001)
    except ValueError as error:
        assert "97001" in str(error)
    else:
        raise AssertionError("the quiet-train seed was accepted as a scored seed")
