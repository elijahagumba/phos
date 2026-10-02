"""Scenarios: an adversary who pursues a goal, and is not told what a detector would see.

The behaviour under test is that a goal produces writes, that patience decides how the move is
spread, and that the adversary is closed-loop on the *reported* readings — which is what makes an
adversary who has also falsified those readings capable of being wrong.

The structural properties — that a scenario cannot name a detector quantity, and must carry
provenance — live in `test_anti_bias.py`, because they are enforcement rather than behaviour.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.synth.catalogue_scenarios import SCENARIOS, scenarios_for
from phos.synth.scenarios import (
    Direction,
    GoalSeekingSource,
    PhysicalGoal,
    Provenance,
    ProvenanceKind,
    Scenario,
)

START = datetime(2026, 3, 1, tzinfo=UTC)
SIGNAL = "clearwell_level_setpoint_m"

CITATION = Provenance(
    kind=ProvenanceKind.PROCESS_FAILURE_MODE,
    citation="Conventional surface-water treatment practice on clearwell overflow to waste",
    shape="A level target walked outside the range the works is operated within",
)


def scenario(patience: int = 4, first: int = 10, limit: float = 5.0) -> Scenario:
    """Build a scenario raising the clearwell level toward ``limit``."""
    return Scenario(
        scenario_id="fixture-goal",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative="Raise the clearwell level past the point the works is operated to",
            signal=SIGNAL,
            direction=Direction.RAISE,
            limit=limit,
            constraints=("Use the ordinary write path",),
        ),
        provenance=CITATION,
        issuer="scada",
        asset_id="clearwell",
        patience_steps=patience,
        first_step=first,
    )


def drive(source: GoalSeekingSource, steps: int, start_value: float = 3.0) -> list[float]:
    """Step a source through ``steps`` samples, holding the reported setpoint constant."""
    written: list[float] = []
    for index in range(steps):
        writes = source.writes_at(index, START + timedelta(minutes=index), {SIGNAL: start_value})
        written.extend(write.value for write in writes)
    return written


class TestTheAdversaryPursuesTheGoal:
    """A goal in plant terms becomes writes, and the writes go where the goal says."""

    def test_it_writes_nothing_before_it_begins(self) -> None:
        assert drive(scenario(first=10).source(low=0.0, high=6.0), steps=10) == []

    def test_it_writes_nothing_after_its_patience_is_spent(self) -> None:
        source = scenario(patience=4, first=10).source(low=0.0, high=6.0)
        assert len(drive(source, steps=40)) == 4

    def test_an_impatient_adversary_arrives_in_one_move(self) -> None:
        written = drive(scenario(patience=1, first=0, limit=5.0).source(low=0.0, high=6.0), 5)
        assert written == [pytest.approx(5.0)]

    def test_a_patient_adversary_walks_there_in_equal_steps(self) -> None:
        written = drive(scenario(patience=4, first=0, limit=5.0).source(low=0.0, high=6.0), 6)
        assert written == [
            pytest.approx(3.5),
            pytest.approx(4.0),
            pytest.approx(4.5),
            pytest.approx(5.0),
        ]

    def test_the_walk_ends_at_the_goal_however_long_the_patience(self) -> None:
        for patience in (1, 2, 17, 300):
            written = drive(scenario(patience=patience, first=0).source(low=0.0, high=6.0), 400)
            assert written[-1] == pytest.approx(5.0)

    def test_a_lowering_goal_walks_downward(self) -> None:
        lowering = Scenario(
            scenario_id="fixture-lower",
            plant_id="water-treatment",
            goal=PhysicalGoal(
                narrative="Lower the clearwell level enough to erode contact time",
                signal=SIGNAL,
                direction=Direction.LOWER,
                limit=1.0,
            ),
            provenance=CITATION,
            issuer="scada",
            asset_id="clearwell",
            patience_steps=4,
            first_step=0,
        )
        written = drive(lowering.source(low=0.0, high=6.0), 6)
        assert written == sorted(written, reverse=True)
        assert written[-1] == pytest.approx(1.0)

    def test_the_goal_is_bounded_by_the_instrument_span(self) -> None:
        """A goal past the span is clipped to it; the plant would clamp anyway."""
        written = drive(scenario(patience=1, first=0, limit=99.0).source(low=0.0, high=6.0), 3)
        assert written == [pytest.approx(6.0)]

    def test_the_anchor_is_fixed_at_the_first_write(self) -> None:
        """A walk that re-anchored each step would chase a value it is itself moving."""
        source = scenario(patience=4, first=0, limit=5.0).source(low=0.0, high=6.0)
        first = source.writes_at(0, START, {SIGNAL: 3.0})[0].value
        # The plant has now moved; the adversary sees the new value on its next look.
        second = source.writes_at(1, START, {SIGNAL: first})[0].value
        assert second == pytest.approx(4.0)


class TestTheAdversarySeesOnlyReports:
    """Closed-loop on what a hijacked station shows, which is what lets it be fooled."""

    def test_a_target_the_plant_does_not_report_is_refused(self) -> None:
        source = scenario(first=0).source(low=0.0, high=6.0)
        with pytest.raises(KeyError, match="does not report"):
            source.writes_at(0, START, {"something_else": 1.0})

    def test_the_write_carries_the_scenario_as_provenance(self) -> None:
        source = scenario(first=0).source(low=0.0, high=6.0)
        write = source.writes_at(0, START, {SIGNAL: 3.0})[0]
        assert write.reason == "scenario: fixture-goal"
        assert write.issuer == "scada"
        assert write.signal == SIGNAL


class TestTheScenarioIsValidated:
    """A scenario that cannot happen is a definition mistake."""

    def test_patience_below_one_sample_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            scenario(patience=0)

    def test_a_negative_start_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            scenario(first=-1)

    def test_an_empty_narrative_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            PhysicalGoal(narrative="short", signal=SIGNAL, direction=Direction.RAISE, limit=1.0)

    def test_prose_gathers_every_free_text_field(self) -> None:
        text = scenario().prose()
        assert "clearwell" in text
        assert "surface-water treatment" in text
        assert "ordinary write path" in text


class TestTheCatalogue:
    """What ships, and which plants it is written against."""

    def test_every_scenario_is_bound_to_a_plant_with_a_control_network(self) -> None:
        assert {item.plant_id for item in SCENARIOS} == {"water-treatment", "power-generation"}

    def test_scenario_identifiers_are_unique(self) -> None:
        ids = [item.scenario_id for item in SCENARIOS]
        assert len(set(ids)) == len(ids)

    def test_scenarios_are_written_from_more_than_one_issuer(self) -> None:
        """Known station, compromised known station and silent workstation all appear."""
        assert {item.issuer for item in SCENARIOS} == {"hmi", "scada", "engineering"}

    def test_selecting_by_plant_returns_only_that_plant(self) -> None:
        assert all(item.plant_id == "water-treatment" for item in scenarios_for("water-treatment"))

    def test_selecting_an_unknown_plant_returns_nothing(self) -> None:
        assert scenarios_for("no-such-plant") == ()

    def test_every_catalogue_scenario_produces_writes(self) -> None:
        """A scenario that reached the catalogue and does nothing would be silent ground truth."""
        for item in SCENARIOS:
            source = item.source(low=0.0, high=100.0)
            written = [
                write
                for index in range(item.first_step, item.first_step + item.patience_steps)
                for write in source.writes_at(
                    index, START + timedelta(minutes=index), {item.goal.signal: 1.0}
                )
            ]
            assert written, item.scenario_id
