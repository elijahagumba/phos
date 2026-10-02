"""The Atlas operator-queue report exists, says the queue does not rank, and rewrites nothing.

Session Build 1's result is a **refusal**: no severity Atlas carries orders the HAI subsystem-event
queue towards the incidents. These pins exist so a later change that appears to "fix" the queue
has to turn them red first and say why, in the same idiom as the CERT autopsy freeze test.

The number these pins guard hardest is `0.1250`. Ranked by calibrated weight, the top-48 cut shows
6 true positives, precision 0.1250 and window recall 1.00 — better than the CERT 6B ruler. It is
an artifact: all 424 alerts share one weight, so that queue is timestamp order, and HAI's attacks
fall early in the test slice. Every such point is struck as `cut_is_arbitrary`, and it must never
be quoted.
"""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "eval_runs" / "atlas" / "hai-operator-queue.md"
LOG = REPO / "eval_runs" / "log.jsonl"


def report() -> str:
    """Return the committed queue report."""
    return REPORT.read_text(encoding="utf-8")


class TestTheReportRecordsTheRefusal:
    """The finding is that the queue cannot be ranked. It has to survive in the file."""

    def test_the_queue_measured_is_the_one_the_vertical_logged(self) -> None:
        text = report()
        assert "**424** subsystem events" in text
        assert "**2** labelled attack window(s)" in text

    def test_magnitude_is_recorded_as_ranking_the_wrong_way(self) -> None:
        text = report()
        assert "atlas-queue:magnitude" in text
        assert "ranked the wrong way" in text

    def test_the_true_alerts_are_recorded_in_the_back_half(self) -> None:
        # 187, 204, 255, 320, 348, 359 of 424 under magnitude: the median sits past halfway.
        assert "rank 187 (44%)" in report()

    def test_no_budget_scored_beat_a_random_draw_under_a_key_that_ranked(self) -> None:
        # Every magnitude row says "no": the severity signal points away from the incidents.
        text = report()
        magnitude_section = text.split("## Ranked by `weight`")[0]
        assert "| yes |" not in magnitude_section

    def test_weight_is_recorded_as_a_constant(self) -> None:
        text = report()
        assert "atlas-queue:weight" in text
        assert "1 distinct score(s). This key **did not rank**" in text


class TestTheFakeHeadlineIsStruck:
    """0.1250 at 48 is the tiebreak's number, not Atlas's."""

    def test_the_flattering_weight_row_is_marked_as_decided_by_the_tiebreak(self) -> None:
        text = report()
        flattering = [
            line for line in text.splitlines() if line.startswith("| 48 |") and "0.1250" in line
        ]
        assert flattering, "the 48-alert weight row should still be in the report"
        for line in flattering:
            assert "**tiebreak (struck)**" in line

    def test_the_report_says_why_that_number_is_not_a_result(self) -> None:
        assert "decided by the deterministic tiebreak" in report()


class TestNothingFrozenWasRewritten:
    """646.58, 53.26 and the vertical's names are public rows. A queue row is not one of them."""

    def test_the_experiment_log_has_no_queue_detector_row(self) -> None:
        blob = LOG.read_text(encoding="utf-8")
        for key in ("magnitude", "weight", "breadth"):
            assert f'"detector_name":"atlas-queue:{key}"' not in blob

    def test_the_frozen_grouped_row_is_still_in_the_log_unchanged(self) -> None:
        rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line]
        grouped = [
            row
            for row in rows
            if row.get("dataset_name") == "hai[after]"
            and row.get("detector_name", "").startswith("atlas-vertical:")
        ]
        assert grouped, "the frozen hai[after] row must still be present"
        for row in grouped:
            assert row["n_alerts"] == 424
            assert row["window_recall"] == 1.0
            assert row["false_positives"] / row["normal_hours"] == pytest.approx(53.26, abs=0.01)

    def test_the_report_states_it_does_not_replace_the_public_rows(self) -> None:
        text = report()
        assert "646.58" in text
        assert "53.26" in text
        assert "not a control-room budget" in text
