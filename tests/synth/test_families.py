"""A seed draws a plant, the same seed draws that plant again, and other seeds draw other plants.

PART R2 names six things it wants held in place, and five of them are here (the sixth, that no
module in this part imports Atlas, is in ``test_randomisation_imports.py`` where the whole package
is walked):

* the same seed gives a byte-identical plant;
* fifty different seeds per family give structurally different plants;
* tag names differ across seeds;
* a plant rebuilt from its serialised spec reproduces identical telemetry;
* every drawn parameter came through a declared bound.

The last is the one that does the most work over time. A family is only as reviewable as its
`bounds()` list, so a parameter that reached a plant without appearing there would be a knob
nobody had argued about and nobody could see in the public table.

**Drawing is cheap and running is not.** Structural variety is checked over fifty seeds per
family, which only draws specs; telemetry identity is checked on short runs of two seeds per
family. That keeps this module inside the default suite, where a reproducibility test belongs.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.synth.families import (
    BoundScale,
    FamilyError,
    ParameterBound,
    bounded,
    bounds_table,
    family_ids,
    get_family,
    list_families,
)
from phos.synth.plant import RunSpec, SignalKind
from phos.synth.plant_spec import PlantSpec
from phos.synth.randomise import SeedStreams
from phos.synth.templates import build_from_spec, process_names
from phos.synth.topology import subsystems, subsystems_from_components

OPEN_FAMILIES = list_families()
FAMILY_IDS = family_ids()
SEEDS = range(90_000, 90_050)
RUN = RunSpec(
    seed=771,
    start=datetime(2026, 11, 12, tzinfo=UTC),
    duration=timedelta(minutes=40),
    sample_interval=timedelta(seconds=30),
)


def _telemetry(spec: PlantSpec) -> list[tuple[float, ...]]:
    """Return every reported reading of a short run, in declaration order."""
    plant = build_from_spec(spec, RUN)
    keys = spec.describe().signal_keys()
    return [tuple(plant.step(None).report.values[key] for key in keys) for _ in range(RUN.n_steps)]


def test_the_five_open_families_are_registered() -> None:
    assert FAMILY_IDS == ("batch_mix", "hybrid", "level_flow", "power", "thermal")


def test_every_family_names_a_process_that_exists() -> None:
    available = process_names()
    for family in OPEN_FAMILIES:
        assert family.process in available, f"{family.family_id} draws for a missing template"


def test_every_family_describes_itself() -> None:
    for family in OPEN_FAMILIES:
        assert family.label and family.industry
        assert len(family.summary) > 60, f"{family.family_id} needs a real summary"
        assert not family.sealed, "list_families() must not return a sealed family"


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_the_same_seed_draws_an_identical_plant(family_id: str) -> None:
    family = get_family(family_id)

    first = family.draw(4242)
    second = family.draw(4242)

    assert first == second
    assert first.to_json() == second.to_json()


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_the_same_seed_gives_identical_telemetry(family_id: str) -> None:
    family = get_family(family_id)

    assert _telemetry(family.draw(515)) == _telemetry(family.draw(515))


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_plant_rebuilt_from_its_own_document_runs_identically(family_id: str) -> None:
    """The claim that makes a drawn plant reproducible from a file rather than from a function."""
    drawn = get_family(family_id).draw(516)

    rebuilt = PlantSpec.from_json(drawn.to_json())

    assert rebuilt == drawn
    assert _telemetry(rebuilt) == _telemetry(drawn)


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_different_seed_gives_different_telemetry(family_id: str) -> None:
    family = get_family(family_id)

    assert _telemetry(family.draw(517)) != _telemetry(family.draw(518))


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_fifty_seeds_give_structurally_different_plants(family_id: str) -> None:
    family = get_family(family_id)

    specs = [family.draw(seed) for seed in SEEDS]
    shapes = {
        (len(spec.signals), len(spec.components), len(spec.controllers), len(spec.units))
        for spec in specs
    }
    parameter_sets = {tuple(sorted(spec.parameters.items())) for spec in specs}

    assert len(parameter_sets) == len(specs), (
        f"{family_id} drew two plants with identical parameters in fifty seeds"
    )
    assert len(shapes) > 1, f"{family_id} never varies its topology across fifty seeds"


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_tag_names_differ_across_seeds(family_id: str) -> None:
    family = get_family(family_id)

    first_tags = {family.draw(seed).signals[0].key for seed in SEEDS}

    assert len(first_tags) > len(list(SEEDS)) // 3, (
        f"{family_id} reuses the same tag names across seeds; a detector could key off them"
    )


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_no_declared_bound_is_dead(family_id: str) -> None:
    """Every bound in the published table is actually drawn.

    The converse — that every drawn parameter has a bound — needs no test, because
    `phos.synth.families.bounded` refuses a name no bound declares, so it holds by construction.
    What can rot is the other direction: a bound left in the list after the draw that used it was
    removed, which puts a knob in the public table that does not exist in the plant.

    A drawn value does not always land in `PlantSpec.parameters` — the event gaps land in the
    disturbance model and the tag styles in the naming scheme — so this reads the family's own
    source for the `bounded(..., "name")` call rather than looking for the name in the result.
    """
    family = get_family(family_id)
    module = inspect.getmodule(type(family))
    assert module is not None and module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")

    undrawn = [bound.name for bound in family.bounds() if f'"{bound.name}")' not in source]

    assert not undrawn, (
        f"{family_id} declares bound(s) nothing draws: {undrawn}. Either draw them or stop "
        "publishing them."
    )


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_every_bound_is_reviewable(family_id: str) -> None:
    for bound in get_family(family_id).bounds():
        assert len(bound.why) > 20, f"{family_id}:{bound.name} has no argued reason"
        if bound.scale is not BoundScale.CHOICE:
            assert bound.low < bound.high


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_drawn_plant_says_what_every_signal_is(family_id: str) -> None:
    spec = get_family(family_id).draw(520)

    unexplained = sorted(set(spec.describe().signal_keys()) - set(spec.roles))

    assert not unexplained, (
        f"{family_id} drew signal(s) with no role: {unexplained}. A randomised tag name with no "
        "role is a column nobody can read."
    )


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_drawn_plant_can_be_grouped_from_its_own_structure(family_id: str) -> None:
    spec = get_family(family_id).draw(521)

    assert subsystems_from_components(spec) == subsystems(spec.describe())


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_drawn_plant_has_a_loop_on_something(family_id: str) -> None:
    spec = get_family(family_id).draw(522)

    assert spec.controllers, f"{family_id} drew a plant with no control at all"
    actuators = set(spec.describe().keys_of_kind(SignalKind.ACTUATOR))
    driven = {
        controller.output for controller in spec.controllers if controller.output in actuators
    }
    assert driven, f"{family_id} drew loops that drive nothing"


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_drawn_plant_grants_the_operator_its_setpoints_and_nobody_else_anything(
    family_id: str,
) -> None:
    spec = get_family(family_id).draw(523)
    authority = spec.write_authority
    network = spec.control_network
    assert authority is not None and network is not None

    assert set(authority.grants) == {"hmi"}, "only the operator's HMI writes in normal operation"
    setpoints = set(spec.describe().keys_of_kind(SignalKind.SETPOINT))
    assert set(authority.grants["hmi"]) <= setpoints
    assert any(node.node_id == "engineering" for node in network.nodes), (
        "a declared device that is granted nothing is what makes an unknown-master write "
        "measurable at all (ADR 0027)"
    )


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_a_drawn_plant_leaves_most_of_a_run_normal(family_id: str) -> None:
    spec = get_family(family_id).draw(524)
    disturbance = spec.disturbance

    low, high = disturbance.gap_steps
    assert low >= 1 and low <= high
    assert disturbance.event_plans, f"{family_id} drew a plant where nothing ever happens"
    longest = max(plan.duration_steps for plan in disturbance.event_plans)
    assert low >= 1, "events must not abut"
    assert longest < 10_000, "an event should not span a whole run"


def test_bounded_refuses_a_parameter_no_bound_declares() -> None:
    draw = SeedStreams(master_seed=1).draw("sizing")
    limits = {"area": ParameterBound("area", 1.0, 2.0, BoundScale.LINEAR, "m2", "x" * 40)}

    assert 1.0 <= bounded(draw, limits, "area") <= 2.0
    with pytest.raises(FamilyError, match="no declared bound"):
        bounded(draw, limits, "undeclared")


def test_an_empty_bound_is_refused() -> None:
    with pytest.raises(FamilyError, match="is empty"):
        ParameterBound("fixed", 5.0, 5.0, BoundScale.LINEAR)


def test_a_log_bound_reaching_zero_is_refused() -> None:
    with pytest.raises(FamilyError, match="orders of magnitude"):
        ParameterBound("tau", 0.0, 10.0, BoundScale.LOG)


def test_a_choice_bound_needs_more_than_one_option() -> None:
    with pytest.raises(FamilyError, match="is fixed, not drawn"):
        ParameterBound.among("nominal_hz", (50.0,))
    with pytest.raises(FamilyError, match="same option twice"):
        ParameterBound.among("nominal_hz", (50.0, 50.0))


def test_a_ranged_bound_may_not_name_options() -> None:
    with pytest.raises(FamilyError, match="only a CHOICE bound"):
        ParameterBound("x", 1.0, 2.0, BoundScale.LINEAR, options=(1.0, 2.0))


def test_a_choice_bound_draws_only_its_options_and_reaches_all_of_them() -> None:
    draw = SeedStreams(master_seed=9).draw("sizing")
    seen = {
        bounded(
            draw,
            {f"hz_{index}": ParameterBound.among(f"hz_{index}", (50.0, 60.0))},
            f"hz_{index}",
        )
        for index in range(60)
    }

    assert seen == {50.0, 60.0}


def test_an_unknown_family_names_the_ones_that_exist() -> None:
    with pytest.raises(FamilyError, match="level_flow"):
        get_family("not_a_family")


def test_the_bounds_table_renders_every_family_and_every_bound() -> None:
    table = bounds_table(OPEN_FAMILIES)

    for family in OPEN_FAMILIES:
        assert f"`{family.family_id}`" in table
        for bound in family.bounds():
            assert f"`{bound.name}`" in table, f"{family.family_id}:{bound.name} is not rendered"


def test_a_family_is_not_asked_to_validate_its_own_physics() -> None:
    """PART R3 owns the validity gate, and this test is here so that stays true.

    A family's job is to draw inside its declared bounds. Whether the result could exist — the
    pumps meeting the demand, the loops settling, the levels staying inside their spans — is a
    separate question answered by `phos.synth.validity`, which refuses a plant rather than
    nudging it into range. If a family starts rejecting its own draws, that reasoning has moved
    somewhere nobody is reviewing it.
    """
    for family in OPEN_FAMILIES:
        assert not hasattr(family, "validate"), (
            f"{family.family_id} has grown a validity check; it belongs in PART R3's gate"
        )


def test_a_family_declares_its_own_streams_rather_than_sharing_one() -> None:
    """Two families drawn on the same seed are different plants.

    Each draws from a `SeedStreams` on its own master seed and names its own process, so one
    seed does not give the same plant wearing five different physics.
    """
    specs = [get_family(family_id).draw(777) for family_id in FAMILY_IDS]

    processes = {spec.process for spec in specs}
    assert len(processes) == len(specs)
