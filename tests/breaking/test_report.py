"""The report: two maps kept apart, the caveats carried, and the log written."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.breaking.conftest import ground_truth

from phos.breaking import FingerprintStatus, assess_fingerprint
from phos.breaking.commands import (
    ATTACK_TEMPLATE_ID,
    CommandIssuerKind,
    CommandReasoningResult,
    ExplanationRanking,
)
from phos.breaking.harness import BreakingConfig, CorpusBreakdown
from phos.breaking.outcome import AttackOutcome, RobustnessOutcome, RobustnessVerdict
from phos.breaking.report import (
    ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT,
    BREAKING_HARNESS_CAVEATS,
    assemble,
    render,
    summary_json,
    write_report,
)
from phos.breaking.robustness import CorpusRobustness
from phos.breaking.truth import SignalExcursion, TrueStateVerdict
from phos.eval.report import EvaluationReport, LatencySummary
from phos.ontology import Domain
from phos.synth import PlantDescription
from phos.synth.attacks import INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT, AttackType, DifficultyLevel


def harness_report(name: str = "fixture") -> EvaluationReport:
    """A minimal `phos.eval` report, so the renderer has real numbers to lay out."""
    return EvaluationReport(
        detector_name="atlas-vertical:fixture",
        dataset_name=name,
        domain=Domain.ATLAS,
        seed=7,
        alert_threshold=0.0,
        match_tolerance_seconds=60.0,
        calibration_bins=10,
        n_observations=100,
        n_detections=4,
        n_alerts=4,
        n_attack_intervals=2,
        normal_hours=10.0,
        window_recall=0.5,
        false_positives=3,
        false_positive_rate=0.3,
        precision=0.25,
        recall_sample=0.1,
        f1=0.14,
        latency=LatencySummary(
            count=1, min_seconds=30.0, median_seconds=30.0, mean_seconds=30.0, max_seconds=30.0
        ),
        expected_calibration_error=0.1,
        brier_score=0.2,
    )


def outcome(
    plant: PlantDescription,
    attack_id: str,
    attack_type: AttackType,
    subtlety: float,
    *,
    detected: bool,
    targets: tuple[str, ...] = ("pump_pct",),
    dangerous: bool = False,
) -> AttackOutcome:
    """One measured outcome, assembled without running anything."""
    truth = ground_truth(attack_id, attack_type, subtlety=subtlety, targets=targets)
    excursions: tuple[SignalExcursion, ...] = ()
    if dangerous:
        excursions = (
            SignalExcursion(
                signal="level_m",
                envelope_low=0.0,
                envelope_high=10.0,
                window_low=10.0,
                window_high=40.0,
                excess=30.0,
                margin=0.03,
            ),
        )
    return AttackOutcome(
        attack_id=attack_id,
        attack_type=attack_type,
        subtlety=subtlety,
        difficulty=DifficultyLevel.for_subtlety(subtlety),
        corpus="fixture",
        plant_id=plant.plant_id,
        detected=detected,
        n_alerts=1 if detected else 0,
        fingerprint=assess_fingerprint(truth, plant),
        true_state=TrueStateVerdict(
            attack_id=attack_id,
            dangerous=dangerous,
            excursions=excursions,
            peak_excess=30.0 if dangerous else 0.0,
            peak_signal="level_m" if dangerous else "",
        ),
    )


def breakdown(plant: PlantDescription, *outcomes: AttackOutcome) -> CorpusBreakdown:
    """A per-corpus result carrying the given outcomes."""
    return CorpusBreakdown(
        corpus="fixture",
        plant_id=plant.plant_id,
        fit_corpus="synth-fixture-train",
        outcomes=outcomes,
        report=harness_report(),
        n_events=4,
        n_narratives=2,
    )


def test_the_two_maps_never_share_a_row(plant: PlantDescription) -> None:
    """The headline claim must not rest on a result carrying D2's documented residual."""
    report = assemble(
        [
            breakdown(
                plant,
                outcome(plant, "clean", AttackType.BLATANT, 0.0, detected=True),
                outcome(
                    plant, "caveated", AttackType.LIAR, 0.0, detected=True, targets=("level_m",)
                ),
            )
        ],
        [],
        BreakingConfig(),
    )
    assert all(row.fingerprint is FingerprintStatus.CLEAN for row in report.clean_map)
    assert all(row.fingerprint is FingerprintStatus.CAVEATED for row in report.caveated_map)
    clean_types = {row.attack_type for row in report.clean_map}
    caveated_types = {row.attack_type for row in report.caveated_map}
    assert not clean_types & caveated_types


def test_the_rendered_report_keeps_the_flavours_in_separate_sections(
    plant: PlantDescription,
) -> None:
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [
            CorpusRobustness(
                corpus="synth-hostile-fixture",
                outcomes=(
                    RobustnessOutcome(
                        attack_id="h1",
                        attack_type=AttackType.MALFORMED_RECORD,
                        verdict=RobustnessVerdict.REFUSED,
                        error_type="ParserError",
                    ),
                ),
                loaded=False,
            )
        ],
        BreakingConfig(),
    )
    text = render(report)
    detection_at = text.index("breaking-point map — clean results")
    hostile_at = text.index("Input-hostile robustness — a separate claim")
    assert detection_at < hostile_at
    assert "supports no claim" in text or "not evidence that PHOS is secure" in text
    assert "NEVER combined" in text


def test_every_caveat_reaches_the_rendered_report(plant: PlantDescription) -> None:
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    text = render(report)
    for caveat in BREAKING_HARNESS_CAVEATS:
        assert caveat in text, f"missing caveat: {caveat[:60]}"


def test_a_dangerous_miss_is_named_in_the_blind_spot_summary(plant: PlantDescription) -> None:
    """The worst cell must not be something a reader has to hunt for."""
    report = assemble(
        [
            breakdown(
                plant,
                outcome(
                    plant,
                    "wt-liar",
                    AttackType.LIAR,
                    0.75,
                    detected=False,
                    targets=("steady_sensor",),
                    dangerous=True,
                ),
            )
        ],
        [],
        BreakingConfig(),
    )
    assert [o.attack_id for o in report.dangerous_misses()] == ["wt-liar"]
    text = render(report)
    assert "wt-liar" in text
    assert "all-clear" in text
    assert "not from the telemetry" in text


def test_an_alert_on_the_inert_control_is_reported_as_a_leaked_fingerprint(
    plant: PlantDescription,
) -> None:
    report = assemble(
        [breakdown(plant, outcome(plant, "control", AttackType.BLATANT, 1.0, detected=True))],
        [],
        BreakingConfig(),
    )
    assert [o.attack_id for o in report.leaked_fingerprints()] == ["control"]
    text = render(report)
    assert "WARNING" in text
    assert "leaking a tell" in text


def test_a_quiet_inert_control_is_reported_as_the_check_passing(plant: PlantDescription) -> None:
    report = assemble(
        [breakdown(plant, outcome(plant, "control", AttackType.BLATANT, 1.0, detected=False))],
        [],
        BreakingConfig(),
    )
    assert report.leaked_fingerprints() == ()
    assert "anti-fingerprint check" in render(report)


def test_the_report_carries_the_seed_and_the_commit(plant: PlantDescription) -> None:
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(seed=99),
    )
    assert report.config.seed == 99
    text = render(report)
    assert "**Seed:** 99" in text
    # The commit is whatever git says, including "unknown" outside a repository.
    assert "**Commit:**" in text


def test_writing_the_report_produces_both_files_and_logs_the_harness_reports(
    plant: PlantDescription, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(
        "phos.breaking.report.append_to_experiment_log", lambda report: _append(report, log)
    )
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    markdown, machine = write_report(report, tmp_path / "breaking")
    assert markdown.is_file()
    assert machine.is_file()
    assert markdown.name == "breaking-report.md"
    assert machine.name == "breaking-report.json"
    assert json.loads(machine.read_text(encoding="utf-8"))["config"]["seed"] == 7
    assert log.read_text(encoding="utf-8").count("\n") == 1


def _append(report: EvaluationReport, path: Path) -> None:
    """Stand-in for the experiment log, so a test never writes into the real one."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(report.model_dump_json() + "\n")


def test_write_can_be_asked_to_log_nothing(plant: PlantDescription, tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    write_report(report, tmp_path / "breaking", log=False)
    assert not log.exists()


def test_the_summary_json_is_deterministic_and_names_both_maps(plant: PlantDescription) -> None:
    report = assemble(
        [
            breakdown(
                plant,
                outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True),
                outcome(plant, "b", AttackType.LIAR, 0.0, detected=False, targets=("level_m",)),
            )
        ],
        [],
        BreakingConfig(),
    )
    first = summary_json(report)
    assert first == summary_json(report)
    parsed = json.loads(first)
    assert {row["type"] for row in parsed["clean"]} == {"BLATANT"}
    assert {row["type"] for row in parsed["caveated"]} == {"LIAR"}


def test_a_report_with_no_command_attacks_says_why_rather_than_leaving_a_gap(
    plant: PlantDescription,
) -> None:
    """The batch reactor declares no control network, and the report must say that plainly."""
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    text = render(report)
    assert "no control network" in text
    assert "by construction" in text


def test_a_run_that_measured_nothing_still_renders(plant: PlantDescription) -> None:
    report = assemble([], [], BreakingConfig())
    text = render(report)
    assert "No attacks of this kind were measured" in text
    assert "No input-hostile corpora were measured" in text


def _hostile_only_report() -> CorpusRobustness:
    """One input-hostile corpus result, with no detection breakdowns beside it."""
    return CorpusRobustness(
        corpus="synth-hostile-fixture",
        outcomes=(
            RobustnessOutcome(
                attack_id="h1",
                attack_type=AttackType.MALFORMED_RECORD,
                verdict=RobustnessVerdict.REFUSED,
                error_type="ParserError",
            ),
        ),
        loaded=False,
    )


def test_write_report_with_a_stem_does_not_create_the_canonical_breaking_report(
    tmp_path: Path,
) -> None:
    """A hostile-only run must not wipe the detection maps by writing breaking-report.md."""
    report = assemble([], [_hostile_only_report()], BreakingConfig())
    directory = tmp_path / "breaking"
    markdown, machine = write_report(report, directory, log=False, stem="input-hostile-robustness")
    assert markdown == directory / "input-hostile-robustness.md"
    assert machine == directory / "input-hostile-robustness.json"
    assert markdown.is_file()
    assert machine.is_file()
    assert not (directory / "breaking-report.md").exists()
    assert not (directory / "breaking-report.json").exists()


def test_committed_detection_report_does_not_absorb_the_hostile_measurement() -> None:
    """ADR 0041: software-survival lives on the robustness stem; detection files stay unmeasured.

    This pins the files on disk, not a tmp_path fixture. If the robustness report is missing,
    the named gap closed in prose but not in the tree.
    """
    repo = Path(__file__).resolve().parents[2]
    detection = (repo / "eval_runs" / "breaking" / "breaking-report.md").read_text(encoding="utf-8")
    robustness = (repo / "eval_runs" / "breaking" / "input-hostile-robustness.md").read_text(
        encoding="utf-8"
    )
    assert "_No input-hostile corpora were measured._" in detection
    assert "_No input-hostile corpora were measured._" not in robustness
    assert "synth-hostile-malformed-records" in robustness
    assert "ParserError" in robustness
    assert "INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT" in robustness or (
        "not evidence that PHOS is secure" in robustness
    )


def test_rendered_robustness_still_carries_the_input_hostile_is_not_security_caveat() -> None:
    text = render(assemble([], [_hostile_only_report()], BreakingConfig()))
    assert INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT in text


def test_no_input_hostile_line_appears_only_when_the_robustness_list_is_empty() -> None:
    """Empty breakdowns with a robustness row must not say nothing hostile was measured."""
    empty = render(assemble([], [], BreakingConfig()))
    assert "No input-hostile corpora were measured" in empty

    measured = render(assemble([], [_hostile_only_report()], BreakingConfig()))
    assert "No input-hostile corpora were measured" not in measured
    assert "synth-hostile-fixture" in measured


def test_latency_and_false_positive_load_come_from_the_harness_report(
    plant: PlantDescription,
) -> None:
    """Reuse, not reimplementation: the numbers in the table are `phos.eval`'s own."""
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    text = render(report)
    assert "0.3000" in text  # false_positive_rate straight off the EvaluationReport
    assert "10.00" in text  # normal_hours, the FP-rate denominator
    assert timedelta(seconds=30).total_seconds() == 30.0
    assert "| 30 |" in text or "30 " in text


def test_the_command_section_reports_movement_when_there_is_any(plant: PlantDescription) -> None:
    """P3's open question, rendered: how many orderings moved, and how many actually led."""
    from phos.breaking.commands import CommandReasoningResult, ExplanationRanking

    moved = CommandReasoningResult(
        attack_id="wt-rogue-write-obvious",
        subtlety=0.0,
        sensor_only=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=None),
        with_commands=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=3),
        n_command_evidence=104,
    )
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": (moved,)})
        ],
        [],
        BreakingConfig(),
    )
    text = render(report)
    assert "wt-rogue-write-obvious" in text
    assert "not raised" in text  # absent on sensors alone
    assert "moved" in text or "Moved" in text
    assert "**1**" in text  # one ordering moved


def test_the_attribution_rank_carries_its_refusal_beside_the_counts(
    plant: PlantDescription,
) -> None:
    """A count like "moved in n of m" is the line most likely to be lifted out of this report.

    So the refusal is printed in the command section itself, not only in the caveat block at the
    end: the rank is an ordinal measured against our own attack library and our own plant model,
    and it may not be quoted as a real-world detection rate.
    """
    result = CommandReasoningResult(
        attack_id="wt-rogue-write-obvious",
        subtlety=0.0,
        sensor_only=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=None),
        with_commands=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=3),
        n_command_evidence=104,
    )
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": (result,)})
        ],
        [],
        BreakingConfig(),
    )
    section = render(report).split("Input-hostile robustness")[0]
    assert ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT in section
    assert "may not be cited as a real-world detection rate" in section


def test_known_station_and_unknown_master_lead_rates_are_not_pooled(
    plant: PlantDescription,
) -> None:
    """A single 'led in 1 of 2' headline would mix ADR 0014 with ADR 0027."""
    known = CommandReasoningResult(
        attack_id="wt-rogue-write-obvious",
        subtlety=0.0,
        sensor_only=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=3),
        with_commands=ExplanationRanking(attack_id="wt-rogue-write-obvious", rank=2),
        n_command_evidence=10,
        issuer="scada",
        issuer_kind=CommandIssuerKind.KNOWN_STATION,
    )
    unknown = CommandReasoningResult(
        attack_id="wt-unknown-master-obvious",
        subtlety=0.0,
        sensor_only=ExplanationRanking(attack_id="wt-unknown-master-obvious", rank=3),
        with_commands=ExplanationRanking(attack_id="wt-unknown-master-obvious", rank=1),
        n_command_evidence=10,
        issuer="engineering",
        issuer_kind=CommandIssuerKind.UNKNOWN_MASTER,
    )
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": (known, unknown)})
        ],
        [],
        BreakingConfig(),
    )
    text = render(report)
    known_section, unknown_section = text.split("### Unknown-master issuers")
    assert "### Known-station issuers" in known_section
    assert "leading explanation in **0**" in known_section.split("### Known-station issuers")[1]
    assert "leading explanation in **1**" in unknown_section
    # The pooled lie: 1 of 2 overall, with no split.
    assert "Of 2 command attack(s)" not in text


def _ranking(
    attack_id: str,
    rank: int | None,
    *,
    tied_leaders: tuple[str, ...] = (),
    templates: tuple[str, ...] | None = None,
) -> ExplanationRanking:
    """A ranking whose ``leads`` bit follows ``tied_leaders`` and the attack's position."""
    if templates is not None:
        listing = templates
    elif rank is None:
        listing = ()
    elif rank == 1:
        listing = (ATTACK_TEMPLATE_ID, "engineering_maintenance")
    else:
        listing = ("engineering_maintenance",) * (rank - 1) + (ATTACK_TEMPLATE_ID,)
    return ExplanationRanking(
        attack_id=attack_id,
        templates=listing,
        rank=rank,
        n_hypotheses=len(listing),
        tied_leaders=tied_leaders,
    )


def _command_row(
    attack_id: str,
    *,
    issuer: str,
    kind: CommandIssuerKind,
    sensor_rank: int | None,
    command_rank: int | None,
    tied_leaders: tuple[str, ...] = (),
    templates: tuple[str, ...] | None = None,
    subtlety: float = 0.0,
) -> CommandReasoningResult:
    """One command-reasoning row for a report fixture."""
    return CommandReasoningResult(
        attack_id=attack_id,
        subtlety=subtlety,
        sensor_only=_ranking(attack_id, sensor_rank),
        with_commands=_ranking(
            attack_id, command_rank, tied_leaders=tied_leaders, templates=templates
        ),
        n_command_evidence=10,
        issuer=issuer,
        issuer_kind=kind,
    )


def test_rank_one_with_tied_leaders_is_not_counted_as_a_unique_lead(
    plant: PlantDescription,
) -> None:
    """``wt-unknown-master-subtle`` lists at rank 1 with tied_leaders; the report must not count it.

    Counting ``rank == 1`` would turn a refusal into a unique unauthorised lead (ADR 0036).
    """
    tied = _command_row(
        "wt-unknown-master-subtle",
        issuer="engineering",
        kind=CommandIssuerKind.UNKNOWN_MASTER,
        sensor_rank=3,
        command_rank=1,
        tied_leaders=(ATTACK_TEMPLATE_ID,),
        templates=(ATTACK_TEMPLATE_ID, ATTACK_TEMPLATE_ID),
        subtlety=0.7,
    )
    assert not tied.newly_leads
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": (tied,)})
        ],
        [],
        BreakingConfig(),
    )
    unknown_section = render(report).split("### Unknown-master issuers")[1]
    assert "leading explanation in **0**" in unknown_section
    assert "leading explanation in **1**" not in unknown_section.split("| Attack |")[0]


def test_insufficient_evidence_first_is_not_counted_as_command_reasoning_lead(
    plant: PlantDescription,
) -> None:
    """The residual listed first is silence, not a command-reasoning win."""
    residual_first = _command_row(
        "wt-rogue-write-obvious",
        issuer="scada",
        kind=CommandIssuerKind.KNOWN_STATION,
        sensor_rank=3,
        command_rank=2,
        templates=("insufficient_evidence", ATTACK_TEMPLATE_ID),
    )
    assert not residual_first.newly_leads
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": (residual_first,)})
        ],
        [],
        BreakingConfig(),
    )
    known_section = (
        render(report).split("### Known-station issuers")[1].split("### Unknown-master issuers")[0]
    )
    assert "leading explanation in **0**" in known_section
    assert "leading explanation in **1**" not in known_section.split("| Attack |")[0]


def test_frozen_zero_of_sixteen_and_one_of_four_are_not_rendered_as_one_pooled_lead_rate(
    plant: PlantDescription,
) -> None:
    """Known-station 0/16 and unknown-master 1/4 must not become a pooled 'led in n of m'.

    The 1/4 is a D2 diagnostic with ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT, not ≥70%, not a field
    rate, and not a number that may be added to the 0/16.
    """
    known = tuple(
        _command_row(
            f"known-station-{index}",
            issuer="scada",
            kind=CommandIssuerKind.KNOWN_STATION,
            sensor_rank=3,
            command_rank=2 if index < 6 else 3,
        )
        for index in range(16)
    )
    unknown = (
        _command_row(
            "wt-unknown-master-obvious",
            issuer="engineering",
            kind=CommandIssuerKind.UNKNOWN_MASTER,
            sensor_rank=3,
            command_rank=2,
        ),
        _command_row(
            "wt-unknown-master-moderate",
            issuer="engineering",
            kind=CommandIssuerKind.UNKNOWN_MASTER,
            sensor_rank=4,
            command_rank=3,
            subtlety=0.4,
        ),
        _command_row(
            "wt-unknown-master-subtle",
            issuer="engineering",
            kind=CommandIssuerKind.UNKNOWN_MASTER,
            sensor_rank=3,
            command_rank=1,
            tied_leaders=(ATTACK_TEMPLATE_ID,),
            templates=(ATTACK_TEMPLATE_ID, ATTACK_TEMPLATE_ID),
            subtlety=0.7,
        ),
        _command_row(
            "wt-unknown-master-near-invisible",
            issuer="engineering",
            kind=CommandIssuerKind.UNKNOWN_MASTER,
            sensor_rank=3,
            command_rank=1,
            subtlety=0.9,
        ),
    )
    assert sum(1 for row in known if row.newly_leads) == 0
    assert sum(1 for row in unknown if row.newly_leads) == 1
    report = assemble(
        [
            breakdown(
                plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True)
            ).model_copy(update={"command_results": known + unknown})
        ],
        [],
        BreakingConfig(),
    )
    text = render(report)
    known_section, unknown_section = text.split("### Unknown-master issuers")
    known_counts = known_section.split("### Known-station issuers")[1].split("| Attack |")[0]
    unknown_counts = unknown_section.split("| Attack |")[0]
    assert "Of 16 command attack(s)" in known_counts
    assert "leading explanation in **0**" in known_counts
    assert "Of 4 command attack(s)" in unknown_counts
    assert "leading explanation in **1**" in unknown_counts
    assert "Of 20 command attack(s)" not in text
    assert "led in 1 of 20" not in text
    assert "led in 2 of 20" not in text
    assert ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT in text


def test_a_type_never_caught_is_called_a_blind_spot_not_a_boundary(
    plant: PlantDescription,
) -> None:
    report = assemble(
        [
            breakdown(
                plant,
                outcome(plant, "a", AttackType.BLATANT, 0.0, detected=False),
                outcome(plant, "b", AttackType.BLATANT, 0.9, detected=False),
            )
        ],
        [],
        BreakingConfig(),
    )
    text = render(report)
    assert "Whole attack types Atlas never saw" in text
    assert "deaf to on that machine" in text


def test_a_crash_is_escalated_in_the_robustness_section() -> None:
    report = assemble(
        [],
        [
            CorpusRobustness(
                corpus="synth-hostile-fixture",
                outcomes=(
                    RobustnessOutcome(
                        attack_id="h1",
                        attack_type=AttackType.TRUNCATED,
                        verdict=RobustnessVerdict.CRASHED,
                        error_type="IndexError",
                    ),
                ),
                loaded=True,
            )
        ],
        BreakingConfig(),
    )
    text = render(report)
    assert "1 case(s) crashed" in text
    assert "is a defect" in text


def test_the_map_names_the_plant_each_sweep_was_run_against(plant: PlantDescription) -> None:
    """Pooling plants would make every row read ragged whether it was or not."""
    report = assemble(
        [breakdown(plant, outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True))],
        [],
        BreakingConfig(),
    )
    assert report.clean_map[0].plant_id == plant.plant_id
    assert f"`{plant.plant_id}`" in render(report)


def saturated_breakdown(plant: PlantDescription, fp_rate: float, events: int) -> CorpusBreakdown:
    """A per-corpus result with a chosen false-positive load and event count."""
    return CorpusBreakdown(
        corpus="fixture",
        plant_id=plant.plant_id,
        fit_corpus="synth-fixture-train",
        outcomes=(
            outcome(plant, "a", AttackType.BLATANT, 0.0, detected=True),
            outcome(plant, "b", AttackType.BLATANT, 0.99, detected=True),
        ),
        report=harness_report().model_copy(
            update={"false_positive_rate": fp_rate, "false_positives": int(fp_rate * 10)}
        ),
        n_events=events,
        n_narratives=1,
    )


def test_a_saturated_corpus_is_named_before_the_map_is_shown(plant: PlantDescription) -> None:
    """Perfect recall bought with a hundred alarms an hour reads like a working detector.

    That is the most flattering way these numbers could be misread, so the report says it first.
    """
    report = assemble([saturated_breakdown(plant, 134.5, 15903)], [], BreakingConfig())
    assert [b.corpus for b in report.saturated()] == ["fixture"]
    text = render(report)
    assert "Read no detection claim off" in text
    assert "134.5 false positives per normal hour" in text
    # And the "never broken" line must carry the mark rather than stand unqualified.
    assert "*(saturated — see above)*" in text
    # The warning precedes the map it qualifies.
    assert text.index("Read no detection claim off") < text.index("Caught to")


def test_a_quiet_corpus_is_not_called_saturated(plant: PlantDescription) -> None:
    report = assemble([saturated_breakdown(plant, 0.39, 598)], [], BreakingConfig())
    assert report.saturated() == ()
    text = render(report)
    assert "Read no detection claim off" not in text
    assert "*(saturated — see above)*" not in text


def test_a_corpus_atlas_said_nothing_on_is_distinguished_from_being_outwitted(
    plant: PlantDescription,
) -> None:
    """Zero events is a different finding from missing each attack on its merits."""
    breakdown_ = CorpusBreakdown(
        corpus="silent-fixture",
        plant_id=plant.plant_id,
        fit_corpus="synth-fixture-train",
        outcomes=(outcome(plant, "a", AttackType.BLATANT, 0.0, detected=False),),
        report=harness_report().model_copy(
            update={"false_positive_rate": 0.0, "false_positives": 0}
        ),
        n_events=0,
    )
    report = assemble([breakdown_], [], BreakingConfig())
    assert [b.corpus for b in report.silent()] == ["silent-fixture"]
    text = render(report)
    assert "emitted nothing at all" in text
    assert "never spoke" in text


def test_the_saturation_threshold_is_anchored_rather_than_invented() -> None:
    """Documented against PART 2's own adoption statement, so a change is a visible one."""
    from phos.breaking.report import SATURATED_FP_PER_HOUR

    assert SATURATED_FP_PER_HOUR == 1.0


def test_the_summary_json_records_saturated_and_silent_corpora(plant: PlantDescription) -> None:
    report = assemble([saturated_breakdown(plant, 134.5, 15903)], [], BreakingConfig())
    parsed = json.loads(summary_json(report))
    assert parsed["saturated_corpora"] == ["fixture"]
    assert parsed["silent_corpora"] == []
