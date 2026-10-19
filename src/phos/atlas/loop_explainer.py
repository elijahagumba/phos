"""Name the lying sensor with every declared control coupling read as a loop (ADR 0170).

Lane D's explainer (`phos.atlas.sensor_explainer`, ADR 0161) turns a plant's `CONTROL` coupling
into a loop only when it names exactly one sensor and one setpoint. Batch declares three control
couplings and none of them has that shape, so batch had no loop at all, and ADR 0123's first rule
barred every preliminary descendant from every level form. Reactor pressure then had only an
increment model, which cannot see a reading held flat after its first step.

Water declares its loops, but ADR 0126 bars a loop's outputs *and everything they reach* from the
reading's level form. Water's preliminary graph is connected, so the dose and booster outputs reach
every signal, and chlorine residual and distribution pressure were left with no model at all.

This explainer changes two things and nothing else:

1. Every `CONTROL` coupling whose driven signal is an actuator is a loop. Where lane D's rule names
   a reading, that loop is kept as it was. Otherwise the loop names its output and no reading; the
   setpoint is named only when the coupling names exactly one. Nothing is inferred from a key's
   spelling.
2. A loop bars only its declared outputs from the level form (`MapSettings.loop_bar="outputs"`).
   The output is the echo ADR 0123 guards against: a controller moved by a false reading. A signal
   further downstream follows the real process, which the false reading contradicts.

The champion still decides the alerts. This module does not add, drop or reorder one. A synthetic
pass is diagnosis, not a result on a real plant (ADR 0143).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from phos.atlas.sensor_explainer import (
    EXPLAINER_SETTINGS,
    FROZEN_SUBJECTS,
    SURVEY_SUBJECTS,
    LiarSubject,
    SubjectResult,
    roles_from_plant,
    score_subject,
)
from phos.atlas.signal_roles import ControlLoop, SignalRoles
from phos.synth.plant import CouplingKind, PlantDescription, SignalKind
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION
from phos.synth.plants.water import WATER_DESCRIPTION

__all__ = [
    "ALL_NINE",
    "LOOP_EXPLAINER_RESULT_NAME",
    "LOOP_EXPLAINER_SETTINGS",
    "NamingTotals",
    "every_sensor_subjects",
    "naming_totals",
    "roles_with_every_control_coupling",
    "score_all_nine",
    "score_subjects",
]

logger = logging.getLogger(__name__)

LOOP_EXPLAINER_RESULT_NAME: Final = "lane-e-loop-explainer"
"""Not lane D's explainer and not `atlas-plant-map-v1`."""

LOOP_EXPLAINER_SETTINGS: Final = replace(EXPLAINER_SETTINGS, loop_bar="outputs")
"""Lane D's windows and ADR 0135's naming rules, with ADR 0170's level-form bar."""

ALL_NINE: Final[tuple[LiarSubject, ...]] = (*FROZEN_SUBJECTS, *SURVEY_SUBJECTS)
"""Lane D's three frozen sensors and six survey sensors: the nine sensor types of target 2."""


def roles_with_every_control_coupling(description: PlantDescription) -> SignalRoles:
    """Lane D's roles, plus one loop for each `CONTROL` coupling lane D did not turn into one.

    Args:
        description: A synthetic plant's declaration.

    Returns:
        The same role declarations, with the extra loops. A coupling whose driven signal is not
        an actuator is skipped, as lane D skips it.
    """
    base = roles_from_plant(description)
    kind = {spec.key: spec.kind for spec in description.signals}
    named = {loop.name for loop in base.loops}
    loops = list(base.loops)
    for coupling in description.couplings:
        if coupling.kind is not CouplingKind.CONTROL or coupling.driven in named:
            continue
        if kind[coupling.driven] is not SignalKind.ACTUATOR:
            continue
        setpoints = [driver for driver in coupling.drivers if kind[driver] is SignalKind.SETPOINT]
        loops.append(
            ControlLoop(
                name=coupling.driven,
                cited=f"{description.plant_id} couplings",
                statement=coupling.relation,
                reading=None,
                outputs=(coupling.driven,),
                setpoint=setpoints[0] if len(setpoints) == 1 else None,
            )
        )
    return SignalRoles(
        base.declarations,
        [spec.key for spec in description.signals],
        source=description.label,
        loops=loops,
    )


def score_all_nine(split: str, *, seeds: Sequence[int] | None = None) -> tuple[SubjectResult, ...]:
    """Score this explainer on all nine sensor types of ``split``."""
    return score_subjects(ALL_NINE, split, seeds=seeds)


def score_subjects(
    subjects: Sequence[LiarSubject], split: str, *, seeds: Sequence[int] | None = None
) -> tuple[SubjectResult, ...]:
    """Score this explainer on ``subjects`` of ``split``."""
    return tuple(
        score_subject(
            subject,
            split=split,
            seeds=seeds,
            settings=LOOP_EXPLAINER_SETTINGS,
            roles_for=roles_with_every_control_coupling,
        )
        for subject in subjects
    )


def every_sensor_subjects() -> tuple[LiarSubject, ...]:
    """Every declared sensor of the three plants, at the nine subjects' sample periods.

    A guard, not the target: it shows whether a change that helps the nine names something else
    wrongly. ``on_the_bar`` is false for all of them.
    """
    shape = {subject.plant_id: subject for subject in FROZEN_SUBJECTS}
    found: list[LiarSubject] = []
    for description in (WATER_DESCRIPTION, POWER_DESCRIPTION, BATCH_DESCRIPTION):
        like = shape[description.plant_id]
        for spec in description.signals:
            if spec.kind is SignalKind.SENSOR:
                found.append(
                    LiarSubject(
                        description.plant_id, like.sample_seconds, like.n_steps, spec.key, False
                    )
                )
    return tuple(found)


class NamingTotals:
    """Named right and wrong across every caught run of every subject. Counts, not a rate claim.

    Attributes:
        caught: Runs where the champion alerted on the held column inside the window.
        named_right: Caught runs where every such alert named the held sensor within 10% of span.
        named_wrong: Caught runs where some such alert named another instrument.
    """

    __slots__ = ("caught", "named_right", "named_wrong")

    def __init__(self, caught: int, named_right: int, named_wrong: int) -> None:
        """Store the three counts."""
        self.caught = caught
        self.named_right = named_right
        self.named_wrong = named_wrong

    @property
    def right_share(self) -> float | None:
        """``named_right / caught``, or ``None`` when nothing was caught."""
        return None if self.caught == 0 else self.named_right / self.caught

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "caught": self.caught,
            "named_right": self.named_right,
            "named_wrong": self.named_wrong,
            "right_share": self.right_share,
        }


def naming_totals(results: Sequence[SubjectResult]) -> NamingTotals:
    """Sum caught, named right and named wrong across ``results``."""
    return NamingTotals(
        caught=sum(item.caught for item in results),
        named_right=sum(item.named_right for item in results),
        named_wrong=sum(item.named_wrong for item in results),
    )
