"""Markdown for the G1 table. Recall within budget is the first numeric column.

Point-adjusted F1 is in the second table and is named as reported, not headlined.
``HAICON_2020.alpha`` is printed and is not passed to the scorer.
"""

from __future__ import annotations

from collections.abc import Sequence

from phos.eval.baseline_table import (
    ATLAS_DETECTOR,
    CHECKED_OPPONENTS,
    G1_ATLAS_THRESHOLD,
    CorpusReport,
    DetectorScore,
)
from phos.eval.etapr import HAICON_2020, REFERENCE_ETAPR

__all__ = ["recall_comparison", "render_report"]


def recall_comparison(report: CorpusReport) -> str:
    """One sentence on Atlas against the best checked opponent, by the headline only."""
    if report.status == "not_scored":
        return f"{report.corpus}: not scored ({report.note}). Counts as not won."
    if not report.judges:
        return f"{report.corpus}: reported only. It does not judge."
    scores = report.scores
    atlas = _named(scores, ATLAS_DETECTOR)
    opponents = [score for score in scores if score.detector in CHECKED_OPPONENTS]
    best = max(
        opponents,
        key=lambda score: (score.caught / score.attacks) if score.attacks else 0.0,
    )
    atlas_rate = (atlas.caught / atlas.attacks) if atlas.attacks else 0.0
    best_rate = (best.caught / best.attacks) if best.attacks else 0.0
    if atlas_rate < best_rate:
        relation = "below"
    elif atlas_rate > best_rate:
        relation = "above"
    else:
        relation = "tied with"
    return (
        f"{report.corpus}: Atlas {atlas.caught}/{atlas.attacks} is {relation} "
        f"{best.detector} {best.caught}/{best.attacks}."
    )


def render_report(reports: Sequence[CorpusReport]) -> str:
    """Markdown table. The first numeric column is recall within budget."""
    lines = [
        "# G1 baseline table",
        "",
        "Headline: recall within budget, 8 alerts per 8-hour shift.",
        "Beside it: eTaPR at the reference defaults "
        f"(theta_p={REFERENCE_ETAPR.theta_p}, theta_r={REFERENCE_ETAPR.theta_r}, "
        f"delta={REFERENCE_ETAPR.delta}), and eTaPR at HAICon "
        f"pi={HAICON_2020.theta_p}, rho={HAICON_2020.theta_r}, "
        f"{HAICON_2020.ambiguous_samples} samples. "
        f"Alpha={HAICON_2020.alpha} is not an argument.",
        "Point-adjusted F1 is reported and is not the headline.",
        "One Atlas configuration: ungated Mahalanobis, alert threshold "
        f"{G1_ATLAS_THRESHOLD}. Result names start with `g1-baseline:`.",
        "Nothing here is appended to `eval_runs/log.jsonl`.",
        "",
        "## Recall within budget",
        "",
        "| Corpus | Judges | Detector | Checked | Caught | Attacks | Recall within budget |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for report in reports:
        if not report.scores:
            judges = "yes" if report.judges else "no"
            lines.append(f"| {report.corpus} | {judges} | — | — | — | — | not scored |")
            continue
        for score in report.scores:
            lines.append(
                "| {corpus} | {judges} | {detector} | {checked} | {caught} | {attacks} | "
                "{recall:.6f} |".format(
                    corpus=report.corpus,
                    judges="yes" if report.judges else "no",
                    detector=score.detector,
                    checked=_checked_cell(score.detector),
                    caught=score.caught,
                    attacks=score.attacks,
                    recall=score.recall_within_budget,
                )
            )
    lines.extend(
        [
            "",
            "## Beside the headline",
            "",
            "| Corpus | Detector | Recall within budget | "
            "eTaPR reference (theta_p=0.5, theta_r=0.1, delta=0) | "
            "eTaPR HAICon (pi=0.7, rho=0.1, 180 samples; alpha is not an argument) | "
            "Point-adjusted F1 (reported, not the headline) | Alerts before the cut |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for report in reports:
        for score in report.scores:
            lines.append(
                f"| {report.corpus} | {score.detector} | {score.recall_within_budget:.6f} | "
                f"{score.etapr_reference_f1:.6f} | {score.etapr_haicon_f1:.6f} | "
                f"{score.point_adjusted_f1:.6f} | {score.alerts} |"
            )
    lines.extend(["", "## Atlas against the best checked opponent", ""])
    lines.extend(recall_comparison(report) for report in reports)
    lines.extend(["", "## Notes", ""])
    for report in reports:
        period = (
            "no sample period"
            if report.sample_period_seconds is None
            else f"measured median step {report.sample_period_seconds:.6g} s"
        )
        declared = (
            "no declared period"
            if report.declared_period_seconds is None
            else f"declared {report.declared_period_seconds:.6g} s"
        )
        lines.append(
            f"- **{report.corpus}** ({report.status}): {period}; {declared}. {report.note}"
        )
    lines.append("")
    return "\n".join(lines)


def _named(scores: Sequence[DetectorScore], name: str) -> DetectorScore:
    for score in scores:
        if score.detector == name:
            return score
    raise KeyError(name)


def _checked_cell(detector: str) -> str:
    if detector == ATLAS_DETECTOR:
        return "engine"
    if detector in CHECKED_OPPONENTS:
        return "yes"
    return "no"
