"""The HAI error taxonomy exists, says modelling error dominates, and rewrites no frozen row.

U1's result is a **diagnosis**: the 53.26 FP/normal-hour load on HAI is what this model does to
ordinary operation, because it was fitted on 15% of one duty cycle. These pins exist so that a later
change which appears to "improve" Atlas has to turn them red first and say why, in the same idiom as
`tests/atlas/test_queue_report_freeze.py` and the CERT autopsy freeze test.

The thing they guard hardest is the pair **55.74% / 55.81%**. The model exceeds its own band on
55.74% of moments across sixty hours of declared-normal data it never saw, and on 55.81% of the
scored slice's normal moments. Those two numbers agreeing is the whole finding, and a later session
that quietly widens the fit set would make both of them vanish along with the reason the frozen row
reads as it does.

They also guard what the taxonomy must **not** have become. Nothing here may appear in
`eval_runs/log.jsonl`, the 60-hour contrast must stay labelled as a diagnostic rather than an
operating point, and the four refuted categories must keep their measured bases — a later reader has
to be able to see that start-up was ruled out because every run-state signal was constant, not
because nobody looked.
"""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "eval_runs" / "atlas" / "hai-error-taxonomy.md"
LOG = REPO / "eval_runs" / "log.jsonl"


def report() -> str:
    """Return the committed taxonomy report."""
    return REPORT.read_text(encoding="utf-8")


class TestTheReportExistsAndDescribesTheLoggedAlertSet:
    def test_the_report_is_committed(self) -> None:
        assert REPORT.is_file(), f"{REPORT} is the U1 deliverable and must be tracked"

    def test_the_frozen_gate_is_stated_before_any_new_number(self) -> None:
        text = report()
        gate = text.index("Frozen-row gate")
        assert gate < text.index("## The answer")
        assert "646.58 FP/normal-hour ungated" in text
        assert "53.26 grouped" in text
        assert "424 subsystem events" in text
        assert "window recall 1.00" in text

    def test_every_alert_in_the_queue_is_accounted_for(self) -> None:
        assert "Alerts classified: **424** (418 false, 6 overlapping an attack)" in report()


class TestTheAnswer:
    def test_modelling_error_dominates_and_is_named_as_such(self) -> None:
        assert "**Modelling error, in 418 of 418 false alerts.**" in report()

    def test_insufficient_context_is_explicitly_excluded(self) -> None:
        # The two point in opposite directions, so the report has to say which it is.
        assert "Not insufficient context" in report()

    def test_the_pair_that_carries_the_finding_survives(self) -> None:
        text = report()
        assert "**55.74%**" in text, "the declared-normal alert rate is the finding"
        assert "**55.81%**" in text, "the scored-slice alert rate is the finding"

    def test_the_shrinkage_floor_is_named_as_a_mechanism(self) -> None:
        assert "shrinkage_floor_mixed_scale" in report()

    def test_the_fit_is_recorded_as_a_fraction_of_one_duty_cycle(self) -> None:
        text = report()
        assert "0.48 h" in text
        assert "3.15 h" in text


class TestTheFitLengthSweepIsADiagnosticAndNotAnOperatingPoint:
    def test_the_step_is_recorded_between_the_two_lengths_it_falls_between(self) -> None:
        text = report()
        assert "3.89 h" in text
        assert "4.86 h" in text
        assert "The transition is a step, not a slope" in text

    def test_recall_is_recorded_as_unchanged_across_every_fit_length(self) -> None:
        assert "none of this is bought with detection" in report()

    def test_the_report_refuses_to_be_read_as_a_proposal(self) -> None:
        text = report()
        assert "It is not a proposal, an operating point or a detection claim" in text
        assert "Not a detection claim and not a new operating point" in text

    def test_the_reason_the_public_fit_is_short_is_recorded_rather_than_blamed(self) -> None:
        assert "is not an oversight" in report()


class TestTheRefutedCategoriesKeepTheirMeasuredBases:
    @pytest.mark.parametrize(
        ("category", "evidence"),
        [
            ("communication_artefacts", "exactly 10.0 s"),
            ("startup_shutdown_transition", "declared run-state signals are constant"),
            ("grade_or_recipe_change", "no declared mode or setpoint change"),
            ("sensor_noise", "No instrument became materially noisier"),
        ],
    )
    def test_a_refuted_category_says_what_refuted_it(self, category: str, evidence: str) -> None:
        text = report()
        assert f"`{category}` | **refuted**" in text
        assert evidence in text

    @pytest.mark.parametrize("category", ["maintenance", "equipment_ageing"])
    def test_a_not_separable_category_says_what_would_lift_it(self, category: str) -> None:
        assert f"`{category}` | **not_separable**" in report()

    def test_the_work_order_refusal_names_the_inlet_that_would_lift_it(self) -> None:
        assert "ADR 0069" in report()

    def test_the_residual_is_stated_with_why_it_is_zero(self) -> None:
        text = report()
        assert "Residual in `not_separable`: **0**" in text
        assert 'a zero here means "no two claimants"' in text


class TestTheQueueIsRecordedAsFewerPhenomenaThanAlerts:
    def test_the_signature_collapse_survives(self) -> None:
        text = report()
        assert "**15 distinct signatures**" in text
        assert "| 221 | 2 | `p1-boiler` |" in text, (
            "over half the queue is one condition in two runs; that is the operator's experience"
        )


class TestTheTrueAlertsExplainTheRankingRefusal:
    def test_four_of_six_are_recorded_as_indistinguishable_from_the_false_ones(self) -> None:
        text = report()
        assert text.count("inside the model's declared-normal noise") >= 4

    def test_the_two_unprecedented_ones_are_recorded(self) -> None:
        text = report()
        assert "`P2_CO_rpm` | 3.648 | **unprecedented**" in text
        assert "`P2_CO_rpm` | 3.772 | **unprecedented**" in text


class TestNothingHereReachedThePublicLog:
    def test_no_taxonomy_row_was_appended_to_the_experiment_log(self) -> None:
        names = {
            json.loads(line).get("detector_name", "")
            for line in LOG.read_text().splitlines()
            if line
        }
        offending = sorted(name for name in names if "taxonomy" in name.lower())
        assert not offending, f"a taxonomy row reached the public log: {offending}"

    def test_the_frozen_vertical_rows_are_still_the_ones_in_the_log(self) -> None:
        rows = [json.loads(line) for line in LOG.read_text().splitlines() if line]
        grouped = [
            row
            for row in rows
            if row.get("dataset_name") == "hai[after]"
            and "subsystem-events" in row.get("detector_name", "")
        ]
        assert grouped, "the frozen grouped row must still be in the log"
        for row in grouped:
            assert row["n_alerts"] == 424
            assert row["window_recall"] == 1.0
            assert row["false_positive_rate"] == pytest.approx(53.25818950334625)
