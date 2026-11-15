"""What each level of the discovery ladder demands before a claim may hold it.

Charter section IX names six levels and says "never promote a result without satisfying its
evidentiary requirements". Written only in prose, that sentence is advice. Here it is a function:
``promotable`` returns the reasons a level is not available, and an empty tuple is the only thing
that lets the promotion through.

The requirements compound. A level 5 claim must satisfy every level below it as well, because the
ladder is cumulative: a scientific contribution that was never reproduced is not one.
"""

from __future__ import annotations

from typing import Final

from phos.genesis.records import Experiment, Finding

#: What each level is called, for messages and for the rendered record.
LEVEL_NAMES: Final[dict[int, str]] = {
    0: "idea",
    1: "reproduced",
    2: "improved",
    3: "novel methodology",
    4: "novel finding",
    5: "scientific contribution",
}

#: The highest level a finding may hold without a kept experiment behind it. An idea needs no
#: evidence; everything above it does.
IDEA: Final = 0


def _kept(experiments: dict[str, Experiment], ids: tuple[str, ...]) -> list[Experiment]:
    """Return the experiments among ``ids`` whose verdict is ``kept``."""
    found = []
    for experiment_id in ids:
        experiment = experiments.get(experiment_id)
        if experiment is not None and experiment.verdict is not None:
            if experiment.verdict.outcome == "kept":
                found.append(experiment)
    return found


def _judged(experiments: dict[str, Experiment], ids: tuple[str, ...]) -> list[Experiment]:
    """Return the experiments among ``ids`` that carry a verdict either way."""
    return [experiments[i] for i in ids if i in experiments and experiments[i].verdict is not None]


def promotable(finding: Finding, level: int, experiments: dict[str, Experiment]) -> tuple[str, ...]:
    """Return the reasons ``finding`` may not hold ``level``.

    Args:
        finding: The claim, carrying the evidence it has.
        level: The level being asked for, 0--5.
        experiments: Every experiment record in the store, by id.

    Returns:
        One string per unmet requirement, in the order the levels demand them. An empty tuple
        means the promotion is available.
    """
    if not 0 <= level <= 5:
        return (f"level {level} is not on the ladder (0--5)",)

    reasons: list[str] = []
    missing_evidence = [i for i in finding.evidence if i not in experiments]
    if missing_evidence:
        reasons.append(f"evidence names no such experiment: {', '.join(missing_evidence)}")

    if level == IDEA:
        return tuple(reasons)

    kept = _kept(experiments, finding.evidence)
    judged = _judged(experiments, finding.evidence)

    if not judged:
        reasons.append("no judged experiment behind the claim")
    elif not kept:
        reasons.append("no experiment with a kept verdict behind the claim")
    if not finding.limitations.strip():
        reasons.append("limitations are empty, and above level 0 they may not be")
    if not finding.prior_work:
        reasons.append("no named prior work the claim is positioned against")

    if level >= 2 and not finding.improvement.strip():
        # Every declaration already names a baseline -- the record refuses one without it -- so
        # the thing still missing at level 2 is the comparison itself: both numbers, on the
        # record, where a reviewer can disagree with them.
        reasons.append(
            "no improvement stated: level 2 claims an existing method was measurably beaten, "
            "so the baseline's number and the challenger's belong in the finding"
        )

    if level >= 3:
        if len(finding.prior_work) < 2:
            reasons.append(
                "a novel methodology needs the state of the art surveyed, not one citation: "
                "at least two named prior works"
            )

    if level >= 4:
        distinct = {e.declared.corpus for e in kept} | set(finding.corpora)
        if len(distinct) < 2:
            reasons.append(
                "a novel finding holds on more than one corpus: "
                f"the evidence covers {len(distinct)}"
            )

    if level == 5:
        attempted = [r for r in finding.reviews if r.survived]
        if not attempted:
            reasons.append(
                "no independent review that attempted falsification and the claim survived"
            )
        if not finding.reproduction.strip():
            reasons.append("no reproduction instructions")

    return tuple(reasons)


def ladder_report(findings: list[Finding]) -> dict[str, int]:
    """Return how many findings sit at each level, named.

    Args:
        findings: Every finding in the store.

    Returns:
        A mapping from level name to count, including levels with none.
    """
    counts = dict.fromkeys(LEVEL_NAMES.values(), 0)
    for finding in findings:
        counts[LEVEL_NAMES[finding.level]] += 1
    return counts
