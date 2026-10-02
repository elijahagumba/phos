"""Tests for phase-conditional modelling: is this reading normal *now*, not normal in general.

D3 found Atlas wholly blind on the batch reactor. ADR 0018 measured why: pooled across phases, one
signal's variance dominates the covariance trace, and `_shrink`'s scale-dependent target turns that
into an absolute noise floor on *every* signal's conditional sigma — 133.6 units on a plant whose
signals span 4 to 5,420. Every band ends up wider than the range of the signal it judges, so nothing
is ever out of band.

The fixture here is that failure in miniature, and it is built so the two models genuinely disagree:

- `feed_rate` runs at 5,000 during RUN and is flat zero during IDLE, so pooling gives it a variance
  six orders of magnitude above `temp`'s and hoists the shrinkage floor above `temp`'s entire range.
- `temp` sits at 20 during IDLE and 80 during RUN. **80 is perfectly ordinary — in the other
  phase.** A pooled model cannot object to it. A phase-conditional model must.

`test_pooled_model_is_blind_to_a_phase_violation` is the control: it asserts the fixture really does
defeat the shipped model, so that the phase model's success is a measured difference rather than a
test that would pass against anything.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
from pydantic import ValidationError

from phos.atlas.multivariate import (
    MahalanobisModel,
    MultivariateFittedModel,
    PcaResidualModel,
)
from phos.atlas.phased import (
    PhaseConditionalFittedModel,
    PhaseConditionalModel,
    _narrow,
    phase_at,
)
from phos.atlas.vectorise import SignalSpace, VectorisePolicy
from phos.models import BehaviouralModel, FittedModel
from phos.ontology import Deviation, Domain, Observation
from phos.reasoning import evidence_from_deviation, is_out_of_band

T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
STEP = timedelta(seconds=30)
PLANT = "ent_0000000plant"

PHASE = "phase"
FEED = "feed_rate"
TEMP = "temp"

IDLE = 0
RUN = 1
PURGE = 2

IDLE_TEMP = 20.0
RUN_TEMP = 80.0
RUN_FEED = 5000.0


# --------------------------------------------------------------------------------------------
# Fixtures: a two-phase plant whose phases have nothing in common
# --------------------------------------------------------------------------------------------


def reading(row: int, feature: str, value: float) -> Observation:
    return Observation(
        id=f"obs_{row:08d}{feature[:4]}",
        entity_ids=[PLANT],
        feature=feature,
        value=value,
        timestamp=T0 + row * STEP,
        domain=Domain.ATLAS,
    )


def moment(row: int, phase: int, feed: float, temp: float) -> list[Observation]:
    """One fully observed instant of the three-signal plant."""
    return [
        reading(row, PHASE, float(phase)),
        reading(row, FEED, feed),
        reading(row, TEMP, temp),
    ]


def phased_training(cycles: int = 40, seed: int = 5) -> list[Observation]:
    """Alternating IDLE and RUN blocks, each phase internally tight and mutually unlike.

    Within a phase every signal is its phase's level plus small noise, so a per-phase model learns
    a narrow band. Pooled, `feed_rate` swings 0 to 5,000 and swamps everything.
    """
    generator = numpy.random.default_rng(seed)
    observations: list[Observation] = []
    row = 0
    for _ in range(cycles):
        for _ in range(10):
            observations.extend(
                moment(row, IDLE, generator.normal(0.0, 0.5), generator.normal(IDLE_TEMP, 0.4))
            )
            row += 1
        for _ in range(10):
            observations.extend(
                moment(row, RUN, generator.normal(RUN_FEED, 8.0), generator.normal(RUN_TEMP, 0.4))
            )
            row += 1
    return observations


def phase_violation(row: int) -> list[Observation]:
    """An IDLE moment reading RUN's temperature. Every value is one the plant produces daily."""
    return moment(row, IDLE, 0.0, RUN_TEMP)


HEADLESS = [
    Observation(
        id="obs_headless0feed",
        entity_ids=[PLANT],
        feature=FEED,
        value=50_000.0,
        timestamp=T0 + 9999 * STEP,
        domain=Domain.ATLAS,
    ),
    Observation(
        id="obs_headless0temp",
        entity_ids=[PLANT],
        feature=TEMP,
        value=IDLE_TEMP,
        timestamp=T0 + 9999 * STEP,
        domain=Domain.ATLAS,
    ),
]
"""One instant carrying no phase register at all, and a feed rate the plant never produces."""


def fitted_phase_model(**kwargs: object) -> PhaseConditionalFittedModel:
    model = PhaseConditionalModel(phase_feature=PHASE, **kwargs)  # type: ignore[arg-type]
    return model.fit(phased_training())


def comparable(deviations: list[Deviation]) -> list[tuple[str, float, datetime, float, float]]:
    """Everything a deviation asserts, minus its identity.

    `Deviation.id` is minted fresh per instance, so two scorings of one moment are never equal as
    objects however identical their claims. This compares the claims.
    """
    return [
        (d.expected.feature, d.magnitude, d.timestamp, d.expected.low, d.expected.high)
        for d in deviations
    ]


def out_of_band_features(deviations: list[Deviation], observations: list[Observation]) -> set[str]:
    """The features whose reading actually left its band — the boundary reasoning promotes on."""
    by_id = {observation.id: observation for observation in observations}
    return {
        deviation.expected.feature
        for deviation in deviations
        if is_out_of_band(deviation, by_id[deviation.observation_id])
    }


# --------------------------------------------------------------------------------------------
# The control: the fixture really does defeat the shipped model
# --------------------------------------------------------------------------------------------


def test_pooled_model_is_blind_to_a_phase_violation() -> None:
    """The shipped joint model cannot object to RUN's temperature during IDLE.

    This is D3's finding reproduced in eleven lines. If this test ever fails, the fixture has
    stopped reproducing the defect and every phase-model test below has lost its meaning.
    """
    training = phased_training()
    fitted = MahalanobisModel().fit(training)
    probe = phase_violation(9999)

    assert out_of_band_features(fitted.score(training + probe), training + probe) == set()


def test_pooled_bands_are_wider_than_the_signal_they_judge() -> None:
    """The mechanism ADR 0018 measured: an absolute sigma floor set by the widest-ranging signal."""
    fitted = MahalanobisModel().fit(phased_training())
    names = [f for _, f in fitted.signal_space.signals]
    spread = dict(zip(names, fitted._signal_spread(), strict=True))

    # temp spans 20 to 80; its learned band is +/-3 sigma about the conditional mean.
    assert 6.0 * spread[TEMP] > RUN_TEMP - IDLE_TEMP


# --------------------------------------------------------------------------------------------
# The claim: a reading normal in another phase is caught in this one
# --------------------------------------------------------------------------------------------


def test_catches_a_reading_that_is_only_normal_in_another_phase() -> None:
    """The whole point. RUN's temperature during IDLE must leave IDLE's band."""
    fitted = fitted_phase_model()
    probe = phase_violation(9999)

    assert TEMP in out_of_band_features(fitted.score(probe), probe)


def test_does_not_object_to_the_same_reading_in_its_own_phase() -> None:
    """RUN's temperature during RUN is ordinary, and must stay in band."""
    fitted = fitted_phase_model()
    ordinary = moment(9999, RUN, RUN_FEED, RUN_TEMP)

    assert TEMP not in out_of_band_features(fitted.score(ordinary), ordinary)


def test_a_phase_model_is_fitted_for_every_phase_seen_in_training() -> None:
    fitted = fitted_phase_model()

    assert set(fitted.per_phase) == {IDLE, RUN}


def test_each_phase_learned_its_own_band() -> None:
    """The bands must genuinely differ, or routing is decoration."""
    fitted = fitted_phase_model()

    idle_temp = fitted.per_phase[IDLE].expected_ranges[(PLANT, TEMP)]
    run_temp = fitted.per_phase[RUN].expected_ranges[(PLANT, TEMP)]
    assert idle_temp.stddev != run_temp.stddev


# --------------------------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------------------------


def test_phase_at_reads_the_register_per_timestamp() -> None:
    observations = moment(0, IDLE, 0.0, IDLE_TEMP) + moment(1, RUN, RUN_FEED, RUN_TEMP)

    assert phase_at(observations, PHASE) == {T0: IDLE, T0 + STEP: RUN}


def test_phase_at_rounds_a_noisy_register() -> None:
    """A phase ordinal arriving as 0.98 is phase 1; the register is an integer read as a float."""
    observations = [reading(0, PHASE, 0.98)]

    assert phase_at(observations, PHASE) == {T0: 1}


def test_a_moment_is_judged_by_its_own_phase_model() -> None:
    """Routing, asserted against the models directly rather than through their agreement."""
    fitted = fitted_phase_model()
    probe = phase_violation(9999)
    by_id = {observation.id: observation for observation in probe}

    routed = fitted.score(probe)
    assert comparable(routed) == comparable(fitted.per_phase[IDLE].score(probe))
    assert comparable(routed) != comparable(fitted.per_phase[RUN].score(probe))
    assert TEMP in out_of_band_features(routed, list(by_id.values()))


def test_an_unseen_phase_falls_back_rather_than_going_silent() -> None:
    """A phase training never saw must still be judged; silence there is a free pass."""
    fitted = fitted_phase_model()
    unseen = moment(9999, PURGE, 0.0, IDLE_TEMP)

    assert PURGE not in fitted.per_phase
    assert comparable(fitted.score(unseen)) == comparable(fitted.fallback.score(unseen))


def test_the_fallback_spans_the_phase_register_itself() -> None:
    """Per-phase models cannot judge a constant. The fallback is what watches the router's key."""
    fitted = fitted_phase_model()

    assert (PLANT, PHASE) in dict.fromkeys(fitted.fallback.signal_space.signals)
    for model in fitted.per_phase.values():
        assert (PLANT, PHASE) not in dict.fromkeys(model.signal_space.signals)


def test_a_moment_with_no_phase_reading_goes_to_the_registerless_fallback() -> None:
    """No register value at that instant is an absence, not a phase, and must not be guessed."""
    fitted = fitted_phase_model()

    scored = fitted.score(HEADLESS)
    assert comparable(scored) == comparable(fitted.registerless_fallback.score(HEADLESS))
    assert comparable(scored) != comparable(fitted.fallback.score(HEADLESS))


def test_the_registerless_fallback_can_actually_judge_a_headless_moment() -> None:
    """The teeth in the test above, and the reason it is a separate fit.

    `fallback` spans the register; an unrouted moment by definition lacks it; `vectorise` discards a
    row with an unfillable hole. So `fallback` scores *nothing at all* here, and asserting only that
    the two agree would pass on two empty lists while the moment went unjudged.
    """
    fitted = fitted_phase_model()

    assert fitted.fallback.score(HEADLESS) == []
    assert fitted.registerless_fallback.score(HEADLESS) != []


def test_the_registerless_fallback_does_not_span_the_register() -> None:
    """It cannot: the moments it exists for are exactly the ones that never carry one."""
    fitted = fitted_phase_model()

    assert (PLANT, PHASE) not in dict.fromkeys(fitted.registerless_fallback.signal_space.signals)


def test_a_phase_too_rare_to_learn_falls_back() -> None:
    """Below min_samples the inner model learns nothing, and nothing is not a baseline."""
    training = phased_training()
    training.extend(moment(5000, PURGE, 0.0, IDLE_TEMP))
    fitted = PhaseConditionalModel(phase_feature=PHASE, min_samples=8).fit(training)

    assert PURGE not in fitted.per_phase


# --------------------------------------------------------------------------------------------
# Contract conformance — it must be an ordinary model to everything downstream
# --------------------------------------------------------------------------------------------


def test_is_a_behavioural_model_producing_a_fitted_model() -> None:
    model = PhaseConditionalModel(phase_feature=PHASE)

    assert isinstance(model, BehaviouralModel)
    assert isinstance(model.fit(phased_training()), FittedModel)


def test_deviations_pair_with_their_observations_and_promote_to_evidence() -> None:
    """The emitted objects must survive 4A's boundary unchanged (Constitution §3.2)."""
    fitted = fitted_phase_model()
    probe = phase_violation(9999)
    by_id = {observation.id: observation for observation in probe}

    promoted = [
        evidence_from_deviation(d, by_id[d.observation_id], 0.5, summary="phase violation")
        for d in fitted.score(probe)
        if is_out_of_band(d, by_id[d.observation_id])
    ]
    assert promoted
    assert all(evidence.weight == 0.5 for evidence in promoted)


def test_deviations_come_back_in_ascending_timestamp_order() -> None:
    """Scoring buckets by phase; the result must still be a time series."""
    fitted = fitted_phase_model()
    interleaved = (
        phase_violation(9000)
        + moment(9001, RUN, RUN_FEED, IDLE_TEMP)
        + phase_violation(9002)
        + moment(9003, RUN, 0.0, RUN_TEMP)
    )

    stamps = [deviation.timestamp for deviation in fitted.score(interleaved)]
    assert stamps == sorted(stamps)


def test_magnitudes_are_finite_and_non_negative() -> None:
    fitted = fitted_phase_model()
    probe = phase_violation(9999) + moment(10000, RUN, RUN_FEED, RUN_TEMP)

    for deviation in fitted.score(probe):
        assert 0.0 <= deviation.magnitude < float("inf")


def test_fitting_is_deterministic() -> None:
    """Same corpus, same numbers, twice (Constitution §3.7)."""
    first = fitted_phase_model()
    second = fitted_phase_model()

    assert first.model_dump_json() == second.model_dump_json()


def test_the_wrappers_knobs_govern_every_inner_fit() -> None:
    """One setting must not come to mean two things."""
    fitted = fitted_phase_model(band_k=2.5, emit_k=0.75, min_samples=12)

    for model in (*fitted.per_phase.values(), fitted.fallback):
        assert (model.band_k, model.emit_k) == (2.5, 0.75)


def test_the_inner_representation_is_selectable() -> None:
    model = PhaseConditionalModel(phase_feature=PHASE, inner=PcaResidualModel())
    fitted = model.fit(phased_training())

    assert all(m.name == "atlas-pca" for m in fitted.per_phase.values())


# --------------------------------------------------------------------------------------------
# Refusals — what it must decline to do
# --------------------------------------------------------------------------------------------


def test_phase_feature_is_required() -> None:
    """Sniffing for 'a signal with few integer values' would partition a plant on a tap position."""
    with pytest.raises(ValidationError):
        PhaseConditionalModel()  # type: ignore[call-arg]


def test_phase_feature_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        PhaseConditionalModel(phase_feature="")


def test_a_corpus_without_the_register_learns_nothing_and_scores_nothing() -> None:
    """Not an error: an absent register is a fact about the corpus, as the siblings treat it."""
    unphased = [o for o in phased_training() if o.feature != PHASE]
    fitted = PhaseConditionalModel(phase_feature=PHASE).fit(unphased)

    assert fitted.per_phase == {}
    assert fitted.score(unphased) == []


def test_an_empty_corpus_learns_nothing_and_scores_nothing() -> None:
    fitted = PhaseConditionalModel(phase_feature=PHASE).fit([])

    assert fitted.per_phase == {}
    assert fitted.score([]) == []


def test_scoring_a_signal_the_model_never_saw_emits_nothing_for_it() -> None:
    """Unknown is not anomalous (Constitution §3.2)."""
    fitted = fitted_phase_model()
    stranger = [reading(9999, PHASE, float(IDLE)), reading(9999, "vibration", 900.0)]

    assert "vibration" not in {d.expected.feature for d in fitted.score(stranger)}


def test_a_fitted_model_rebuilt_from_its_stored_parameters_scores_identically() -> None:
    """A fitted model is stored parameters, not a live estimator — the PART 4A precedent.

    This is what the closed `InnerFittedModel` union buys: under the abstract
    `MultivariateFittedModel` annotation the covariance would not survive the round trip.
    """
    fitted = fitted_phase_model()
    probe = phase_violation(9999)

    restored = PhaseConditionalFittedModel.model_validate(fitted.model_dump())

    assert restored == fitted
    assert comparable(restored.score(probe)) == comparable(fitted.score(probe))


def test_a_fit_outside_the_union_is_refused_rather_than_silently_stored() -> None:
    """Storing an unlisted model would serialise as the base class and drop its parameters."""

    class Impostor(MultivariateFittedModel):
        def _expected_values(
            self, matrix: numpy.typing.NDArray[numpy.float64]
        ) -> numpy.typing.NDArray[numpy.float64]:
            return matrix

        def _signal_spread(self) -> numpy.typing.NDArray[numpy.float64]:
            return numpy.ones(self.signal_space.size)

    impostor = Impostor(
        name="impostor",
        expected_ranges={},
        feature_ranges={},
        emit_k=1.0,
        band_k=3.0,
        signal_space=SignalSpace(),
        fill_policy=VectorisePolicy(),
        training_window=None,
    )
    with pytest.raises(TypeError, match="InnerFittedModel"):
        _narrow(impostor)


# --------------------------------------------------------------------------------------------
# The settling allowance (A-FIX-2): what the phase being left explains is not a deviation
# --------------------------------------------------------------------------------------------


def settling_probe(row: int, feed: float, temp: float, run_moments: int = 1) -> list[Observation]:
    """An IDLE moment, then ``run_moments`` of RUN whose first reading is ``feed``/``temp``.

    The register flips to RUN at ``row + 1``. That instant is position 0 of the new phase, which is
    where the batch reactor's real transient lives: the register has moved and the plant has not.
    """
    probe = moment(row, IDLE, 0.0, IDLE_TEMP)
    for offset in range(run_moments):
        probe.extend(moment(row + 1 + offset, RUN, feed, temp))
    return probe


def test_a_reading_the_outgoing_phase_explains_is_forgiven_at_a_phase_change() -> None:
    """The transient itself: at the instant RUN begins, the plant still reads IDLE.

    ADR 0019 measured this on the real plant — `reagent_feed_kgph` is out of band in 20 of 20
    batches at the CHARGE flip, because the register leads the physics by one sample.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP)

    assert out_of_band_features(fitted.score(probe), probe) == set()


def test_the_unforgiving_model_does_flag_that_same_reading() -> None:
    """The control: without the allowance, that same reading is a false positive.

    A-FIX-1 left it exactly so, which is what makes the test above a measured difference rather
    than one that would pass against anything.
    """
    fitted = fitted_phase_model(settling_window=timedelta(0))
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP)

    assert out_of_band_features(fitted.score(probe), probe) == {FEED, TEMP}


def test_a_reading_outside_both_phases_is_still_caught_during_settling() -> None:
    """The security claim. The allowance forgives what the outgoing phase explains — nothing more.

    A feed rate the plant never produces in *either* phase must survive the allowance, or the fix
    has simply bought quiet with a blind window.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = settling_probe(9990, feed=50_000.0, temp=IDLE_TEMP)

    assert FEED in out_of_band_features(fitted.score(probe), probe)


def test_the_allowance_expires_with_the_window() -> None:
    """A lagging reading is forgiven at the flip and flagged once the window has passed."""
    window = timedelta(seconds=90)
    fitted = fitted_phase_model(settling_window=window)
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=6)

    by_id = {observation.id: observation for observation in probe}
    flagged = sorted(
        deviation.timestamp
        for deviation in fitted.score(probe)
        if deviation.expected.feature == FEED
        and is_out_of_band(deviation, by_id[deviation.observation_id])
    )
    start = T0 + 9991 * STEP

    assert all(timestamp - start >= window for timestamp in flagged)
    assert flagged, "past the window the lagging reading must be flagged again"


def test_a_forgiven_deviation_names_the_band_it_was_judged_against() -> None:
    """A forgiven moment stays readable, and names what it was judged against.

    Constitution §3.2: it keeps a `Deviation` carrying the real learned band of the phase being
    left, and that band contains the reading.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP)
    by_id = {observation.id: observation for observation in probe}

    flip = T0 + 9991 * STEP
    feed = [d for d in fitted.score(probe) if d.expected.feature == FEED and d.timestamp == flip]

    assert feed, "the forgiven moment must still be reported, not deleted"
    assert feed[0].expected.contains(by_id[feed[0].observation_id].value)
    # IDLE's band for feed sits near zero; RUN's sits near 5,000.
    assert feed[0].expected.mean < RUN_FEED / 2.0


def test_the_allowance_never_creates_a_deviation() -> None:
    """The allowance may only ever weaken a judgement.

    Every deviation it reports must correspond to one the unforgiving model reported for the same
    observation, so nothing is invented.
    """
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=4)
    unforgiving = fitted_phase_model(settling_window=timedelta(0))
    strict = {d.observation_id for d in unforgiving.score(probe)}
    lenient = {
        d.observation_id
        for d in fitted_phase_model(settling_window=timedelta(minutes=10)).score(probe)
    }

    assert lenient <= strict


def test_the_first_phase_run_has_nothing_to_settle_from() -> None:
    """A corpus that opens mid-phase has no outgoing phase, so nothing is forgiven."""
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = moment(9990, RUN, 0.0, IDLE_TEMP)

    assert out_of_band_features(fitted.score(probe), probe) == {FEED, TEMP}


def test_an_unlearned_outgoing_phase_forgives_nothing() -> None:
    """Settling from a phase the model never learned leaves the judgement untouched.

    There is no learned band to be explained by, and inventing a permissive one is precisely the
    blind window this design refuses.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = moment(9990, PURGE, 0.0, IDLE_TEMP) + moment(9991, RUN, 0.0, IDLE_TEMP)

    assert PURGE not in fitted.per_phase
    assert FEED in out_of_band_features(fitted.score(probe), probe)


def test_settling_window_zero_reproduces_the_pre_fix_model_exactly() -> None:
    """The before-and-after switch, mirroring `BreakingConfig.phase_features = {}` in A-FIX-1."""
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=3)
    off = fitted_phase_model(settling_window=timedelta(0))
    training = phased_training()
    baseline = (
        PhaseConditionalModel(phase_feature=PHASE)
        .model_copy(update={"settling_window": timedelta(0)})
        .fit(training)
    )

    assert comparable(off.score(probe)) == comparable(baseline.score(probe))


def test_the_settling_window_survives_serialisation() -> None:
    """A fitted model is stored parameters, and the window is one of them.

    A window that did not round-trip would silently change what a restored model forgives.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=7))
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=3)
    restored = PhaseConditionalFittedModel.model_validate(fitted.model_dump())

    assert restored.settling_window == timedelta(minutes=7)
    assert comparable(restored.score(probe)) == comparable(fitted.score(probe))


def test_a_reading_between_the_two_phases_is_not_forgiven() -> None:
    """Union, not convex hull — the distinction ADR 0019 chose on the measurement.

    Forgiving the *hull* of the two bands would additionally excuse everything between them: for
    the batch reactor's feed that is the whole range 0 to 5,400 kg/h. Both rules remove exactly the
    same false positives, so the wider one buys nothing and costs a much larger blind window. A
    value the plant never holds in either phase must stay visible.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = settling_probe(9990, feed=RUN_FEED / 2.0, temp=IDLE_TEMP)

    assert FEED in out_of_band_features(fitted.score(probe), probe)


def test_the_window_boundary_is_exact() -> None:
    """The allowance must end exactly at the window, not a sample later.

    An off-by-one here drifts in the direction that costs detection rather than false positives,
    which is the direction this PART is least willing to drift in.
    """
    window = timedelta(seconds=90)
    fitted = fitted_phase_model(settling_window=window)
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=6)
    by_id = {observation.id: observation for observation in probe}
    start = T0 + 9991 * STEP

    flagged = sorted(
        deviation.timestamp
        for deviation in fitted.score(probe)
        if deviation.expected.feature == FEED
        and is_out_of_band(deviation, by_id[deviation.observation_id])
    )

    assert flagged[0] - start == window


def test_a_reading_neither_phase_explains_is_reported_as_the_entering_phase_judged_it() -> None:
    """Traceability under the allowance: the band on a surviving deviation must be the real one.

    Substituting the outgoing phase's judgement for a reading that phase does *not* explain would
    leave the deviation naming a band it never satisfied, and hand the calibrator a magnitude
    measured against the wrong baseline.
    """
    lenient = fitted_phase_model(settling_window=timedelta(minutes=10))
    strict = fitted_phase_model(settling_window=timedelta(0))
    probe = settling_probe(9990, feed=50_000.0, temp=IDLE_TEMP)
    flip = T0 + 9991 * STEP

    def feed_at_flip(model: PhaseConditionalFittedModel) -> Deviation:
        return next(
            d for d in model.score(probe) if d.expected.feature == FEED and d.timestamp == flip
        )

    assert comparable([feed_at_flip(lenient)]) == comparable([feed_at_flip(strict)])


def test_the_allowance_never_turns_an_in_band_reading_out_of_band() -> None:
    """It may only ever weaken a judgement, in out-of-band terms as well as in count.

    Judging forgiveness against the *entering* band rather than the outgoing one would substitute
    the outgoing model's verdict for readings that were perfectly in band, turning the allowance
    into a source of false positives.
    """
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP, run_moments=4)
    strict = fitted_phase_model(settling_window=timedelta(0))
    lenient = fitted_phase_model(settling_window=timedelta(minutes=10))

    assert out_of_band_features(lenient.score(probe), probe) <= out_of_band_features(
        strict.score(probe), probe
    )


def test_a_reading_plausible_for_the_outgoing_phase_is_the_known_blind_window() -> None:
    """The exposure ADR 0019 accepts, asserted rather than left implicit.

    Inside the window an attacker who moves a signal to a value that is *normal for the phase just
    left* is not flagged on it. This test exists so the limit cannot be lost silently: if the
    allowance is ever narrowed, this test fails and the ADR must be revisited.
    """
    fitted = fitted_phase_model(settling_window=timedelta(minutes=10))
    probe = settling_probe(9990, feed=0.0, temp=IDLE_TEMP)

    assert FEED not in out_of_band_features(fitted.score(probe), probe)
