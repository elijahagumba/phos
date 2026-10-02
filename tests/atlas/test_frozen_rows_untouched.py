"""ADR 0070: the facet refactor moved no logged number.

The experiment log is append-only and its rows are public names other documents quote. A refactor
that claims to change no reasoning outcome has to be able to say so about the artefacts, not only
about the code — so this test pins the log's length and the frozen public figures inside it.

It is a guard against a *future* edit, not a measurement. If a real re-measurement ever lands, the
row it appends is a new line carrying a new detector name and these assertions still hold; a row
that rewrites 646.58, 53.26 or 14071.07 **in place** is what this refuses.

Note that `model:atlas-var1` appears more than once on the same split (Clock B re-ran it), so the
rates are asserted as a set per detector rather than by picking a single row — asserting a count
would pin a re-run rather than a number.
"""

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG = REPO_ROOT / "eval_runs" / "log.jsonl"

FROZEN_ROWS = 183
"""Rows present when the facet refactor landed. Appends raise this; rewrites do not."""

HAI_SPLIT = "hai-test-test"


def rows() -> list[dict[str, Any]]:
    """Return every logged evaluation, parsed."""
    with LOG.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def rates(detector: str, dataset: str) -> set[float]:
    """Return every false-positive rate logged for ``(detector, dataset)``."""
    found = {
        row["false_positive_rate"]
        for row in rows()
        if row["detector_name"] == detector and row["dataset_name"] == dataset
    }
    assert found, f"no logged row for {detector} on {dataset}"
    return found


def recalls(detector: str, dataset: str) -> set[float]:
    """Return every window recall logged for ``(detector, dataset)``."""
    return {
        row["window_recall"]
        for row in rows()
        if row["detector_name"] == detector and row["dataset_name"] == dataset
    }


def test_the_log_is_append_only_and_has_not_shrunk() -> None:
    assert len(rows()) >= FROZEN_ROWS


def test_the_public_hai_mahalanobis_row_is_unchanged() -> None:
    """646.58 FP/normal hour at recall 1.00 — the in-plant ruler (README, ADR 0064)."""
    assert rates("model:atlas-mahalanobis", HAI_SPLIT) == {646.5797816132441}
    assert recalls("model:atlas-mahalanobis", HAI_SPLIT) == {1.0}


def test_the_grouped_operator_queue_row_is_unchanged() -> None:
    """53.26 FP/normal hour — the 12.1x grouping result, a counting change (ADR 0068)."""
    detector = "atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events"
    assert rates(detector, "hai[after]") == {53.25818950334625}
    assert recalls(detector, "hai[after]") == {1.0}


def test_the_normal_score_grouped_row_is_unchanged() -> None:
    """3.55 FP/normal hour — ADR 0083 long attack-free fit, logged beside 53.26."""
    detector = "atlas-vertical:atlas-mahalanobis+normal-score-cdf/subsystem-events"
    assert rates(detector, "hai[designed-normal-score][after]") == {3.55054596688975}
    assert recalls(detector, "hai[designed-normal-score][after]") == {1.0}


def test_the_ungrouped_vertical_row_is_unchanged() -> None:
    """646.58 before grouping — the other half of the same comparison."""
    detector = "atlas-vertical:atlas-mahalanobis+isotonic/per-signal-evidence"
    assert rates(detector, "hai[before]") == {646.5797816132441}


def test_the_var1_row_is_still_the_louder_refused_one() -> None:
    """14071.07 — measured, refused as the HAI detector (ADR 0064). Not quietly improved."""
    assert rates("model:atlas-var1", HAI_SPLIT) == {14071.067277210286}
    assert recalls("model:atlas-var1", HAI_SPLIT) == {1.0}


def test_no_row_names_a_facet_or_a_refactor() -> None:
    """A pure refactor appends nothing. If this fails, something logged a run it should not have."""
    minted = [row["detector_name"] for row in rows() if "facet" in row["detector_name"].lower()]
    assert not minted, f"the facet refactor must not mint a detector name, got {minted}"


def test_the_cross_plant_zero_shot_row_is_unchanged() -> None:
    """1078.99 FP/normal hour at recall 1.00 — the BATADAL→HAI transfer number (ADR 0063).

    Added by the PART 6C audit. This row is quoted by `README.md`, `docs/atlas-report.md`,
    `easy to reads/29`, two encyclopedia volumes and three ADRs, and it sits in the tracker's
    `frozen_measurements`, but nothing pinned it — so a rewrite in place would have left every
    test green while ten documents silently disagreed with the log. Its siblings above are all
    pinned; this closes the one hole in the set.
    """
    detector = "model:atlas-mahalanobis-physical-roles"
    split = "zero-shot:hai-physical-roles"
    assert rates(detector, split) == {1078.986866791745}
    assert recalls(detector, split) == {1.0}


FROZEN_SEED = 11
"""The seed every frozen row above was measured under. Determinism is Constitution §3.7."""

FROZEN_CONDITIONS = (
    ("model:atlas-mahalanobis", HAI_SPLIT, 3.0),
    ("atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events", "hai[after]", 0.0),
    ("atlas-vertical:atlas-mahalanobis+isotonic/per-signal-evidence", "hai[before]", 0.0),
    ("model:atlas-var1", HAI_SPLIT, 3.0),
    ("model:atlas-mahalanobis-physical-roles", "zero-shot:hai-physical-roles", 3.0),
)
"""Every pinned row above, with the alert threshold its rate was measured at."""


def seeds(detector: str, dataset: str) -> set[int]:
    """Return every seed logged for ``(detector, dataset)``."""
    found = {
        row["seed"]
        for row in rows()
        if row["detector_name"] == detector and row["dataset_name"] == dataset
    }
    assert found, f"no logged row for {detector} on {dataset}"
    return found


def thresholds(detector: str, dataset: str) -> set[float]:
    """Return every alert threshold logged for ``(detector, dataset)``."""
    found = {
        row["alert_threshold"]
        for row in rows()
        if row["detector_name"] == detector and row["dataset_name"] == dataset
    }
    assert found, f"no logged row for {detector} on {dataset}"
    return found


def test_the_frozen_rows_keep_the_conditions_they_were_measured_under() -> None:
    """The rates above are only claims while their operating point and seed hold.

    Added by the PART 6C audit, which found the numbers pinned and the conditions producing
    them unpinned. A false-positive rate is quoted *at a threshold*: 646.58 at 3.0 and 646.58
    at 0.0 are different statements about the same detector, so a threshold rewritten in place
    leaves every rate assertion above green while every document quoting the rate becomes wrong
    about what it measured. The seed is the other half — Constitution §3.7 makes a result a
    result only if it can be re-created, and a row whose seed moved is not the row the
    encyclopedia and the ADRs cite.

    Asserted as sets per row for the same reason `rates` is: `model:atlas-var1` is logged twice
    on one split, and pinning a count would freeze a re-run rather than a condition.
    """
    for detector, dataset, threshold in FROZEN_CONDITIONS:
        assert seeds(detector, dataset) == {FROZEN_SEED}, (
            f"{detector} on {dataset} changed seed; the frozen rate is no longer reproducible"
        )
        assert thresholds(detector, dataset) == {threshold}, (
            f"{detector} on {dataset} changed operating point; its rate now means something else"
        )
