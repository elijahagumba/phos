"""Two runs of one seed, and whether the difference between them is what the label says it is.

The tests that matter most here are the ones that check each attack does the specific thing its
name claims. It is easy to write an injector that produces *a* difference and label it "liar"; the
question is whether the true state really ran away while the telemetry really stayed calm, and
that is only answerable because D1 records truth independently of the instruments.
"""

import statistics
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import pytest
from tests.synth.attacks.conftest import (
    CHLORINE_DOSE,
    CLEARWELL_LEVEL,
    INTAKE_SPEED,
    LEVEL_SETPOINT,
    LEVEL_SETPOINT_CHANGE,
    PLANT,
    RAW_INFLOW,
    a_spec,
)

from phos.atlas.packet import (
    UNKNOWN_COMMAND_RELATIONSHIP,
    CaptureStats,
    DissectorRegistry,
    MalformedFrame,
    ModbusDissector,
    ModbusMessage,
    compare_to_graph,
    device_entity_id,
    dissect_capture,
    learn_device_command_graph,
)
from phos.eval import Dataset
from phos.synth import TrafficPolicy, modbus_frames, write_pcap
from phos.synth.attacks.inject import (
    ATTACK_LABEL_VALUE,
    NORMAL_LABEL_VALUE,
    AttackRun,
    attack_dataset,
    attack_source_note,
    inject,
    truth_rows,
)
from phos.synth.attacks.spec import AttackPlan, AttackType

REGISTRY = DissectorRegistry([ModbusDissector()])


def blatant(**overrides: object) -> AttackPlan:
    """A blunt push on the intake pump, 02:00 to 04:00."""
    fields: dict[str, object] = {
        "attack_id": "blatant",
        "type": AttackType.BLATANT,
        "subtlety": 0.0,
        "start_hours": 2.0,
        "duration_hours": 2.0,
        "target": INTAKE_SPEED,
    }
    fields.update(overrides)
    return AttackPlan.model_validate(fields)


LIAR = AttackPlan(
    attack_id="liar",
    type=AttackType.LIAR,
    subtlety=0.0,
    start_hours=2.0,
    duration_hours=3.0,
    target=CLEARWELL_LEVEL,
    reference=LEVEL_SETPOINT,
)

CORRELATION = AttackPlan(
    attack_id="correlation",
    type=AttackType.CORRELATION_BREAK,
    subtlety=0.0,
    start_hours=2.0,
    duration_hours=3.0,
    target=RAW_INFLOW,
    reference=INTAKE_SPEED,
)

MIMIC = AttackPlan(
    attack_id="mimic",
    type=AttackType.MIMIC,
    subtlety=0.0,
    start_hours=2.0,
    duration_hours=3.0,
    target=LEVEL_SETPOINT,
    mimics=LEVEL_SETPOINT_CHANGE,
)

ROGUE = AttackPlan(
    attack_id="rogue",
    type=AttackType.ROGUE_COMMAND,
    subtlety=0.0,
    start_hours=6.0,
    duration_hours=2.0,
    target=LEVEL_SETPOINT,
    issuer="scada",
)


def run_with(*plans: AttackPlan, allow_inert: bool = False) -> AttackRun:
    """Inject the given attacks into twelve hours of the works."""
    return inject(PLANT, a_spec(), plans, allow_inert=allow_inert)


def reported(run: AttackRun, key: str, first: int, last: int) -> list[float]:
    """Return a slice of what the attacked run reported for one signal."""
    return [step.report.values[key] for step in run.attacked.steps[first:last]]


def truth(run: AttackRun, key: str, first: int, last: int) -> list[float]:
    """Return a slice of what the attacked run was truly doing for one signal."""
    return [step.truth.values[key] for step in run.attacked.steps[first:last]]


def _increments(values: list[float]) -> list[float]:
    """Return the absolute sample-to-sample movement of a series."""
    return [abs(later - earlier) for earlier, later in pairwise(values)]


class TestTheCleanBaseline:
    """The first run is the reference, and nothing about it may have been disturbed."""

    def test_a_corpus_with_no_attacks_is_the_clean_run_twice(self) -> None:
        run = run_with()
        assert [step.report.values for step in run.attacked.steps] == [
            step.report.values for step in run.clean.steps
        ]
        assert run.attacks == ()
        assert run.intervals() == []

    def test_the_two_runs_are_identical_until_the_first_window_opens(self) -> None:
        run = run_with(blatant())
        opens_at = run.attacks[0].started_at
        for clean_step, attacked_step in zip(run.clean.steps, run.attacked.steps, strict=True):
            if clean_step.timestamp >= opens_at:
                break
            # Bit-identical, not close: D1's property, inherited unchanged by every D2 attack.
            assert clean_step.report.values == attacked_step.report.values
            assert clean_step.truth.values == attacked_step.truth.values

    def test_the_clean_run_carries_no_injected_commands(self) -> None:
        run = run_with(ROGUE)
        assert run.clean.command_count < run.attacked.command_count

    def test_injection_is_reproducible(self) -> None:
        first = run_with(blatant(), ROGUE)
        second = run_with(blatant(), ROGUE)
        assert [s.report.values for s in first.attacked.steps] == [
            s.report.values for s in second.attacked.steps
        ]
        assert first.attacks == second.attacks


class TestBlatant:
    """The control case: it should be impossible to miss."""

    def test_it_moves_the_plant_a_long_way(self) -> None:
        run = run_with(blatant())
        assert run.attacks[0].physical_effect
        assert run.attacks[0].peak_truth_departure() > 1.0

    def test_what_it_did_is_visible_in_the_telemetry_while_it_happens(self) -> None:
        run = run_with(blatant())
        assert run.attacks[0].peak_report_departure() > 1.0

    def test_the_intake_itself_is_among_the_signals_that_moved(self) -> None:
        run = run_with(blatant())
        assert INTAKE_SPEED in run.attacks[0].truth_departure


class TestStealthDrift:
    """Nothing to see between one sample and the next, and a long way from where it started."""

    def test_no_single_step_of_the_manipulated_signal_is_larger_than_normal_ones(self) -> None:
        clean = run_with()
        run = run_with(
            AttackPlan(
                attack_id="drift",
                type=AttackType.STEALTH_DRIFT,
                subtlety=0.0,
                start_hours=2.0,
                duration_hours=6.0,
                target=CHLORINE_DOSE,
            )
        )
        first, last = 240, 960
        normal_steps = _increments(reported(clean, CHLORINE_DOSE, first, last))
        attacked_steps = _increments(reported(run, CHLORINE_DOSE, first, last))
        # The sample-to-sample movement is indistinguishable in size from ordinary operation.
        assert max(attacked_steps) < max(normal_steps) * 1.5

    def test_and_yet_it_ends_somewhere_it_should_not_be(self) -> None:
        run = run_with(
            AttackPlan(
                attack_id="drift",
                type=AttackType.STEALTH_DRIFT,
                subtlety=0.0,
                start_hours=2.0,
                duration_hours=6.0,
                target=CHLORINE_DOSE,
            )
        )
        assert run.attacks[0].peak_truth_departure() > 0.5
        assert run.attacks[0].physical_effect


class TestCorrelationBreak:
    """Every signal in its own normal range, and the relation between them gone."""

    def test_the_falsified_signal_never_leaves_the_range_it_normally_occupies(self) -> None:
        clean = run_with()
        run = run_with(CORRELATION)
        normal = [step.report.values[RAW_INFLOW] for step in clean.attacked.steps]
        during = reported(run, RAW_INFLOW, 240, 600)
        assert min(during) >= min(normal)
        assert max(during) <= max(normal)

    def test_the_declared_relation_between_the_two_signals_is_destroyed(self) -> None:
        clean = run_with()
        run = run_with(CORRELATION)
        first, last = 240, 600
        before = statistics.correlation(
            [step.report.values[RAW_INFLOW] for step in clean.attacked.steps[first:last]],
            [step.report.values[INTAKE_SPEED] for step in clean.attacked.steps[first:last]],
        )
        after = statistics.correlation(
            reported(run, RAW_INFLOW, first, last), reported(run, INTAKE_SPEED, first, last)
        )
        # The plant declares that inflow follows the square root of pump speed. It did, and now
        # it does not — while neither signal has left its own range.
        assert before > 0.9
        assert abs(after) < 0.3

    def test_the_falsified_signal_still_carries_noise_of_a_plausible_size(self) -> None:
        # A transmitter that suddenly stopped being noisy would announce the injection to the
        # crudest variance check there is, and Atlas would be catching our machinery.
        run = run_with(CORRELATION)
        during = reported(run, RAW_INFLOW, 300, 540)
        declared = run.description.signal(RAW_INFLOW).noise_stddev
        assert statistics.pstdev(during) == pytest.approx(declared, rel=0.35)

    def test_it_moves_no_plant_and_says_so(self) -> None:
        # Nothing on this works controls on raw inflow, so falsifying it deceives no loop. That
        # is an honest answer and the ground truth records it rather than implying danger.
        run = run_with(CORRELATION)
        assert not run.attacks[0].physical_effect
        assert run.attacks[0].peak_truth_departure() == 0.0
        assert run.attacks[0].peak_report_departure() > 0.0


class TestLiar:
    """The data looks calmest when things are worst."""

    def test_the_true_state_is_driven_away_from_where_it_should_have_been(self) -> None:
        run = run_with(LIAR)
        clean = run_with()
        # Against the counterfactual, not against an absolute threshold: the question is what
        # this plant would have been doing had nobody lied to it.
        during = truth(run, CLEARWELL_LEVEL, 240, 600)
        would_have = [step.truth.values[CLEARWELL_LEVEL] for step in clean.attacked.steps[240:600]]
        assert max(during) > max(would_have)
        assert run.attacks[0].truth_departure[CLEARWELL_LEVEL] > 0.4
        assert run.attacks[0].physical_effect

    def test_while_the_telemetry_stays_inside_its_normal_range(self) -> None:
        run = run_with(LIAR)
        clean = run_with()
        during_report = reported(run, CLEARWELL_LEVEL, 240, 600)
        normal_report = [step.report.values[CLEARWELL_LEVEL] for step in clean.attacked.steps]
        assert max(during_report) <= max(normal_report)
        assert min(during_report) >= min(normal_report)

    def test_truth_and_telemetry_stop_agreeing_which_is_the_whole_attack(self) -> None:
        clean = run_with()
        run = run_with(LIAR)

        def divergence(candidate: AttackRun) -> float:
            """Return how far the instruments were from the plant, at worst, during the window."""
            return max(
                abs(step.truth.values[CLEARWELL_LEVEL] - step.report.values[CLEARWELL_LEVEL])
                for step in candidate.attacked.steps[240:600]
            )

        # In normal operation the instruments agree with the plant to within D1's declared error
        # model — noise plus a bounded calibration drift. Under the liar they do not, and the
        # size of that disagreement is the size of the blindfold. It is only measurable at all
        # because D1 recorded the truth independently of the instruments from sample zero.
        assert divergence(clean) < 0.05
        assert divergence(run) > 0.35

    def test_the_reported_level_is_never_far_from_its_setpoint(self) -> None:
        run = run_with(LIAR)
        levels = reported(run, CLEARWELL_LEVEL, 300, 540)
        setpoints = reported(run, LEVEL_SETPOINT, 300, 540)
        gaps = [abs(level - setpoint) for level, setpoint in zip(levels, setpoints, strict=True)]
        assert max(gaps) < 0.6

    def test_the_falsified_level_still_wobbles(self) -> None:
        run = run_with(LIAR)
        during = reported(run, CLEARWELL_LEVEL, 300, 540)
        assert statistics.pstdev(during) > 0.0


class TestMimic:
    """A setpoint that moved, and nobody who moved it."""

    def test_the_reported_setpoint_takes_a_value_it_legitimately_takes(self) -> None:
        clean = run_with()
        run = run_with(MIMIC)
        normal = [step.report.values[LEVEL_SETPOINT] for step in clean.attacked.steps]
        during = reported(run, LEVEL_SETPOINT, 240, 600)
        assert min(during) >= min(normal)
        assert max(during) <= max(normal)

    def test_the_plant_s_own_setpoint_never_moved(self) -> None:
        # The true setpoint is what an operator set. It is untouched; only the report lies. That
        # separation is what lets the corpus say "this was not an operator" with certainty.
        run = run_with(MIMIC)
        assert run.attacks[0].truth_departure.get(LEVEL_SETPOINT) is None

    def test_and_the_plant_moved_anyway(self) -> None:
        # The level loop reads the report, so a falsified setpoint is a real setpoint.
        run = run_with(MIMIC)
        assert run.attacks[0].physical_effect
        assert CLEARWELL_LEVEL in run.attacks[0].truth_departure

    def test_nothing_was_written_on_the_network(self) -> None:
        run = run_with(MIMIC)
        assert run.attacks[0].commands_injected == 0
        assert run.attacked.command_count == run.clean.command_count


class TestCommandAttacks:
    """Traffic an attacker added, and a capture that still parses."""

    def test_the_extra_writes_reach_the_run(self) -> None:
        run = run_with(ROGUE)
        added = run.attacked.command_count - run.clean.command_count
        assert added == run.attacks[0].commands_injected > 0

    def test_the_capture_still_parses_without_one_malformed_frame(self, tmp_path: Path) -> None:
        run = run_with(ROGUE)
        path = tmp_path / "capture.pcap"
        frames = modbus_frames(run.description, run.attacked.steps, TrafficPolicy(seed=11))
        write_pcap(frames, path)
        stats = CaptureStats()
        results = list(dissect_capture(path, REGISTRY, stats))
        assert results
        assert not [result for result in results if isinstance(result, MalformedFrame)]
        assert stats.accounts_for_every_frame()

    def test_the_rogue_write_is_visible_in_the_capture_as_coming_from_the_wrong_device(
        self, tmp_path: Path
    ) -> None:
        run = run_with(ROGUE)
        path = tmp_path / "capture.pcap"
        write_pcap(modbus_frames(run.description, run.attacked.steps, TrafficPolicy(seed=11)), path)
        network = run.description.control_network
        assert network is not None
        writes = [
            result
            for result in dissect_capture(path, REGISTRY, None)
            if isinstance(result, ModbusMessage) and result.function_code == 6
        ]
        assert network.node("scada").ip in {message.src.ip for message in writes}

    def test_an_engineering_write_is_an_unknown_command_relationship(self, tmp_path: Path) -> None:
        """The ADR 0027 shape: a silent workstation writes, and the graph names a new link."""
        plan = AttackPlan(
            attack_id="unknown-master",
            type=AttackType.ROGUE_COMMAND,
            subtlety=0.0,
            start_hours=3.0,
            duration_hours=1.5,
            target=LEVEL_SETPOINT,
            issuer="engineering",
        )
        run = run_with(plan)
        policy = TrafficPolicy(seed=11)
        baseline = tmp_path / "baseline.pcap"
        live = tmp_path / "live.pcap"
        write_pcap(modbus_frames(run.description, run.clean.steps, policy), baseline)
        write_pcap(modbus_frames(run.description, run.attacked.steps, policy), live)
        graph = learn_device_command_graph(dissect_capture(baseline, REGISTRY))
        findings = compare_to_graph(graph, dissect_capture(live, REGISTRY))
        network = run.description.control_network
        assert network is not None
        engineering = device_entity_id(network.node("engineering").ip)
        unknown = [
            finding
            for finding in findings
            if finding.feature == UNKNOWN_COMMAND_RELATIONSHIP and engineering in finding.entity_ids
        ]
        assert unknown
        assert engineering not in {edge.issuer for edge in graph.edges}

    def test_the_setpoint_moved_to_exactly_what_the_write_carried(self) -> None:
        # Wire and telemetry agree, so nothing can find this attack by their disagreement.
        run = run_with(ROGUE)
        first = run.attacked.steps[run.clean.spec.n_steps // 2]
        assert first.report.values[LEVEL_SETPOINT] > 0.0
        assert run.attacks[0].physical_effect


class TestGroundTruth:
    """What the corpus claims, and the claims it refuses to make."""

    def test_one_interval_per_attack_in_time_order(self) -> None:
        run = run_with(blatant(), ROGUE)
        intervals = run.intervals()
        assert len(intervals) == 2
        assert intervals[0].start < intervals[1].start
        assert {interval.label for interval in intervals} == {"attack"}
        assert {interval.attack_type for interval in intervals} == {"BLATANT", "ROGUE_COMMAND"}

    def test_the_label_column_follows_the_intervals(self) -> None:
        run = run_with(blatant())
        inside = run.attacks[0].started_at + timedelta(minutes=30)
        outside = run.spec.start + timedelta(minutes=5)
        assert run.label_at(inside) == ATTACK_LABEL_VALUE
        assert run.label_at(outside) == NORMAL_LABEL_VALUE

    def test_the_attacks_are_recorded_in_time_order_whatever_order_they_were_given(self) -> None:
        run = run_with(ROGUE, blatant())
        assert [attack.attack_id for attack in run.attacks] == ["blatant", "rogue"]

    def test_an_attack_that_changed_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="ground truth that lies"):
            run_with(blatant(subtlety=1.0))

    def test_the_zero_magnitude_control_can_be_asked_for_explicitly(self) -> None:
        run = run_with(blatant(subtlety=1.0), allow_inert=True)
        assert run.attacks[0].peak_truth_departure() == 0.0
        assert not run.attacks[0].physical_effect

    def test_overlapping_attacks_are_refused(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            run_with(blatant(), blatant(attack_id="second", start_hours=3.0))

    def test_attacks_that_merely_abut_are_allowed(self) -> None:
        run = run_with(blatant(), blatant(attack_id="second", start_hours=4.0))
        assert len(run.attacks) == 2

    def test_the_true_state_is_recorded_for_every_sample(self) -> None:
        run = run_with(LIAR)
        rows = truth_rows(run)
        assert len(rows) == len(run.attacked.steps)
        assert set(rows[0]) == set(run.description.signal_keys())

    def test_the_recorded_truth_is_the_truth_and_not_the_telemetry(self) -> None:
        run = run_with(LIAR)
        rows = truth_rows(run)
        during = [row[CLEARWELL_LEVEL] for row in rows[240:600]]
        assert max(during) > max(reported(run, CLEARWELL_LEVEL, 240, 600))


class TestTheCorpus:
    """What leaves through the door the evaluation harness already has."""

    def test_it_is_a_dataset_the_harness_can_score(self) -> None:
        run = run_with(blatant())
        dataset = attack_dataset(run)
        assert isinstance(dataset, Dataset)
        assert dataset.attack_intervals
        assert dataset.observations

    def test_the_observations_are_what_the_instruments_said_and_not_the_truth(self) -> None:
        run = run_with(LIAR)
        dataset = attack_dataset(run)
        levels = [
            observation.value
            for observation in dataset.observations
            if observation.feature == CLEARWELL_LEVEL
        ]
        assert levels == [step.report.values[CLEARWELL_LEVEL] for step in run.attacked.steps]

    def test_the_normal_span_excludes_the_attack_windows(self) -> None:
        run = run_with(blatant())
        dataset = attack_dataset(run)
        assert dataset.normal_duration() < dataset.duration()

    def test_the_note_carries_both_caveats(self) -> None:
        note = attack_source_note(run_with(blatant()))
        assert "MODEL of an industrial process" in note
        assert "attacks WE designed" in note
        assert "fingerprint" in note

    def test_the_dataset_takes_the_name_it_is_given(self) -> None:
        assert attack_dataset(run_with(blatant()), "named").name == "named"

    def test_the_default_name_says_which_plant_it_is(self) -> None:
        assert attack_dataset(run_with(blatant())).name == f"synth-attack-{PLANT}"
