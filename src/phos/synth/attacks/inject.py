"""Running a plant twice, and measuring the difference: where ground truth actually comes from.

Every attack corpus is **two simulations of the same seed**. The first is clean, and it is what
`phos.synth.attacks.library` parameterises the attacks against — a manipulation blended toward a
value that run actually took cannot leave the range that run actually occupied, which is how the
library's claims stay true by construction. The second carries the attacks. Ground truth is the
difference between them.

That is worth the doubled cost for a reason that is not convenience. **Ground truth here is
measured, not intended.** An attack whose parameters looked dangerous but which the plant absorbed
is an attack that did nothing, and a corpus that labelled it as an attack anyway would be teaching
D3 to score Atlas against a lie. So `inject` compares the two runs sample by sample, records what
actually moved, and — unless explicitly told otherwise — **refuses to produce a corpus containing
an attack that changed nothing at all**. D1's warning was that a manipulation quietly doing nothing
would be labelled as an attack that quietly did nothing, "the worst possible ground truth". This is
where that is enforced.

**Two spans, because two different questions are being asked.**

* `report_departure` is measured over the attack's own window: *what could a detector have seen
  while this was happening?* For the liar this is the number that matters, and it is small on
  purpose.
* `truth_departure` is measured from the window's start to the next attack's window (or the end of
  the run): *how much real danger did this attack cause?* The danger outlives the manipulation —
  a clearwell filled by a lie is still full after the lie stops — and cutting the measurement at
  the window's edge would understate it. Windows do not overlap, so every sample is attributed to
  exactly one attack.

The corpus is labelled over the **window**, which is the convention every published ICS corpus
uses. The recovery tail is recorded in `truth_departure` and not labelled, so a detector that only
fires during the manipulation is not penalised for the plant taking an hour to come back.

**Commands are spliced, not simulated.** D1's plant emits the traffic its own process implies. An
attacker's writes are added afterwards, as `CommandIntent`s on the steps they land on, so the
traffic renderer treats them exactly as it treats a cyclic poll — there is no branch anywhere for
"this one is an attack". Because a command attack also pins the setpoint it writes, the capture and
the telemetry agree about what the value became.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import pairwise
from typing import Final

from phos.eval import Dataset, LabelledInterval
from phos.ontology import Domain
from phos.synth.attacks.library import NormalReference, StagedAttack, stage_attack
from phos.synth.attacks.spec import (
    ATTACKS_ARE_OURS_CAVEAT,
    AttackGroundTruth,
    AttackPlan,
)
from phos.synth.injection import CompositeInjection
from phos.synth.plant import (
    MODEL_NOT_REALITY_CAVEAT,
    CommandIntent,
    PlantDescription,
    PlantStep,
    RunSpec,
)
from phos.synth.run import PlantRun, run_plant
from phos.synth.telemetry import observations

__all__ = [
    "ATTACK_LABEL_VALUE",
    "NORMAL_LABEL_VALUE",
    "AttackRun",
    "attack_dataset",
    "attack_source_note",
    "inject",
]

logger = logging.getLogger(__name__)

NORMAL_LABEL_VALUE: Final = "0"
ATTACK_LABEL_VALUE: Final = "1"
"""What the label column carries. Zero and one, as `phos.eval.default_attack_when` reads them and
as every published ICS corpus PHOS consumes writes them."""


@dataclass(frozen=True)
class AttackRun:
    """A clean run, the same run under attack, and exactly what the difference was.

    Attributes:
        plant_id: Which plant was run.
        spec: The run both simulations used. With ``plant_id`` and the plans, the whole of what
            has to be kept to regenerate this corpus.
        description: The plant's declaration.
        clean: The normal run. Not published as a corpus — it is the reference the attacks were
            built against and the baseline the departures were measured from.
        attacked: The manipulated run, with the attacker's commands spliced in.
        attacks: What each attack actually did, measured rather than intended.
    """

    plant_id: str
    spec: RunSpec
    description: PlantDescription
    clean: PlantRun
    attacked: PlantRun
    attacks: tuple[AttackGroundTruth, ...]

    def intervals(self) -> list[LabelledInterval]:
        """Return the ground-truth attack windows, one per detection attack, in time order.

        Only detection attacks appear. There is no route from an input-hostile case to this list —
        see `phos.synth.attacks.spec` for why that is enforced by the absence of a method rather
        than by a rule.
        """
        return [attack.interval() for attack in self.attacks]

    def is_attack(self, timestamp: datetime) -> bool:
        """Return whether ground truth marks an instant as inside an attack window."""
        return any(interval.contains(timestamp) for interval in self.intervals())

    def label_at(self, timestamp: datetime) -> str:
        """Return the label-column value for an instant."""
        return ATTACK_LABEL_VALUE if self.is_attack(timestamp) else NORMAL_LABEL_VALUE

    def attacked_samples(self) -> int:
        """Return how many samples ground truth marks as attacked."""
        return sum(1 for step in self.attacked.steps if self.is_attack(step.timestamp))

    def commands_injected(self) -> int:
        """Return how many of those exchanges an attacker put there."""
        return sum(attack.commands_injected for attack in self.attacks)


def inject(
    plant_id: str,
    spec: RunSpec,
    plans: Sequence[AttackPlan],
    *,
    allow_inert: bool = False,
) -> AttackRun:
    """Run a plant clean, run it again under attack, and measure the difference.

    Args:
        plant_id: One of `phos.synth.run.PLANT_IDS`.
        spec: How long to run, how often to sample, and from what seed. Both runs use it, so the
            two are comparable sample for sample.
        plans: The attacks to inject, in any order. Their windows must not overlap.
        allow_inert: Whether to permit an attack that changed nothing. Off for any corpus that
            will be published: an attack window labelled over data the attack never touched is
            ground truth that lies. On only for the anti-fingerprint tests, whose whole subject is
            the zero-magnitude control.

    Returns:
        The completed pair, with measured ground truth.

    Raises:
        KeyError: If the plant, or something a plan names, is not declared.
        ValueError: If two attack windows overlap, if a plan cannot be staged against this plant,
            or if an attack turned out to be inert and ``allow_inert`` is off.
    """
    clean = run_plant(plant_id, spec)
    reference = NormalReference.of(clean)
    staged = tuple(stage_attack(plan, reference) for plan in plans)
    _refuse_overlap(staged)

    ordered = tuple(sorted(staged, key=lambda attack: attack.window.start))
    attacked = run_plant(plant_id, spec, CompositeInjection(parts=[a.injection for a in ordered]))
    attacked = _with_injected_commands(attacked, ordered)

    truths = tuple(
        _measure(attack, clean, attacked, reference, _attribution_end(ordered, position))
        for position, attack in enumerate(ordered)
    )
    if not allow_inert:
        _refuse_inert(truths)

    logger.debug(
        "injected %d attack(s) into %s: %d command(s) added, %d of %d samples labelled attack",
        len(truths),
        plant_id,
        sum(truth.commands_injected for truth in truths),
        sum(
            1
            for step in attacked.steps
            if any(truth.interval().contains(step.timestamp) for truth in truths)
        ),
        len(attacked.steps),
    )
    return AttackRun(
        plant_id=plant_id,
        spec=spec,
        description=clean.description,
        clean=clean,
        attacked=attacked,
        attacks=truths,
    )


def _refuse_overlap(staged: Sequence[StagedAttack]) -> None:
    """Refuse two attacks in force at the same instant.

    Raises:
        ValueError: If any two windows overlap. Overlapping attacks would make "which attack was
            this sample" have two answers, and the whole value of synthetic ground truth is that
            it has one.
    """
    ordered = sorted(staged, key=lambda attack: attack.window.start)
    for earlier, later in pairwise(ordered):
        if later.window.start < earlier.window.end:
            raise ValueError(
                f"attacks {earlier.plan.attack_id!r} and {later.plan.attack_id!r} overlap: the "
                f"first runs to {earlier.window.end.isoformat()} and the second opens at "
                f"{later.window.start.isoformat()}, so a sample between them belongs to both"
            )


def _attribution_end(ordered: Sequence[StagedAttack], position: int) -> datetime | None:
    """Return where one attack's consequences stop being attributed to it.

    The next attack's window opens, or nothing — in which case the measurement runs to the end of
    the run, because the last attack's tail belongs to nobody else.
    """
    following = position + 1
    if following < len(ordered):
        return ordered[following].window.start
    return None


def _with_injected_commands(run: PlantRun, staged: Sequence[StagedAttack]) -> PlantRun:
    """Return the run with each attack's extra exchanges added to the steps they land on.

    Appended after whatever the process itself generated at that sample, which is the same order
    D1 uses for an operator's write following a cyclic poll — so the ordering carries no tell.
    """
    extra: dict[int, list[CommandIntent]] = {}
    for attack in staged:
        for scheduled in attack.commands:
            extra.setdefault(scheduled.step_index, []).append(scheduled.intent)
    if not extra:
        return run
    steps = tuple(
        replace(step, commands=step.commands + tuple(extra[step.index]))
        if step.index in extra
        else step
        for step in run.steps
    )
    return replace(run, steps=steps)


def _peak_gap(
    clean: Sequence[PlantStep],
    attacked: Sequence[PlantStep],
    key: str,
    first: int,
    last: int,
    *,
    of_truth: bool,
) -> float:
    """Return the largest absolute gap between the two runs for one signal over a span."""
    gap = 0.0
    for index in range(first, last + 1):
        before = clean[index].truth if of_truth else clean[index].report
        after = attacked[index].truth if of_truth else attacked[index].report
        gap = max(gap, abs(after.values[key] - before.values[key]))
    return gap


def _measure(
    attack: StagedAttack,
    clean: PlantRun,
    attacked: PlantRun,
    reference: NormalReference,
    attribution_end: datetime | None,
) -> AttackGroundTruth:
    """Compare the two runs and record what this attack actually did.

    See the module docstring for why the true-state and reported departures are measured over
    different spans.
    """
    keys = clean.description.signal_keys()
    window = attack.window
    first = reference.step_index(window.start)
    window_last = reference.step_index(window.end) - 1
    tail_last = (
        reference.step_index(attribution_end) - 1
        if attribution_end is not None
        else len(clean.steps) - 1
    )

    truth_departure = {}
    report_departure = {}
    for key in keys:
        moved = _peak_gap(clean.steps, attacked.steps, key, first, tail_last, of_truth=True)
        if moved > 0.0:
            truth_departure[key] = moved
        seen = _peak_gap(clean.steps, attacked.steps, key, first, window_last, of_truth=False)
        if seen > 0.0:
            report_departure[key] = seen

    return AttackGroundTruth(
        attack_id=attack.plan.attack_id,
        type=attack.plan.type,
        subtlety=attack.plan.subtlety,
        started_at=window.start,
        ended_at=clean.steps[window_last].timestamp,
        target_signals=attack.target_signals,
        issuer=attack.plan.issuer,
        manipulation=attack.manipulation,
        physical_effect=bool(truth_departure),
        truth_departure=truth_departure,
        report_departure=report_departure,
        commands_injected=len(attack.commands),
    )


def _refuse_inert(truths: Sequence[AttackGroundTruth]) -> None:
    """Refuse a corpus containing an attack that changed nothing.

    Raises:
        ValueError: If any attack moved neither the true state nor a single reading. Labelling
            such a window as an attack would tell D3 that Atlas missed something that never
            happened, and a recall figure computed against it would be wrong in the direction
            that flatters nobody.
    """
    for truth in truths:
        if truth.peak_truth_departure() == 0.0 and truth.peak_report_departure() == 0.0:
            raise ValueError(
                f"attack {truth.attack_id!r} ({truth.type.value} at subtlety {truth.subtlety}) "
                "moved neither the plant nor a single reading, so labelling its window as an "
                "attack would be ground truth that lies; raise its magnitude, or pass "
                "allow_inert=True if a zero-magnitude control is what you meant"
            )


def attack_source_note(run: AttackRun) -> str:
    """Return the provenance string an attack corpus carries everywhere it goes.

    Names the plant, the seed and the sampling rate — enough to regenerate the corpus exactly —
    then the two sentences that must never be separated from a number measured on it: what a plant
    model is, and whose imagination these attacks came out of.
    """
    return (
        f"phos.synth.attacks: {run.description.label} ({run.plant_id}), seed={run.spec.seed}, "
        f"{run.spec.duration} at {run.spec.interval_seconds:g}s sampling, "
        f"{len(run.description.signals)} signals. "
        f"{len(run.attacks)} labelled detection attack(s) covering {run.attacked_samples()} of "
        f"{len(run.attacked.steps)} samples; {run.commands_injected()} injected command(s). "
        f"{MODEL_NOT_REALITY_CAVEAT} {ATTACKS_ARE_OURS_CAVEAT}"
    )


def attack_dataset(run: AttackRun, name: str | None = None) -> Dataset:
    """Return the attacked run as a labelled `Dataset` the evaluation harness can score.

    Args:
        run: The completed pair.
        name: Dataset name. Defaults to ``synth-attack-<plant_id>``.

    Returns:
        The corpus. Its observations are the *attacked* run's reported readings — never the true
        state, which is ground truth and would make detection trivial — and its attack intervals
        are one per detection attack.
    """
    return Dataset(
        name=name or f"synth-attack-{run.plant_id}",
        domain=Domain.ATLAS,
        observations=observations(run.attacked),
        attack_intervals=run.intervals(),
        source_note=attack_source_note(run),
    )


def truth_rows(run: AttackRun) -> list[Mapping[str, float]]:
    """Return the true state of every signal at every sample, as rows.

    The companion to the published telemetry and the thing that makes a liar attack labellable:
    where the corpus says the clearwell was calm, this says how full it really was. Never fed to a
    detector — a detector that could read this would be detecting nothing.
    """
    return [dict(step.truth.values) for step in run.attacked.steps]
