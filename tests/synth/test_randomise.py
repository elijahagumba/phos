"""Drawing is reproducible, addressed by name, and recorded.

The property this module exists for is the one in `phos.synth.randomise`'s docstring and it is
easy to lose by accident: **adding a stream must not shift the numbers an existing stream gets.**
`SeedSequence.spawn` is deterministic by child *index*, so a generator built on it quietly
rewrites every plant ever drawn the day somebody adds a component. The streams here are addressed
by a hash of their name instead, and the test below is what holds that in place.
"""

from __future__ import annotations

import pytest

from phos.synth.randomise import (
    DRAWN_DIGITS,
    DrawError,
    NamingScheme,
    NumberStyle,
    SeedStreams,
    settled,
    stream_key,
)

SEED = 20261112


def test_the_same_name_gives_the_same_numbers() -> None:
    streams = SeedStreams(master_seed=SEED)

    first = [streams.for_("sizing").uniform(0.0, 1.0) for _ in range(3)]
    second = [streams.for_("sizing").uniform(0.0, 1.0) for _ in range(3)]

    assert first == second, "a named stream must restart at the same place every time"


def test_different_names_give_different_numbers() -> None:
    streams = SeedStreams(master_seed=SEED)

    assert streams.for_("sizing").uniform(0.0, 1.0) != streams.for_("tuning").uniform(0.0, 1.0)


def test_the_same_seed_gives_the_same_streams() -> None:
    one = SeedStreams(master_seed=SEED).for_("structure").integers(0, 1000, size=5).tolist()
    two = SeedStreams(master_seed=SEED).for_("structure").integers(0, 1000, size=5).tolist()

    assert one == two


def test_a_different_seed_gives_different_streams() -> None:
    one = SeedStreams(master_seed=SEED).for_("structure").integers(0, 10**9, size=5).tolist()
    two = SeedStreams(master_seed=SEED + 1).for_("structure").integers(0, 10**9, size=5).tolist()

    assert one != two


def test_adding_a_stream_does_not_shift_an_existing_one() -> None:
    """The whole reason streams are addressed by name rather than by spawn index."""
    streams = SeedStreams(master_seed=SEED)
    before = streams.for_("instruments").uniform(0.0, 1.0, size=4).tolist()

    # Ask for several streams that did not exist when `before` was taken, in any order.
    for name in ("faults", "agitation", "weather", "aaa", "zzz"):
        streams.for_(name).uniform(0.0, 1.0)

    after = SeedStreams(master_seed=SEED).for_("instruments").uniform(0.0, 1.0, size=4).tolist()

    assert after == before


def test_stream_keys_are_stable_across_processes() -> None:
    """Pinned values, because a salted hash would reproduce within a run and not between them."""
    assert stream_key("sizing") == stream_key("sizing")
    assert stream_key("sizing") != stream_key("tuning")
    assert 0 <= stream_key("structure") < 2**64


def test_a_draw_records_what_it_took() -> None:
    draw = SeedStreams(master_seed=SEED).draw("sizing")

    area = draw.uniform("tank_area_m2", 20.0, 400.0)
    stages = draw.integer("stages", 2, 4)
    style = draw.choice("tag_style", ("a", "b", "c"))

    assert draw.taken["tank_area_m2"] == area
    assert draw.taken["stages"] == float(stages)
    assert style in ("a", "b", "c")
    assert list(draw.taken) == ["tank_area_m2", "stages", "tag_style"], (
        "the record keeps the order the draws were made in"
    )


def test_drawing_one_name_twice_is_refused() -> None:
    draw = SeedStreams(master_seed=SEED).draw("sizing")
    draw.uniform("area", 1.0, 2.0)

    with pytest.raises(DrawError, match="already drawn"):
        draw.uniform("area", 1.0, 2.0)


def test_an_empty_range_is_refused() -> None:
    draw = SeedStreams(master_seed=SEED).draw("sizing")

    with pytest.raises(DrawError, match="empty range"):
        draw.uniform("fixed", 5.0, 5.0)
    with pytest.raises(DrawError, match="empty range"):
        draw.uniform("inverted", 9.0, 1.0)


def test_a_log_draw_refuses_a_bound_that_reaches_zero() -> None:
    draw = SeedStreams(master_seed=SEED).draw("sizing")

    with pytest.raises(DrawError, match="orders of magnitude"):
        draw.log_uniform("tau", 0.0, 10.0)


def test_a_log_draw_spreads_across_the_decades() -> None:
    """Drawn evenly, nine values in ten would sit in the top decade. That is the point of it."""
    draw = SeedStreams(master_seed=SEED).draw("sizing")

    values = [draw.log_uniform(f"tau_{index}", 1.0, 1000.0) for index in range(600)]
    bottom = sum(1 for value in values if value < 10.0)
    middle = sum(1 for value in values if 10.0 <= value < 100.0)
    top = sum(1 for value in values if value >= 100.0)

    assert min(bottom, middle, top) > 150, (bottom, middle, top)


def test_an_integer_draw_includes_both_bounds() -> None:
    draw = SeedStreams(master_seed=SEED).draw("structure")

    drawn = {draw.integer(f"trains_{index}", 1, 3) for index in range(200)}

    assert drawn == {1, 2, 3}


def test_an_inverted_integer_range_is_refused() -> None:
    draw = SeedStreams(master_seed=SEED).draw("structure")

    with pytest.raises(DrawError, match="inverted range"):
        draw.integer("trains", 3, 1)


def test_choosing_from_nothing_is_refused() -> None:
    draw = SeedStreams(master_seed=SEED).draw("naming")

    with pytest.raises(DrawError, match="no options"):
        draw.choice("style", ())


def test_a_naming_scheme_renders_the_parts_it_was_given() -> None:
    abbreviated = NamingScheme(
        prefix="WTW",
        separator="_",
        number_style=NumberStyle.LOOP,
        upper=True,
        suffix=".PV",
        abbreviate=True,
    )
    spelled = NamingScheme(separator="-", number_style=NumberStyle.PADDED)

    assert abbreviated.tag("level", train=1, stage=2, unit="m") == "WTW_LT_302.PV"
    assert spelled.tag("level", train=1, stage=2, unit="m") == "level-13-m"


def test_number_styles_differ_from_one_another() -> None:
    """At the first position, which is where padding shows.

    Padding only differs below ten, so comparing the styles at train 1 stage 2 would find PLAIN
    and PADDED identical and prove nothing.
    """
    rendered = {
        style: NamingScheme(number_style=style).tag("level", train=0, stage=0, unit="m")
        for style in NumberStyle
    }

    assert len(set(rendered.values())) == len(NumberStyle), rendered
    assert rendered[NumberStyle.PLAIN] == "level_1_m"
    assert rendered[NumberStyle.PADDED] == "level_01_m"
    assert rendered[NumberStyle.LOOP] == "level_101_m"


def test_a_role_with_no_instrument_letters_still_renders() -> None:
    """A family may invent a role.

    It gets its first two letters, and `SignalRole` keeps the meaning — the tag was never where
    the meaning lived.
    """
    scheme = NamingScheme(abbreviate=True, upper=True)

    assert scheme.tag("sparge_rate", train=0, stage=0, unit="kg/h") == "SP_1"


def test_engineering_units_are_rendered_as_tag_tokens() -> None:
    scheme = NamingScheme(separator="_")

    assert scheme.tag("inflow", train=0, stage=0, unit="m3/h").endswith("m3ph")
    assert scheme.tag("duty", train=0, stage=0, unit="%").endswith("pct")


def _is_settled(value: float) -> bool:
    """Return whether a float already carries no more than `DRAWN_DIGITS` significant digits.

    Stated as a round-trip rather than by counting the digits in a repr, because a repr cannot tell
    a significant trailing zero from a padding one: `123456789012000.0` carries twelve significant
    digits and sixteen characters of mantissa. Formatting and re-reading answers the real question.
    """
    return float(f"{value:.{DRAWN_DIGITS}g}") == value


class TestDrawsAreSettledForCrossArchitectureReproducibility:
    """Every drawn float is rounded at the draw, and ADR 0441 is why.

    A raw `numpy` uniform is **not** bit-reproducible across processor architectures: on arm64 the
    multiply-add inside `low + (high - low) * x` can be fused, rounding once where x86-64 rounds
    twice. `log_uniform` additionally goes through the platform's `libm`. The six standard corpora's
    manifests differed between macOS/arm64 and Linux/x86-64 in exactly one leaf of 404 — one unit in
    the last place of a drawn setpoint — which is how this was found.
    """

    def test_settled_keeps_twelve_significant_digits(self) -> None:
        assert settled(3.5518767597502494) == 3.55187675975
        assert settled(1.0) == 1.0
        assert settled(0.0) == 0.0
        assert settled(-5.4129665744023665) == -5.4129665744

    def test_settled_keeps_relative_precision_at_any_magnitude(self) -> None:
        """Significant digits rather than decimal places, so a gain and a capacity fare alike."""
        assert _is_settled(settled(0.000123456789012345))
        assert _is_settled(settled(123456789012345.6))
        assert settled(0.000123456789012345) == 0.000123456789012
        assert settled(123456789012345.6) == 123456789012000.0

    def test_the_two_values_that_actually_diverged_settle_to_the_same_number(self) -> None:
        """The measured pair from ADR 0441, which is the whole reason this exists."""
        on_arm64, on_x86_64 = 3.55187675975025, 3.5518767597502494

        assert on_arm64 != on_x86_64
        assert settled(on_arm64) == settled(on_x86_64)

    def test_a_uniform_draw_is_settled(self) -> None:
        draw = SeedStreams(1234).draw("physics")
        for index in range(40):
            value = draw.uniform(f"p{index}", 0.1, 900.0)
            assert _is_settled(value), value

    def test_a_log_uniform_draw_is_settled(self) -> None:
        """The one that goes through `math.log` and `math.exp`, so the platform's libm."""
        draw = SeedStreams(1234).draw("physics")
        for index in range(40):
            value = draw.log_uniform(f"t{index}", 30.0, 3600.0)
            assert _is_settled(value), value

    def test_settling_does_not_cost_the_draw_its_range(self) -> None:
        """Rounding must not push a value outside the bounds the family declared."""
        draw = SeedStreams(99).draw("physics")
        for index in range(60):
            assert 2.0 <= draw.uniform(f"p{index}", 2.0, 3.0) <= 3.0
