"""Generate every plant an exam names, and score one detector against all of them.

PART S6. Deterministic aggregation is a property of `phos.referee.scoring.aggregate` reading
plants off `Exam.entries` in the exam's own fixed order — this module preserves that order; it
never scores in parallel or merges results by completion time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from phos.eval import Detector
from phos.referee.exam import Exam
from phos.referee.scoring import PlantScore, score_plant
from phos.synth.events import EventCatalogue
from phos.synth.families import get_family
from phos.synth.outputs import generate_plant

__all__ = ["DEFAULT_EVENT_CATALOGUE", "run_exam"]

DEFAULT_EVENT_CATALOGUE: Final = EventCatalogue(
    sensor_replays=1,
    stuck_valves=1,
    pump_trips=1,
    sensors_offline=1,
    valves_exercised=1,
    event_minutes=(20.0, 60.0),
)
"""The mix of attacks, faults and maintenance every exam plant carries, unless a caller names a
different catalogue. This is part of what a `scorer_version` means: a run that changes this
catalogue is measuring something else and must say so under its own version string."""


def run_exam(
    exam: Exam,
    detector: Detector,
    work_dir: Path,
    *,
    catalogue: EventCatalogue = DEFAULT_EVENT_CATALOGUE,
    skip_impossible_events: bool = True,
) -> list[PlantScore]:
    """Generate every plant ``exam`` names and score ``detector`` against each, in order.

    Args:
        exam: Which plants, and how long each runs.
        detector: Scored fresh against every plant. Nothing here fits, calibrates or retrains
            anything — that is the caller's job, before this is called.
        work_dir: Where generated plants are written, one subdirectory per plant.
        catalogue: The events placed on every plant.
        skip_impossible_events: Whether a plant that cannot host part of the catalogue (for
            example, a family with no inventory signal asked for a leak) has that part skipped
            rather than the whole exam refused. ``True`` by default, because an exam spans many
            families and one family's physics should not stop every other plant from being
            scored.

    Returns:
        One `PlantScore` per exam entry, in `exam.entries`'s own order — never reordered by how
        long each plant took to generate or score.
    """
    scores: list[PlantScore] = []
    for entry in exam.entries:
        family = get_family(entry.family)
        plant = generate_plant(
            family,
            entry.seed,
            work_dir,
            hours=entry.hours,
            events=catalogue,
            event_seed=entry.event_seed,
            skip_impossible_events=skip_impossible_events,
        )
        scores.append(score_plant(detector, plant))
    return scores
