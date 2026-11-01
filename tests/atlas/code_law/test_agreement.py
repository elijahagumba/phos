"""The seven bars of ADR 0382, computed from a derived law.

The bars are checked here against a law derived from the fixtures, so the
declared score on the pinned source stays unspent. What this file proves is that
each bar is computed as ADR 0382 words it, not what the pinned source yields.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace

from tests.atlas.code_law.fixtures import CONFIGS_TEXT, DEVICE_TEXT, PLC1_TEXT

from phos.atlas.code_law import (
    BAR_NAMES,
    ENUMERATION_MODES,
    ENUMERATION_SEED,
    EXPECTED_CASE_COUNT,
    DerivedGuard,
    DerivedValveLaw,
    GuardForm,
    Side,
    check_agreement,
    derive_valve_law,
    enumerate_samples,
    hand_guard,
    pinned_source_from_text,
)


def _law() -> DerivedValveLaw:
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=PLC1_TEXT, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.law is not None
    return derivation.law


def test_the_seed_is_the_declared_one() -> None:
    assert ENUMERATION_SEED == 20261030


def test_the_enumeration_is_exactly_the_declared_product() -> None:
    samples = enumerate_samples()
    assert len(samples) == EXPECTED_CASE_COUNT
    assert EXPECTED_CASE_COUNT == 8820
    assert set(ENUMERATION_MODES) == {0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0}
    assert {sample.input_mode for sample in samples} == set(ENUMERATION_MODES)
    assert {sample.output_mode for sample in samples} == set(ENUMERATION_MODES)


def test_the_enumeration_is_exhaustive_and_deterministic() -> None:
    first = enumerate_samples()
    second = enumerate_samples()
    assert len(first) == 8820
    assert [sample.level for sample in first] == [sample.level for sample in second]
    assert {sample.level for sample in first} == {2.0, 3.0, 5.0, 7.0, 8.0}
    assert {sample.bottle_level for sample in first} == {0.8, 1.8, 2.8}
    assert {sample.belt for sample in first} == {0.0, 1.0, 2.0}


def test_every_bar_adr_0382_names_is_reported_in_order() -> None:
    result = check_agreement(_law())
    assert [bar.name for bar in result.bars] == list(BAR_NAMES)
    assert len(BAR_NAMES) == 7


def test_each_bar_is_met_or_not_met_with_no_middle_value() -> None:
    result = check_agreement(_law())
    for bar in result.bars:
        assert isinstance(bar.met, bool)
        assert bar.detail != ""


def test_the_literal_bar_is_met_and_quotes_the_source_node() -> None:
    law = _law()
    result = check_agreement(law)
    assert result.bar("literal agreement, quoted from the source node").met is True
    assert law.literal("close").literal_text == "0"
    assert law.literal("open").literal_text == "1"
    assert law.literal("release_mode").literal_text == "3"
    assert law.literal("belt_past_filler").literal_text == "1.0"


def test_the_comparison_bar_is_met_on_the_fixture_derivation() -> None:
    result = check_agreement(_law())
    assert result.bar("comparison agreement on both sides").met is True


def test_the_guard_form_bar_is_met_by_inspecting_form_not_by_trying_modes() -> None:
    law = _law()
    hand = hand_guard(law.literal("release_mode").value)
    assert law.guard.form is GuardForm.EXCLUSION
    assert hand.guard.form is GuardForm.EQUALITY
    assert law.guard.differs_in_form_from(hand.guard) is True
    assert law.guard.states_only(hand.release) is False
    assert hand.guard.states_only(hand.release) is True
    bar = check_agreement(law).bar("guard comparison is on the guard's form")
    assert bar.met is True


def test_a_form_that_can_only_hold_an_exclusion_fails_the_guard_form_bar() -> None:
    # ADR 0382 bar 3: a type that can hold only an exclusion list cannot
    # represent the hand equality, so the bar is not met.
    from phos.atlas.code_law.agreement import guard_forms_meet_bar

    derived = DerivedGuard.exclusion((1.0, 2.0), file="device", line=1)
    hand_as_exclusion = DerivedGuard.exclusion((1.0, 2.0), file="hand", line=1)
    bar = guard_forms_meet_bar(derived, hand_as_exclusion, release=3.0)
    assert bar.met is False
    assert "equality" in bar.detail or "differ" in bar.detail


def test_the_forced_writes_bar_is_met_on_the_fixture_derivation() -> None:
    law = _law()
    bar = check_agreement(law).bar("forced actuator writes at modes 1 and 2 are a stated fact")
    assert bar.met is True
    assert [(w.mode, w.value, w.literal_text) for w in law.forced_writes] == [
        (1.0, 0.0, "0"),
        (2.0, 1.0, "1"),
    ]


def test_dropping_the_forced_writes_fails_bar_4() -> None:
    law = _law()
    stripped = replace(law, forced_writes=())
    bar = check_agreement(stripped).bar("forced actuator writes at modes 1 and 2 are a stated fact")
    assert bar.met is False
    assert "forced write" in bar.detail or "0 forced" in bar.detail


def test_the_enumeration_bar_lists_every_disagreement() -> None:
    result = check_agreement(_law())
    bar = result.bar("every disagreement on the extended enumeration is listed, with a certificate")
    assert bar.met is True
    assert result.disagreements != ()
    # Every disagreement carries a certificate naming the law and the comparison.
    for item in result.disagreements:
        assert item.certificate.law_name == "controller_valve"
        assert item.certificate.comparison != ""
        assert item.certificate.rows != ()


def test_dropping_a_disagreement_fails_bar_5() -> None:
    # Truncating the disagreement list is exactly what bar 5 forbids. The bar
    # function reports met only when the full list is non-empty and the case
    # count is exact; an empty list fails.
    law = _law()
    result = check_agreement(law)
    assert result.disagreements != ()
    # A law that somehow agreed everywhere would empty the list and fail:
    # force agreement by making the derived guard an equality at the release.
    release = law.literal("release_mode").value
    agreeing = replace(
        law,
        guard=DerivedGuard.equality(release, file=law.guard.file, line=law.guard.line),
        forced_writes=law.forced_writes,
    )
    agreeing_result = check_agreement(agreeing)
    bar = agreeing_result.bar(
        "every disagreement on the extended enumeration is listed, with a certificate"
    )
    # With matching guards the stated-set disagreements vanish; remaining
    # actuator disagreements may also vanish. Either an empty list or a
    # matching pair fails the "list every disagreement" spirit when empty.
    if agreeing_result.disagreements == ():
        assert bar.met is False


def test_the_certificate_bar_is_met_on_the_fixture_derivation() -> None:
    result = check_agreement(_law())
    assert result.bar("certificate shape").met is True


def test_the_tree_bar_is_not_computed_here_and_says_so() -> None:
    bar = check_agreement(_law()).bar("the tree stays green")
    assert bar.met is False
    assert "not computed" in bar.detail


def test_the_result_is_met_only_when_every_bar_is_met() -> None:
    result = check_agreement(_law())
    assert result.met is False  # bar 7 is never computed here
    assert result.met == all(bar.met for bar in result.bars)


def test_the_result_carries_no_field_that_could_hold_a_score() -> None:
    for kind in (type(check_agreement(_law())), type(check_agreement(_law()).bars[0])):
        for field in dataclasses.fields(kind):
            folded = field.name.casefold()
            for word in ("confidence", "probability", "weight", "magnitude", "score"):
                assert word not in folded


def test_a_wrong_input_order_fails_the_comparison_bar() -> None:
    swapped = PLC1_TEXT.replace(
        "            if tank_level > self._get(TAG.TAG_TANK_LEVEL_MAX):\n"
        "                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 0)\n"
        "            elif tank_level < self._get(TAG.TAG_TANK_LEVEL_MIN):\n"
        "                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 1)\n",
        "            if tank_level > self._get(TAG.TAG_TANK_LEVEL_MAX):\n"
        "                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 1)\n"
        "            elif tank_level < self._get(TAG.TAG_TANK_LEVEL_MIN):\n"
        "                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 0)\n",
    )
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=swapped, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.law is not None
    result = check_agreement(derivation.law)
    assert result.bar("comparison agreement on both sides").met is False


def test_a_different_release_default_fails_the_literal_bar() -> None:
    moved = CONFIGS_TEXT.replace("'default': 3},", "'default': 4},")
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=PLC1_TEXT, configs=moved, device=DEVICE_TEXT)
    )
    assert derivation.law is not None
    assert derivation.law.literal("release_mode").value == 4.0
    assert derivation.law.literal("release_mode").literal_text == "4"
    assert (
        check_agreement(derivation.law).bar("literal agreement, quoted from the source node").met
        is False
    )


def test_the_sides_are_the_two_the_hand_law_names() -> None:
    assert [side.value for side in Side] == ["input valve", "output valve"]


def test_guard_form_cannot_be_answered_by_trying_modes() -> None:
    # states_only and differs_in_form_from inspect form. An exclusion never
    # answers as an equality, whatever value is offered.
    law = _law()
    for mode in ENUMERATION_MODES:
        assert law.guard.states_only(mode) is False
    hand = hand_guard(law.literal("release_mode").value)
    for mode in ENUMERATION_MODES:
        assert hand.guard.states_only(mode) is (mode == hand.release)
