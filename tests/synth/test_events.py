"""Every event acts on the layer its record claims, and the record's facts are measured.

PART R4's test requirement, item by item: the correct layer, labels matching the injected intervals
exactly, conservation still holding, stealthy variants staying in range, and byte-identical output
per seed.

The layer assertions are the ones that would otherwise rot. A record saying ``layer=sensor`` is a
promise that the true state was left alone by the manipulation itself — the loop that believes the
falsified reading may well move the plant, and that is a different thing. Checking the promise
means checking what the injection returned, not what the plant did afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy
import pytest

from phos.synth.events import (
    MAX_EVENT_FRACTION,
    MIN_NORMAL_GAP,
    EventCatalogue,
    EventKind,
    EventLayer,
    EventsError,
    SensorReplay,
    ValveExercise,
    assess_events,
    plan_events,
)
from phos.synth.families import get_family
from phos.synth.injection import TimeWindow
from phos.synth.plant import PlantStep, RunSpec, SignalKind
from phos.synth.plant_spec import PlantSpec
from phos.synth.templates import build_from_spec
from phos.synth.validity import Thresholds, draw_valid

FAST = Thresholds(hours=2.0)
START = datetime(2026, 11, 13, tzinfo=UTC)
FULL = EventCatalogue(
    sensor_replays=1,
    stuck_valves=1,
    pump_trips=1,
    sensors_offline=1,
    valves_exercised=1,
    loops_in_manual=1,
    event_minutes=(20.0, 60.0),
)
"""One of everything the sensor and actuator layers can do, over a day.

Six events averaging forty minutes is about a sixth of a day, comfortably inside the quarter
`MAX_EVENT_FRACTION` allows. An earlier version used twenty-five to ninety minutes, which averages
to within a percent of the limit — so whether the schedule was accepted depended on the seed, and
two of these tests failed on an arithmetic coincidence rather than on anything about events."""


@pytest.fixture(scope="module")
def spec() -> PlantSpec:
    """A plant the validity gate accepts, to put events on."""
    return draw_valid(get_family("level_flow"), 72_000, FAST).spec


@pytest.fixture(scope="module")
def run(spec: PlantSpec) -> RunSpec:
    """A day of that plant, at its own scan period."""
    return RunSpec(
        seed=11,
        start=START,
        duration=timedelta(hours=24),
        sample_interval=timedelta(seconds=spec.scan_period_seconds or 30.0),
    )


def _steps(spec: PlantSpec, run: RunSpec, injection: object | None) -> tuple[PlantStep, ...]:
    """Run a plant with an injection, or without one."""
    plant = build_from_spec(spec, run)
    return tuple(plant.step(injection) for _ in range(run.n_steps))  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def normal(spec: PlantSpec, run: RunSpec) -> tuple[PlantStep, ...]:
    """The same plant with nothing happening to it."""
    return _steps(spec, run, None)


# --------------------------------------------------------------------------------------------
# the two new effects, on their own
# --------------------------------------------------------------------------------------------


def test_a_replay_returns_recorded_values_only_inside_its_window() -> None:
    window = TimeWindow(start=START + timedelta(hours=1), end=START + timedelta(hours=2))
    replay = SensorReplay(
        window=window, signal="level", samples=(1.0, 2.0, 3.0), interval=timedelta(minutes=10)
    )

    assert replay.reading_overrides(START, {"level": 9.0}) == {}
    assert replay.reading_overrides(window.start, {"level": 9.0}) == {"level": 1.0}
    assert replay.reading_overrides(window.start + timedelta(minutes=10), {"level": 9.0}) == {
        "level": 2.0
    }
    assert replay.reading_overrides(window.end, {"level": 9.0}) == {}


def test_a_replay_loops_rather_than_running_out() -> None:
    """A recording that stopped would announce itself at the moment it stopped."""
    window = TimeWindow(start=START, end=START + timedelta(hours=2))
    replay = SensorReplay(
        window=window, signal="level", samples=(1.0, 2.0), interval=timedelta(minutes=10)
    )

    played = [
        replay.reading_overrides(START + timedelta(minutes=10 * index), {"level": 0.0})["level"]
        for index in range(6)
    ]

    assert played == [1.0, 2.0, 1.0, 2.0, 1.0, 2.0]


def test_a_replay_touches_no_actuator() -> None:
    """The layer claim: a replay acts on what is reported, never on what is done."""
    replay = SensorReplay(
        window=TimeWindow(start=START, end=START + timedelta(hours=1)),
        signal="level",
        samples=(1.0,),
        interval=timedelta(minutes=1),
    )

    assert replay.actuator_overrides(START, {"pump": 50.0}) == {}


def test_a_replay_with_nothing_to_play_is_refused() -> None:
    window = TimeWindow(start=START, end=START + timedelta(hours=1))

    with pytest.raises(EventsError, match="no recorded samples"):
        SensorReplay(window=window, signal="level", samples=(), interval=timedelta(minutes=1))
    with pytest.raises(EventsError, match="non-positive interval"):
        SensorReplay(window=window, signal="level", samples=(1.0,), interval=timedelta(0))


def test_a_valve_exercise_strokes_out_and_back() -> None:
    window = TimeWindow(start=START, end=START + timedelta(hours=1))
    exercise = ValveExercise(window=window, actuator="pump", low=0.0, high=100.0)

    at = {
        minutes: exercise.actuator_overrides(START + timedelta(minutes=minutes), {"pump": 40.0})[
            "pump"
        ]
        for minutes in (0, 15, 30, 45)
    }

    assert at[0] == pytest.approx(0.0)
    assert at[15] == pytest.approx(50.0)
    assert at[30] == pytest.approx(100.0)
    assert at[45] == pytest.approx(50.0)
    assert exercise.actuator_overrides(window.end, {"pump": 40.0}) == {}


def test_a_valve_exercise_falsifies_nothing() -> None:
    """The layer claim: the valve really moved, so the instruments tell the truth."""
    exercise = ValveExercise(
        window=TimeWindow(start=START, end=START + timedelta(hours=1)),
        actuator="pump",
        low=0.0,
        high=100.0,
    )

    assert exercise.reading_overrides(START, {"level": 3.0}) == {}


def test_a_stroke_with_no_travel_is_refused() -> None:
    window = TimeWindow(start=START, end=START + timedelta(hours=1))

    with pytest.raises(EventsError, match="no travel at all"):
        ValveExercise(window=window, actuator="pump", low=50.0, high=50.0)


# --------------------------------------------------------------------------------------------
# the schedule
# --------------------------------------------------------------------------------------------


def test_a_full_catalogue_lands_on_the_plant(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)

    assert len(schedule.events) == FULL.total()
    kinds = {record.kind for record in schedule.records}
    assert kinds == {EventKind.ATTACK, EventKind.FAULT, EventKind.MAINTENANCE}
    layers = {record.layer for record in schedule.records}
    assert layers == {EventLayer.SENSOR, EventLayer.ACTUATOR}


def test_most_of_the_run_is_normal(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)

    assert schedule.normal_fraction() >= 1.0 - MAX_EVENT_FRACTION


def test_events_never_abut(spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]) -> None:
    """Two events a minute apart are one event as far as anything watching is concerned."""
    schedule = plan_events(spec, run, numpy.random.default_rng(7), FULL, history=normal)

    records = sorted(schedule.records, key=lambda record: record.started_at)
    for earlier, later in pairwise(records):
        assert later.started_at - earlier.ended_at >= MIN_NORMAL_GAP


def test_too_many_events_are_refused_rather_than_crammed_in(
    spec: PlantSpec, normal: tuple[PlantStep, ...]
) -> None:
    short = RunSpec(
        seed=11, start=START, duration=timedelta(hours=3), sample_interval=timedelta(seconds=60)
    )
    greedy = EventCatalogue(stuck_valves=6, pump_trips=6, event_minutes=(60.0, 120.0))

    with pytest.raises(EventsError, match=r"need \d|below the"):
        plan_events(spec, short, numpy.random.default_rng(5), greedy, history=normal)


def test_an_empty_catalogue_gives_no_injection_at_all(spec: PlantSpec, run: RunSpec) -> None:
    """``None`` rather than an empty composite, so a run with no events takes the untouched path.

    That is what keeps a corpus generated with an empty catalogue byte-identical to one generated
    before events existed.
    """
    schedule = plan_events(spec, run, numpy.random.default_rng(5), EventCatalogue())

    assert schedule.events == ()
    assert schedule.injection() is None
    assert schedule.normal_fraction() == 1.0


def test_a_replay_without_a_recording_is_refused(spec: PlantSpec, run: RunSpec) -> None:
    """An attacker needs a tap before a replay; inventing the values would be a fabrication."""
    with pytest.raises(EventsError, match="needs a recording"):
        plan_events(
            spec, run, numpy.random.default_rng(5), EventCatalogue(sensor_replays=1), history=()
        )


def test_a_stuck_valve_without_a_recording_is_refused(spec: PlantSpec, run: RunSpec) -> None:
    """Holding at an invented number would be a valve driven somewhere, a different fault."""
    with pytest.raises(EventsError, match="hold the actuator where it was"):
        plan_events(
            spec, run, numpy.random.default_rng(5), EventCatalogue(stuck_valves=1), history=()
        )


def test_a_bad_catalogue_is_refused() -> None:
    with pytest.raises(EventsError, match="not a range of durations"):
        EventCatalogue(stuck_valves=1, event_minutes=(90.0, 20.0))


# --------------------------------------------------------------------------------------------
# what the records claim, against what happened
# --------------------------------------------------------------------------------------------


def test_the_labels_match_the_injected_intervals_exactly(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    """PART R4's requirement, and the one a scorer depends on absolutely.

    Checked by asking each injection when it is active rather than by trusting the record: a
    record whose window disagreed with its effect by one sample would put a detection on the
    wrong side of a boundary and nothing else would notice.
    """
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    actuators = set(spec.describe().keys_of_kind(SignalKind.ACTUATOR))

    for event in schedule.events:
        injection = event.injection
        assert injection is not None
        record = event.record
        inside = record.started_at + (record.ended_at - record.started_at) / 2
        before = record.started_at - timedelta(seconds=1)

        commanded = dict.fromkeys(actuators, 50.0)
        readings = dict.fromkeys(spec.describe().signal_keys(), 1.0)
        acted = bool(
            injection.actuator_overrides(inside, commanded)
            or injection.reading_overrides(inside, readings)
        )
        quiet = bool(
            injection.actuator_overrides(before, commanded)
            or injection.reading_overrides(before, readings)
        )

        assert acted, f"{record.event_id} does nothing in the middle of its own window"
        assert not quiet, f"{record.event_id} acts before its window opens"


def test_each_event_acts_on_the_layer_its_record_claims(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    actuators = set(spec.describe().keys_of_kind(SignalKind.ACTUATOR))

    for event in schedule.events:
        injection = event.injection
        assert injection is not None
        record = event.record
        inside = record.started_at + (record.ended_at - record.started_at) / 2
        commanded = dict.fromkeys(actuators, 50.0)
        readings = dict.fromkeys(spec.describe().signal_keys(), 1.0)

        touched_actuators = bool(injection.actuator_overrides(inside, commanded))
        touched_readings = bool(injection.reading_overrides(inside, readings))

        if record.layer is EventLayer.SENSOR:
            assert touched_readings and not touched_actuators, record.event_id
        elif record.layer is EventLayer.ACTUATOR:
            assert touched_actuators and not touched_readings, record.event_id


def test_the_measured_facts_are_measured_not_declared(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    disturbed = _steps(spec, run, schedule.injection())

    assessed = assess_events(schedule.records, normal, disturbed)

    assert len(assessed) == len(schedule.records)
    # Every one of these events reaches the process, including the sensor-layer ones: a loop that
    # believes a falsified reading moves the plant, which is why a fabricated reading is worth
    # attacking with at all.
    assert all(record.physical_effect for record in assessed)
    # And at least one of them is not stealthy, or the measure is not measuring anything.
    assert any(not record.within_normal_range for record in assessed)


def test_comparing_two_different_runs_is_refused() -> None:
    with pytest.raises(EventsError, match="the same run with and without events"):
        assess_events((), (), (object(),))  # type: ignore[arg-type]


def test_conservation_still_holds_with_events_running(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    """A fault must be carried by the physics, not painted on the telemetry.

    If an event were applied by editing the output, the balance would keep closing exactly — and a
    closing balance during a stuck valve is the tell that the valve was never really stuck. So the
    residual has to stay *finite and bounded*, not stay at zero.
    """
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    plant = build_from_spec(spec, run)
    steps = tuple(plant.step(schedule.injection()) for _ in range(run.n_steps))

    residuals = plant.conservation_residuals(steps, run.interval_seconds)  # type: ignore[attr-defined]

    assert residuals
    for name, residual in residuals.items():
        assert abs(residual) < 0.5, f"{name} left {residual:.1%} unexplained"


def test_the_same_seed_gives_the_same_schedule(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    first = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    second = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)

    assert [record.document() for record in first.records] == [
        record.document() for record in second.records
    ]


def test_a_different_seed_gives_a_different_schedule(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    first = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)
    second = plan_events(spec, run, numpy.random.default_rng(6), FULL, history=normal)

    assert [record.started_at for record in first.records] != [
        record.started_at for record in second.records
    ]


def test_a_record_documents_everything_r4_asks_for(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    schedule = plan_events(spec, run, numpy.random.default_rng(5), FULL, history=normal)

    for record in schedule.records:
        document = record.document()
        assert set(document) == {
            "event_id",
            "kind",
            "type",
            "layer",
            "started_at",
            "ended_at",
            "signals",
            "physical_effect",
            "within_normal_range",
            "technique",
            "issuer",
            "detail",
        }
        assert document["signals"], f"{record.event_id} names no tags"
        assert document["detail"], f"{record.event_id} has no plain-language description"
        if record.kind is EventKind.FAULT:
            assert document["issuer"] == "", "a fault has nobody responsible for it"
        if record.kind is EventKind.ATTACK:
            assert document["technique"], "an attack should name its closest technique"


# --------------------------------------------------------------------------------------------
# the leak, which is the fault conservation is built to catch
# --------------------------------------------------------------------------------------------


def test_a_leak_drains_only_inside_its_window() -> None:
    from phos.synth.events import Leak

    window = TimeWindow(start=START + timedelta(hours=1), end=START + timedelta(hours=2))
    leak = Leak(window=window, signal="level", per_step=0.01)

    assert leak.state_losses(START, {"level": 3.0}) == {}
    assert leak.state_losses(window.start, {"level": 3.0}) == {"level": 0.01}
    assert leak.state_losses(window.end, {"level": 3.0}) == {}
    # a leak commands nothing and falsifies nothing: it is the process layer
    assert leak.actuator_overrides(window.start, {"pump": 50.0}) == {}
    assert leak.reading_overrides(window.start, {"level": 3.0}) == {}


def test_a_leak_that_drains_nothing_is_refused() -> None:
    from phos.synth.events import Leak

    window = TimeWindow(start=START, end=START + timedelta(hours=1))
    with pytest.raises(EventsError, match="per step"):
        Leak(window=window, signal="level", per_step=0.0)


def test_a_leak_breaks_the_conservation_balance_it_is_in(
    spec: PlantSpec, run: RunSpec, normal: tuple[PlantStep, ...]
) -> None:
    """The whole point of the leak, and the proof it emerges from the physics rather than paint.

    A fault applied by editing the telemetry would leave the balance closing exactly — a closing
    balance during a leak is the tell that nothing really leaked. So the residual on the drained
    tank's own balance must rise well clear of the noise floor the undisturbed plant sits at.
    """
    catalogue = EventCatalogue(leaks=1, event_minutes=(60.0, 120.0))
    schedule = plan_events(spec, run, numpy.random.default_rng(3), catalogue, history=normal)
    leaked_signal = schedule.records[0].signals[0]

    plain_plant = build_from_spec(spec, run)
    plain = tuple(plain_plant.step(None) for _ in range(run.n_steps))
    leak_plant = build_from_spec(spec, run)
    leaked = tuple(leak_plant.step(schedule.injection()) for _ in range(run.n_steps))

    plain_residuals = plain_plant.conservation_residuals(plain, run.interval_seconds)  # type: ignore[attr-defined]
    leak_residuals = leak_plant.conservation_residuals(leaked, run.interval_seconds)  # type: ignore[attr-defined]

    # The balance that holds the leaked tank is the one that moved.
    moved = [
        name
        for name in leak_residuals
        if abs(leak_residuals[name]) > abs(plain_residuals[name]) + 1e-3
    ]
    assert moved, (
        f"leaking {leaked_signal} left every balance closing; the leak was not carried by the "
        "physics"
    )


def test_a_leak_needs_an_inventory_signal(spec: PlantSpec, run: RunSpec) -> None:
    """A leak means nothing on a process that stores none; it is refused, not misaimed.

    level_flow has levels, so this uses a stand-in with its roles stripped to show the refusal
    rather than relying on a family that happens to have no inventory.
    """
    from phos.synth.events import INVENTORY_ROLES, _leak

    assert "level" in INVENTORY_ROLES
    stripped = PlantSpec.model_validate({**spec.model_dump(), "roles": {}})
    window = TimeWindow(start=run.start, end=run.start + timedelta(hours=1))

    with pytest.raises(EventsError, match="no inventory signal"):
        _leak(window, numpy.random.default_rng(0), stripped, run)
