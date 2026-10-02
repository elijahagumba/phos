"""Rendering the episode measurement so that no table can travel without what limits it.

`phos.atlas.queue.render_queue_markdown` set the pattern this follows: every table is followed by
the caveats it must be read with, because a table that travels without them is the thing this
repository exists not to produce. The additions here are the ones an episode measurement needs and
a queue measurement did not — a sensitivity grid over the declared boundary rule, and a section
that reports what the graph and sequence layers were *able to ask* on this corpus as distinct from
what they found.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.compression import COMPRESSION_CAVEATS, BudgetComparison, EpisodeAlert
from phos.sentiel.episodes import SensitivityRow
from phos.sentiel.graph import (
    UNDECLARED_DEVICE_OWNERSHIP,
    UNDECLARED_RESOURCE_OWNERSHIP,
    GraphSummary,
)
from phos.sentiel.paths import PATH_NOT_VALIDATED_CAVEAT, VACUOUS_TOP_LEVEL_FINDING
from phos.sentiel.sequence_scoring import ORDER_INVARIANCE_CLAIM
from phos.sentiel.weak_signals import WEAK_SIGNAL_CEILING_CAVEAT, WeakSignalProfile

__all__ = ["EpisodeMeasurement", "render_measurement_markdown"]

_MEASURED_VS_BUILT: Final = (
    "**What was measured and what was merely built.** The compression ratio, the coverage "
    "comparison and the weak-signal profile are MEASURED on CERT r3.1 against its two labelled "
    "insiders. The declared-graph path findings and the sequence-anomaly evidence are BUILT and "
    "exercised end to end, and their FIRING RATES are measured — but r3.1 contains no labelled "
    "positive for either, so neither has a detection claim of any kind attached to it."
)


class EpisodeMeasurement(BaseModel):
    """Everything one run measured, in the shape the report renders.

    Attributes:
        budget: The operator budget the comparison was made at.
        comparison: The per-day versus episode comparison at that budget.
        extra_budgets: The same comparison at other budgets, for the shape of the curve.
        sensitivity: The full sweep over the declared boundary rule's two parameters.
        top_episodes: The episodes an analyst would actually read, in queue order.
        profiles: Weak-signal profiles for those episodes.
        graph: What the directory supported.
        path_firing: How often each path finding fired, and on how many entity-days.
        path_on_malicious: The same, restricted to labelled malicious entity-days.
        path_expected_by_chance: How many malicious entity-days a finding firing that often would
            be expected to touch **at random**. Without it a table of firing counts reads as
            evidence; with it, a finding that fires 132,513 times and touches 35 of 53 malicious
            days is visibly doing nothing.
        interaction_verdicts: Pooled verdicts from the declared interaction policy.
        sequence_alerts: Entity-days whose ordered path cleared the declared cut.
        sequence_alerts_malicious: How many of those are labelled malicious.
        sequence_expected_by_chance: How many malicious entity-days that many alerts would touch
            at random.
        sequence_cut: The cut, read off the training distribution.
        sequence_rank_agreement: Spearman correlation between the ordered surprise and the
            order-blind baseline over the test half. Near 1.0 means the sequence score is a more
            expensive way to say what the counts already said.
        n_malicious_days: Malicious entity-days in the test half.
        n_scored_days: Entity-days scored in the test half.
        n_episodes: Episodes assembled.
        notes: Free-form findings a reader must see.
    """

    model_config = ConfigDict(frozen=True)

    budget: int = Field(ge=1)
    comparison: BudgetComparison
    extra_budgets: tuple[BudgetComparison, ...] = ()
    sensitivity: tuple[SensitivityRow, ...] = ()
    top_episodes: tuple[EpisodeAlert, ...] = ()
    profiles: tuple[WeakSignalProfile, ...] = ()
    graph: GraphSummary = GraphSummary()
    path_firing: dict[str, int] = Field(default_factory=dict)
    path_on_malicious: dict[str, int] = Field(default_factory=dict)
    path_expected_by_chance: dict[str, float] = Field(default_factory=dict)
    interaction_verdicts: dict[str, int] = Field(default_factory=dict)
    sequence_alerts: int = Field(default=0, ge=0)
    sequence_alerts_malicious: int = Field(default=0, ge=0)
    sequence_expected_by_chance: float = 0.0
    sequence_cut: float = 0.0
    sequence_rank_agreement: float = 0.0
    n_malicious_days: int = Field(default=0, ge=0)
    n_scored_days: int = Field(default=0, ge=0)
    n_episodes: int = Field(default=0, ge=0)
    notes: tuple[str, ...] = ()


def render_measurement_markdown(
    measurement: EpisodeMeasurement,
    *,
    corpus: str,
    seed: int,
    git_commit: str | None,
    frozen: Mapping[str, object],
) -> str:
    """Render the whole measurement as a standalone report.

    Args:
        measurement: What the run produced.
        corpus: Which corpus it was measured on.
        seed: The run's seed.
        git_commit: Commit that produced it, when known.
        frozen: PART 6B's operating point, restated so a reader can see it was not moved.

    Returns:
        Markdown.
    """
    comparison = measurement.comparison
    lines = [
        f"# Sentiel episodes on {corpus} — coverage at an operator budget",
        "",
        "**This does not supersede PART 6B.** The frozen row is reproduced from the trace cache",
        "as a gate before any number below is computed, and it is unchanged:",
        "",
        f"- `{frozen['detector_name']}` at **{frozen['n_alerts']}** alerts —"
        f" precision **{frozen['precision']:.4f}**, window recall **{frozen['window_recall']}**,"
        f" sample recall **{frozen['recall_sample']:.4f}**",
        "",
        f"- Corpus: **{measurement.n_scored_days:,}** scored entity-days,"
        f" **{measurement.n_malicious_days}** of them labelled malicious across"
        f" **{comparison.n_insiders}** insider(s)",
        f"- Episodes assembled: **{measurement.n_episodes:,}**"
        f" (compression **{comparison.compression_ratio:.1f}** entity-days per episode)",
        f"- Seed: `{seed}` — Commit: `{git_commit or 'unknown'}`",
        "",
        "## The comparison at a fixed budget",
        "",
        "| Budget | Queue | Items read | Entity-days contained | Malicious entity-days shown |"
        " Insiders named | Coverage |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for point in (comparison, *measurement.extra_budgets):
        taken = min(point.budget, point.n_episodes_available)
        lines.append(
            f"| {point.budget} | per-day (6B) | {point.budget} | {point.budget} |"
            f" {point.baseline_malicious_days} | {point.baseline_insiders}"
            f" | {point.baseline_coverage:.1%} |"
        )
        lines.append(
            f"| {point.budget} | episodes | {taken} | {point.episode_entity_days} |"
            f" {point.episode_malicious_days} | {point.episode_insiders}"
            f" | {point.episode_coverage:.1%} |"
        )
    lines.extend(
        [
            "",
            f"**{comparison.verdict()}**",
            "",
            f"Of the entity-days inside the episodes an analyst reads at budget"
            f" {comparison.budget}, **{comparison.episode_carried_days}** sit below the anchor"
            " threshold — behaviour the per-day queue could not have shown at this budget at all.",
            "",
        ]
    )
    if comparison.cut_is_arbitrary:
        lines.extend(
            [
                f"> **The cut at {comparison.budget} is arbitrary.**"
                f" {comparison.tie_span_at_cut} episodes share the cut score"
                f" {comparison.cut_score}, so which of them made the queue was decided by the"
                " deterministic tiebreak and not by the ranking. Precision at this budget is a"
                " property of the sort order.",
                "",
            ]
        )

    lines.extend(
        [
            "## The episodes an analyst would read",
            "",
            "| # | User | Start | End | Days | Carried | Peak | Trajectory | Malicious days |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for index, alert in enumerate(measurement.top_episodes, start=1):
        lines.append(
            f"| {index} | `{alert.user_id}` | {alert.start.date()} | {alert.end.date()} |"
            f" {alert.n_days} | {alert.n_carried_days} | {alert.peak:.2f} | {alert.trajectory} |"
            f" {len(alert.malicious_days)} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Was the boundary rule fitted? The whole sweep, so you can see it was not",
            "",
            "The declared default is a **7-day** gap — inherited from the correlation window",
            "`SentielConfig` already sets — at the **0.90** extension floor. Every other cell was",
            "computed by the same code and is reported here rather than discarded.",
            "",
            "| Gap (days) | Floor quantile | Floor score | Episodes | Entity-days | Carried days |"
            " Longest |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in measurement.sensitivity:
        marker = " **(declared)**" if row.gap_days == 7 and row.quantile == 0.90 else ""
        lines.append(
            f"| {row.gap_days}{marker} | {row.quantile:.2f} | {row.extension_floor:.3f} |"
            f" {row.n_episodes:,} | {row.n_days:,} | {row.n_carried_days:,} | {row.max_days} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Weak-signal accumulation",
            "",
            "What accumulating an episode's days added over its single loudest day.",
            "",
            "| User | Days | Anchor | Carried | Families in episode | Best single day |"
            " Families only carried days spoke for |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for profile in measurement.profiles:
        carried = ", ".join(profile.carried_only_families) or "—"
        lines.append(
            f"| `{profile.entity_id.removeprefix('ent_')}` | {profile.n_days} |"
            f" {profile.n_anchor_days} | {profile.n_carried_days} |"
            f" {len(profile.episode_families)} | {profile.best_day_families} | {carried} |"
        )
    accumulated = sum(1 for profile in measurement.profiles if profile.accumulated)
    lines.extend(
        [
            "",
            f"**{accumulated} of {len(measurement.profiles)}** episodes in the queue gained"
            " something from accumulation that no single day of them could have supplied.",
            f"- {WEAK_SIGNAL_CEILING_CAVEAT}",
            "",
        ]
    )

    lines.extend(
        [
            "## The declared graph, and what it could and could not be asked",
            "",
            f"{measurement.graph.note()}",
            "",
            f"- {VACUOUS_TOP_LEVEL_FINDING}",
            f"- {UNDECLARED_DEVICE_OWNERSHIP}",
            f"- {UNDECLARED_RESOURCE_OWNERSHIP}",
            "",
            "### Path findings — firing rates, not detection rates",
            "",
            "| Finding | Entity-days it fired on | Labelled malicious | Chance would give |"
            " Beats chance |",
            "| --- | ---: | ---: | ---: | :---: |",
        ]
    )
    for name in sorted(measurement.path_firing):
        found = measurement.path_on_malicious.get(name, 0)
        chance = measurement.path_expected_by_chance.get(name, 0.0)
        lines.append(
            f"| `{name}` | {measurement.path_firing[name]:,} | {found}"
            f" | {chance:.1f} | {'yes' if found > chance else '**no**'} |"
        )
    verdicts = ", ".join(
        f"{verdict}={count:,}"
        for verdict, count in sorted(measurement.interaction_verdicts.items())
    )
    _beats_chance = (
        "above"
        if measurement.sequence_alerts_malicious > measurement.sequence_expected_by_chance
        else "**at or below**"
    )
    lines.extend(
        [
            "",
            f"Declared role-interaction policy verdicts: **{verdicts or 'none asked'}**.",
            "",
            f"- {PATH_NOT_VALIDATED_CAVEAT}",
            "",
            "## Sequence anomaly",
            "",
            f"- Alert cut, read off the attack-free training distribution: **"
            f"{measurement.sequence_cut:.4f}** nats per gram",
            f"- Entity-days clearing it: **{measurement.sequence_alerts:,}**, of which"
            f" **{measurement.sequence_alerts_malicious}** are labelled malicious"
            f" — chance alone would give **{measurement.sequence_expected_by_chance:.1f}**"
            f" ({_beats_chance} chance)",
            f"- Rank agreement with the order-blind baseline: **"
            f"{measurement.sequence_rank_agreement:.3f}**",
            "",
            f"- {ORDER_INVARIANCE_CLAIM}",
            "",
        ]
    )

    if measurement.notes:
        lines.extend(["## Findings a reader must not miss", ""])
        lines.extend(f"- {note}" for note in measurement.notes)
        lines.append("")

    lines.extend(["## Read every number above with these", "", _MEASURED_VS_BUILT, ""])
    lines.extend(f"- {caveat}" for caveat in COMPRESSION_CAVEATS)
    lines.append("")
    return "\n".join(lines)


def spearman(one: Sequence[float], other: Sequence[float]) -> float:
    """Return Spearman's rank correlation, or ``0.0`` when either series does not vary.

    Written here rather than reached for because the only question it answers in this report is
    "is the sequence score a relabelling of the count baseline?", and a dependency for two dozen
    lines of ranking would be scope this cycle does not need.
    """
    if len(one) != len(other) or len(one) < 2:
        return 0.0
    ranks_one = _ranks(one)
    ranks_other = _ranks(other)
    mean_one = sum(ranks_one) / len(ranks_one)
    mean_other = sum(ranks_other) / len(ranks_other)
    covariance = sum(
        (a - mean_one) * (b - mean_other) for a, b in zip(ranks_one, ranks_other, strict=True)
    )
    spread_one = sum((a - mean_one) ** 2 for a in ranks_one) ** 0.5
    spread_other = sum((b - mean_other) ** 2 for b in ranks_other) ** 0.5
    if spread_one == 0.0 or spread_other == 0.0:
        return 0.0
    return float(covariance / (spread_one * spread_other))


def _ranks(values: Sequence[float]) -> list[float]:
    """Return average ranks, so ties do not manufacture an ordering."""
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and values[ordered[end + 1]] == values[ordered[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            ranks[ordered[index]] = average
        position = end + 1
    return ranks
