"""The twelve U3 scenarios: constructible, seeded, and refused where a plant cannot host them."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phos.synth.command import Authorisation
from phos.synth.diagnostic_scenarios import (
    NO_NETWORK_REFUSAL,
    DiagnosticKind,
    construct,
    kinds,
    run_scenario,
)
from phos.synth.plant import SYNTHETIC_DERIVED


class TestTheTwelve:
    def test_there_are_twelve(self) -> None:
        assert len(kinds()) == 12

    def test_each_kind_is_constructible_on_water_treatment(self) -> None:
        for kind in kinds():
            scenario = construct(kind, seed=11)
            assert scenario.label == SYNTHETIC_DERIVED
            assert scenario.ground_truth
            run = run_scenario(scenario)
            assert len(run.steps) == scenario.spec.n_steps

    def test_batch_reactor_refuses_the_kinds_that_need_a_network(self) -> None:
        needing = (
            DiagnosticKind.COMMUNICATION_FAILURES,
            DiagnosticKind.LEGITIMATE_OPERATOR,
            DiagnosticKind.UNAUTHORISED_COMMANDS,
            DiagnosticKind.ATTACKER_ACTIVITY,
            DiagnosticKind.ATTACKER_DURING_MAINTENANCE,
        )
        for kind in needing:
            with pytest.raises(ValueError, match="no control network"):
                construct(kind, seed=11, plant_id="batch-reactor")
        ordinary = construct(DiagnosticKind.ORDINARY_OPERATION, seed=11, plant_id="batch-reactor")
        assert ordinary.plant_id == "batch-reactor"
        assert NO_NETWORK_REFUSAL

    def test_unauthorised_scada_write_is_unauthorised_in_ground_truth(self) -> None:
        scenario = construct(DiagnosticKind.UNAUTHORISED_COMMANDS, seed=11)
        run = run_scenario(scenario)
        issued = [command for step in run.steps for command in step.issued]
        assert issued
        assert all(command.authorised is Authorisation.UNAUTHORISED for command in issued)

    def test_authorised_hmi_write_is_authorised_in_ground_truth(self) -> None:
        scenario = construct(DiagnosticKind.LEGITIMATE_OPERATOR, seed=11)
        run = run_scenario(scenario)
        issued = [command for step in run.steps for command in step.issued]
        assert issued
        assert all(command.authorised is Authorisation.AUTHORISED for command in issued)

    def test_incomplete_observations_withhold_the_capture(self) -> None:
        scenario = construct(DiagnosticKind.INCOMPLETE_OBSERVATIONS, seed=11)
        assert scenario.with_capture is False

    def test_attacker_during_maintenance_does_not_move_the_calendar(self) -> None:
        scenario = construct(DiagnosticKind.ATTACKER_DURING_MAINTENANCE, seed=11)
        assert scenario.calendar is not None
        assert any("was not moved" in line for line in scenario.ground_truth)

    def test_when_the_adversary_picks_a_window_the_write_lands_inside_it(self) -> None:
        """A chosen window is a step at or after the order's start, not a floored miss."""
        scenario = construct(DiagnosticKind.ATTACKER_DURING_MAINTENANCE, seed=7)
        assert any("overlap_on_this_seed=True" in line for line in scenario.ground_truth)
        run = run_scenario(scenario)
        issued = [command for step in run.steps for command in step.issued]
        assert issued
        assert scenario.calendar is not None
        moments = [command.timestamp for command in issued]
        assert scenario.calendar.covered_windows({"clearwell": moments})

    def test_conflicting_observations_declare_two_true_stories(self) -> None:
        scenario = construct(DiagnosticKind.CONFLICTING_OBSERVATIONS, seed=11)
        assert any("two true stories" in line for line in scenario.ground_truth)
        run = run_scenario(scenario)
        assert run.realism.faults


def _digest_in_process(kind: str, seed: int) -> str:
    scenario = construct(DiagnosticKind(kind), seed=seed)
    run = run_scenario(scenario)
    payload = json.dumps([step.report.values for step in run.steps], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _digest_in_child(kind: str, seed: int) -> str:
    script = (
        "from phos.synth.diagnostic_scenarios import DiagnosticKind, construct, run_scenario;"
        "import hashlib, json;"
        f"s = construct(DiagnosticKind({kind!r}), seed={seed});"
        "r = run_scenario(s);"
        "p = json.dumps([step.report.values for step in r.steps], sort_keys=True);"
        "print(hashlib.sha256(p.encode()).hexdigest())"
    )
    env_python = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python"
    python = str(env_python) if env_python.exists() else sys.executable
    out = subprocess.check_output([python, "-c", script], text=True)
    return out.strip()


class TestReproducibilityAcrossProcesses:
    @pytest.mark.parametrize("kind", [kind.value for kind in DiagnosticKind])
    def test_three_separate_processes_agree(self, kind: str) -> None:
        first = _digest_in_child(kind, 11)
        second = _digest_in_child(kind, 11)
        third = _digest_in_process(kind, 11)
        assert first == second == third
