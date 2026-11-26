"""The side-by-side demo: real runs, real counts, and a label that cannot be dropped.

The tests here are deliberately about the properties a demo can quietly lose rather than about the
numbers it produces. A demo whose output is asserted exactly would fail on every generator change
for no reason; a demo whose label and honesty notes are not asserted would drift into a screenshot
with no context, which is the failure this stage exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from phos.referee import side_by_side


@pytest.fixture(scope="module")
def output() -> str:
    """Return the demo's output once for the whole module, since generating a plant is slow."""
    return side_by_side.side_by_side(hours=8.0)


def test_the_output_is_labelled_simulated_before_any_number(output: str) -> None:
    """A demo whose label appears only at the foot is quotable from the middle."""
    first_line_with_a_number = next(
        line for line in output.splitlines() if re.search(r"\d", line) and not line.startswith("=")
    )
    assert "SIMULATED" in output.split(first_line_with_a_number)[0]


def test_the_output_carries_the_label_at_the_foot_too(output: str) -> None:
    """A screenshot of the bottom of the page must be as quotable as the top."""
    assert "SIMULATED" in output.splitlines()[-3] or "SIMULATED" in output.splitlines()[-4]


def test_the_output_says_it_is_not_a_detection_claim(output: str) -> None:
    """The one sentence that stops this being read as a result."""
    assert "not a detection claim" in output.lower()


def test_both_baseline_fits_are_printed(output: str) -> None:
    """Printing one fit would let the choice of fit decide the comparison."""
    assert "fitted on the same plant" in output
    assert "fitted on a different plant" in output


def test_the_reason_the_two_baselines_differ_is_stated(output: str) -> None:
    """Two columns with no explanation is a puzzle, not a comparison."""
    assert "Why the two baseline columns differ" in output


def test_the_baseline_weakness_is_stated_rather_than_left_to_be_inferred(output: str) -> None:
    """A weak opponent presented without its weakness is a staged comparison."""
    assert "models each signal on its own" in output


def test_atlas_output_is_shown_as_a_page(output: str) -> None:
    """The point of the right-hand column is that it is the page, not a number."""
    assert "Atlas's page" in output or "Atlas's page is empty" in output


def test_confidence_is_labelled_uncalibrated_where_it_appears(output: str) -> None:
    """Constitution 3.3: an uncalibrated number must never be presented as a probability."""
    for line in output.splitlines():
        if "confidence" in line.lower() and re.search(r"\d\.\d", line):
            assert "uncalibrated" in line.lower(), line


def test_the_two_alert_counts_are_measured_not_fixed() -> None:
    """The counts must move with the plant, or they are decoration.

    Two different seeds give two different plants, so a hardcoded number would show up here.
    """
    first = side_by_side.side_by_side(seed=771001, hours=8.0)
    second = side_by_side.side_by_side(seed=771003, hours=8.0)
    counts = [
        re.search(r"detections\s+(\d+)", block).group(1)  # type: ignore[union-attr]
        for text in (first, second)
        for block in text.split("-" * 78)
        if re.search(r"detections\s+(\d+)", block)
    ]
    assert len(counts) >= 4
    assert len(set(counts)) > 1, "every detection count was identical; the run may be fixed"


def test_the_quiet_plant_observation_is_only_made_when_it_is_true(output: str) -> None:
    """The unflattering note must be conditional, or it becomes boilerplate nobody reads."""
    if "Something this comparison shows" in output:
        assert "more alerts is more noise" in output


def test_the_module_does_not_score_anything() -> None:
    """A demo that computed recall would be an evaluation in the place most likely to be quoted."""
    source = (
        Path(__file__).resolve().parents[2] / "src" / "phos" / "referee" / "side_by_side.py"
    ).read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.startswith(("from ", "import "))]
    joined = "\n".join(imports)
    assert "metrics" not in joined, "the demo must not import the metric functions"
    assert "evaluate" not in joined, "the demo must not run the evaluation harness"
    # No scoring call anywhere, which is stronger than checking for a word.
    assert "score_plant" not in source
    assert "aggregate(" not in source
    assert "window_recall(" not in source
    assert "precision(" not in source


def test_two_different_plants_can_give_different_results() -> None:
    """A demo whose output never varies would be a fixture pretending to be a measurement."""
    first = side_by_side.side_by_side(seed=771001, hours=8.0)
    second = side_by_side.side_by_side(seed=771003, hours=8.0)
    assert first != second, "two different seeds produced identical output"
