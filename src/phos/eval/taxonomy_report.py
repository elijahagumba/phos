"""Rendering the error taxonomy as a report a reader can argue with.

Split from `phos.eval.taxonomy` so the classification stays a pure function of its arguments with
no presentation in it. The shape follows `phos.atlas.queue.render_queue_markdown`: the frozen-row
gate first, then the answer, then the evidence, then the caveats that must be read with all of it.

**The order is load-bearing.** The reproduced frozen rows come before any new number, so a reader
can check that the alert set being decomposed is the one that was logged. The written answer comes
next, because a table of counts without a stated conclusion is how a diagnosis turns into a
dashboard. The signature collapse comes before the categories, because "424 alerts" and "fifteen
signatures in a hundred-odd runs" are the same fact told to two different people, and the second is
the one an operator experiences.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from phos.eval.taxonomy import (
    DISCRIMINATED,
    MODEL_FAULT_PRECEDENCE,
    MODEL_SIDE_CATEGORIES,
    NOT_SEPARABLE,
    PLANT_SIDE_CATEGORIES,
    TAXONOMY_CAVEATS,
    ClassifiedEvent,
    CorpusScreen,
    SignalReference,
    contributions,
)

__all__ = ["render_taxonomy_markdown"]


def render_taxonomy_markdown(
    classified: Sequence[ClassifiedEvent],
    screens: Sequence[CorpusScreen],
    references: Mapping[str, SignalReference],
    runs: Mapping[tuple[str, tuple[str, ...]], tuple[int, int]],
    *,
    corpus: str,
    seed: int,
    git_commit: str,
    gate: str,
    answer: str,
) -> str:
    """Render the taxonomy as a diagnostic report, with the frozen-row gate stated first.

    Args:
        classified: Every alert's verdict.
        screens: The corpus screen, in declared order.
        references: Declared-normal behaviour per signal.
        runs: Signature collapse from `signature_runs`.
        corpus: Which corpus this describes.
        seed: The seed the run used.
        git_commit: The commit it ran at.
        gate: The reproduced frozen rows, stated before any new number.
        answer: The written answer to "what kind of uncertainty is generating our false alerts".

    Returns:
        A markdown document.
    """
    counted = contributions(classified)
    false_alerts = [event for event in classified if not event.overlaps_attack]
    lines = [
        f"# Atlas error taxonomy on {corpus} — what kind of uncertainty generates the false alerts",
        "",
        "**Not a detection claim and not a new operating point.** This decomposes an alert set the",
        "Atlas vertical already logged. No model was refitted for a public row, no threshold was",
        "searched, and no frozen number was re-derived.",
        "",
        f"- Frozen-row gate, reproduced before any number below: {gate}",
        f"- Alerts classified: **{len(classified)}** "
        f"({len(false_alerts)} false, {len(classified) - len(false_alerts)} overlapping an attack)",
        f"- Seed: `{seed}`",
        f"- Commit: `{git_commit}`",
        "",
        "## The answer",
        "",
        answer,
        "",
        "## Before anything else: the queue is not as long as it looks",
        "",
        f"The {len(classified)} events carry **{len(runs)} distinct signatures** — "
        f"(subsystem, departing-signal-set) pairs — in "
        f"**{sum(count for _, count in runs.values())} contiguous runs**. A signature with many",
        "events and few runs is one condition re-counted once per grouping window.",
        "",
        "| Events | Runs | Subsystem | Signals that departed |",
        "| ---: | ---: | --- | --- |",
        *(
            f"| {events} | {count} | `{subsystem}` | {', '.join(f'`{s}`' for s in signals)} |"
            for (subsystem, signals), (events, count) in runs.items()
        ),
        "",
        "## Stage 1 — what the corpus can say about each category, before any event was looked at",
        "",
        "| Category | Verdict | Basis | What would lift it |",
        "| --- | --- | --- | --- |",
        *(
            f"| `{screen.category}` | **{screen.verdict}** | {screen.basis} "
            f"| {screen.what_would_lift_it or '—'} |"
            for screen in screens
        ),
        "",
        "## Stage 2 — what the same fitted model does to declared-normal data it never saw",
        "",
        "The instrument that separates modelling error from a plant phenomenon. A signal whose",
        "band is narrower than its own declared-normal variation must alert in normal operation.",
        "",
        "| Signal | Band ± | Declared-normal sd | Band covers it | Exceeds band on normal | "
        "Max departure there | Floored |",
        "| --- | ---: | ---: | :---: | ---: | ---: | :---: |",
        *(
            f"| `{reference.signal}` | {reference.band_high:,.2f} "
            f"| {reference.declared_normal_stddev:,.2f} "
            f"| {'yes' if reference.band_covers_declared_normal else '**no**'} "
            f"| {reference.declared_normal_exceedance:.2%} "
            f"| {reference.declared_normal_max_magnitude:.3f} "
            f"| {'**yes**' if reference.at_shrinkage_floor else 'no'} |"
            for reference in sorted(
                references.values(), key=lambda r: -r.declared_normal_exceedance
            )
        ),
        "",
        f"Reference length: **{next(iter(references.values())).reference_hours:.2f} h** of",
        "declared-normal data. Every verdict below is relative to it; a shorter reference holds",
        "fewer tails and makes more alerts look unprecedented.",
        "",
        "## Stage 3 — contribution per category",
        "",
        "| Category | Axis | Events | Share of the queue |",
        "| --- | --- | ---: | ---: |",
        *(
            f"| `{category}` "
            f"| {
                'plant'
                if category in PLANT_SIDE_CATEGORIES
                else 'model'
                if category in MODEL_SIDE_CATEGORIES
                else '—'
            } "
            f"| {count} | {count / len(classified):.1%} |"
            for category, count in sorted(counted.items(), key=lambda item: -item[1])
        ),
        "",
        f"Residual in `{NOT_SEPARABLE}`: **{counted[NOT_SEPARABLE]}**, stated rather than",
        "distributed across the categories that claimed those events.",
        "",
        f"**Read that residual with the screen.** {len(_decided_per_event(screens))} of the "
        f"{len(screens)} categories screened reached a per-event test at all "
        f"({', '.join(f'`{c}`' for c in _decided_per_event(screens))}); the rest were settled by "
        "the screen, which is where the categories this corpus could not decide are recorded. "
        "Where only two plant-side discriminators are available and they are complements — a "
        "departure the model also makes on declared-normal data, or one it does not — no two can "
        "fire at once, so "
        'a zero here means "no two claimants" and not "nothing was ambiguous".',
        "",
        "### Precedence, stated so it can be disagreed with",
        "",
        MODEL_FAULT_PRECEDENCE,
        "",
        "### Where a second category also fired",
        "",
        "| Primary | Also fired | Events |",
        "| --- | --- | ---: |",
        *(
            f"| `{primary}` | {', '.join(f'`{c}`' for c in co) or '—'} | {count} |"
            for (primary, co), count in sorted(
                _co_firing_counts(classified).items(), key=lambda item: -item[1]
            )
        ),
        "",
        "## The alerts that overlap a labelled attack window",
        "",
        "Not false alerts, so not the taxonomy's subject — but what the references say about them",
        "is the mechanical reason a queue of this kind cannot be ranked.",
        "",
        "| Timestamp | Subsystem | Strongest | Magnitude | Verdict against declared normal |",
        "| --- | --- | --- | ---: | --- |",
        *(
            f"| {event.timestamp:%H:%M:%S} | `{event.subsystem}` | `{event.strongest_signal}` "
            f"| {event.strongest_magnitude:.3f} "
            f"| {
                '**unprecedented**'
                if not references[event.strongest_signal].covers(event.strongest_magnitude)
                else "inside the model's declared-normal noise"
            } |"
            for event in classified
            if event.overlaps_attack
        ),
        "",
        "## Read every number above with these",
        "",
        *(f"- {caveat}" for caveat in TAXONOMY_CAVEATS),
        "",
    ]
    return "\n".join(lines)


def _co_firing_counts(
    classified: Sequence[ClassifiedEvent],
) -> dict[tuple[str, tuple[str, ...]], int]:
    """Count ``(primary, co-firing)`` pairs, so overlap between categories stays visible."""
    counted: dict[tuple[str, tuple[str, ...]], int] = {}
    for event in classified:
        key = (event.primary_category, event.co_firing)
        counted[key] = counted.get(key, 0) + 1
    return counted


def _decided_per_event(screens: Sequence[CorpusScreen]) -> list[str]:
    """Return the screened categories an alert-level discriminator could actually decide."""
    return sorted(
        screen.category
        for screen in screens
        if screen.may_compete and screen.category in DISCRIMINATED
    )
