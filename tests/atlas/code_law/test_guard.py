"""The guard type that holds both an exclusion list and an equality (ADR 0382)."""

from __future__ import annotations

import dataclasses

import pytest

from phos.atlas.code_law import DerivedGuard, GuardForm


def test_an_exclusion_states_every_mode_not_in_its_list() -> None:
    guard = DerivedGuard.exclusion((1.0, 2.0), file="device", line=4)
    assert guard.form is GuardForm.EXCLUSION
    assert guard.states(0.0) is True
    assert guard.states(1.0) is False
    assert guard.states(2.0) is False
    assert guard.states(3.0) is True
    assert guard.states(3.3) is True
    assert guard.states(4.0) is True
    assert guard.states(100.0) is True


def test_an_equality_states_only_its_mode() -> None:
    guard = DerivedGuard.equality(3.0, file="hand", line=0)
    assert guard.form is GuardForm.EQUALITY
    assert guard.states(3.0) is True
    assert guard.states(1.0) is False
    assert guard.states(2.0) is False
    assert guard.states(3.3) is False
    assert guard.states(4.0) is False


def test_states_only_answers_from_form_not_by_trying_modes() -> None:
    exclusion = DerivedGuard.exclusion((1.0, 2.0), file="device", line=4)
    equality = DerivedGuard.equality(3.0, file="hand", line=0)
    # An exclusion never states exactly one value, whatever is offered.
    for mode in (0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0):
        assert exclusion.states_only(mode) is False
    assert equality.states_only(3.0) is True
    assert equality.states_only(3.3) is False


def test_differs_in_form_from_inspects_form() -> None:
    exclusion = DerivedGuard.exclusion((1.0, 2.0), file="device", line=4)
    equality = DerivedGuard.equality(3.0, file="hand", line=0)
    other_exclusion = DerivedGuard.exclusion((1.0,), file="other", line=1)
    assert exclusion.differs_in_form_from(equality) is True
    assert equality.differs_in_form_from(exclusion) is True
    assert exclusion.differs_in_form_from(other_exclusion) is False


def test_an_exclusion_refuses_an_empty_manual_list() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DerivedGuard.exclusion((), file="device", line=1)


def test_a_guard_cannot_mix_shapes() -> None:
    with pytest.raises(ValueError, match="exclusion"):
        DerivedGuard(
            form=GuardForm.EXCLUSION,
            manual_modes=(1.0,),
            equals_mode=3.0,
            file="x",
            line=1,
        )
    with pytest.raises(ValueError, match="equality"):
        DerivedGuard(
            form=GuardForm.EQUALITY,
            manual_modes=(1.0,),
            equals_mode=3.0,
            file="x",
            line=1,
        )


def test_no_guard_field_can_hold_a_score() -> None:
    for kind in (DerivedGuard,):
        for field in dataclasses.fields(kind):
            folded = field.name.casefold()
            for word in ("confidence", "probability", "weight", "magnitude", "score"):
                assert word not in folded
