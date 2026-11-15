"""Whether a drawn plant could exist: the checks that refuse one that could not.

PART R3. PART R2 draws a plant from a family's declared bounds. Sampling parameters inside their
own ranges still produces combinations no engineer would build and no process would survive — a
pump that cannot fill its tank against the outlet it is paired with, a loop whose gain and the
loop's time constant put it into sustained oscillation, a vessel whose operating point sits
outside its own instrument span, a signal that never moves. Data from such a plant is not hard
training data; it is wrong, and a model that learns it learns something untrue about industry.

So every candidate is **run** and then judged, and one that fails is refused with the specific
relation it broke named — not clipped, not nudged, not warned about. A refusal is a result here in
the same way it is everywhere else in this repository: it says the family's declared ranges are
wider than its physics, which is a finding about the family and is recorded in the manifest as a
rejection count rather than hidden.

**The gate runs the integrator, which is why it lives here and not in a test.** Some of these
questions can only be settled by stepping the plant and looking: a loop that is stable on paper
can still fail to settle. A check that runs the plant has to refuse a corpus *before* it is
written, not fail a suite afterwards.

**A process that states no balance cannot be validated, and that is a failure rather than a
pass.** Conservation is the one check this module cannot write generically: it does not know which
of a coupling's drivers is an inflow and which an outflow. So a process template declares its own
balances through `conservation_residuals`, and a template that declares none fails the gate. That
is deliberate — the alternative is a gate that silently approves exactly the plants whose physics
nobody checked.

**What this module does not do.** It does not score a detector, it does not know what a plant is
for, and it does not look at labels or attacks. It answers one question — could this plant exist —
and PART R4's events and PART S6's referee are somewhere else entirely.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol, runtime_checkable

import numpy

from phos.synth.families import PlantFamily
from phos.synth.plant import PlantStep, RunSpec, SignalKind
from phos.synth.plant_spec import ControllerKind, PlantSpec
from phos.synth.templates import build_from_spec

__all__ = [
    "MAX_ATTEMPTS",
    "Finding",
    "Thresholds",
    "ValidDraw",
    "ValidityError",
    "Verdict",
    "candidate_seed",
    "check",
    "draw_valid",
]

logger = logging.getLogger(__name__)

MAX_ATTEMPTS: Final = 24
"""How many candidates may be refused before the family itself is reported as the problem.

A family that cannot produce a valid plant in two dozen tries has declared ranges that do not
describe its physics, and resampling for ever would hide that behind a slow generator."""

_TRIAL_START: Final = datetime(2026, 1, 1, tzinfo=UTC)
"""Fixed start instant for a trial run, so a verdict does not depend on the day it was taken."""


@dataclass(frozen=True)
class Thresholds:
    """What the gate requires, with every bar a named number rather than a literal in a branch.

    Attributes:
        hours: How long a candidate is run for before it is judged. Longer finds slow failures —
            a loop that creeps, a tank that fills over an afternoon — and costs time per draw.
        sample_interval_seconds: Sampling and integration step of the trial run, used only for a
            plant that declares no control network. A plant that declares one is judged at **its
            own scan period**, because in this engine the sample interval is also the interval
            the controllers run at: judging a plant at a rate it did not choose asks whether its
            loops would be stable on somebody else's SCADA system, which is not a question about
            the plant.
        warmup_fraction: Fraction of the run ignored before judging. A plant is started at its
            operating point, so this is short; it exists because the first few samples of any
            closed loop carry its own initial transient.
        in_range_fraction: Fraction of samples a sensor must spend inside its declared span.
            Below one because a real transmitter does occasionally read off-scale, and an
            instrument that never does is one whose span was chosen after the fact.
        min_variation_ratio: A sensor must vary by at least this fraction of its span over the
            run to count as varying at all.
        min_varying_sensors: Fraction of a plant's sensors that must clear
            ``min_variation_ratio``. Not all of them: an ambient temperature or a suction
            pressure held from outside the boundary is legitimately quiet, and a plant is only
            useless when most of it is.
        max_saturated_fraction: Fraction of the run an actuator may spend pinned at a limit. An
            actuator at its stop is a loop with no authority left, and a plant whose actuators
            are pinned throughout has no control behaviour to learn. This is the bar that the
            measurement in PART R2 was taken against.
        reach_tolerance_ratio: How close to its setpoint a tracking loop must come *at some
            point*, as a fraction of the measured signal's span. This is the spec's "setpoints
            reachable": a loop that never once gets near its target is holding to something the
            plant cannot deliver, and the tight bar belongs here.
        hold_tolerance_ratio: How far from its setpoint a loop may typically sit, as a fraction
            of span. This is the spec's "loops settle", and it is deliberately looser than
            reachability, because the two are different failures. A level loop in a chain is
            being drained by the loop below it while a daily demand swing moves underneath both;
            riding that at a tenth of its span is a working plant, and only a loop that has
            wandered away from its setpoint altogether is a broken one.
        settle_fraction: Fraction of the run ignored before a tracking loop is judged, so a
            plant is not refused for its own opening transient.
        settle_percentile: Which percentile of the offset the holding bar is judged at, rather
            than the worst instant. An operator moving a setpoint is a benign event every one of
            these plants is built to contain, and for a minute afterwards the loop is legitimately
            a long way off. Judging the maximum would refuse every plant whose setpoint moved late
            in the run, which is a fact about the schedule and not about the loop.
        max_conservation_residual: Largest relative residual a declared balance may show. Not
            zero: these are explicit integrations at a finite step, so a residual of order the
            step divided by the time constant is arithmetic rather than a broken plant.

    Invariants:
        Every fraction is in its unit interval and the run holds at least one sample.
    """

    hours: float = 6.0
    sample_interval_seconds: float = 30.0
    warmup_fraction: float = 0.05
    in_range_fraction: float = 0.98
    min_variation_ratio: float = 1e-3
    min_varying_sensors: float = 0.5
    max_saturated_fraction: float = 0.9
    reach_tolerance_ratio: float = 0.08
    hold_tolerance_ratio: float = 0.20
    settle_fraction: float = 0.6
    settle_percentile: float = 90.0
    max_conservation_residual: float = 0.05

    def __post_init__(self) -> None:
        """Refuse thresholds that do not describe a check.

        Raises:
            ValidityError: If a fraction is outside its unit interval, or the run would hold no
                samples. A gate configured to look at nothing passes everything.
        """
        if self.hours <= 0.0 or self.sample_interval_seconds <= 0.0:
            raise ValidityError("a trial run needs a positive duration and interval")
        if self.n_steps < 10:
            raise ValidityError(
                f"a trial run of {self.hours}h at {self.sample_interval_seconds}s holds "
                f"{self.n_steps} sample(s); a verdict from that is noise"
            )
        for name in (
            "warmup_fraction",
            "in_range_fraction",
            "min_varying_sensors",
            "max_saturated_fraction",
            "settle_fraction",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValidityError(f"{name} is {value}, which is not a fraction")
        if not 0.0 < self.settle_percentile <= 100.0:
            raise ValidityError(
                f"settle_percentile is {self.settle_percentile}, which is not a percentile"
            )

    @property
    def n_steps(self) -> int:
        """How many samples a trial run holds."""
        return int(self.hours * 3600.0 // self.sample_interval_seconds)

    def run_spec(self, seed: int, interval_seconds: float | None = None) -> RunSpec:
        """Return the trial run this configuration describes, for one candidate.

        Args:
            seed: Seeds the trial's sensor noise and event schedule.
            interval_seconds: The candidate's own scan period, or ``None`` to use the configured
                default. See ``sample_interval_seconds``.

        Returns:
            The run.
        """
        return RunSpec(
            seed=seed,
            start=_TRIAL_START,
            duration=timedelta(hours=self.hours),
            sample_interval=timedelta(
                seconds=interval_seconds
                if interval_seconds is not None
                else self.sample_interval_seconds
            ),
        )


class ValidityError(ValueError):
    """Raised when the gate itself is misconfigured, or a family cannot produce a valid plant."""


@runtime_checkable
class SelfAuditing(Protocol):
    """What a process template owes the gate so that its physics can be checked at all.

    Implemented on the plant rather than here because only the template knows which of its
    signals is an inflow, which an outflow, and what its balances are. `phos.synth.validity`
    deliberately does not guess: a coupling says that a level depends on two flows, not which way
    either of them points.
    """

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return each declared balance's residual over a completed run, relative.

        Args:
            steps: Every sample of the run, in order. True state, not reported readings — a
                balance is a statement about the process, and checking it against the
                instruments would be checking the sensor model instead.
            interval_seconds: The integration step the run used.

        Returns:
            ``{balance name: relative residual}``, where a residual is the unexplained part of
            the balance divided by the total that passed through it. Empty is allowed only for a
            plant with nothing to conserve, which is not a thing this package generates.
        """

    def tracking_loops(self) -> tuple[str, ...]:
        """Return the controller ids expected to hold their setpoint throughout a normal run.

        Empty for a process where no loop tracks continuously — a batch plant's temperature loop
        is deliberately far from setpoint while the vessel is filling, and judging it against
        setpoint across the whole run would refuse every correct plant.
        """


@dataclass(frozen=True)
class Finding:
    """One reason a candidate was refused, specific enough to act on.

    Attributes:
        check: Which check failed — ``"conservation"``, ``"finite"``, ``"range"``,
            ``"variability"``, ``"saturation"``, ``"controllability"``, ``"declaration"``.
        detail: What broke, in a sentence naming the relation or the signal and the numbers.
        signal: The signal or controller implicated, or ``""`` where the finding is about the
            plant as a whole.
    """

    check: str
    detail: str
    signal: str = ""

    def __str__(self) -> str:
        """Render the finding for a log line or a report."""
        where = f" [{self.signal}]" if self.signal else ""
        return f"{self.check}{where}: {self.detail}"


@dataclass(frozen=True)
class Verdict:
    """What the gate concluded about one candidate.

    Attributes:
        plant_id: The candidate.
        process: The process template it runs on.
        hours: How long it was run before judging.
        findings: Every reason it was refused. Empty means it passed.
        balances: The declared balances and their residuals, kept whether or not they passed, so
            a reviewer can see how close a plant that passed actually was.
    """

    plant_id: str
    process: str
    hours: float
    findings: tuple[Finding, ...] = ()
    balances: Mapping[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether this candidate may be used."""
        return not self.findings

    def summary(self) -> str:
        """Return a one-line verdict, and the reasons when there are any."""
        if self.passed:
            return f"{self.plant_id}: valid over {self.hours}h"
        reasons = "; ".join(str(finding) for finding in self.findings)
        return f"{self.plant_id}: refused over {self.hours}h — {reasons}"


def check(spec: PlantSpec, thresholds: Thresholds | None = None, trial_seed: int = 0) -> Verdict:
    """Run a candidate plant and judge whether it could exist.

    Args:
        spec: The candidate.
        thresholds: What to require, or ``None`` for the documented defaults.
        trial_seed: Seeds the trial run's sensor noise and event schedule. Part of the verdict:
            two trial seeds can disagree about a marginal plant, which is a fact about the plant
            and is why the seed is recorded rather than hidden.

    Returns:
        The verdict, with every reason the candidate was refused.

    Raises:
        SpecError: If the spec names a process no template implements. That is a broken spec
            rather than an invalid plant, and the two should not be confused.
    """
    bars = thresholds or Thresholds()
    run = bars.run_spec(trial_seed, spec.scan_period_seconds)
    plant = build_from_spec(spec, run)
    steps = tuple(plant.step(None) for _ in range(run.n_steps))
    warmup = int(len(steps) * bars.warmup_fraction)
    judged = steps[warmup:] or steps

    findings: list[Finding] = []
    findings.extend(_check_finite(spec, judged))
    balances = _residuals(plant, steps, run.interval_seconds)
    findings.extend(_check_conservation(plant, balances, bars))
    findings.extend(_check_range(spec, judged, bars))
    findings.extend(_check_variability(spec, judged, bars))
    findings.extend(_check_saturation(spec, judged, bars))
    findings.extend(_check_controllability(spec, plant, judged, bars))

    verdict = Verdict(
        plant_id=spec.plant_id,
        process=spec.process,
        hours=bars.hours,
        findings=tuple(findings),
        balances=balances,
    )
    logger.debug("%s", verdict.summary())
    return verdict


def _residuals(
    plant: object, steps: Sequence[PlantStep], interval_seconds: float
) -> dict[str, float]:
    """Return a plant's declared balance residuals, or an empty mapping if it declares none."""
    if not isinstance(plant, SelfAuditing):
        return {}
    return dict(plant.conservation_residuals(steps, interval_seconds))


def _check_finite(spec: PlantSpec, steps: Sequence[PlantStep]) -> list[Finding]:
    """Refuse a plant that produced a value no instrument could read."""
    findings: list[Finding] = []
    for key in spec.describe().signal_keys():
        for step in steps:
            for source, values in (("true", step.truth.values), ("reported", step.report.values)):
                value = values[key]
                if not math.isfinite(value):
                    findings.append(
                        Finding(
                            "finite",
                            f"the {source} value is {value} at {step.timestamp.isoformat()}; the "
                            "integration diverged",
                            key,
                        )
                    )
                    break
            else:
                continue
            break
    return findings


def _check_conservation(
    plant: object, balances: Mapping[str, float], bars: Thresholds
) -> list[Finding]:
    """Refuse a plant whose declared balances do not close, and one that declares none."""
    if not isinstance(plant, SelfAuditing):
        return [
            Finding(
                "declaration",
                "this process states no balances, so nothing can check its physics. A template "
                "owes `conservation_residuals`; see phos.synth.validity.SelfAuditing.",
            )
        ]
    if not balances:
        return [
            Finding(
                "declaration",
                "this process stated an empty set of balances, which is not the same as having "
                "nothing to conserve",
            )
        ]
    return [
        Finding(
            "conservation",
            f"the {name} balance leaves {residual:.3%} of what passed through it unexplained, "
            f"above the {bars.max_conservation_residual:.1%} the gate allows",
            name,
        )
        for name, residual in sorted(balances.items())
        if not math.isfinite(residual) or abs(residual) > bars.max_conservation_residual
    ]


def _check_range(spec: PlantSpec, steps: Sequence[PlantStep], bars: Thresholds) -> list[Finding]:
    """Refuse a plant whose process spends the run outside what its instruments can read.

    Judged on the **true** state, not the reported reading. A transmitter is bounded by its own
    calibrated span — `phos.synth.plant` clamps a report into it, as a real one does — so a check
    against the reported value can never fail however wrong the plant is. It would have been
    quietly dead, and that is exactly the kind of check whose absence nobody notices.

    What the spec asks for is that the *process* sits where its instruments can see it. A tank
    whose level runs above the top of its gauge is a plant whose operating point was chosen for a
    different vessel, and the telemetry would show a reading pinned at full scale rather than
    anything wrong — which is the shape a detector has no chance against.
    """
    findings: list[Finding] = []
    for signal in spec.signals:
        if signal.kind is not SignalKind.SENSOR:
            continue
        inside = sum(
            1 for step in steps if signal.low <= step.truth.values[signal.key] <= signal.high
        )
        fraction = inside / len(steps)
        if fraction < bars.in_range_fraction:
            findings.append(
                Finding(
                    "range",
                    f"is truly inside its {signal.low:g} to {signal.high:g} {signal.unit} span "
                    f"for {fraction:.1%} of the run, below the {bars.in_range_fraction:.0%} the "
                    "gate allows; the operating point is outside the instrument, so the reading "
                    "would sit pinned at full scale",
                    signal.key,
                )
            )
    return findings


def _check_variability(
    spec: PlantSpec, steps: Sequence[PlantStep], bars: Thresholds
) -> list[Finding]:
    """Refuse a plant whose signals do not move.

    A constant signal is not a quiet plant, it is a plant where nothing is happening — and a
    detector scored on it is measuring its own noise floor.
    """
    findings: list[Finding] = []
    sensors = [signal for signal in spec.signals if signal.kind is SignalKind.SENSOR]
    if not sensors:
        return [Finding("variability", "the plant declares no sensors at all")]

    varying = 0
    for signal in sensors:
        series = [step.report.values[signal.key] for step in steps]
        spread = max(series) - min(series)
        span = signal.high - signal.low
        if spread <= 0.0:
            findings.append(
                Finding(
                    "variability",
                    "never changes over the whole run; a constant reading is not a quiet plant",
                    signal.key,
                )
            )
        elif spread >= span * bars.min_variation_ratio:
            varying += 1

    fraction = varying / len(sensors)
    if fraction < bars.min_varying_sensors:
        findings.append(
            Finding(
                "variability",
                f"only {fraction:.0%} of sensors move by {bars.min_variation_ratio:.2%} of their "
                f"span, below the {bars.min_varying_sensors:.0%} the gate requires; most of this "
                "plant is standing still",
            )
        )
    return findings


def _check_saturation(
    spec: PlantSpec, steps: Sequence[PlantStep], bars: Thresholds
) -> list[Finding]:
    """Refuse a plant whose *modulating* actuators are pinned.

    This is the failure PART R2 measured before moving its sizing bounds onto a ratio: a heater
    at full duty for a whole run, or a pump that never comes off its stop, is a loop with no
    authority and a signal with nothing to learn from.

    **Only actuators a declared PI loop drives are checked.** A batch plant's feed valve is open
    while the vessel charges and shut the rest of the time, and its agitator runs at one of two
    speeds; both sit at a limit for the whole run and both are completely correct. They are not
    loops with no authority, they are not loops at all, and the spec already says so — nothing in
    `PlantSpec.controllers` drives them. Checking every actuator refused every batch plant.
    """
    findings: list[Finding] = []
    modulated = {
        controller.output for controller in spec.controllers if controller.kind is ControllerKind.PI
    }
    for signal in spec.signals:
        if signal.kind is not SignalKind.ACTUATOR or signal.key not in modulated:
            continue
        span = signal.high - signal.low
        edge = span * 0.005
        pinned = sum(
            1
            for step in steps
            if step.truth.values[signal.key] <= signal.low + edge
            or step.truth.values[signal.key] >= signal.high - edge
        )
        fraction = pinned / len(steps)
        if fraction > bars.max_saturated_fraction:
            findings.append(
                Finding(
                    "saturation",
                    f"sits at a limit for {fraction:.0%} of the run, above the "
                    f"{bars.max_saturated_fraction:.0%} the gate allows; its loop has no "
                    "authority left",
                    signal.key,
                )
            )
    return findings


def _check_controllability(
    spec: PlantSpec, plant: object, steps: Sequence[PlantStep], bars: Thresholds
) -> list[Finding]:
    """Refuse a plant whose tracking loops never reach their setpoint, or leave it again.

    Which loops are expected to track is the template's statement, not this module's guess: a
    batch plant's temperature loop is deliberately nowhere near setpoint while the vessel fills.
    """
    if not isinstance(plant, SelfAuditing):
        return []
    expected = set(plant.tracking_loops())
    if not expected:
        return []

    findings: list[Finding] = []
    settle_from = int(len(steps) * bars.settle_fraction)
    for controller in spec.controllers:
        if controller.controller_id not in expected or controller.kind is not ControllerKind.PI:
            continue
        measured = spec.describe().signal(controller.measurement)
        span = measured.high - measured.low
        offsets = [
            abs(
                step.truth.values[controller.measurement]
                - (
                    step.truth.values[controller.setpoint]
                    if controller.setpoint is not None
                    else float(controller.setpoint_value or 0.0)
                )
            )
            for step in steps[settle_from:]
        ]
        if not offsets:
            continue
        closest = min(offsets)
        reach = span * bars.reach_tolerance_ratio
        if closest > reach:
            findings.append(
                Finding(
                    "controllability",
                    f"never comes closer than {closest:g} {measured.unit} to its setpoint, "
                    f"outside the {reach:g} {measured.unit} the gate allows; the setpoint is not "
                    "reachable on this plant",
                    controller.controller_id,
                )
            )
            continue
        typical = float(numpy.percentile(offsets, bars.settle_percentile))
        hold = span * bars.hold_tolerance_ratio
        if typical > hold:
            findings.append(
                Finding(
                    "controllability",
                    f"reaches its setpoint but then sits {typical:g} {measured.unit} away at the "
                    f"{bars.settle_percentile:g}th percentile, outside the {hold:g} "
                    f"{measured.unit} the gate allows; the loop does not hold it",
                    controller.controller_id,
                )
            )
    return findings


def candidate_seed(master_seed: int, attempt: int) -> int:
    """Return the seed for one attempt at drawing a valid plant.

    Attempt zero *is* the master seed, so a family whose first draw is valid produces exactly
    `PlantFamily.draw(master_seed)` and the two paths cannot disagree. Later attempts are derived
    by hashing, not by incrementing, so the candidates after a rejection are not the plants a
    neighbouring master seed would have given — which would make two plants in a batch correlated
    in a way nothing documented.

    Args:
        master_seed: The seed the whole plant is drawn from.
        attempt: Which attempt, counting from zero.

    Returns:
        The seed to draw with.

    Raises:
        ValidityError: If the attempt is negative.
    """
    if attempt < 0:
        raise ValidityError(f"attempt must be non-negative, got {attempt}")
    if attempt == 0:
        return master_seed
    digest = hashlib.blake2b(
        f"phos.synth.validity:{master_seed}:{attempt}".encode(), digest_size=8
    ).digest()
    return int.from_bytes(digest, "big")


@dataclass(frozen=True)
class ValidDraw:
    """A plant that passed the gate, and what it took to get one.

    Attributes:
        spec: The accepted plant.
        verdict: Its passing verdict, balances included, so a reviewer can see how close it was.
        master_seed: The seed the draw started from.
        child_seed: The seed the accepted candidate was actually drawn with. Equal to the master
            seed when the first candidate passed.
        attempts: How many candidates were drawn in total, the accepted one included.
        rejected: The verdict of every refused candidate, in the order they were refused. This is
            what the manifest's rejection count counts, and keeping the verdicts rather than only
            the count is what lets a wide family be diagnosed instead of merely noticed.
    """

    spec: PlantSpec
    verdict: Verdict
    master_seed: int
    child_seed: int
    attempts: int
    rejected: tuple[Verdict, ...] = ()

    @property
    def rejection_count(self) -> int:
        """How many candidates were refused before this one was accepted."""
        return len(self.rejected)


def draw_valid(
    family: PlantFamily,
    master_seed: int,
    thresholds: Thresholds | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> ValidDraw:
    """Draw from a family until a candidate passes the gate.

    Args:
        family: The family to draw from.
        master_seed: The seed the draw starts from.
        thresholds: What the gate requires, or ``None`` for the documented defaults.
        max_attempts: How many candidates may be refused before the family is reported as the
            problem rather than the seed.

    Returns:
        The accepted plant and the record of what was refused on the way.

    Raises:
        ValidityError: If no candidate passed within ``max_attempts``. The message carries the
            first refused verdict in full, because a family that cannot produce a valid plant has
            declared ranges wider than its physics and the reasons are the finding.
    """
    bars = thresholds or Thresholds()
    rejected: list[Verdict] = []
    for attempt in range(max_attempts):
        seed = candidate_seed(master_seed, attempt)
        spec = family.draw(seed)
        verdict = check(spec, bars, trial_seed=seed)
        if verdict.passed:
            logger.debug(
                "%s accepted on attempt %d (%d refused)", spec.plant_id, attempt + 1, len(rejected)
            )
            return ValidDraw(
                spec=spec,
                verdict=verdict,
                master_seed=master_seed,
                child_seed=seed,
                attempts=attempt + 1,
                rejected=tuple(rejected),
            )
        rejected.append(verdict)
    reasons = "\n  ".join(verdict.summary() for verdict in rejected[:3])
    raise ValidityError(
        f"family {family.family_id!r} produced no valid plant in {max_attempts} attempts from "
        f"master seed {master_seed}. Its declared ranges are wider than its physics. The first "
        f"refusals were:\n  {reasons}"
    )
