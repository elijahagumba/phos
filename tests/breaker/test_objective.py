"""Tests for `phos.breaker.objective`: stealth subject to harm (PART S7)."""

from __future__ import annotations

import pytest

from phos.breaker.objective import OBJECTIVE_VERSION, Objective, objective_version, score


def test_score_stealthy_and_harmful_scores_high() -> None:
    result = score(alerts_raised=0, max_alerts=10, physical_effect=True)
    assert result.stealth == 1.0
    assert result.harm == 1.0
    assert result.value == 1.0


def test_score_caught_and_harmless_scores_zero() -> None:
    result = score(alerts_raised=10, max_alerts=10, physical_effect=False)
    assert result.stealth == 0.0
    assert result.harm == 0.0
    assert result.value == 0.0


def test_score_caught_but_harmful_scores_zero() -> None:
    result = score(alerts_raised=10, max_alerts=10, physical_effect=True)
    assert result.stealth == 0.0
    assert result.harm == 1.0
    assert result.value == 0.0


def test_score_stealthy_but_harmless_scores_zero() -> None:
    result = score(alerts_raised=0, max_alerts=10, physical_effect=False)
    assert result.stealth == 1.0
    assert result.harm == 0.0
    assert result.value == 0.0


def test_score_partial_stealth() -> None:
    result = score(alerts_raised=3, max_alerts=10, physical_effect=True)
    assert result.stealth == 0.7
    assert result.harm == 1.0
    assert result.value == 0.7


def test_objective_out_of_range_refused() -> None:
    with pytest.raises(ValueError, match=r"stealth must be in \[0, 1\]"):
        Objective(stealth=1.5, harm=0.5, value=0.75)


def test_version_is_stable_string() -> None:
    assert objective_version() == OBJECTIVE_VERSION
    assert isinstance(OBJECTIVE_VERSION, str)
    assert len(OBJECTIVE_VERSION) > 0


__all__ = []
