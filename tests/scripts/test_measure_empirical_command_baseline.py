"""The ordinary-run false-alarm count, without simulating a plant."""

from dataclasses import replace

from scripts.measure_empirical_command_baseline import SEEDS, concerns_the_write, false_alarms

from phos.demo import DemoResult, Scenario
from phos.demo.pipeline import Stage
from phos.eval.decision_fixtures import atlas_cases
from phos.reasoning.analyst import assess_narrative


def _result(**overrides: object) -> DemoResult:
    case = next(item for item in atlas_cases() if item.case_id == "known-station-write")
    result = DemoResult(
        scenario=Scenario.OPERATOR,
        seed=11,
        plant_label="Water treatment",
        stages=(Stage(name="Learning", detail="messages", seconds=1.0),),
        subject="SCADA server",
        brief=assess_narrative(case.narrative, case.store, case.library),
        findings=(),
        other_incidents=0,
        truth=("The Control room HMI wrote a setpoint. It is allowed to. Authorised.",),
        writes=1,
        unauthorised=False,
        concerns_truth=False,
    )
    return replace(result, **overrides)  # type: ignore[arg-type]


def test_silence_is_zero_false_alarms() -> None:
    assert false_alarms(replace(_result(), brief=None)) == 0


def test_an_unrelated_incident_is_one_false_alarm() -> None:
    assert false_alarms(_result()) == 1


def test_further_incidents_count_with_the_one_shown() -> None:
    assert false_alarms(replace(_result(), other_incidents=2)) == 3


def test_a_brief_about_the_write_is_not_itself_a_false_alarm() -> None:
    # Extras still are: the demo only checks the narrative it shows.
    assert false_alarms(replace(_result(), concerns_truth=True, other_incidents=1)) == 1
    assert false_alarms(replace(_result(), concerns_truth=True, other_incidents=0)) == 0


def test_a_brief_concerns_the_write_only_when_the_demo_says_it_does() -> None:
    assert concerns_the_write(replace(_result(), concerns_truth=True))
    assert not concerns_the_write(_result())
    assert not concerns_the_write(replace(_result(), brief=None, concerns_truth=True))


def test_the_seed_list_was_fixed_at_twenty_starting_from_the_named_seed() -> None:
    assert SEEDS == tuple(range(11, 31))
    assert len(SEEDS) == 20
    assert SEEDS[0] == 11
