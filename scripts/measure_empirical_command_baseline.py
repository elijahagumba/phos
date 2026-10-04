#!/usr/bin/env python3
"""Two ADR 0086 figures: ordinary-run false alarms, and unauthorised-write detection.

An ordinary run is the demo's ``operator`` scenario: an authorised HMI write. The write is
allowed, so a narrative is a false alarm. A detection run is the ``unauthorised`` scenario: the
SCADA server writes a setpoint only the HMI may write. The brief concerns that write when the
shown narrative cites the writing device, or the link, in the minute of the write.

The seeds are the twenty integers from 11, the seed ADR 0085 already named, through 30. They
were fixed before either figure. This is a plant we simulated. It is not a public-corpus row,
not command-lead 0/16 or 1/4, and it is not appended to ``eval_runs/log.jsonl``.

Usage::

    uv run python scripts/measure_empirical_command_baseline.py
    uv run python scripts/measure_empirical_command_baseline.py --figure detection
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from phos.demo.pipeline import DemoResult, Scenario, run_demo
from phos.models import GaussianBaseline

SEEDS: tuple[int, ...] = tuple(range(11, 31))
"""Twenty ordinary-run seeds, fixed before measurement. Seed 11 is the one ADR 0085 named."""

REPORT: Path = Path("eval_runs/sandbox/adr0086-empirical-command-baseline/measurement.md")
DETECTION_REPORT: Path = Path("eval_runs/sandbox/adr0086-empirical-command-baseline/detection.md")


@dataclass(frozen=True)
class OrdinaryCount:
    """How many false-alarm narratives one ordinary run produced.

    Attributes:
        seed: The plant and capture seed.
        model: ``"gaussian"`` or ``"empirical"``.
        false_alarms: Narratives that do not concern the authorised write.
        concerns_write: Whether the narrative the demo shows is about that write.
    """

    seed: int
    model: str
    false_alarms: int
    concerns_write: bool
    finding: str


def false_alarms(result: DemoResult) -> int:
    """Return how many narratives on ``result`` are false alarms.

    The shown narrative is a false alarm when it does not concern a write that happened.
    Further narratives are counted with it: the demo only checks the one it shows, and on
    this scenario every extra incident is still an incident about something other than the
    authorised write. A run that raises nothing returns 0.

    Args:
        result: One finished demo run.

    Returns:
        The number of false-alarm narratives. Zero when Atlas stayed silent, and zero for
        the shown narrative when that narrative concerns the write.
    """
    if result.brief is None:
        return 0
    extras = result.other_incidents
    if result.concerns_truth:
        return extras
    return extras + 1


@dataclass(frozen=True)
class DetectionCount:
    """Whether one unauthorised run's shown brief concerns the real write.

    Attributes:
        seed: The plant and capture seed.
        model: ``"gaussian"`` or ``"empirical"``.
        concerns_write: The shown narrative cites the writing device or the link, in the minute
            of the write.
        silent: Atlas raised no narrative.
        finding: The first sentence of the shown incident, or empty when silent.
    """

    seed: int
    model: str
    concerns_write: bool
    silent: bool
    finding: str


def concerns_the_write(result: DemoResult) -> bool:
    """Return whether the shown brief concerns a write that actually happened.

    Args:
        result: One finished demo run.

    Returns:
        True when the narrative the demo shows cites the writing device, or the link it wrote
        on, within a minute of a write. False when Atlas is silent or the shown incident is
        about something else.
    """
    return result.brief is not None and result.concerns_truth


def measure(seed: int, model: str) -> OrdinaryCount:
    """Run one ordinary scenario under ``model`` and count its false alarms.

    Args:
        seed: Plant and capture seed.
        model: ``"gaussian"`` or ``"empirical"``.

    Returns:
        The count for that seed and model.
    """
    behaviour = GaussianBaseline() if model == "gaussian" else None
    result = run_demo(Scenario.OPERATOR, seed=seed, behaviour=behaviour)
    return OrdinaryCount(
        seed=seed,
        model=model,
        false_alarms=false_alarms(result),
        concerns_write=result.concerns_truth,
        finding=result.findings[0] if result.findings else "",
    )


def measure_detection(seed: int, model: str) -> DetectionCount:
    """Run one unauthorised scenario under ``model`` and record whether the brief hits.

    Args:
        seed: Plant and capture seed.
        model: ``"gaussian"`` or ``"empirical"``.

    Returns:
        Whether the shown brief concerns the real write.
    """
    behaviour = GaussianBaseline() if model == "gaussian" else None
    result = run_demo(Scenario.UNAUTHORISED, seed=seed, behaviour=behaviour)
    return DetectionCount(
        seed=seed,
        model=model,
        concerns_write=concerns_the_write(result),
        silent=result.brief is None,
        finding=result.findings[0] if result.findings else "",
    )


def _mean(rows: list[OrdinaryCount]) -> float:
    """Return the mean false-alarm count, or 0 when ``rows`` is empty."""
    if not rows:
        return 0.0
    return sum(row.false_alarms for row in rows) / len(rows)


def render(rows: list[OrdinaryCount], seeds: tuple[int, ...] = SEEDS) -> str:
    """Return the measurement as markdown.

    Args:
        rows: One count per seed and model.
        seeds: The seed order to print. The ADR figure uses `SEEDS`.

    Returns:
        A report that names the figure, the seeds, and the two means.
    """
    by_model = {
        "gaussian": [row for row in rows if row.model == "gaussian"],
        "empirical": [row for row in rows if row.model == "empirical"],
    }
    declared = seeds == SEEDS
    lines = [
        "# Empirical command baseline — ordinary-run false alarms (ADR 0086)",
        "",
        "Figure name: `empirical-command-baseline:operator-false-alarms`.",
        "SYNTHETIC-DERIVED. Not a row on `eval_runs/log.jsonl`. Not command-lead 0/16 or 1/4.",
        "Ordinary run: `phos demo --scenario operator`, 120-hour fit, authorised write.",
        "A false alarm is a narrative that does not concern that write. Silence is 0.",
        (
            f"Seeds, fixed before the runs: {', '.join(str(seed) for seed in seeds)}."
            if declared
            else "Seed override, not the ADR figure: "
            + ", ".join(str(seed) for seed in seeds)
            + "."
        ),
        "",
        "| Seed | Gaussian | Empirical | Gaussian concerns write | Empirical concerns write |",
        "| --- | --- | --- | --- | --- |",
    ]
    for seed in seeds:
        gaussian = next(row for row in by_model["gaussian"] if row.seed == seed)
        empirical = next(row for row in by_model["empirical"] if row.seed == seed)
        lines.append(
            f"| {seed} | {gaussian.false_alarms} | {empirical.false_alarms} | "
            f"{gaussian.concerns_write} | {empirical.concerns_write} |"
        )
    lines += ["", "## What the shown incident said", ""]
    for seed in seeds:
        gaussian = next(row for row in by_model["gaussian"] if row.seed == seed)
        empirical = next(row for row in by_model["empirical"] if row.seed == seed)
        lines.append(f"- Seed {seed}, Gaussian: {gaussian.finding or 'silence'}")
        lines.append(f"- Seed {seed}, empirical: {empirical.finding or 'silence'}")
    lines += [
        "",
        f"Gaussian mean false alarms per ordinary run: {_mean(by_model['gaussian']):.2f} "
        f"over {len(by_model['gaussian'])} seeds.",
        f"Empirical mean false alarms per ordinary run: {_mean(by_model['empirical']):.2f} "
        f"over {len(by_model['empirical'])} seeds.",
        "",
        "The tail is `one_sided_gaussian_tail(3)`, about 0.00135, inherited from the Gaussian",
        "three-sigma claim. It was not searched. Template priors and evidence strength are the",
        "placeholder values from ADR 0008.",
        "",
    ]
    return "\n".join(lines)


def render_detection(rows: list[DetectionCount], seeds: tuple[int, ...] = SEEDS) -> str:
    """Return the unauthorised-write figure as markdown.

    Args:
        rows: One count per seed and model.
        seeds: The seed order to print. The ADR figure uses `SEEDS`.

    Returns:
        A report of how many shown briefs concern the real write.
    """
    by_model = {
        "gaussian": [row for row in rows if row.model == "gaussian"],
        "empirical": [row for row in rows if row.model == "empirical"],
    }

    def hits(model: str) -> int:
        return sum(1 for row in by_model[model] if row.concerns_write)

    declared = seeds == SEEDS
    lines = [
        "# Empirical command baseline — unauthorised-write detection (ADR 0086)",
        "",
        "Figure name: `empirical-command-baseline:unauthorised-concerns-write`.",
        "SYNTHETIC-DERIVED. Not a row on `eval_runs/log.jsonl`. Not command-lead 0/16 or 1/4.",
        "Run: `phos demo --scenario unauthorised`, 120-hour fit, SCADA writes the HMI setpoint.",
        "A hit is a shown brief that concerns that write. Silence is a miss.",
        (
            f"Seeds, fixed before the runs: {', '.join(str(seed) for seed in seeds)}."
            if declared
            else "Seed override, not the ADR figure: "
            + ", ".join(str(seed) for seed in seeds)
            + "."
        ),
        "",
        "| Seed | Gaussian hit | Empirical hit | Gaussian silent | Empirical silent |",
        "| --- | --- | --- | --- | --- |",
    ]
    for seed in seeds:
        gaussian = next(row for row in by_model["gaussian"] if row.seed == seed)
        empirical = next(row for row in by_model["empirical"] if row.seed == seed)
        lines.append(
            f"| {seed} | {gaussian.concerns_write} | {empirical.concerns_write} | "
            f"{gaussian.silent} | {empirical.silent} |"
        )
    gaussian_hits = hits("gaussian")
    empirical_hits = hits("empirical")
    lines += [
        "",
        f"Gaussian briefs that concern the write: {gaussian_hits} of {len(seeds)}.",
        f"Empirical briefs that concern the write: {empirical_hits} of {len(seeds)}.",
        "",
    ]
    if empirical_hits < gaussian_hits:
        lines.append(
            f"The empirical model sees the write less often: {empirical_hits} against "
            f"{gaussian_hits}."
        )
    elif empirical_hits == gaussian_hits:
        lines.append(
            f"The empirical model sees the write as often as the Gaussian one: "
            f"{empirical_hits} of {len(seeds)}."
        )
    else:
        lines.append(
            f"The empirical model sees the write more often: {empirical_hits} against "
            f"{gaussian_hits}."
        )
    lines += ["", "## What the shown incident said", ""]
    for seed in seeds:
        gaussian = next(row for row in by_model["gaussian"] if row.seed == seed)
        empirical = next(row for row in by_model["empirical"] if row.seed == seed)
        lines.append(f"- Seed {seed}, Gaussian: {gaussian.finding or 'silence'}")
        lines.append(f"- Seed {seed}, empirical: {empirical.finding or 'silence'}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Measure every fixed seed under both models and write the sandbox report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--figure",
        choices=("operator", "detection"),
        default="operator",
        help="operator false alarms (default) or unauthorised-write detection",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="*",
        default=list(SEEDS),
        help="override the fixed seed list (the ADR figure uses the default)",
    )
    args = parser.parse_args()
    seeds = tuple(args.seeds)
    if args.figure == "detection":
        rows_d: list[DetectionCount] = []
        for seed in seeds:
            for model in ("gaussian", "empirical"):
                count_d = measure_detection(seed, model)
                rows_d.append(count_d)
                print(
                    f"seed {seed} {model}: concerns_write={count_d.concerns_write} "
                    f"silent={count_d.silent}",
                    flush=True,
                )
        text = render_detection(rows_d, seeds)
        DETECTION_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DETECTION_REPORT.write_text(text, encoding="utf-8")
        print(text, flush=True)
        return
    rows: list[OrdinaryCount] = []
    for seed in seeds:
        for model in ("gaussian", "empirical"):
            count = measure(seed, model)
            rows.append(count)
            print(
                f"seed {seed} {model}: false_alarms={count.false_alarms} "
                f"concerns_write={count.concerns_write}",
                flush=True,
            )
    # Re-render against the declared seed order when the default list was used.
    text = render(rows, seeds)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(text, flush=True)


if __name__ == "__main__":
    main()
