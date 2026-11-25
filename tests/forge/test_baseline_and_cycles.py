"""Tests for the Step 5 baseline harness and the Step 6 cycle gates.

The parts that must be right are the ones that decide whether a measurement is real: a trial must
use the commit before the result, a blocked measurement must not read as a result, and a cycle must
not start when Step 5 has not shown the team helps.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import typing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str) -> types.ModuleType:
    """Load a script as a module.

    Args:
        name: The module name to give it.
        relative: Its path from the repository root.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def baseline() -> types.ModuleType:
    """Return the baseline module.

    Returns:
        The loaded module.
    """
    return _load("forge_baseline_under_test", "scripts/forge_baseline.py")


@pytest.fixture(scope="module")
def atlas() -> types.ModuleType:
    """Return the Atlas cycle module.

    Returns:
        The loaded module.
    """
    return _load("forge_atlas_under_test", "scripts/forge_atlas.py")


# -- the baseline case's own facts -------------------------------------------------------------


def test_each_base_commit_is_the_parent_of_its_result(baseline: types.ModuleType) -> None:
    """The validity of a backtest rests on its base being the commit before the result."""
    import subprocess

    for case in baseline.CASES:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{case.result_commit}^{{commit}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{result}^"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        base = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", f"{case.base_commit}^{{commit}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert parent == base, f"{case.key}: base is not the parent of its result commit"


def test_the_recorded_outcome_matches_the_first_record(baseline: types.ModuleType) -> None:
    """The expected answer for ADR 0418 is read from the record, not invented here."""
    record = json.loads((ROOT / "docs/genesis/experiments/E-0001.json").read_text())
    case = baseline.case_by_key("adr-0418-sequential-column")
    assert record["verdict"]["outcome"] == case.outcome
    assert record["verdict"]["per_bar"] == case.bars


def test_every_case_input_exists_at_its_base_commit(baseline: types.ModuleType) -> None:
    """A case whose files are missing at its base commit fails every trial for that case.

    That is a mechanical failure dressed up as a result: six trials on case 3 would have read a
    script that was never there, and the report would have shown an arm that could not answer. The
    check is against the base commit rather than the working tree, because the working tree is the
    version the trial never sees.
    """
    import subprocess

    for case in baseline.CASES:
        for relative in case.reads:
            done = subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-e", f"{case.base_commit}:{relative}"],
                capture_output=True,
                text=True,
                check=False,
            )
            assert done.returncode == 0, (
                f"{relative} is not in {case.base_commit}, so every trial on {case.key} would "
                "have read nothing"
            )


def test_no_case_can_see_its_own_result_at_its_base_commit(baseline: types.ModuleType) -> None:
    """The answer must not be in the tree the trial reads, or the backtest measures nothing."""
    import glob
    import os
    import subprocess

    for case in baseline.CASES:
        matches = glob.glob(os.path.join(str(ROOT), "docs/adr", f"{case.adr}*.md"))
        assert matches, f"ADR {case.adr} is not in the tree at all"
        relative = os.path.relpath(matches[0], str(ROOT))
        done = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{case.base_commit}:{relative}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode != 0, (
            f"ADR {case.adr} is present at {case.base_commit}, so a trial could read the answer"
        )


def test_every_case_names_an_iterate_tier_corpus(baseline: types.ModuleType) -> None:
    """Only iterate-freely data may be used, and the resolver is what decides that."""
    from phos.forge.genesis_api import tier

    for case in baseline.CASES:
        verdict = tier(ROOT, case.corpus, "iterate")
        assert not verdict.refused, f"{case.corpus} is refused by the tier rule"
        assert verdict.tier == "green", f"{case.corpus} is {verdict.tier}, not green"


def test_the_cases_cover_three_different_records_and_verdicts(baseline: types.ModuleType) -> None:
    """Three cases, and they must not all have the same recorded answer."""
    assert len(baseline.CASES) == 3
    assert len({case.adr for case in baseline.CASES}) == 3
    assert len({case.outcome for case in baseline.CASES}) > 1


def test_every_trial_is_assigned_a_ready_runtime(baseline: types.ModuleType) -> None:
    """Every case, arm and trial gets a runtime, and only from the ready set."""
    assignment = baseline.assign_runtimes(("claude", "cursor"))
    expected = len(baseline.CASES) * len(baseline.ARMS) * baseline.TRIALS
    assert len(assignment) == expected
    assert set(assignment.values()) == {"claude", "cursor"}
    assert len(assignment) == 18


def test_the_runtime_spread_is_even(baseline: types.ModuleType) -> None:
    """With two runtimes the trials split evenly, so neither carries the run alone."""
    assignment = baseline.assign_runtimes(("claude", "cursor"))
    counts: dict[str, int] = {}
    for runtime in assignment.values():
        counts[runtime] = counts.get(runtime, 0) + 1
    assert counts == {"claude": 9, "cursor": 9}


def test_every_case_carries_both_arms_on_every_runtime(baseline: types.ModuleType) -> None:
    """No case may be judged entirely by one runtime, or a runtime difference hides as a result."""
    assignment = baseline.assign_runtimes(("claude", "cursor"))
    for case in baseline.CASES:
        for arm in baseline.ARMS:
            runtimes = {
                assignment[(case.key, arm, trial)] for trial in range(1, baseline.TRIALS + 1)
            }
            assert len(runtimes) >= 2, f"{case.key} {arm} ran only on {runtimes}"


def test_an_assignment_with_one_runtime_uses_it_for_everything(baseline: types.ModuleType) -> None:
    assignment = baseline.assign_runtimes(("claude",))
    assert set(assignment.values()) == {"claude"}


def test_no_runtime_ready_means_no_assignment(baseline: types.ModuleType) -> None:
    assert baseline.assign_runtimes(()) == {}


# -- the verdict reader ------------------------------------------------------------------------


class _CaseLike(typing.Protocol):
    """The three fields the reader and report tests need from a case.

    The module is loaded by path at test time, so its ``Case`` class cannot be imported for an
    annotation. A protocol names exactly what is used, which is narrower than ``Any`` and stops a
    test reaching into the case for something the protocol does not promise.
    """

    key: str
    outcome: str
    bars: dict[str, bool]


def _case(baseline: types.ModuleType) -> _CaseLike:
    """Return the first case, for reader tests that need a bar set.

    Args:
        baseline: The loaded module.

    Returns:
        The case.
    """
    return baseline.CASES[0]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("b1 met\nb2 missed", {"b1": True, "b2": False}),
        ("b1: met\nb2: missed", {"b1": True, "b2": False}),
        ("**b1 met**\n**b2 missed**", {"b1": True, "b2": False}),
        ("nothing to say", {}),
    ],
)
def test_the_verdict_reader_reads_the_shapes_a_trial_answers_in(
    baseline: types.ModuleType, text: str, expected: dict[str, bool]
) -> None:
    bars, _ = baseline.read_verdict(text, _case(baseline))
    assert bars == expected


def test_the_verdict_reader_does_not_read_the_prompt_echo(baseline: types.ModuleType) -> None:
    """The first real run scored both arms "kept" because the prompt names all three verdicts.

    The regression that mattered: the echo of the question came before the answer in the
    transcript, and a substring search found "kept" in "kept, rejected or refused". The reader has
    to take the answer, which is a line that is only the verdict.
    """
    transcript = (
        "user\nState the overall verdict the bars imply (kept, rejected or refused).\n"
        "codex\n"
        "b1 met\nb2 missed\n"
        "refused\n"
    )
    _, outcome = baseline.read_verdict(transcript, _case(baseline))
    assert outcome == "refused"


def test_the_verdict_reader_accepts_a_labelled_verdict(baseline: types.ModuleType) -> None:
    _, outcome = baseline.read_verdict("verdict: rejected", _case(baseline))
    assert outcome == "rejected"


def test_the_verdict_reader_says_unknown_when_it_cannot_tell(baseline: types.ModuleType) -> None:
    _, outcome = baseline.read_verdict("I could not decide", _case(baseline))
    assert outcome == "unknown"


def test_the_verdict_reader_takes_the_later_bar_statement(baseline: types.ModuleType) -> None:
    """A role that corrects itself means the later answer, so the last line wins per bar."""
    bars, _ = baseline.read_verdict("b2 met\n... thinking ...\nb2 missed", _case(baseline))
    assert bars["b2"] is False


def test_a_trial_with_no_bars_does_not_count_as_a_match(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    trial = baseline.Trial(case=case.key, arm="single", trial=1, runtime="claude", status="ran")
    assert not trial.matches(case)


def test_a_trial_with_the_exact_bars_counts_as_a_match(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    trial = baseline.Trial(
        case=case.key,
        arm="single",
        trial=1,
        runtime="claude",
        status="ran",
        outcome=case.outcome,
        bars=dict(case.bars),
    )
    assert trial.matches(case)


def test_one_wrong_bar_is_not_a_match(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    bars = dict(case.bars)
    bars["b2"] = not bars["b2"]
    trial = baseline.Trial(
        case=case.key,
        arm="single",
        trial=1,
        runtime="claude",
        status="ran",
        outcome=case.outcome,
        bars=bars,
    )
    assert not trial.matches(case)


def test_the_right_bars_with_the_wrong_verdict_are_not_a_match(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    trial = baseline.Trial(
        case=case.key,
        arm="single",
        trial=1,
        runtime="claude",
        status="ran",
        outcome="kept",
        bars=dict(case.bars),
    )
    assert not trial.matches(case)


# -- the report says the plain thing ------------------------------------------------------------


def test_the_report_never_claims_a_result_when_nothing_ran(baseline: types.ModuleType) -> None:
    blocked = [
        baseline.Trial(case=case.key, arm=arm, trial=1, runtime="none", status="blocked")
        for case in baseline.CASES
        for arm in baseline.ARMS
    ]
    text = baseline._overall([], blocked, [], blocked)
    assert "makes no claim" in text
    assert "No trial ran" in text


def test_the_report_counts_failed_trials_as_neither_arm(baseline: types.ModuleType) -> None:
    """A failed trial must not read as a loss for its arm."""
    case = _case(baseline)
    ran = [
        baseline.Trial(
            case=case.key,
            arm="single",
            trial=1,
            runtime="claude",
            status="ran",
            outcome=case.outcome,
            bars=dict(case.bars),
        )
    ]
    failed = [baseline.Trial(case=case.key, arm="team", trial=1, runtime="claude", status="failed")]
    text = baseline._overall(ran, [], failed, ran + failed)
    assert "failed mechanically" in text
    assert "neither arm" in text


def test_the_report_says_the_team_did_not_win_when_it_did_not(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    single = baseline.Trial(
        case=case.key,
        arm="single",
        trial=1,
        runtime="claude",
        status="ran",
        outcome=case.outcome,
        bars=dict(case.bars),
    )
    team = baseline.Trial(
        case=case.key, arm="team", trial=1, runtime="claude", status="ran", outcome="unknown"
    )
    text = baseline._overall([single, team], [], [], [single, team])
    assert "did not win" in text


def test_the_report_says_so_when_the_team_won(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    single = baseline.Trial(
        case=case.key, arm="single", trial=1, runtime="claude", status="ran", outcome="unknown"
    )
    team = baseline.Trial(
        case=case.key,
        arm="team",
        trial=1,
        runtime="claude",
        status="ran",
        outcome=case.outcome,
        bars=dict(case.bars),
    )
    text = baseline._overall([single, team], [], [], [single, team])
    assert "more often" in text


def test_the_report_refuses_a_comparison_on_one_arm(baseline: types.ModuleType) -> None:
    case = _case(baseline)
    single = baseline.Trial(
        case=case.key, arm="single", trial=1, runtime="claude", status="ran", outcome="unknown"
    )
    text = baseline._overall([single], [], [], [single])
    assert "no comparison" in text


def test_a_case_sentence_says_the_team_lost_when_it_did(baseline: types.ModuleType) -> None:
    sentence = baseline._case_sentence(2, 2, 0, 2, "refused")
    assert "the team lost" in sentence


def test_a_case_sentence_says_the_team_won_when_it_did(baseline: types.ModuleType) -> None:
    sentence = baseline._case_sentence(0, 2, 2, 2, "kept")
    assert "did better" in sentence


def test_a_case_sentence_says_a_case_separates_nothing_on_a_tie(
    baseline: types.ModuleType,
) -> None:
    sentence = baseline._case_sentence(1, 2, 1, 2, "rejected")
    assert "does not separate" in sentence


def test_the_runner_saves_after_every_trial() -> None:
    """A run that is killed must keep what it measured.

    The first attempt lost forty minutes of real trials because the harness wrote only at the end.
    The save call inside the trial loop is what makes an interruption survivable, so it is checked
    in the source rather than by running a two hour job in a test.
    """
    source = (ROOT / "scripts/forge_baseline.py").read_text(encoding="utf-8")
    loop_start = source.index("for case in CASES:")
    loop_body = source[loop_start : source.index('print("scoring seeded defects')]
    assert "save(results, ())" in loop_body, "the runner must save inside the trial loop"
    # And the save must actually reach disk, not just append to a list.
    save_body = source[source.index("    def save(") : source.index("    if not assignment:")]
    assert "partial.write_text" in save_body, "save must write the file"


def test_the_runner_can_resume_its_own_file() -> None:
    """Restarting must not repeat a trial that already finished cleanly."""
    source = (ROOT / "scripts/forge_baseline.py").read_text(encoding="utf-8")
    assert "_resume_from" in source
    # The runner must subtract what was already done. It builds a `remaining` list from the trials
    # not in `already`, which is the behaviour; asserting on a log sentence was too brittle and
    # broke when the loop was made parallel.
    assert "remaining = [" in source
    assert "if (case.key, arm, trial) not in already" in source


def test_a_resume_reuses_only_clean_trials(baseline: types.ModuleType, tmp_path: Path) -> None:
    """A blocked or failed trial is retried; a clean one is not repeated."""
    payload = {
        "generated_at": "x",
        "complete": False,
        "trials": [
            {
                "case": "c1",
                "arm": "single",
                "trial": 1,
                "runtime": "claude",
                "status": "ran",
                "outcome": "kept",
                "bars": {"b1": True},
            },
            {
                "case": "c1",
                "arm": "team",
                "trial": 1,
                "runtime": "cursor",
                "status": "failed",
                "outcome": "unknown",
                "bars": {},
            },
        ],
    }
    (tmp_path / "trials-20260101T000000+0000.json").write_text(json.dumps(payload))
    assignment = {("c1", "single", 1): "claude", ("c1", "team", 1): "cursor"}
    resumed = baseline._resume_from(tmp_path, assignment)
    assert ("c1", "single", 1) in resumed
    assert ("c1", "team", 1) not in resumed


def test_a_complete_run_is_not_resumed(baseline: types.ModuleType, tmp_path: Path) -> None:
    payload = {
        "generated_at": "x",
        "complete": True,
        "trials": [
            {
                "case": "c1",
                "arm": "single",
                "trial": 1,
                "runtime": "claude",
                "status": "ran",
                "outcome": "kept",
                "bars": {"b1": True},
            }
        ],
    }
    (tmp_path / "trials-20260101T000000+0000.json").write_text(json.dumps(payload))
    assert baseline._resume_from(tmp_path, {("c1", "single", 1): "claude"}) == {}


def test_a_mutation_script_that_aborts_is_not_reported_as_zero(baseline: types.ModuleType) -> None:
    """A script whose target text has moved did not measure zero, and must not say it did.

    ``mutate_command_integration.py`` seeds 27 defects and then aborts, because one mutation targets
    text that is no longer in ``phos/atlas/templates.py``. Reporting "0 of 27 caught" would read as
    a test suite with no teeth, which is the opposite of what happened: the script never ran the
    suite at all on those defects.
    """
    import subprocess as sp

    done = sp.run(
        [sys.executable, str(ROOT / "scripts/mutate_command_integration.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    text = done.stdout + done.stderr
    assert "target text appears 0 time" in text, (
        "this test describes a known abort; if the script now completes, the abort is fixed and "
        "the score should be read normally"
    )
    # And the harness recognises it rather than reading a tally that is not there.
    source = (ROOT / "scripts/forge_baseline.py").read_text(encoding="utf-8")
    assert "target text appears 0 time" in source
    assert "did not measure zero" in source


def test_the_mutation_scores_are_tagged_with_a_commit(baseline: types.ModuleType) -> None:
    """A stored score is only reusable against the commit it was measured at."""
    stored = ROOT / baseline.RUNS / "mutation-scores.json"
    if not stored.is_file():
        pytest.skip("no stored scores yet")
    payload = json.loads(stored.read_text())
    assert "commit" in payload
    assert payload["scores"], "a stored file must hold at least one score"


def test_no_task_prompt_contains_any_cases_true_answer(baseline: types.ModuleType) -> None:
    """The prompt must never contain the verdict it is asking the agent to produce.

    This is the defect that cost a run. The prompt ended with the example line
    ``verdict: rejected``, which is the true answer for ADR 0315 and a wrong one for the other two
    cases. A hint pointing at the right answer is a leaked answer; a hint pointing at a wrong one
    is merely confusing. Neither belongs in a trial, so the check is that no case's own verdict
    word appears in its own prompt outside the vocabulary list.
    """
    for case in baseline.CASES:
        for arm in ("single", "team"):
            prompt = baseline.build_task(case, arm)
            # The vocabulary sentence legitimately names all three words. Strip it, then look.
            body = prompt.replace("kept, rejected, refused", "")
            body = body.replace("[one of kept, rejected, refused]", "")
            for word in ("Use kept", "Use rejected", "Use refused"):
                body = body.replace(word, "")
            assert f"verdict: {case.outcome}" not in body, (
                f"{case.key} prompt contains its own answer"
            )


def test_no_task_prompt_offers_an_example_answer(baseline: types.ModuleType) -> None:
    """An example line with a filled-in verdict is an answer, whatever case it is for."""
    for case in baseline.CASES:
        prompt = baseline.build_task(case, "single")
        for verdict in ("kept", "rejected", "refused"):
            assert f"verdict: {verdict}\n" not in prompt


def test_the_prompt_defines_the_three_verdicts(baseline: types.ModuleType) -> None:
    """The distinction has to be stated, or a right answer can be recorded as a wrong word."""
    prompt = baseline.build_task(baseline.CASES[0], "single")
    assert "Use kept when every bar is met" in prompt
    assert "Use rejected when the score was judged" in prompt
    assert "Use refused when the run could not be judged" in prompt


# -- the cycle gates ---------------------------------------------------------------------------


def test_the_approval_is_found_and_covers_four_cycles(atlas: types.ModuleType) -> None:
    covered, detail = atlas.approval_state()
    assert covered, detail
    assert "four cycles" in detail


def test_the_gate_reads_the_report_that_exists(atlas: types.ModuleType) -> None:
    """Whatever the report says here, the gate reaches a conclusion and says why."""
    allowed, detail = atlas.baseline_allows_start()
    assert detail, "a closed or open gate must say why"
    report = ROOT / atlas.BASELINE
    if not report.is_file():
        assert not allowed
        assert "does not exist" in detail
        return
    text = report.read_text()
    if "did not win" in text and not (
        ROOT / "docs/method/approvals/elijah-agrees-despite-baseline.md"
    ).is_file():
        assert not allowed
    if "No trial ran" in text or "did not run" in text:
        assert not allowed


def test_a_baseline_report_that_says_the_team_did_not_win_closes_the_gate(
    atlas: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The condition the instruction names: no cycle unless the team helps or Elijah agrees."""
    report = tmp_path / "BASELINE.md"
    report.write_text("The team did not win. The single agent matched the record more often.")
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    monkeypatch.setattr(atlas, "BASELINE", Path("BASELINE.md"))
    allowed, detail = atlas.baseline_allows_start()
    assert not allowed
    assert "did not win" in detail
    assert "Elijah" in detail


def test_elijahs_recorded_agreement_opens_the_gate(
    atlas: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the team did not win, his agreement is the only thing that lets a cycle run."""
    (tmp_path / "docs/method/approvals").mkdir(parents=True)
    (tmp_path / "BASELINE.md").write_text("The team did not win.")
    (tmp_path / "docs/method/approvals/elijah-agrees-despite-baseline.md").write_text(
        "Elijah agrees to proceed.\n"
    )
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    monkeypatch.setattr(atlas, "BASELINE", Path("BASELINE.md"))
    allowed, detail = atlas.baseline_allows_start()
    assert allowed
    assert "Elijah's agreement" in detail


def test_a_blocked_baseline_does_not_open_the_gate(
    atlas: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A measurement that did not run shows nothing either way, so it gates nothing open."""
    (tmp_path / "BASELINE.md").write_text("No trial ran, so this report makes no claim.")
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    monkeypatch.setattr(atlas, "BASELINE", Path("BASELINE.md"))
    allowed, detail = atlas.baseline_allows_start()
    assert not allowed
    assert "blocked" in detail


def test_the_approval_covers_exactly_four_cycles(atlas: types.ModuleType) -> None:
    assert atlas.APPROVED_CYCLES == 4
    assert atlas.SEALED_CYCLE == 4


def test_a_cycle_outside_the_approval_is_refused(atlas: types.ModuleType) -> None:
    assert atlas.run_cycle(5, "codex", ["an idea"]) == 2


def test_a_cycle_before_the_baseline_is_refused(
    atlas: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no report at all, cycle 1 is refused rather than started on hope."""
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    monkeypatch.setattr(atlas, "BASELINE", Path("BASELINE.md"))
    monkeypatch.setattr(atlas, "APPROVAL", Path("approval.md"))
    (tmp_path / "approval.md").write_text(
        "four Atlas cycles\n\n**The day cycle 4 ends.**\n", encoding="utf-8"
    )
    assert atlas.run_cycle(1, "codex", ["an idea"]) == 2
    assert not (tmp_path / "docs/forge/cycles").exists()


def test_learning_cannot_be_recorded_for_a_cycle_that_did_not_run(atlas: types.ModuleType) -> None:
    assert atlas.record_learning(3, ["a finding"], [], []) == 2


def test_finishing_a_cycle_that_did_not_start_is_refused(atlas: types.ModuleType) -> None:
    """A cycle that never started cannot be finished.

    The test used to hard-code cycle 2, which was unrun when it was written and has since run. That
    is the trap in any test that names a specific cycle: the record moves and the test quietly stops
    testing what it says. So it now finds an unrun cycle from the record itself, and skips only if
    every cycle has run.
    """
    unrun = [cycle for cycle in range(1, atlas.APPROVED_CYCLES + 1) if atlas._load(cycle) is None]
    if not unrun:
        pytest.skip("every approved cycle has run; there is no unstarted cycle to refuse")
    assert atlas.finish_cycle(unrun[0], "done") == 2


def test_finishing_a_cycle_that_did_start_is_accepted(
    atlas: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: a started cycle can be finished, and finishing records the time."""
    monkeypatch.setattr(atlas, "ROOT", tmp_path)
    (tmp_path / "docs/forge/cycles").mkdir(parents=True)
    record = atlas.CycleRecord(cycle=1, label="development", started_at="2026-11-25T00:00:00+00:00")
    (tmp_path / "docs/forge/cycles/cycle-1.json").write_text(
        json.dumps(atlas.asdict(record), indent=2)
    )
    assert atlas.finish_cycle(1, "done") == 0
    saved = json.loads((tmp_path / "docs/forge/cycles/cycle-1.json").read_text())
    assert saved["finished_at"], "finishing must record when"


def test_the_one_page_report_refuses_when_nothing_ran(atlas: types.ModuleType) -> None:
    if any(atlas._load(cycle) for cycle in range(1, 5)):
        pytest.skip("at least one cycle has run")
    assert atlas.one_page() == 2


def test_a_development_cycle_is_labelled_development(atlas: types.ModuleType) -> None:
    record = atlas.CycleRecord(cycle=1)
    assert record.label == "development"
    assert record.is_development


def test_a_cycle_with_a_sealed_score_is_not_labelled_development(atlas: types.ModuleType) -> None:
    record = atlas.CycleRecord(cycle=4, label="with one sealed score")
    assert not record.is_development


def test_the_sealed_batch_check_never_mounts_anything(atlas: types.ModuleType) -> None:
    """Gate (b) is used as-is, and that gate never mounts the volume."""
    module_file = atlas.__file__
    assert module_file is not None
    source = Path(module_file).read_text(encoding="utf-8")
    for forbidden in ("hdiutil", "password", "getpass"):
        assert forbidden not in source.replace("its password", "")
