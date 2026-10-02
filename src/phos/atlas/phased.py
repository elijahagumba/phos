"""Modelling a plant whose normal is a sequence: is this reading normal *now*, not in general.

`phos.atlas.multivariate` learns one joint model spanning a whole plant, and on a continuous
process that is the right shape. On a **batch** process it is not, and D3 measured what that costs:
Atlas was wholly blind on the batch reactor — zero subsystem events across all twenty attacks, at
every subtlety, and zero across thirty-four hours of normal operation.

**Why a pooled model fails, precisely.** A batch reactor's `reagent_feed_kgph` runs at ~5,400 kg/h
during the charge and is flat zero in the other four phases, so its *pooled* variance is 4.63 x 10^6
while `reactor_pressure_barg` sits at 0.913 — a spread of five million to one. `_shrink` pulls the
covariance toward `shrinkage * trace(cov) / width` times the identity, a target expressed **in the
units of the signals**, so that spread adds 17,842 to every diagonal entry and no signal's
conditional standard deviation can fall below `sqrt(17,842) = 133.6` units. Against `band_k = 3.0`
every band comes out ~801 units wide, while the signals themselves span 4 to 5,420. Thirteen
signals of thirteen end up with a band wider than their entire observed range, the largest
departure anywhere in the attacked corpus is 1.99 against a threshold of 3.0, and nothing is ever
out of band.

**Why conditioning on phase removes the cause rather than the symptom.** `reagent_feed_kgph` only
has that variance because the pool mixes the charge with the four phases in which it is zero. Fitted
within a phase the trace collapses and the floor falls with it — 1.65, 53.3, 40.5, 1.30 and 2.47
across the reactor's five phases — using `_shrink` completely unchanged. That matters: the
measured alternative, making the shrinkage target scale-invariant, revives the batch plant but
flags water treatment's attack-free holdout at *nearly twice* the rate of its attacked corpus. See
[ADR 0018](../../../docs/adr/0018-phase-conditional-modelling-for-a-batch-process.md) for both
measurements and the options that were rejected.

**What this is, honestly.** A mechanical lookup, not mode inference. The phase is read from a
declared signal the plant already publishes — the batch reactor's `batch_phase` register — and
each moment is routed to the model fitted on the moments that reported the same phase. Nothing
here infers an operating mode, clusters a regime, or discovers structure, and the naming says so
(Constitution §3.6).

**The limit that is not handled, stated plainly.** Routing depends on a *reported* signal. An
attacker who can falsify the register to another valid phase routes the moment to the wrong
baseline, and no per-phase model spans the register to notice — within a phase it is constant, so
the existing zero-variance filter drops it. The pooled fallback does span it, which covers an
out-of-range value but not a plausible one. D2 never targets a phase register, so **this risk is
unmeasured and is not claimed to be handled.**
"""

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final, NamedTuple

from pydantic import Field

from phos.atlas.dynamics import LinearDynamicsFittedModel, LinearDynamicsModel
from phos.atlas.multivariate import (
    MahalanobisFittedModel,
    MahalanobisModel,
    MultivariateFittedModel,
    PcaResidualFittedModel,
    PcaResidualModel,
)
from phos.models import BehaviouralModel, FittedModel
from phos.ontology import Deviation, Observation

__all__ = [
    "DEFAULT_SETTLING_WINDOW",
    "InnerFittedModel",
    "InnerModel",
    "PhaseConditionalFittedModel",
    "PhaseConditionalModel",
    "PhaseMoment",
    "phase_at",
    "phase_moments",
]

logger = logging.getLogger(__name__)

type InnerModel = MahalanobisModel | PcaResidualModel | LinearDynamicsModel
"""The joint models a phase may be represented with.

A closed union rather than the abstract `MultivariateModel` because a fitted model is *stored
parameters* (the PART 4A precedent) and must survive `model_dump`/`model_validate` as the concrete
type it is. An abstract annotation would serialise the base fields and silently drop the covariance.
Session C7 adds the VAR residual as a third inner; it is not the public distillation name.
"""

type InnerFittedModel = MahalanobisFittedModel | PcaResidualFittedModel | LinearDynamicsFittedModel
"""The fitted forms of `InnerModel`, for the same reason."""


def phase_at(observations: Sequence[Observation], phase_feature: str) -> dict[datetime, int]:
    """Read the reported phase ordinal at each timestamp.

    Args:
        observations: The corpus to read. Order is irrelevant.
        phase_feature: The feature carrying the phase register, e.g. ``"batch_phase"``.

    Returns:
        The phase at each timestamp that carried a reading of ``phase_feature``. Timestamps with no
        such reading are absent rather than guessed — an absence is not a phase.

    Note:
        The value is rounded, because a phase register is an integer that arrives as a float and may
        carry measurement noise. Rounding is Python's, so exact halves go to even; a register
        reporting 0.5 is not a phase this code can rescue.

        If one timestamp carries two readings of the register the later in input order wins, which
        is what `phos.atlas.vectorise.vectorise` does with a duplicated signal and for the same
        reason: that is a corpus defect, and taking one reading beats averaging two ordinals.
    """
    return {
        observation.timestamp: round(observation.value)
        for observation in observations
        if observation.feature == phase_feature
    }


DEFAULT_SETTLING_WINDOW: Final = timedelta(minutes=10)
"""How long after a phase change the plant is still allowed to resemble the phase it left.

Ten minutes, and the number is measured rather than chosen. On the batch reactor the holdout's
out-of-band rate per moment runs 0.657 at the instant of the flip, decays through ~0.07 over the
next nine samples, and reaches its settled 0.004 at the tenth. Widening the window to twenty
samples removes **no further false positives at all** (28 either way) while the share of attacked
out-of-band deviations it suppresses climbs from 7.6% to 14.6%, and 66.4% unbounded. So the window
stops where the transient stops: past that point it buys nothing and costs monotonically more.

A duration rather than a sample count because settling is physics and physics runs in time; the
same count would mean different things on corpora of different sample intervals. See
[ADR 0019](../../../docs/adr/0019-the-settling-allowance-and-the-blind-window-it-is-bounded-by.md).
"""


class PhaseMoment(NamedTuple):
    """Where one instant sits in the plant's sequence of phases.

    Attributes:
        phase: The phase reported at this instant.
        started_at: When the current run of that phase began, within the observations given.
        previous: The phase this run followed, or ``None`` for the first run in the corpus — which
            has nothing to be settling from.
    """

    phase: int
    started_at: datetime
    previous: int | None


def phase_moments(
    observations: Sequence[Observation], phase_feature: str
) -> dict[datetime, PhaseMoment]:
    """Read each instant's phase, when that phase run began, and the phase it followed.

    Args:
        observations: The corpus to read. Order is irrelevant; instants are walked in time order.
        phase_feature: The feature carrying the phase register.

    Returns:
        One `PhaseMoment` per timestamp that reported a phase. Timestamps with no reading are
        absent, exactly as in `phase_at`.

    Note:
        Everything here is relative to the observations given. Scoring a *slice* of a corpus makes
        that slice's first instant the start of a run with no predecessor, so nothing there is
        forgiven. That is the conservative direction — a settling allowance is only ever granted
        where the sequence proves a phase change happened — and it is why a fold boundary can cost
        a few false positives but can never hide an attack.
    """
    phases = phase_at(observations, phase_feature)
    timestamps = sorted(phases)
    if not timestamps:
        return {}

    moments: dict[datetime, PhaseMoment] = {}
    started_at = timestamps[0]
    last = phases[timestamps[0]]
    previous: int | None = None
    for timestamp in timestamps:
        phase = phases[timestamp]
        if phase != last:
            previous, started_at = last, timestamp
        moments[timestamp] = PhaseMoment(phase=phase, started_at=started_at, previous=previous)
        last = phase
    return moments


def _bucket(
    observations: Sequence[Observation], phase_feature: str
) -> tuple[dict[int, list[Observation]], list[Observation]]:
    """Split observations into per-phase buckets, and those whose instant reported no phase.

    Returns:
        ``(by_phase, unrouted)``. Every observation appears exactly once across the two, so nothing
        is scored twice and nothing is dropped.
    """
    phases = phase_at(observations, phase_feature)
    by_phase: dict[int, list[Observation]] = defaultdict(list)
    unrouted: list[Observation] = []
    for observation in observations:
        phase = phases.get(observation.timestamp)
        if phase is None:
            unrouted.append(observation)
        else:
            by_phase[phase].append(observation)
    return dict(by_phase), unrouted


def _narrow(fitted: MultivariateFittedModel) -> InnerFittedModel:
    """Narrow a fitted inner model to the closed union this module stores it in.

    `MultivariateModel.fit` is annotated with the abstract base, while the fields here hold the
    concrete union so that a fit survives `model_dump`/`model_validate` intact.

    This is not defensive padding. It is what fires if a third joint model is ever added to
    `InnerModel` without being added to `InnerFittedModel` — which would otherwise be stored under
    an abstract annotation, serialise as the base class, and silently drop the learned parameters.

    Raises:
        TypeError: If the fit produced something outside `InnerFittedModel`, naming what to add.
    """
    if not isinstance(
        fitted, MahalanobisFittedModel | PcaResidualFittedModel | LinearDynamicsFittedModel
    ):
        raise TypeError(
            f"{type(fitted).__name__} is not in InnerFittedModel, so storing it would drop its "
            "learned parameters on serialisation; add it to both InnerModel and InnerFittedModel"
        )
    return fitted


class PhaseConditionalModel(BehaviouralModel):
    """Learns one joint model per operating phase, routed by a declared phase register.

    Attributes:
        name: ``"atlas-phase-conditional"``.
        phase_feature: The feature carrying the phase ordinal. **Required, never inferred**:
            sniffing for "a signal with few distinct integer values" would happily partition a plant
            on a tap position or a pump stage count, and a model fitted on that is worse than no
            model because it looks like one.
        inner: How a single phase is represented. Chooses the representation only — every knob
            below governs the fit.
        settling_window: How long after a phase change a reading the *outgoing* phase explains is
            forgiven. See `DEFAULT_SETTLING_WINDOW` for why it is ten minutes and
            `PhaseConditionalFittedModel.score` for exactly what is forgiven. ``timedelta(0)``
            disables the allowance and reproduces A-FIX-1's model exactly, which is how the
            before-and-after is measured.
        min_samples: Inherited, and now counted **per phase** in fully observed timestamps. A phase
            too rare to learn from gets no model and falls through to the pooled fallback.
        band_k: Inherited. Half-width of the reported band, in learned spreads.
        emit_k: Inherited. Departure at which a signal becomes a candidate.

    Invariants:
        The wrapper's `min_samples`, `band_k` and `emit_k` govern every inner fit, so one setting
        cannot come to mean two things.
    """

    name: str = "atlas-phase-conditional"
    phase_feature: str = Field(min_length=1)
    inner: InnerModel = MahalanobisModel()
    settling_window: timedelta = Field(default=DEFAULT_SETTLING_WINDOW, ge=timedelta(0))

    def fit(self, observations: Sequence[Observation]) -> "PhaseConditionalFittedModel":
        """Learn one joint model per reported phase, plus a pooled fallback.

        Args:
            observations: The training corpus. Should be attack-free — see
                `phos.models.train_test_split`.

        Returns:
            A `PhaseConditionalFittedModel` holding one inner model per phase that had enough fully
            observed moments to learn from, and a pooled model fitted across the whole corpus.

        Note:
            A corpus carrying no reading of `phase_feature` yields a model that learned nothing and
            scores nothing, reported through the log rather than raised. An absent register is a
            fact about the corpus, and the sibling models in `phos.models` answer an unlearnable
            corpus the same way.
        """
        inner = self._configured_inner()
        by_phase, _ = _bucket(observations, self.phase_feature)

        if not by_phase:
            logger.warning(
                "%s: no reading of %r in %d observation(s); the fitted model will span no phases "
                "and score nothing",
                self.name,
                self.phase_feature,
                len(observations),
            )
            return PhaseConditionalFittedModel(
                name=self.name,
                expected_ranges={},
                feature_ranges={},
                emit_k=self.emit_k,
                phase_feature=self.phase_feature,
                settling_window=self.settling_window,
                per_phase={},
                fallback=_narrow(inner.fit([])),
                registerless_fallback=_narrow(inner.fit([])),
                starved_phases=(),
            )

        learned: dict[int, InnerFittedModel] = {}
        starved: list[int] = []
        for phase in sorted(by_phase):
            fitted = inner.fit(by_phase[phase])
            if fitted.signal_space.size == 0:
                logger.info(
                    "%s: phase %d has %d observation(s), too few to learn from; it will fall back "
                    "to the pooled model",
                    self.name,
                    phase,
                    len(by_phase[phase]),
                )
                starved.append(phase)
                continue
            learned[phase] = _narrow(fitted)

        logger.info(
            "fitted %s on %d phase(s) of %d seen, keyed on %r",
            self.name,
            len(learned),
            len(by_phase),
            self.phase_feature,
        )
        return PhaseConditionalFittedModel(
            name=self.name,
            expected_ranges={},
            feature_ranges={},
            emit_k=self.emit_k,
            phase_feature=self.phase_feature,
            settling_window=self.settling_window,
            per_phase=learned,
            fallback=_narrow(inner.fit(observations)),
            registerless_fallback=_narrow(
                inner.fit([o for o in observations if o.feature != self.phase_feature])
            ),
            starved_phases=tuple(starved),
        )

    def _configured_inner(self) -> InnerModel:
        """Return `inner` carrying this wrapper's knobs, so there is one source of truth for them.

        `model_copy` rather than a rebuild: every value being written has already been validated
        against the identical constraint on this model, so there is nothing left to check.
        """
        return self.inner.model_copy(
            update={
                "min_samples": self.min_samples,
                "band_k": self.band_k,
                "emit_k": self.emit_k,
            }
        )


class PhaseConditionalFittedModel(FittedModel):
    """One fitted joint model per phase, and the routing that picks between them.

    Attributes:
        phase_feature: The feature the router reads.
        settling_window: How long after a phase change the outgoing phase may still explain a
            reading. ``timedelta(0)`` disables the allowance entirely.
        per_phase: The learned model for each phase, keyed by its ordinal. A phase absent here was
            never seen in training, or was too rare to learn from.
        fallback: A model fitted across the whole training corpus, used for a moment that
            **reported** a phase for which nothing was learned. Emitting nothing there would make an
            unrecognised register value a guaranteed blind spot, which is exactly what an attacker
            able to write to the register would want. Unlike the per-phase models this one spans the
            register itself, so a wild value is out of band on its own terms.
        registerless_fallback: A model fitted across the whole corpus **with the register removed**,
            used for a moment that carried no phase reading at all. It is a separate fit rather than
            a second use of `fallback` for a mechanical reason: `fallback` spans the register, an
            unrouted moment by definition lacks it, and `vectorise` discards any row with an
            unfillable hole — so `fallback` would silently score nothing at all for exactly these
            moments. Suppressing one signal is easier than forging a plausible value for it, so the
            case that is cheaper to attack must not be the one left unwatched.
        starved_phases: Session C7. Ordinals seen in train but too rare to fit a tight inner
            model. They are scored by `fallback`. That is not "the mode was learned."
        expected_ranges: Always empty. There is no single learned band per key here — that is the
            whole point — and the band a reading was actually judged against travels on the emitted
            `Deviation`, which is what Constitution §3.2 requires to be traceable.
        feature_ranges: Always empty, for the same reason `MultivariateFittedModel` leaves it so:
            there is nothing in a learned joint structure to reconstruct a signal it does not span.

    Note:
        Both fallbacks are **pooled across phases**, so both inherit the blindness this module
        exists to remove. That is not an oversight and cannot be fixed here: without a phase reading
        there is no phase to condition on. A moment that reaches either fallback gets the weaker
        judgement Atlas had before this PART, and the blind spot is narrowed rather than closed.
    """

    phase_feature: str = Field(min_length=1)
    settling_window: timedelta = Field(default=DEFAULT_SETTLING_WINDOW, ge=timedelta(0))
    per_phase: Mapping[int, InnerFittedModel]
    fallback: InnerFittedModel
    registerless_fallback: InnerFittedModel
    starved_phases: tuple[int, ...] = Field(default=())

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Route each moment to the model for its reported phase, and judge it there.

        Args:
            observations: The measurements to score. A moment reporting a phase with a learned
                model is judged by it; a moment reporting an unlearned phase is judged by
                `fallback`; a moment carrying no phase reading is judged by `registerless_fallback`.
                Within `settling_window` of a phase change the judgement is then re-tested against
                the phase being *left*, and a reading that phase explains is reported as **it**
                judged it — in band, and so never promoted to evidence. See `_settle`, and ADR 0019
                for the measurement and the blind window it accepts.

        Returns:
            `Deviation`s in ascending timestamp order. Within one timestamp the order follows the
            phase ordinal and then the inner model's own column order, so two runs over one corpus
            produce one ordering (Constitution §3.7).

        Note:
            Each bucket is assembled and scored as its own series, so the inner model's
            forward-fill policy carries a missing reading to the next moment **of the same phase**
            rather than the next moment in wall-clock time. On a corpus where every signal is
            reported at every instant — which is what D1 generates — nothing is ever filled and the
            distinction does not arise. On a sparse corpus it means a carried value can cross a
            phase boundary, which is a weaker guarantee than the pooled model gives and is recorded
            rather than worked around.
        """
        by_phase, unrouted = _bucket(observations, self.phase_feature)

        scored: list[Deviation] = []
        for phase in sorted(by_phase):
            model = self.per_phase.get(phase, self.fallback)
            scored.extend(model.score(by_phase[phase]))
        if unrouted:
            scored.extend(self.registerless_fallback.score(unrouted))

        scored = self._settle(scored, observations)
        return sorted(scored, key=lambda deviation: deviation.timestamp)

    def _settle(
        self, deviations: list[Deviation], observations: Sequence[Observation]
    ) -> list[Deviation]:
        """Re-judge settling deviations against the phase being left, and forgive what it explains.

        Args:
            deviations: What the entering phase's models made of every moment.
            observations: The corpus being scored, for the settling context and the readings.

        Returns:
            The same list, with each settling deviation the outgoing phase explains **replaced by
            the outgoing model's own judgement of it**. Every other deviation is returned
            untouched, and nothing is added or removed.

        Note:
            The replacement is a swap rather than a deletion because a forgiven moment still
            happened and must stay readable (Constitution §3.2). What it carries afterwards is a
            real learned `ExpectedRange` — the outgoing phase's band for that signal at that
            instant — so `phos.reasoning.boundary.is_out_of_band` returns ``False`` for it by
            construction, and no boundary, calibration, grouping or reasoning code changes.

            The outgoing pass runs with ``emit_k = 0`` so that every observed cell is judged, not
            only the ones that were already surprising there. Without it a cell the outgoing phase
            found *perfectly* ordinary would emit nothing, there would be no band to test against,
            and the moments most clearly explained by the phase being left would be the ones the
            allowance failed to reach.

            Settling moments are scored as their own series, so the inner model's forward-fill
            carries a missing reading across the gaps between transitions. On a corpus where every
            signal is reported at every instant — which is what D1 generates — nothing is filled
            and the distinction does not arise.
        """
        if self.settling_window <= timedelta(0):
            return deviations  # a fast path, not a guard: the elapsed test below excludes
            # every moment on its own when the window is zero.

        moments = phase_moments(observations, self.phase_feature)
        settling: dict[int, list[Observation]] = defaultdict(list)
        for observation in observations:
            moment = moments.get(observation.timestamp)
            if moment is None or moment.previous is None:
                continue
            if observation.timestamp - moment.started_at >= self.settling_window:
                continue
            if moment.previous in self.per_phase:
                settling[moment.previous].append(observation)
        if not settling:
            return deviations

        outgoing: dict[str, Deviation] = {}
        for phase in sorted(settling):
            judge = self.per_phase[phase].model_copy(update={"emit_k": 0.0})
            for deviation in judge.score(settling[phase]):
                outgoing[deviation.observation_id] = deviation

        values = {observation.id: observation.value for observation in observations}
        settled: list[Deviation] = []
        forgiven = 0
        for deviation in deviations:
            explained = outgoing.get(deviation.observation_id)
            reading = values[deviation.observation_id]
            if explained is not None and explained.expected.contains(reading):
                settled.append(explained)
                forgiven += 1
            else:
                settled.append(deviation)

        if forgiven:
            logger.info(
                "%s: %d of %d deviation(s) were within %s of a phase change and are explained by "
                "the phase being left",
                self.name,
                forgiven,
                len(deviations),
                self.settling_window,
            )
        return settled
