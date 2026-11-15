"""The record kinds refuse what the charter says may not be recorded."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from phos.genesis.records import (
    PRIORITY_CRITERIA,
    Bar,
    Declaration,
    Experiment,
    Measurement,
    Priority,
)


def a_bar(**overrides: object) -> Bar:
    fields: dict[str, object] = {
        "id": "b1",
        "metric": "false_alerts_per_shift",
        "comparator": "<=",
        "threshold": 8.0,
        "text": "No more than 8 false alerts a shift.",
    }
    fields.update(overrides)
    return Bar.model_validate(fields)


def a_declaration(**overrides: object) -> Declaration:
    fields: dict[str, object] = {
        "date": date(2026, 11, 3),
        "hypothesis": "The walk detector halves the remaining misses of the subfloor class.",
        "why_it_might_be_wrong": "The walk length may be the only thing carrying the signal.",
        "falsifier": "The same miss survives every walk length in the declared sweep.",
        "baseline": "The champion scored in ADR 0313",
        "command": "uv run python scripts/lane_daily_walk.py",
        "corpus": "phos-icssim-dev4-walk",
        "tier": "iterate",
        "result_name": "atlas-walk:misses",
        "bars": [a_bar()],
    }
    fields.update(overrides)
    return Declaration.model_validate(fields)


def a_measurement(**overrides: object) -> Measurement:
    fields: dict[str, object] = {
        "date": date(2026, 11, 3),
        "commit": "abcdef1",
        "report": "eval_runs/build/lane-daily/walk.md",
        "values": {"b1": 6.0},
        "failures": "One shift produced 11 alerts; it is the shift with the valve swap.",
    }
    fields.update(overrides)
    return Measurement.model_validate(fields)


class TestBar:
    @pytest.mark.parametrize(
        ("comparator", "threshold", "value", "met"),
        [
            (">=", 0.9, 0.9, True),
            (">=", 0.9, 0.89, False),
            (">", 0.0, 0.0, False),
            ("<=", 8.0, 8.0, True),
            ("<", 8.0, 8.0, False),
            ("==", 1.0, 1.0, True),
            ("!=", 1.0, 1.0, False),
        ],
    )
    def test_every_comparator_is_a_threshold_that_clears_or_does_not(
        self, comparator: str, threshold: float, value: float, met: bool
    ) -> None:
        assert a_bar(comparator=comparator, threshold=threshold).met_by(value) is met


class TestDeclaration:
    def test_a_never_tier_corpus_cannot_be_declared(self) -> None:
        with pytest.raises(ValidationError, match="tier 'never'"):
            a_declaration(corpus="hai-21.03", tier="never")

    def test_two_bars_may_not_share_an_id(self) -> None:
        with pytest.raises(ValidationError, match="bar ids must be unique"):
            a_declaration(bars=[a_bar(), a_bar(metric="recall")])

    def test_a_declaration_needs_at_least_one_bar(self) -> None:
        with pytest.raises(ValidationError):
            a_declaration(bars=[])

    def test_a_declaration_needs_the_reason_it_might_be_wrong(self) -> None:
        with pytest.raises(ValidationError):
            a_declaration(why_it_might_be_wrong="")


class TestExperiment:
    def test_a_declared_record_may_not_already_carry_a_measurement(self) -> None:
        with pytest.raises(ValidationError, match="with a measurement already attached"):
            Experiment(
                id="E-0001",
                question="Q-0001",
                phase="declared",
                declared=a_declaration(),
                measured=a_measurement(),
            )

    def test_a_judged_record_needs_a_verdict(self) -> None:
        with pytest.raises(ValidationError, match="no verdict"):
            Experiment(
                id="E-0001",
                question="Q-0001",
                phase="judged",
                declared=a_declaration(),
                measured=a_measurement(),
            )

    def test_a_declared_bar_may_not_be_left_unmeasured(self) -> None:
        with pytest.raises(ValidationError, match="no measured value for declared bar"):
            Experiment(
                id="E-0001",
                question="Q-0001",
                phase="measured",
                declared=a_declaration(bars=[a_bar(), a_bar(id="b2", metric="recall")]),
                measured=a_measurement(values={"b1": 6.0}),
            )

    def test_a_value_may_not_appear_for_a_bar_that_was_never_declared(self) -> None:
        with pytest.raises(ValidationError, match="undeclared bar"):
            Experiment(
                id="E-0001",
                question="Q-0001",
                phase="measured",
                declared=a_declaration(),
                measured=a_measurement(values={"b1": 6.0, "b9": 1.0}),
            )

    def test_the_verdict_is_computed_from_the_bars_and_not_typed_in(self) -> None:
        experiment = Experiment(
            id="E-0001",
            question="Q-0001",
            phase="measured",
            declared=a_declaration(
                bars=[
                    a_bar(),
                    a_bar(
                        id="b2",
                        metric="recall",
                        comparator=">=",
                        threshold=0.8,
                        text="Recall at least 0.80.",
                    ),
                ]
            ),
            measured=a_measurement(values={"b1": 6.0, "b2": 0.7}),
        )
        verdict = experiment.compute_verdict()
        assert verdict.outcome == "refused"
        assert verdict.per_bar == {"b1": True, "b2": False}

    def test_a_record_with_no_measurement_cannot_be_judged(self) -> None:
        experiment = Experiment(
            id="E-0001", question="Q-0001", phase="declared", declared=a_declaration()
        )
        with pytest.raises(ValueError, match="no measurement to judge"):
            experiment.compute_verdict()

    def test_the_record_is_frozen_so_a_committed_declaration_cannot_be_mutated(self) -> None:
        experiment = Experiment(
            id="E-0001", question="Q-0001", phase="declared", declared=a_declaration()
        )
        with pytest.raises(ValidationError):
            experiment.phase = "judged"  # type: ignore[misc]


class TestPriority:
    def test_the_named_criteria_are_exactly_the_model_fields(self) -> None:
        assert set(PRIORITY_CRITERIA) == set(Priority.model_fields)
        assert len(PRIORITY_CRITERIA) == 9

    def test_cost_is_subtracted_so_the_cheapest_question_does_not_win_by_default(self) -> None:
        scores = dict.fromkeys(
            (
                "significance",
                "originality",
                "feasibility",
                "information_gain",
                "tractability",
                "relevance",
                "operational_impact",
                "evidence",
            ),
            3,
        )
        cheap = Priority(**scores, cost=1)
        dear = Priority(**scores, cost=5)
        assert cheap.rank() > dear.rank()

    def test_an_expensive_significant_question_outranks_a_cheap_trivial_one(self) -> None:
        significant = Priority(
            significance=5,
            originality=5,
            feasibility=4,
            information_gain=5,
            tractability=4,
            relevance=5,
            operational_impact=5,
            evidence=3,
            cost=5,
        )
        trivial = Priority(
            significance=1,
            originality=1,
            feasibility=5,
            information_gain=1,
            tractability=5,
            relevance=1,
            operational_impact=1,
            evidence=1,
            cost=1,
        )
        assert significant.rank() > trivial.rank()
