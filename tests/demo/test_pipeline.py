"""``phos demo`` runs the real path, and reads ground truth only after Atlas has finished."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.demo import DemoResult, Scenario, run_demo
from phos.demo.pipeline import PLANT, describe_truth
from phos.reasoning.analyst import Assessment
from phos.synth.command import Authorisation, IssuedCommand
from phos.synth.plant import PlantDescription, RunSpec
from phos.synth.run import run_plant


@pytest.fixture(scope="module")
def unauthorised() -> DemoResult:
    return run_demo(Scenario.UNAUTHORISED, seed=11)


@pytest.fixture(scope="module")
def attacker() -> DemoResult:
    return run_demo(Scenario.ATTACKER, seed=11)


class TestUnauthorisedWrite:
    def test_atlas_sees_the_write_and_cannot_separate_maintenance_from_attack(
        self, unauthorised: DemoResult
    ) -> None:
        assert unauthorised.brief is not None
        assert unauthorised.brief.assessment is Assessment.UNRESOLVED
        assert unauthorised.concerns_truth
        assert unauthorised.unauthorised
        assert any("function 6" in finding for finding in unauthorised.findings)

    def test_stages_report_in_order(self, unauthorised: DemoResult) -> None:
        names = [stage.name for stage in unauthorised.stages]
        assert names == ["Simulating", "Learning", "Watching", "Reasoning"]


class TestAttackerAtTheEdge:
    def test_the_brief_shown_is_not_about_the_write_and_says_nothing_of_it(
        self, attacker: DemoResult
    ) -> None:
        # The catalogue attacker writes in the run's last minute and Atlas raises nothing about
        # it. Pinned so the demo keeps reporting the miss rather than borrowing an unrelated alert.
        assert attacker.unauthorised
        assert not attacker.concerns_truth


def _description() -> PlantDescription:
    spec = RunSpec(
        seed=1,
        start=datetime(2026, 3, 1, tzinfo=UTC),
        duration=timedelta(minutes=2),
        sample_interval=timedelta(seconds=30),
    )
    return run_plant(PLANT, spec).description


def test_truth_names_who_may_write_what_was_written() -> None:
    command = IssuedCommand(
        step_index=0,
        timestamp=datetime(2026, 3, 1, tzinfo=UTC),
        issuer="scada",
        target="plc_outlet",
        address=0,
        signal="clearwell_level_setpoint_m",
        requested=3.0,
        applied=3.0,
        authorised=Authorisation.UNAUTHORISED,
        reason="test",
    )
    (line,) = describe_truth([command, command], _description())
    assert line.startswith("The SCADA server wrote the clearwell level setpoint")
    assert line.endswith("Only the Control room HMI may write it. Unauthorised.")


def test_no_writes_is_said_plainly() -> None:
    assert describe_truth([], _description()) == ("No device wrote anything to the plant.",)
