"""Autopsy of a CERT identity-6B queue: which features led the top-N.

The public row remains identity aggregation at 48 alerts (precision 0.104, 5 TP / 43 FP).
This module ranks already-scored windows and counts leading stems in true positives versus
false positives. It does not retune ``precision_policy``, does not invent a contradictory
template, does not revive peer-group advantage, and does not append a 6B detector name to
the experiment log.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.detectors import Detection
from phos.ontology import EntityId, UtcDatetime
from phos.sentiel.entities import user_id_of
from phos.sentiel.labels import EntityLabelledInterval
from phos.sentiel.scoring import AggregationPolicy, ScoredWindow, stem_of

__all__ = [
    "AUTOPSY_DETECTOR_NAME",
    "FROZEN_SIX_B_DETECTOR_NAME",
    "BudgetAutopsy",
    "RankedAlert",
    "StemCount",
    "autopsy_budget_queue",
    "features_for_stem",
    "is_true_positive",
    "named_subset_detector_name",
    "named_subset_policy",
    "ranked_from_detection",
    "ranked_from_window",
    "render_autopsy_markdown",
]

FROZEN_SIX_B_DETECTOR_NAME: Final = "aggregate:gaussian:peer set (34 features) (6B)"
"""The public 6B headline. Autopsy output must never reuse this as a detector_name."""

AUTOPSY_DETECTOR_NAME: Final = "autopsy:6b-top-budget"
"""Name for autopsy artifacts. Not a public detection row."""

NAMED_SUBSET_LOG_TAG_PREFIX: Final = "autopsy-subset"
"""Prefix for optional stem-only ``AggregationPolicy.log_tag`` values."""


def named_subset_detector_name(stem: str) -> str:
    """Return the experiment-log name for a stem-only bakeoff.

    Never the frozen 6B headline. A loss versus 0.104 is a valid result.
    """
    if not stem or stem == "(none)":
        raise ValueError("named subset needs a real stem")
    return f"aggregate:gaussian:{stem} subset:{NAMED_SUBSET_LOG_TAG_PREFIX}"


def named_subset_policy(stem: str) -> AggregationPolicy:
    """Return identity aggregation tagged so it cannot overwrite 6B or ``:precision``."""
    return AggregationPolicy(log_tag=f"{NAMED_SUBSET_LOG_TAG_PREFIX}-{stem}")


def features_for_stem(feature_names: Sequence[str], stem: str) -> frozenset[str]:
    """Return emitted features whose starter-count stem is ``stem``."""
    matched = frozenset(name for name in feature_names if stem_of(name) == stem)
    if not matched:
        raise ValueError(f"no emitted feature has stem {stem!r}")
    return matched


class RankedAlert(BaseModel):
    """One entity-window in a ranked queue, enough to autopsy without a full ScoredWindow."""

    model_config = ConfigDict(frozen=True)

    entity_id: EntityId
    timestamp: UtcDatetime
    score: float
    leading_feature: str | None = None


class StemCount(BaseModel):
    """How often a starter-count stem led true-positive versus false-positive alerts."""

    model_config = ConfigDict(frozen=True)

    stem: str
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)


class BudgetAutopsy(BaseModel):
    """The top-``budget`` identity-6B queue, split by entity-scoped truth.

    Attributes:
        budget: Alert count, matching the frozen 48-alert operating point.
        true_positives: Windows whose entity and timestamp fall in a labelled incident.
        false_positives: The rest of the queue.
        leading_stems: Stem counts, highest TP then FP then name.
        detector_name: Always ``autopsy:6b-top-budget``. Never the frozen 6B headline.
    """

    model_config = ConfigDict(frozen=True)

    budget: int = Field(ge=1)
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    leading_stems: tuple[StemCount, ...] = ()
    detector_name: str = AUTOPSY_DETECTOR_NAME

    def dominant_true_positive_stem(self) -> str | None:
        """Return a stem that led every TP and none of the FPs, else ``None``.

        A named-subset bakeoff is only justified when one family is doing the labelled work
        without also flooding the false-alarm half. Silence is the honest default.
        """
        exclusive = [
            row.stem
            for row in self.leading_stems
            if row.true_positives == self.true_positives
            and row.true_positives > 0
            and row.false_positives == 0
        ]
        if len(exclusive) == 1:
            return exclusive[0]
        return None


def ranked_from_detection(detection: Detection) -> RankedAlert:
    """Lift a PART 2 detection. ``feature`` is the leading stem source on aggregated 6B alerts."""
    if not detection.entity_ids:
        raise ValueError("detection names no entity")
    return RankedAlert(
        entity_id=detection.entity_ids[0],
        timestamp=detection.timestamp,
        score=detection.score,
        leading_feature=detection.feature,
    )


def ranked_from_window(window: ScoredWindow) -> RankedAlert:
    """Lift a scored entity-window."""
    return RankedAlert(
        entity_id=window.entity_id,
        timestamp=window.timestamp,
        score=window.score,
        leading_feature=window.leading_feature,
    )


def is_true_positive(
    alert: RankedAlert,
    labels: Sequence[EntityLabelledInterval],
) -> bool:
    """Return whether ``alert`` names a labelled user inside their incident window."""
    user_id = user_id_of(alert.entity_id)
    stamp: datetime = alert.timestamp
    return any(label.contains(user_id, stamp) for label in labels)


def autopsy_budget_queue(
    alerts: Sequence[RankedAlert | ScoredWindow | Detection],
    labels: Sequence[EntityLabelledInterval],
    *,
    budget: int,
) -> BudgetAutopsy:
    """Rank ``alerts`` by score and count leading stems in the top ``budget``.

    Ties break by entity id then timestamp so the queue is deterministic (Constitution §3.7).
    Leading feature uses `stem_of` so ``logon_count_peer`` and ``logon_count`` share a family.
    """
    if budget < 1:
        raise ValueError(f"budget must be ≥ 1, got {budget}")
    ranked = sorted(
        (_as_ranked(item) for item in alerts),
        key=lambda alert: (-alert.score, alert.entity_id, alert.timestamp),
    )
    queue = ranked[:budget]
    tp_stems: Counter[str] = Counter()
    fp_stems: Counter[str] = Counter()
    true_positives = 0
    for alert in queue:
        stem = stem_of(alert.leading_feature) if alert.leading_feature else "(none)"
        if is_true_positive(alert, labels):
            true_positives += 1
            tp_stems[stem] += 1
        else:
            fp_stems[stem] += 1
    false_positives = len(queue) - true_positives
    names = sorted(set(tp_stems) | set(fp_stems))
    leading = tuple(
        StemCount(
            stem=stem,
            true_positives=int(tp_stems[stem]),
            false_positives=int(fp_stems[stem]),
        )
        for stem in sorted(
            names,
            key=lambda name: (-tp_stems[name], -fp_stems[name], name),
        )
    )
    return BudgetAutopsy(
        budget=budget,
        true_positives=true_positives,
        false_positives=false_positives,
        leading_stems=leading,
        detector_name=AUTOPSY_DETECTOR_NAME,
    )


def _as_ranked(item: RankedAlert | ScoredWindow | Detection) -> RankedAlert:
    """Normalise a queue member."""
    if isinstance(item, RankedAlert):
        return item
    if isinstance(item, ScoredWindow):
        return ranked_from_window(item)
    return ranked_from_detection(item)


def render_autopsy_markdown(report: BudgetAutopsy) -> str:
    """Render the autopsy as markdown. Does not mention a quieter 6B."""
    lines = [
        "# CERT r3.1 identity-6B queue autopsy",
        "",
        f"Budget **{report.budget}**. Detector name `{report.detector_name}` "
        f"(not `{FROZEN_SIX_B_DETECTOR_NAME}`).",
        "",
        f"True positives **{report.true_positives}**. "
        f"False positives **{report.false_positives}**.",
        "",
        "The frozen 6B row stays precision **0.104** (5 TP / 43 FP) at 48 alerts. "
        "This table is a diagnosis, not a replacement.",
        "",
        "| Stem | TP | FP |",
        "| --- | --- | --- |",
    ]
    for row in report.leading_stems:
        lines.append(f"| `{row.stem}` | {row.true_positives} | {row.false_positives} |")
    dominant = report.dominant_true_positive_stem()
    lines.extend(
        [
            "",
            "Named-subset bakeoff: "
            + (
                f"`{dominant}` led every TP and no FP — a tagged subset may be scored "
                "under a new `log_tag`."
                if dominant
                else "no stem led every TP with zero FP; do not invent a subset."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
