"""The discovery ladder refuses a level the evidence does not support."""

from __future__ import annotations

from datetime import date

from phos.genesis.levels import LEVEL_NAMES, ladder_report, promotable
from phos.genesis.records import (
    Bar,
    Declaration,
    Experiment,
    Finding,
    Measurement,
    Review,
    Verdict,
)


def judged(
    experiment_id: str,
    *,
    outcome: str,
    corpus: str = "phos-icssim-dev4",
    baseline: str = "champion",
) -> Experiment:
    """Return a judged experiment with the given outcome, for use as evidence."""
    bar = Bar(
        id="b1", metric="recall", comparator=">=", threshold=0.8, text="Recall at least 0.80."
    )
    value = 0.9 if outcome == "kept" else 0.5
    return Experiment(
        id=experiment_id,
        question="Q-0001",
        phase="judged",
        declared=Declaration(
            date=date(2026, 11, 3),
            hypothesis="The challenger separates the subfloor class from normal operation.",
            why_it_might_be_wrong="The class may only separate on the seeds that were tuned.",
            falsifier="The same miss survives on a corpus nothing was tuned against.",
            baseline=baseline,
            command=f"uv run python scripts/lane_{experiment_id}.py",
            corpus=corpus,
            tier="iterate",
            result_name=f"atlas:{experiment_id}",
            bars=(bar,),
        ),
        measured=Measurement(
            date=date(2026, 11, 3),
            commit="abcdef1",
            report="eval_runs/x.md",
            values={"b1": value},
            failures="One seed produced no episode at all.",
        ),
        verdict=Verdict(
            outcome="kept" if outcome == "kept" else "refused", per_bar={"b1": value >= 0.8}
        ),
    )


def a_finding(**overrides: object) -> Finding:
    fields: dict[str, object] = {
        "id": "F-0001",
        "level": 0,
        "claim": "The subfloor class is separable without a labelled attack corpus.",
        "evidence": ("E-0001",),
        "prior_work": ("Urbina 2016",),
        "limitations": "Development corpus only.",
    }
    fields.update(overrides)
    return Finding.model_validate(fields)


class TestLevelZero:
    def test_an_idea_needs_no_evidence(self) -> None:
        assert promotable(a_finding(evidence=(), prior_work=(), limitations=""), 0, {}) == ()

    def test_an_idea_may_still_not_cite_an_experiment_that_does_not_exist(self) -> None:
        reasons = promotable(a_finding(evidence=("E-0404",)), 0, {})
        assert any("no such experiment" in reason for reason in reasons)


class TestLevelOne:
    def test_a_refused_experiment_does_not_reproduce_anything(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="refused")}
        reasons = promotable(a_finding(), 1, store)
        assert any("no experiment with a kept verdict" in reason for reason in reasons)

    def test_a_kept_experiment_with_prior_work_and_limits_reproduces(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        assert promotable(a_finding(), 1, store) == ()

    def test_limitations_may_not_be_empty_above_level_zero(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        reasons = promotable(a_finding(limitations="   "), 1, store)
        assert any("limitations are empty" in reason for reason in reasons)

    def test_a_claim_must_be_positioned_against_named_prior_work(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        reasons = promotable(a_finding(prior_work=()), 1, store)
        assert any("no named prior work" in reason for reason in reasons)


class TestLevelTwo:
    def test_an_improvement_claim_needs_both_numbers_on_the_record(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        reasons = promotable(a_finding(), 2, store)
        assert any("no improvement stated" in reason for reason in reasons)

    def test_a_stated_improvement_satisfies_it(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        finding = a_finding(improvement="Recall 0.90 against the champion's 0.72 on dev4.")
        assert promotable(finding, 2, store) == ()


class TestLevelThree:
    def test_one_citation_is_not_a_survey_of_the_state_of_the_art(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        reasons = promotable(a_finding(), 3, store)
        assert any("at least two named prior works" in reason for reason in reasons)

    def test_two_named_prior_works_satisfy_it(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        finding = a_finding(
            prior_work=("Urbina 2016", "Ahmed 2017"),
            improvement="Recall 0.90 against the champion's 0.72 on dev4.",
        )
        assert promotable(finding, 3, store) == ()


class TestLevelFour:
    def test_a_finding_on_one_corpus_is_not_a_novel_finding(self) -> None:
        store = {"E-0001": judged("E-0001", outcome="kept")}
        reasons = promotable(a_finding(prior_work=("a", "b")), 4, store)
        assert any("holds on more than one corpus" in reason for reason in reasons)

    def test_two_corpora_satisfy_it(self) -> None:
        store = {
            "E-0001": judged("E-0001", outcome="kept"),
            "E-0002": judged("E-0002", outcome="kept", corpus="grfics-v3-bridge"),
        }
        finding = a_finding(
            evidence=("E-0001", "E-0002"),
            prior_work=("a", "b"),
            improvement="Recall 0.90 against the champion's 0.72 on both corpora.",
        )
        assert promotable(finding, 4, store) == ()


class TestLevelFive:
    def test_a_contribution_needs_a_survived_falsification_attempt_and_a_recipe(self) -> None:
        store = {
            "E-0001": judged("E-0001", outcome="kept"),
            "E-0002": judged("E-0002", outcome="kept", corpus="grfics-v3-bridge"),
        }
        finding = a_finding(evidence=("E-0001", "E-0002"), prior_work=("a", "b"))
        reasons = promotable(finding, 5, store)
        assert any("attempted falsification" in reason for reason in reasons)
        assert any("reproduction instructions" in reason for reason in reasons)

    def test_a_review_that_broke_the_claim_does_not_promote_it(self) -> None:
        store = {
            "E-0001": judged("E-0001", outcome="kept"),
            "E-0002": judged("E-0002", outcome="kept", corpus="grfics-v3-bridge"),
        }
        broke = Review(
            date=date(2026, 11, 3),
            reviewer="independent-reviewer",
            attempted="Re-scored with the valve tag withheld; the separation vanished.",
            survived=False,
        )
        finding = a_finding(
            evidence=("E-0001", "E-0002"),
            prior_work=("a", "b"),
            reviews=(broke,),
            reproduction="scripts/lane_E-0001.py",
        )
        reasons = promotable(finding, 5, store)
        assert any("attempted falsification" in reason for reason in reasons)

    def test_a_survived_review_with_a_recipe_promotes(self) -> None:
        store = {
            "E-0001": judged("E-0001", outcome="kept"),
            "E-0002": judged("E-0002", outcome="kept", corpus="grfics-v3-bridge"),
        }
        survived = Review(
            date=date(2026, 11, 3),
            reviewer="independent-reviewer",
            attempted="Re-scored with the valve tag withheld and on reshuffled seeds.",
            survived=True,
        )
        finding = a_finding(
            evidence=("E-0001", "E-0002"),
            prior_work=("a", "b"),
            improvement="Recall 0.90 against the champion's 0.72 on both corpora.",
            reviews=(survived,),
            reproduction="uv run python scripts/lane_E-0001.py --corpus data/x",
        )
        assert promotable(finding, 5, store) == ()


class TestLadder:
    def test_a_level_off_the_ladder_is_refused(self) -> None:
        assert promotable(a_finding(), 6, {}) == ("level 6 is not on the ladder (0--5)",)

    def test_the_report_names_every_level_including_the_empty_ones(self) -> None:
        counts = ladder_report([a_finding(), a_finding(id="F-0002", level=2)])
        assert counts[LEVEL_NAMES[0]] == 1
        assert counts[LEVEL_NAMES[2]] == 1
        assert counts[LEVEL_NAMES[5]] == 0
