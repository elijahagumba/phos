"""The taxonomy assigns every alert, refuses what it cannot separate, and never presupposes itself.

The procedure these tests pin is the one U1 turns on. Three properties matter more than the HAI
numbers it happened to produce:

1. **Every alert is accounted for.** A queue of 424 events must leave 424 events in the table, with
   the `not_separable` residual stated rather than quietly distributed.
2. **A screen that is not ``assigned`` removes its category from competition.** Refuting a category
   by measurement has to actually stop it being assigned, or the screen is decoration.
3. **The precedence does not presuppose its answer.** On a model whose bands cover declared-normal
   behaviour and whose departures exceed it, the primary categories must come out plant-side. If the
   procedure can only ever say "modelling error", it has not measured anything.
"""

from datetime import UTC, datetime, timedelta

import pandas
import pytest

from phos.eval.taxonomy import (
    ALERT_CATEGORIES,
    NOT_SEPARABLE,
    OVERLAPS_LABELLED_ATTACK,
    AlertUnderReview,
    CorpusScreen,
    MemberDeparture,
    SignalReference,
    _primary,
    classify,
    classify_event,
    contributions,
    signature_of,
    signature_runs,
)
from phos.eval.taxonomy_evidence import (
    AlertRatePair,
    FitLengthPoint,
    cycle_periods,
    noise_scale_ratios,
    sweep_transition,
    trend_strengths,
)

STAMP = datetime(2020, 7, 7, 22, 11, tzinfo=UTC)


def screens(**overrides: str) -> list[CorpusScreen]:
    """Every category screened as ``assigned`` unless overridden to something else."""
    verdicts: dict[str, str] = {
        "modelling_error": "assigned",
        "normal_process_variation": "assigned",
        "genuinely_unusual_benign": "assigned",
        "insufficient_context": "assigned",
        **overrides,
    }
    return [
        CorpusScreen(
            category=category,
            verdict=verdict,  # type: ignore[arg-type]
            basis="fixture",
            what_would_lift_it="a fixture" if verdict == "not_separable" else None,
        )
        for category, verdict in verdicts.items()
    ]


def reference(
    signal: str = "P1_FT02",
    *,
    band: float = 834.0,
    stddev: float = 878.0,
    exceedance: float = 0.4486,
    max_magnitude: float = 7.11,
) -> SignalReference:
    """A reference whose band does not cover its signal's declared-normal variation."""
    return SignalReference(
        signal=signal,
        band_high=band,
        declared_normal_stddev=stddev,
        declared_normal_exceedance=exceedance,
        declared_normal_max_magnitude=max_magnitude,
        reference_hours=60.0,
        at_shrinkage_floor=True,
        envelope_low=0.0,
        envelope_high=2000.0,
    )


def alert(
    magnitude: float = 5.0, *, value: float = 1000.0, attack: bool = False, signal: str = "P1_FT02"
) -> AlertUnderReview:
    """One single-member alert."""
    return AlertUnderReview(
        evidence_id=f"ev_{signal}_{magnitude}",
        timestamp=STAMP,
        subsystem="p1-boiler",
        members=(MemberDeparture(signal=signal, magnitude=magnitude, value=value),),
        overlaps_attack=attack,
    )


class TestEveryAlertIsAccountedFor:
    def test_contributions_total_the_queue(self) -> None:
        alerts = [alert(5.0), alert(6.0), alert(20.0), alert(4.0, attack=True)]
        counted = contributions(classify(alerts, {"P1_FT02": reference()}, screens()))
        assert sum(counted.values()) == len(alerts)

    def test_every_declared_category_appears_even_at_zero(self) -> None:
        counted = contributions(classify([alert()], {"P1_FT02": reference()}, screens()))
        assert set(counted) == set(ALERT_CATEGORIES)

    def test_a_member_without_a_reference_is_refused_rather_than_guessed(self) -> None:
        with pytest.raises(ValueError, match="no declared-normal reference"):
            classify_event(alert(signal="P9_UNKNOWN"), {"P1_FT02": reference()}, screens())

    def test_a_category_screened_twice_is_refused(self) -> None:
        doubled = [*screens(), screens()[0]]
        with pytest.raises(ValueError, match="screened more than once"):
            classify_event(alert(), {"P1_FT02": reference()}, doubled)


class TestTheModelSideTest:
    def test_a_departure_the_model_also_makes_on_normal_data_is_modelling_error(self) -> None:
        verdict = classify_event(alert(5.0), {"P1_FT02": reference()}, screens())
        assert verdict.primary_category == "modelling_error"
        assert "60.00 h" in verdict.basis

    def test_a_departure_larger_than_anything_on_normal_data_is_not_modelling_error(self) -> None:
        verdict = classify_event(alert(20.0), {"P1_FT02": reference()}, screens())
        assert verdict.primary_category == "genuinely_unusual_benign"

    def test_the_plant_side_reading_survives_in_co_firing(self) -> None:
        verdict = classify_event(alert(5.0), {"P1_FT02": reference()}, screens())
        assert "normal_process_variation" in verdict.co_firing

    def test_an_alert_overlapping_an_attack_window_is_not_a_false_alert(self) -> None:
        verdict = classify_event(alert(5.0, attack=True), {"P1_FT02": reference()}, screens())
        assert verdict.primary_category == OVERLAPS_LABELLED_ATTACK
        # What it would otherwise have been called is the reason a queue cannot be ranked.
        assert "modelling_error" in verdict.co_firing


class TestThePrecedenceDoesNotPresupposeItsAnswer:
    def test_a_model_whose_band_covers_normal_reports_a_plant_side_primary(self) -> None:
        # Departure beyond anything the model managed on declared-normal data, and a band that
        # does cover the signal's own variation: nothing here is the model's fault.
        adequate = reference(band=3000.0, stddev=878.0, exceedance=0.0, max_magnitude=2.9)
        verdict = classify_event(alert(4.0), {"P1_FT02": adequate}, screens())
        assert verdict.primary_category == "genuinely_unusual_benign"

    def test_band_coverage_is_reported_but_does_not_decide(self) -> None:
        # A narrow band with a departure beyond declared normal still is not modelling error: the
        # deciding test is what the model did on normal data, not how the band compares to a spread.
        narrow = reference(band=10.0, stddev=878.0, exceedance=0.0, max_magnitude=2.0)
        assert narrow.band_covers_declared_normal is False
        assert classify_event(alert(4.0), {"P1_FT02": narrow}, screens()).primary_category == (
            "genuinely_unusual_benign"
        )


class TestARefutedScreenRemovesItsCategory:
    def test_a_refuted_category_is_never_assigned(self) -> None:
        verdict = classify_event(
            alert(20.0),
            {"P1_FT02": reference()},
            screens(genuinely_unusual_benign="refuted"),
        )
        assert verdict.primary_category == "insufficient_context"
        assert "genuinely_unusual_benign" not in verdict.co_firing

    def test_a_not_separable_category_is_never_assigned(self) -> None:
        verdict = classify_event(
            alert(5.0),
            {"P1_FT02": reference()},
            screens(modelling_error="not_separable", normal_process_variation="not_separable"),
        )
        assert verdict.primary_category == "insufficient_context"

    def test_nothing_firing_is_insufficient_context_rather_than_a_guess(self) -> None:
        outside = reference(max_magnitude=2.0)
        verdict = classify_event(
            alert(4.0, value=9999.0),
            {"P1_FT02": outside},
            screens(genuinely_unusual_benign="refuted"),
        )
        assert verdict.primary_category == "insufficient_context"
        assert "nothing that could decide" in verdict.basis


class TestTwoPlantSideClaimantsAreNotSeparable:
    """The residual is stated rather than distributed — and on HAI it is structurally empty.

    With the discriminators this corpus supports, `normal_process_variation` needs the departure to
    be one the model also makes on declared-normal data and `genuinely_unusual_benign` needs the
    opposite, so the two can never fire together and `classify_event` cannot reach this branch. That
    is a fact about the corpus, not a reason to delete the branch: a `not_separable` count of zero
    has to mean "no two claimants" rather than "we tidied the table", and the only way to keep that
    honest is to have the code that would report a tie and to test it directly.
    """

    def test_a_tie_with_no_rule_is_stated_rather_than_distributed(self) -> None:
        primary, basis = _primary(
            ["normal_process_variation", "sensor_noise"],
            MemberDeparture(signal="P1_FT02", magnitude=4.0, value=100.0),
            reference(),
        )
        assert primary == NOT_SEPARABLE
        assert "no declared rule" in basis

    def test_the_residual_is_unreachable_through_classify_on_this_corpus(self) -> None:
        # Both plant-side discriminators at once is not constructible: they are complements.
        inside = classify_event(alert(5.0), {"P1_FT02": reference()}, screens())
        outside = classify_event(alert(20.0), {"P1_FT02": reference()}, screens())
        assert "genuinely_unusual_benign" not in (inside.primary_category, *inside.co_firing)
        assert "normal_process_variation" not in (outside.primary_category, *outside.co_firing)


class TestAScreenCannotAssignACategoryNothingDecides:
    def test_an_assigned_category_with_no_discriminator_is_refused(self) -> None:
        extended = [
            *screens(),
            CorpusScreen(category="sensor_noise", verdict="assigned", basis="fixture"),
        ]
        with pytest.raises(ValueError, match="no per-event discriminator"):
            classify_event(alert(), {"P1_FT02": reference()}, extended)

    def test_a_refuted_category_with_no_discriminator_is_fine(self) -> None:
        extended = [
            *screens(),
            CorpusScreen(category="sensor_noise", verdict="refuted", basis="fixture"),
        ]
        assert classify_event(alert(), {"P1_FT02": reference()}, extended).primary_category == (
            "modelling_error"
        )


class TestNormalVariationNeedsMoreThanAnInRangeReading:
    def test_an_in_range_reading_with_an_unprecedented_departure_is_not_normal_variation(
        self,
    ) -> None:
        # Every reading inside the declared-normal envelope, joint departure beyond anything the
        # model managed there. This is the shape of a subtle attack and must not be called normal.
        verdict = classify_event(alert(20.0, value=1000.0), {"P1_FT02": reference()}, screens())
        assert verdict.primary_category == "genuinely_unusual_benign"
        assert "normal_process_variation" not in verdict.co_firing


class TestSignatures:
    def test_a_signature_is_the_unit_and_its_departing_signals(self) -> None:
        two = AlertUnderReview(
            evidence_id="ev_two",
            timestamp=STAMP,
            subsystem="p1-boiler",
            members=(
                MemberDeparture(signal="P1_FT02Z", magnitude=4.0, value=1.0),
                MemberDeparture(signal="P1_B400B", magnitude=5.0, value=2.0),
            ),
        )
        assert signature_of(two) == ("p1-boiler", ("P1_B400B", "P1_FT02Z"))

    def test_a_persisting_condition_is_one_run_not_many_events(self) -> None:
        window = timedelta(minutes=1)
        consecutive = [
            alert(5.0).model_copy(update={"timestamp": STAMP + window * index})
            for index in range(5)
        ]
        runs = signature_runs(consecutive, window)
        assert runs[("p1-boiler", ("P1_FT02",))] == (5, 1)

    def test_a_gap_wider_than_the_window_breaks_the_run(self) -> None:
        window = timedelta(minutes=1)
        split = [
            alert(5.0).model_copy(update={"timestamp": STAMP}),
            alert(5.0).model_copy(update={"timestamp": STAMP + timedelta(hours=2)}),
        ]
        assert signature_runs(split, window)[("p1-boiler", ("P1_FT02",))] == (2, 2)

    def test_a_non_positive_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive duration"):
            signature_runs([alert()], timedelta(0))


class TestEvidenceMeasurements:
    def test_an_instrument_that_did_not_get_noisier_is_not_flagged(self) -> None:
        under = pandas.DataFrame({"s": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]})
        baseline = pandas.DataFrame({"s": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]})
        assert noise_scale_ratios(under, baseline, ["s"])["s"].noisier is False

    def test_an_instrument_that_did_get_noisier_is_flagged(self) -> None:
        under = pandas.DataFrame({"s": [0.0, 10.0, 0.0, 10.0, 0.0, 10.0]})
        baseline = pandas.DataFrame({"s": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]})
        assert noise_scale_ratios(under, baseline, ["s"])["s"].noisier is True

    def test_a_trend_inside_an_unmoved_envelope_is_not_separable_from_a_cycle(self) -> None:
        # A monotone run through the same range the reference already covers.
        under = pandas.DataFrame({"s": list(range(100, 0, -1))})
        baseline = pandas.DataFrame({"s": [*range(1, 101), *range(100, 0, -1)] * 3})
        trend = trend_strengths(under, baseline, ["s"])["s"]
        assert trend.drifting is True
        assert trend.separable_from_cycle_phase is False

    def test_a_signal_with_no_trend_is_never_drifting_however_its_envelope_sits(self) -> None:
        under = pandas.DataFrame({"s": [5.0, 1.0, 4.0, 2.0, 5.0, 1.0] * 10})
        baseline = pandas.DataFrame({"s": [50.0, 10.0, 40.0, 20.0] * 30})
        trend = trend_strengths(under, baseline, ["s"])["s"]
        assert trend.drifting is False
        assert trend.separable_from_cycle_phase is False

    def test_a_cycle_period_is_read_off_the_autocorrelation(self) -> None:
        cycle = [*range(10), *range(10, 0, -1)] * 20
        periods = cycle_periods(
            pandas.DataFrame({"s": [float(v) for v in cycle]}), ["s"], sample_seconds=3600.0
        )
        assert periods["s"].first_peak_hours == pytest.approx(20.0, abs=1.0)

    def test_a_constant_signal_reports_no_period_rather_than_a_fabricated_one(self) -> None:
        periods = cycle_periods(pandas.DataFrame({"s": [1.0] * 50}), ["s"], sample_seconds=10.0)
        assert periods["s"].first_peak_hours == 0.0

    def test_a_non_positive_sample_interval_is_refused(self) -> None:
        with pytest.raises(ValueError, match="sample_seconds must be positive"):
            cycle_periods(pandas.DataFrame({"s": [1.0, 2.0]}), ["s"], sample_seconds=0.0)

    def test_two_agreeing_alert_rates_are_indistinguishable(self) -> None:
        assert AlertRatePair(
            reference_pct=55.74, under_review_pct=55.81, reference_hours=60.0
        ).indistinguishable

    def test_two_disagreeing_alert_rates_are_not(self) -> None:
        assert not AlertRatePair(
            reference_pct=2.49, under_review_pct=55.81, reference_hours=60.0
        ).indistinguishable


class TestTheFitLengthSweep:
    def point(self, timestamps: int, alerts: int) -> FitLengthPoint:
        return FitLengthPoint(
            timestamps=timestamps,
            hours=timestamps / 360.0,
            alerts=alerts,
            moments_pct=1.0,
            windows_caught=2,
            n_windows=2,
        )

    def test_a_step_is_bracketed_by_the_pair_it_falls_between(self) -> None:
        curve = [self.point(n, a) for n, a in ((350, 4458), (1400, 4111), (1750, 186), (2800, 116))]
        step = sweep_transition(curve)
        assert step is not None
        assert (step[0].timestamps, step[1].timestamps) == (1400, 1750)

    def test_a_gradual_curve_reports_no_step(self) -> None:
        curve = [self.point(n, a) for n, a in ((350, 400), (700, 350), (1400, 300))]
        assert sweep_transition(curve) is None

    def test_an_unsorted_curve_is_refused(self) -> None:
        curve = [self.point(n, a) for n, a in ((1400, 4111), (350, 4458))]
        with pytest.raises(ValueError, match="ascending fit length"):
            sweep_transition(curve)
