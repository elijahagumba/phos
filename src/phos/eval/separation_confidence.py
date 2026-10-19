"""Calibrate a lead by how well its evidence separates it from the runner-up.

The key is the separation count, not the evidence shape. A count is scored leave-one-seed-out
on development: ``(right + 1) / (n + 2)``. High means the Wilson 95% lower bound is at least
0.8. A contentful lead with separation 0 is reported as ``insufficient_evidence``: nothing
told it from the runner-up, so the residual may lead. The number is not shown on a public page.
"""

from __future__ import annotations

from collections.abc import Sequence

from phos.atlas.conformal_confidence import (
    HIGH_BOUND,
    CalibratedLead,
    ShapedOutcome,
    wilson_lower,
)
from phos.eval.lane_r import DevelopmentRow
from phos.eval.w5_confidence import chart_bins
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID

__all__ = ["calibrate", "development_counts", "leave_one_seed_out", "reliability"]


def leave_one_seed_out(rows: Sequence[DevelopmentRow]) -> tuple[CalibratedLead, ...]:
    """Calibrate each contentful lead from the other seeds' separation counts.

    A contentful lead whose separation count is 0 is dropped: the residual leads instead,
    and a silence is not a contentful lead.
    """
    adjusted = tuple(_refuse_unseparated(item) for item in rows)
    contentful = [
        item for item in adjusted if item.outcome.contentful and item.outcome.correct is not None
    ]
    seeds = sorted({item.outcome.seed for item in adjusted})
    scored: list[CalibratedLead] = []
    for seed in seeds:
        counts = _fit([item for item in contentful if item.outcome.seed != seed])
        for item in contentful:
            if item.outcome.seed != seed:
                continue
            right, n = counts.get(item.separation, (0, 0))
            outcome = item.outcome
            confidence = (right + 1) / (n + 2)
            lower = wilson_lower(right, n)
            scored.append(CalibratedLead(outcome, confidence, lower, n, lower >= HIGH_BOUND))
    return tuple(scored)


def development_counts(rows: Sequence[DevelopmentRow]) -> dict[int, tuple[int, int]]:
    """Fit ``separation -> (right, n)`` on every development row, after the zero-count refusal.

    Held-back leads use this map. Development's own report uses `leave_one_seed_out` instead.
    """
    adjusted = tuple(_refuse_unseparated(item) for item in rows)
    return _fit(
        [item for item in adjusted if item.outcome.contentful and item.outcome.correct is not None]
    )


def calibrate(
    rows: Sequence[DevelopmentRow], counts: dict[int, tuple[int, int]]
) -> tuple[CalibratedLead, ...]:
    """Apply a frozen separation map to ``rows``.

    A separation count missing from ``counts`` was not seen in development. Its confidence
    is ``1/2`` and it is not high. A count of 0 is silence, not a contentful lead.
    """
    scored: list[CalibratedLead] = []
    for item in rows:
        item = _refuse_unseparated(item)
        if not item.outcome.contentful or item.outcome.correct is None:
            continue
        right, n = counts.get(item.separation, (0, 0))
        confidence = (right + 1) / (n + 2)
        lower = wilson_lower(right, n)
        scored.append(CalibratedLead(item.outcome, confidence, lower, n, lower >= HIGH_BOUND))
    return tuple(scored)


def reliability(leads: Sequence[CalibratedLead]) -> dict[str, object]:
    """The development summary: fraction right, high band, and whether scores separate.

    Right and wrong leads separate when both exist and no calibrated confidence is shared.
    """
    right = [item for item in leads if item.outcome.correct]
    wrong = [item for item in leads if not item.outcome.correct]
    right_scores = {round(item.confidence, 12) for item in right}
    wrong_scores = {round(item.confidence, 12) for item in wrong}
    high = [item for item in leads if item.high]
    high_right = sum(1 for item in high if item.outcome.correct)
    return {
        "contentful": len(leads),
        "right": len(right),
        "wrong": len(wrong),
        "fraction": None if not leads else len(right) / len(leads),
        "high": len(high),
        "high_right": high_right,
        "high_right_share": None if not high else high_right / len(high),
        "high_bar_met": bool(high) and (high_right / len(high) >= HIGH_BOUND if high else False),
        "scores_separate": bool(right) and bool(wrong) and not right_scores & wrong_scores,
        "right_scores": sorted(right_scores),
        "wrong_scores": sorted(wrong_scores),
        "bins": [item.as_dict() for item in chart_bins(leads)],
    }


def _refuse_unseparated(row: DevelopmentRow) -> DevelopmentRow:
    outcome = row.outcome
    if outcome.contentful and row.separation == 0:
        return DevelopmentRow(
            ShapedOutcome(
                seed=outcome.seed,
                plant_id=outcome.plant_id,
                scenario=outcome.scenario,
                lead=INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
                raw_confidence=outcome.raw_confidence,
                shape=(),
                contentful=False,
                correct=None,
            ),
            row.separation,
            row.rival,
        )
    return row


def _fit(rows: Sequence[DevelopmentRow]) -> dict[int, tuple[int, int]]:
    counts: dict[int, tuple[int, int]] = {}
    for row in rows:
        if row.outcome.correct is None:
            continue
        right, n = counts.get(row.separation, (0, 0))
        counts[row.separation] = (right + int(row.outcome.correct), n + 1)
    return counts
