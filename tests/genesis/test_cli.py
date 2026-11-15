"""The gate refuses, and the refusals are the ones the research contract needs.

These are the tests that matter most in this package. Everything else in GENESIS is bookkeeping;
``gate`` and ``result`` are the two places where a shortcut would turn a measurement into a claim
that was never earned, and each refusal below is one of those shortcuts.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.genesis.conftest import COMMAND, EXPERIMENT, MEASUREMENT, QUESTION

from phos.genesis.cli import EXIT_REFUSED, main
from phos.genesis.records import Experiment, Question
from phos.genesis.store import RECORD_DIR, Store

#: Every test here drives the CLI against a checkout built by the `repo` fixture, which copies the
#: real `docs/rules/` into it — a symlink into `.cursor/rules/`, which the public export forbids.
#: So none of them can run in the public tree, and `tests/conftest.py` skips the marker there
#: (ADR 0440). The fixture guards itself as well; this states the fact where a reader meets it.
pytestmark = pytest.mark.lab_only

Payload = Callable[[str, dict[str, Any]], Path]
Commit = Callable[[str], None]


def run(repo: Path, *argv: str) -> int:
    """Run one subcommand against ``repo`` and return its exit code."""
    return main(["--root", str(repo), *argv])


def declared(repo: Path, payload: Payload) -> None:
    """Open the sample question and declare the sample experiment against it."""
    assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
    assert run(repo, "declare", "--from", str(payload("e", EXPERIMENT))) == 0


def write_experiment(repo: Path, **declared_overrides: object) -> Path:
    """Write the sample question and experiment straight to the store, bypassing ``declare``.

    The gate's tier check has to hold for a record already on disk — one committed before the
    resolver existed, or edited by hand — so these tests cannot go through ``declare``, which now
    refuses the payloads they need to pose.

    Args:
        repo: The checkout.
        **declared_overrides: Fields to override inside ``declared``.

    Returns:
        The experiment record's path.
    """
    store = Store(repo)
    store.write(Question.model_validate({**QUESTION, "id": "Q-0001"}))
    record = json.loads(json.dumps(EXPERIMENT))
    record["declared"].update(declared_overrides)
    return store.write(Experiment.model_validate({**record, "id": "E-0001", "phase": "declared"}))


class TestGate:
    def test_an_undeclared_command_is_refused(self, repo: Path) -> None:
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_a_declared_but_uncommitted_command_is_refused(
        self, repo: Path, payload: Payload
    ) -> None:
        declared(repo, payload)
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_a_declared_and_committed_command_is_allowed(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        assert run(repo, "gate", "--command", COMMAND) == 0

    def test_a_bar_edited_after_the_commit_is_refused(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        path = repo / RECORD_DIR / "experiments" / "E-0001.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["declared"]["bars"][0]["threshold"] = 99.0
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_a_spent_score_is_refused(self, repo: Path, payload: Payload, commit: Commit) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        assert run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT))) == 0
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_the_reason_names_which_experiment_and_why(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared(repo, payload)
        run(repo, "gate", "--command", COMMAND)
        assert "E-0001 is declared but not committed" in capsys.readouterr().err

    def test_a_declared_tier_that_contradicts_the_rule_is_refused(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        # Written straight to the store, because `declare` now refuses this payload itself. The
        # gate check has to hold for a record already on disk: a declaration committed before the
        # resolver existed, or edited by hand, is exactly what it is for.
        write_experiment(repo, corpus="phos-icssim-heldout", tier="iterate")
        commit("declare E-0001 with the wrong tier")
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_the_tier_refusal_names_the_rule_and_both_tiers(
        self, repo: Path, payload: Payload, commit: Commit, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_experiment(repo, corpus="phos-icssim-heldout", tier="iterate")
        commit("declare E-0001 with the wrong tier")
        run(repo, "gate", "--command", COMMAND)
        err = capsys.readouterr().err
        assert "docs/rules/data-tiers.md" in err
        assert "once" in err
        assert "iterate" in err

    def test_a_tier_the_rule_agrees_with_is_allowed(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        write_experiment(repo, corpus="phos-icssim-heldout", tier="once")
        commit("declare E-0001")
        assert run(repo, "gate", "--command", COMMAND) == 0

    def test_a_committed_declaration_on_a_never_read_corpus_is_refused(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        # A record written before this phase existed, or written by hand past `declare`.
        write_experiment(repo, corpus="hai-23.05", tier="iterate")
        commit("declare E-0001 on a validation corpus")
        assert run(repo, "gate", "--command", COMMAND) == EXIT_REFUSED

    def test_the_never_read_refusal_is_not_softenable(
        self, repo: Path, payload: Payload, commit: Commit, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_experiment(repo, corpus="hai-23.05", tier="iterate")
        commit("declare E-0001 on a validation corpus")
        run(repo, "gate", "--command", COMMAND)
        assert "softenable" not in capsys.readouterr().err


class TestDeclare:
    def test_an_experiment_serving_no_question_is_refused(
        self, repo: Path, payload: Payload
    ) -> None:
        assert run(repo, "declare", "--from", str(payload("e", EXPERIMENT))) == EXIT_REFUSED

    def test_a_never_tier_corpus_is_refused_at_declaration(
        self, repo: Path, payload: Payload
    ) -> None:
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        forbidden = json.loads(json.dumps(EXPERIMENT))
        forbidden["declared"]["corpus"] = "hai-21.03"
        forbidden["declared"]["tier"] = "never"
        assert run(repo, "declare", "--from", str(payload("e", forbidden))) == EXIT_REFUSED

    def test_a_never_tier_corpus_is_refused_even_when_the_payload_says_iterate(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The audit's hole, exactly: hai-21.03 is named never-read in the rule, and the payload
        # claims it is an iteration corpus. Nothing compared the corpus against the rule.
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        audit_hole = json.loads(json.dumps(EXPERIMENT))
        audit_hole["declared"]["corpus"] = "hai-21.03"
        audit_hole["declared"]["tier"] = "iterate"
        assert run(repo, "declare", "--from", str(payload("e", audit_hole))) == EXIT_REFUSED
        err = capsys.readouterr().err
        assert "hai-21.03" in err
        assert "never-read" in err

    def test_the_refusal_names_the_rule_file_and_quotes_its_sentence(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(repo, "ask", "--from", str(payload("q", QUESTION)))
        forbidden = json.loads(json.dumps(EXPERIMENT))
        forbidden["declared"]["corpus"] = "batadal"
        forbidden["declared"]["tier"] = "iterate"
        run(repo, "declare", "--from", str(payload("e", forbidden)))
        err = capsys.readouterr().err
        assert "docs/rules/data-tiers.md" in err
        assert "Never read, score or iterate on" in err

    @pytest.mark.parametrize("corpus", ["hai-21.03", "hai-22.04", "hai-23.05", "batadal", "hai"])
    def test_each_never_read_corpus_named_in_the_rule_is_refused(
        self, repo: Path, payload: Payload, corpus: str
    ) -> None:
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        forbidden = json.loads(json.dumps(EXPERIMENT))
        forbidden["declared"]["corpus"] = corpus
        forbidden["declared"]["tier"] = "iterate"
        assert run(repo, "declare", "--from", str(payload("e", forbidden))) == EXIT_REFUSED

    def test_an_unknown_corpus_is_refused_rather_than_defaulted(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        unknown = json.loads(json.dumps(EXPERIMENT))
        unknown["declared"]["corpus"] = "a-corpus-nobody-registered"
        assert run(repo, "declare", "--from", str(payload("e", unknown))) == EXIT_REFUSED
        assert "registry.json" in capsys.readouterr().err

    def test_a_corpus_the_rule_does_not_name_but_the_registry_does_may_be_declared_once(
        self, repo: Path, payload: Payload
    ) -> None:
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        registered = json.loads(json.dumps(EXPERIMENT))
        registered["declared"]["corpus"] = "kelmarsh"
        registered["declared"]["tier"] = "once"
        assert run(repo, "declare", "--from", str(payload("e", registered))) == 0

    def test_declare_writes_a_disagreeing_tier_but_says_the_gate_will_refuse_it(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The division the phase states: `declare` refuses never-read and unknown corpora; `gate`
        # refuses a tier that disagrees. So this record is written, and the author is told, in the
        # same breath, that the run it describes is going to be refused.
        assert run(repo, "ask", "--from", str(payload("q", QUESTION))) == 0
        wrong = json.loads(json.dumps(EXPERIMENT))
        wrong["declared"]["corpus"] = "kelmarsh"
        wrong["declared"]["tier"] = "iterate"
        assert run(repo, "declare", "--from", str(payload("e", wrong))) == 0
        assert "the gate will refuse this run" in capsys.readouterr().err

    def test_the_same_command_on_the_same_corpus_cannot_be_declared_twice_once_scored(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        assert run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT))) == 0
        assert run(repo, "declare", "--from", str(payload("e", EXPERIMENT))) == EXIT_REFUSED


class TestResult:
    def test_a_result_against_an_uncommitted_declaration_is_refused(
        self, repo: Path, payload: Payload
    ) -> None:
        declared(repo, payload)
        code = run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT)))
        assert code == EXIT_REFUSED

    def test_the_verdict_is_computed_from_the_declared_bar(
        self, repo: Path, payload: Payload, commit: Commit, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT)))
        out = capsys.readouterr().out
        assert "E-0001: REFUSED" in out
        assert "MISSED" in out

    def test_a_kept_result_says_so(
        self, repo: Path, payload: Payload, commit: Commit, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        met = {**MEASUREMENT, "values": {"b1": 1.0}}
        run(repo, "result", "E-0001", "--from", str(payload("m", met)))
        assert "E-0001: KEPT" in capsys.readouterr().out

    def test_recording_a_result_twice_is_refused(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        assert run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT))) == 0
        commit("result E-0001")
        assert (
            run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT))) == EXIT_REFUSED
        )

    def test_a_result_for_an_experiment_that_does_not_exist_is_refused(
        self, repo: Path, payload: Payload
    ) -> None:
        assert (
            run(repo, "result", "E-0404", "--from", str(payload("m", MEASUREMENT))) == EXIT_REFUSED
        )


class TestPromote:
    def test_a_claim_with_a_refused_experiment_behind_it_does_not_promote(
        self, repo: Path, payload: Payload, commit: Commit
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT)))
        finding = {
            "claim": "The register tables determine the inlet law.",
            "evidence": ["E-0001"],
            "prior_work": ["Urbina 2016"],
            "limitations": "Development corpus only.",
        }
        assert run(repo, "finding", "--from", str(payload("f", finding))) == 0
        assert run(repo, "promote", "F-0001", "--level", "1", "--reason", "x") == EXIT_REFUSED

    def test_promotion_never_moves_a_level_down(self, repo: Path, payload: Payload) -> None:
        finding = {
            "claim": "The register tables determine the inlet law.",
            "evidence": [],
            "prior_work": [],
            "limitations": "",
        }
        assert run(repo, "finding", "--from", str(payload("f", finding))) == 0
        assert run(repo, "promote", "F-0001", "--level", "1", "--reason", "x") == EXIT_REFUSED


class TestReadOnly:
    def test_state_runs_on_an_empty_record(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run(repo, "state") == 0
        assert "questions:   0" in capsys.readouterr().out

    def test_next_ranks_the_open_questions(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(repo, "ask", "--from", str(payload("q", QUESTION)))
        assert run(repo, "next", "-n", "3") == 0
        assert "Q-0001" in capsys.readouterr().out

    def test_every_template_is_valid_json(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for kind in ("question", "experiment", "measurement", "finding"):
            assert run(repo, "template", kind) == 0
            json.loads(capsys.readouterr().out)

    def test_audit_passes_on_a_consistent_record(self, repo: Path, payload: Payload) -> None:
        declared(repo, payload)
        assert run(repo, "audit") == 0

    def test_the_rendered_declaration_leaves_the_judgement_to_a_human(
        self, repo: Path, payload: Payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared(repo, payload)
        assert (
            run(repo, "adr", "E-0001", "--number", "0413", "--title", "the law is derivable") == 0
        )
        out = capsys.readouterr().out
        assert "# ADR 0413 — the law is derivable" in out
        assert "written by hand" in out
        assert "laws_fitting == 1" in out

    def test_the_report_keeps_a_refusal_on_the_record(
        self, repo: Path, payload: Payload, commit: Commit, capsys: pytest.CaptureFixture[str]
    ) -> None:
        declared(repo, payload)
        commit("declare E-0001")
        run(repo, "result", "E-0001", "--from", str(payload("m", MEASUREMENT)))
        capsys.readouterr()
        assert run(repo, "report", "--since", "2026-01-01") == 0
        out = capsys.readouterr().out
        assert "Failed experiments, kept on the record" in out
        assert "E-0001" in out
