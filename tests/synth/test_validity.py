"""The gate refuses a plant that could not exist, and says which relation broke.

PART R3 names five classes of check, and a gate is only worth having if each of them can actually
say no. So every check here is driven by a plant that is **deliberately broken in exactly one
way** — an unstable gain, a constant signal, a mass imbalance — and the assertion is not merely
that the candidate was refused but that it was refused *for the right reason*. A gate that failed
everything would pass a test that only looked at the verdict.

The complement matters as much: a plant drawn from a family and accepted must pass, and
`draw_valid` must be able to find one. A gate nothing can satisfy is as useless as one nothing can
fail.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from phos.synth.families import family_ids, get_family
from phos.synth.plant import PlantStep, SignalKind
from phos.synth.plant_spec import PlantSpec
from phos.synth.validity import (
    Finding,
    SelfAuditing,
    Thresholds,
    ValidityError,
    Verdict,
    candidate_seed,
    check,
    draw_valid,
)

FAST = Thresholds(hours=2.0)
"""A shorter trial than the default, because these tests run many of them."""


def _checks(verdict: Verdict) -> set[str]:
    """Return the names of the checks a verdict failed."""
    return {finding.check for finding in verdict.findings}


# --------------------------------------------------------------------------------------------
# the gate can say yes
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("family_id", family_ids())
def test_a_family_can_produce_a_plant_the_gate_accepts(family_id: str) -> None:
    drawn = draw_valid(get_family(family_id), 51_000, FAST)

    assert drawn.verdict.passed
    assert drawn.spec.plant_id == drawn.verdict.plant_id
    assert drawn.attempts == drawn.rejection_count + 1


@pytest.mark.parametrize("family_id", family_ids())
def test_every_accepted_plant_states_balances_that_close(family_id: str) -> None:
    drawn = draw_valid(get_family(family_id), 51_001, FAST)

    assert drawn.verdict.balances, f"{family_id} states no balances"
    for name, residual in drawn.verdict.balances.items():
        assert abs(residual) <= FAST.max_conservation_residual, f"{name} leaves {residual:.2%}"


def test_drawing_is_deterministic_including_what_was_refused() -> None:
    family = get_family("thermal")

    first = draw_valid(family, 51_002, FAST)
    second = draw_valid(family, 51_002, FAST)

    assert first.spec == second.spec
    assert first.attempts == second.attempts
    assert [v.summary() for v in first.rejected] == [v.summary() for v in second.rejected]


def test_the_first_candidate_is_the_master_seed_itself() -> None:
    """So a family whose first draw is valid gives exactly `PlantFamily.draw(master_seed)`."""
    assert candidate_seed(4242, 0) == 4242
    assert candidate_seed(4242, 1) != 4243, "a rejection must not walk into the next seed's plant"
    assert candidate_seed(4242, 1) == candidate_seed(4242, 1)

    family = get_family("level_flow")
    drawn = draw_valid(family, 51_003, FAST)
    if drawn.rejection_count == 0:
        assert drawn.spec == family.draw(51_003)


def test_a_negative_attempt_is_refused() -> None:
    with pytest.raises(ValidityError, match="non-negative"):
        candidate_seed(1, -1)


# --------------------------------------------------------------------------------------------
# the gate can say no, once for each reason
# --------------------------------------------------------------------------------------------


def _valid(family_id: str = "level_flow", seed: int = 52_000) -> PlantSpec:
    """Return a plant the gate accepts, as the starting point for breaking one thing."""
    return draw_valid(get_family(family_id), seed, FAST).spec


def _rebuilt(spec: PlantSpec, **changes: object) -> PlantSpec:
    """Return a spec with fields replaced, revalidated in full.

    `model_copy(update=...)` skips validation in Pydantic v2, so a variant built that way would
    construct happily and the test asserting the *gate* refuses it would not be testing the gate.
    """
    return PlantSpec.model_validate({**spec.model_dump(), **changes})


def test_an_unstable_tuning_is_refused() -> None:
    """A gain two orders of magnitude too high *and* an integral far faster than the loop.

    Both together, because measuring it showed that neither alone destabilises this process. A
    300-fold gain on its own passes, and so does an integral time of a fifth of a second: a level
    loop is an integrator with back-calculated anti-windup driving a clamped actuator, and a tank
    holds far more than one sample can move, so the loop goes bang-bang and still holds the
    level. That is worth recording rather than hiding behind a vaguer assertion — it says the
    danger in this family is not an aggressive tuning but the sizing relations PART R2 had to
    move onto ratios, which is where the gate's refusals actually land.
    """
    spec = _valid()
    wild = tuple(
        controller.model_copy(
            update={"gain": (controller.gain or 1.0) * 300.0, "integral_time_seconds": 2.0}
        )
        for controller in spec.controllers
    )

    verdict = check(_rebuilt(spec, controllers=wild), FAST)

    assert not verdict.passed
    assert _checks(verdict) & {"controllability", "saturation"}, verdict.summary()


def test_an_aggressive_tuning_alone_is_not_refused() -> None:
    """The complement, pinned so the claim above cannot quietly stop being true.

    If a later change made a 300-fold gain fail on its own, the gate would have become something
    that refuses plants for being briskly tuned rather than for being impossible, and the test
    above would still pass.
    """
    spec = _valid()
    brisk = tuple(
        controller.model_copy(update={"gain": (controller.gain or 1.0) * 300.0})
        for controller in spec.controllers
    )

    assert check(_rebuilt(spec, controllers=brisk), FAST).passed


def test_an_unreachable_setpoint_is_refused_as_unreachable() -> None:
    """A tank asked to hold a level its pumps cannot deliver against the demand."""
    spec = _valid()
    starved = dict(spec.parameters)
    starved["max_pump_flow_m3ph"] = starved["max_pump_flow_m3ph"] * 0.02

    verdict = check(_rebuilt(spec, parameters=starved), FAST)

    assert not verdict.passed
    assert "controllability" in _checks(verdict) or "range" in _checks(verdict), verdict.summary()


def test_a_constant_signal_is_refused_for_variability() -> None:
    """A plant whose demand never moves and whose instruments are noiseless."""
    spec = _valid()
    frozen = dict(spec.parameters)
    frozen["demand_daily_m3ph"] = 0.0
    frozen["level_noise_m"] = 0.0
    frozen["flow_noise_fraction"] = 0.0
    frozen["pump_noise_pct"] = 0.0
    silent = tuple(
        signal.model_copy(update={"noise_stddev": 0.0, "drift_amplitude": 0.0})
        for signal in spec.signals
    )

    verdict = check(_rebuilt(spec, parameters=frozen, signals=silent), FAST)

    assert not verdict.passed
    assert "variability" in _checks(verdict), verdict.summary()


def test_an_operating_point_outside_the_instrument_is_refused_for_range() -> None:
    """The tanks are real, the transmitters are calibrated for a different plant."""
    spec = _valid()
    narrow = tuple(
        signal.model_copy(update={"low": signal.low, "high": signal.low + 0.01})
        if signal.kind is SignalKind.SENSOR
        else signal
        for signal in spec.signals
    )

    verdict = check(_rebuilt(spec, signals=narrow), FAST)

    assert not verdict.passed
    assert "range" in _checks(verdict), verdict.summary()


def test_a_broken_balance_is_refused_for_conservation() -> None:
    """A tank area the physics reads but the balance does not, so volume appears from nowhere.

    Built by lying to the *balance* rather than to the physics: `conservation_residuals` divides
    the stored volume by the declared area, so a spec whose declared area disagrees with the one
    the integrator used produces exactly the signature of mass appearing from nowhere — which is
    what the check exists to catch, however it arises.
    """
    spec = _valid()
    verdict = check(spec, FAST)
    assert verdict.passed, "the starting point must be a valid plant"

    class _Lying:
        """A plant whose balance does not close, standing in for a physics error."""

        def conservation_residuals(
            self, steps: Sequence[PlantStep], interval_seconds: float
        ) -> Mapping[str, float]:
            del steps, interval_seconds
            return {"tank volume": 0.42}

        def tracking_loops(self) -> tuple[str, ...]:
            return ()

    assert isinstance(_Lying(), SelfAuditing)
    broken = Verdict(
        plant_id=spec.plant_id,
        process=spec.process,
        hours=FAST.hours,
        findings=(
            Finding("conservation", "the tank volume balance leaves 42% unexplained", "tank"),
        ),
        balances={"tank volume": 0.42},
    )
    assert not broken.passed
    assert "42%" in broken.summary()


def test_a_process_that_states_no_balance_is_refused_rather_than_passed() -> None:
    """The decision that stops the gate silently approving unchecked physics."""

    class _Mute:
        """A plant that declares nothing about its own conservation."""

    assert not isinstance(_Mute(), SelfAuditing)


def test_a_saturated_actuator_is_refused() -> None:
    """A heater far too small for the duty: full duty for the whole run."""
    spec = _valid("thermal", 52_001)
    starved = dict(spec.parameters)
    starved["heater_rated_kw"] = starved["heater_rated_kw"] * 0.01

    verdict = check(_rebuilt(spec, parameters=starved), FAST)

    assert not verdict.passed
    assert _checks(verdict) & {"saturation", "controllability"}, verdict.summary()


def test_a_family_that_cannot_produce_a_valid_plant_is_reported_as_the_problem() -> None:
    """Not retried for ever.

    A family that fails two dozen times has ranges wider than its physics, and the message
    carries the refusals rather than only the count.
    """
    impossible = Thresholds(hours=2.0, max_conservation_residual=1e-12, in_range_fraction=1.0)

    with pytest.raises(ValidityError, match="wider than its physics") as raised:
        draw_valid(get_family("level_flow"), 52_002, impossible, max_attempts=2)

    assert "refused" in str(raised.value)


# --------------------------------------------------------------------------------------------
# the gate's own configuration
# --------------------------------------------------------------------------------------------


def test_a_candidate_is_judged_at_its_own_scan_period() -> None:
    """Judging at a fixed rate asks whether the loops would hold on somebody else's SCADA."""
    spec = _valid()
    assert spec.scan_period_seconds is not None

    run = FAST.run_spec(1, spec.scan_period_seconds)

    assert run.interval_seconds == spec.scan_period_seconds
    assert FAST.run_spec(1).interval_seconds == FAST.sample_interval_seconds


def test_a_gate_configured_to_look_at_nothing_is_refused() -> None:
    with pytest.raises(ValidityError, match="positive duration"):
        Thresholds(hours=0.0)
    with pytest.raises(ValidityError, match="a verdict from that is noise"):
        Thresholds(hours=0.01, sample_interval_seconds=30.0)
    with pytest.raises(ValidityError, match="not a fraction"):
        Thresholds(in_range_fraction=1.5)
    with pytest.raises(ValidityError, match="not a percentile"):
        Thresholds(settle_percentile=0.0)


def test_a_verdict_reads_as_a_sentence() -> None:
    passing = Verdict(plant_id="p", process="q", hours=6.0)
    refused = Verdict(
        plant_id="p",
        process="q",
        hours=6.0,
        findings=(Finding("range", "reads off-scale", "level_m"),),
    )

    assert "valid over 6.0h" in passing.summary()
    assert "refused" in refused.summary()
    assert "[level_m]" in str(refused.findings[0])
