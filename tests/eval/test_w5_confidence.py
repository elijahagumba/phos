"""ADR 0175: W5 seeds stay in their blocks, and held-back plants are not built early."""

from __future__ import annotations

import pytest

from phos.eval.w5_confidence import (
    KINDS,
    W5AuthorizationError,
    require_w5_seed,
    score_split,
)


def test_w5_kinds_are_the_five_that_were_declared() -> None:
    assert KINDS == (
        "plain_sensor_fault",
        "fault_and_maintenance",
        "subtle_liar",
        "two_sensors",
        "mimic_with_work_order",
    )


def test_used_and_held_back_seeds_are_refused_before_a_plant() -> None:
    require_w5_seed(97401, "development")
    require_w5_seed(97501, "held-back")
    for seed in (94001, 97001, 97101, 97201, 97301, 97401, 97520):
        with pytest.raises(ValueError):
            require_w5_seed(seed, "development" if seed >= 97500 else "held-back")


def test_held_back_split_is_not_built_without_authorization() -> None:
    with pytest.raises(W5AuthorizationError):
        score_split("held-back")
