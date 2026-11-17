"""Shared fixtures for `tests/referee/`: one small generated plant, reused read-only.

Generating a plant with events costs real wall-clock time, so every test file that needs one
reads the same session-scoped plant rather than generating its own. Nothing in `tests/referee/`
writes into it; tests that need their own output directory use `tmp_path`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from phos.synth.events import EventCatalogue
from phos.synth.families import get_family
from phos.synth.outputs import GeneratedPlant, generate_plant

FAMILY = "level_flow"
SEED = 20261116
HOURS = 3.0
TRIAL_HOURS = 0.5
EVENT_SEED = 7

#: Short events so a 3-hour run stays well under `MAX_EVENT_FRACTION`. One of each kind that
#: matters to the referee's own per-kind metrics: an attack, a fault, and sanctioned maintenance.
SMALL_CATALOGUE = EventCatalogue(
    sensor_replays=1,
    stuck_valves=1,
    valves_exercised=1,
    event_minutes=(5.0, 10.0),
)


@pytest.fixture(scope="session")
def small_exam_plant(tmp_path_factory: pytest.TempPathFactory) -> GeneratedPlant:
    """One short, events-bearing plant, generated once for the whole `tests/referee/` run."""
    output = tmp_path_factory.mktemp("referee-plant")
    family = get_family(FAMILY)
    return generate_plant(
        family,
        SEED,
        output,
        hours=HOURS,
        thresholds=None,
        events=SMALL_CATALOGUE,
        event_seed=EVENT_SEED,
    )


@pytest.fixture
def isolated_work_dir(tmp_path: Path) -> Iterator[Path]:
    """A fresh, empty directory for a test that writes its own scratch files."""
    directory = tmp_path / "work"
    directory.mkdir()
    yield directory
