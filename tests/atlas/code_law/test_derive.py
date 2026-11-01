"""Deriving the valve law from controller source text."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.atlas.code_law.fixtures import CONFIGS_TEXT, DEVICE_TEXT, PLC1_TEXT

from phos.atlas.code_law import (
    DerivedValveLaw,
    Side,
    derive_valve_law,
    pinned_source_from_text,
)
from phos.atlas.declared_law import ControllerSample

AT = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)


def _law() -> DerivedValveLaw:
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=PLC1_TEXT, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.refusals == ()
    assert derivation.law is not None
    return derivation.law


def _sample(**over: float) -> ControllerSample:
    values: dict[str, float] = {
        "level": 5.0,
        "level_min": 3.0,
        "level_max": 7.0,
        "input_valve": 1.0,
        "input_mode": 3.0,
        "bottle_level": 0.8,
        "bottle_max": 1.8,
        "belt": 0.0,
        "output_valve": 1.0,
        "output_mode": 3.0,
    }
    values.update(over)
    return ControllerSample(at=AT, **values)


def test_the_four_literals_come_out_with_their_provenance() -> None:
    law = _law()
    close = law.literal("close")
    open_ = law.literal("open")
    release = law.literal("release_mode")
    belt = law.literal("belt_past_filler")
    assert (close.value, open_.value, release.value, belt.value) == (0.0, 1.0, 3.0, 1.0)
    assert close.file == "src/PLC1.py"
    assert open_.file == "src/PLC1.py"
    assert belt.file == "src/PLC1.py"
    # The release value is a tag default, so it is not in the control program.
    assert release.file == "src/Configs.py"
    for literal in (close, open_, release, belt):
        assert literal.line > 0
    # ADR 0382 bar 1: literal_text is the source node's text, not rebuilt.
    assert close.literal_text == "0"
    assert open_.literal_text == "1"
    assert release.literal_text == "3"
    assert belt.literal_text == "1.0"


def test_the_manual_modes_come_from_the_device_guard() -> None:
    from phos.atlas.code_law import GuardForm

    law = _law()
    guard = law.guard
    assert guard.form is GuardForm.EXCLUSION
    assert guard.manual_modes == (1.0, 2.0)
    assert guard.file == "src/ics_sim/Device.py"
    assert guard.line > 0


def test_the_forced_actuator_writes_are_a_stated_fact() -> None:
    law = _law()
    assert len(law.forced_writes) == 2
    first, second = law.forced_writes
    assert (first.mode, first.value, first.literal_text) == (1.0, 0.0, "0")
    assert (second.mode, second.value, second.literal_text) == (2.0, 1.0, "1")
    assert first.file == "src/ics_sim/Device.py"
    assert second.file == "src/ics_sim/Device.py"
    assert first.line > 0 and second.line > 0


def test_the_input_rule_keeps_the_source_order_and_both_band_ends() -> None:
    law = _law()
    rule = law.rule(Side.INPUT)
    assert [branch.writes for branch in rule.branches] == [0.0, 1.0]
    first, second = rule.branches
    assert [(c.left, c.operator, c.right_signal) for c in first.conditions] == [
        ("tank_level_value", ">", "tank_level_max")
    ]
    assert [(c.left, c.operator, c.right_signal) for c in second.conditions] == [
        ("tank_level_value", "<", "tank_level_min")
    ]
    assert rule.otherwise is None


def test_the_output_rule_is_one_branch_of_two_conditions_with_an_otherwise() -> None:
    law = _law()
    rule = law.rule(Side.OUTPUT)
    assert len(rule.branches) == 1
    branch = rule.branches[0]
    assert branch.writes == 0.0
    assert [(c.left, c.operator, c.right_signal) for c in branch.conditions] == [
        ("bottle_level_value", ">", "bottle_level_max"),
        ("bottle_distance_to_filler_value", ">", None),
    ]
    assert branch.conditions[1].right_literal == 1.0
    assert rule.otherwise == 1.0


def test_the_input_side_requires_nothing_inside_the_band_including_both_ends() -> None:
    law = _law()
    assert law.required(_sample(level=5.0), Side.INPUT) is None
    assert law.required(_sample(level=3.0), Side.INPUT) is None
    assert law.required(_sample(level=7.0), Side.INPUT) is None


def test_the_input_side_closes_above_the_maximum_and_opens_below_the_minimum() -> None:
    law = _law()
    assert law.required(_sample(level=8.0), Side.INPUT) == 0.0
    assert law.required(_sample(level=2.0), Side.INPUT) == 1.0


def test_the_output_side_closes_on_either_condition_and_opens_on_equality() -> None:
    law = _law()
    assert law.required(_sample(bottle_level=2.8), Side.OUTPUT) == 0.0
    assert law.required(_sample(belt=2.0), Side.OUTPUT) == 0.0
    assert law.required(_sample(bottle_level=1.8, belt=1.0), Side.OUTPUT) == 1.0


def test_the_law_is_not_stated_when_either_mode_is_manual() -> None:
    law = _law()
    assert law.stated(_sample()) is True
    assert law.stated(_sample(input_mode=1.0)) is False
    assert law.stated(_sample(output_mode=2.0)) is False


def test_a_mode_the_guard_does_not_name_is_stated_which_is_the_known_divergence() -> None:
    # The guard names 1 and 2. Mode 4 is neither, so the derived law states the
    # comparison. The hand-written law treats anything but the release literal as
    # unstated. ADR 0370 names this in advance; it is reported, not patched.
    law = _law()
    assert law.stated(_sample(input_mode=4.0)) is True


def test_source_that_does_not_hold_the_logic_is_refused_not_raised() -> None:
    derivation = derive_valve_law(
        pinned_source_from_text(plc1="x = 1\n", configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.law is None
    assert derivation.refusals != ()


def test_a_guard_with_no_manual_mode_is_refused() -> None:
    derivation = derive_valve_law(
        pinned_source_from_text(
            plc1=PLC1_TEXT,
            configs=CONFIGS_TEXT,
            device="class PLC:\n    def _check_manual_input(self, a, b):\n        return False\n",
        )
    )
    assert derivation.law is None
    assert derivation.refusals != ()
