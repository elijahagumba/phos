"""The gate decision, independent of which editor asked for it.

Claude Code and Cursor both gate a shell command, and each has its own shape for asking and its
own shape for answering: Claude Code hands ``{"tool_input": {"command": ...}}`` and reads an exit
code; Cursor hands ``{"command": ...}`` and reads
``{"permission": "allow" | "deny" | "ask"}``. Those two differences are the whole of the
difference, so the decision itself belongs here, where it is typed and tested, and each host keeps
a shim that translates.

The first version of the Cursor adapter sniffed the English out of ``genesis gate``'s stderr to
work out *why* it had refused. That worked and should not have been kept: a host would have
silently started allowing a spent score the day a message was reworded. ``decide`` returns the
reason as data instead, and the two hosts phrase it however they phrase things.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from phos.genesis.records import Experiment
from phos.genesis.store import RECORD_DIR, Store
from phos.genesis.tiercheck import disagreement, resolve

#: The harness entry points phase 2 of the cycle allows. A command naming none of them is not the
#: gate's business, and ``decide`` returns ``None`` rather than an opinion.
HARNESS: Final = re.compile(r"scripts/(?:measure_|evaluate_|lane_)[\w./-]*\.py|scripts/gate\.py")

#: Why a command was refused, or that it was allowed. ``silent`` is the migration case -- nothing
#: in the record declares this command -- and is the only one a host may soften. ``tier`` is a
#: declaration whose corpus and tier disagree with the data-tier rule, which no host may soften.
Verdict = Literal["allow", "silent", "uncommitted", "tampered", "spent", "tier"]


@dataclass(frozen=True)
class GateDecision:
    """What the gate concluded about one shell command.

    Attributes:
        verdict: ``allow``, or which of the four refusals applies.
        headline: One line naming the problem, for a human.
        detail: The longer explanation, newline-separated.
        experiment: The record the decision is about, where one was found.
    """

    verdict: Verdict
    headline: str
    detail: str
    experiment: str | None = None

    @property
    def allowed(self) -> bool:
        """Return whether the command may run."""
        return self.verdict == "allow"

    @property
    def softenable(self) -> bool:
        """Return whether a host may downgrade this refusal while the lanes are backfilled.

        Only ``silent`` is softenable. Every harness in this repository predates GENESIS and was
        declared properly in an ADR, so refusing on silence would block correct work. A spent
        score, an edited declaration and a tier the rule contradicts have no honest reading and
        are never softened.
        """
        return self.verdict == "silent"


def is_harness(command: str) -> bool:
    """Return whether ``command`` runs one of the declared harness entry points.

    Args:
        command: The shell command about to run.

    Returns:
        True when the gate has an opinion about it.
    """
    return bool(HARNESS.search(command))


def _declaring(store: Store, command: str) -> list[Experiment]:
    """Return the experiments whose declared command appears in ``command``."""
    return sorted(
        (
            experiment
            for experiment in store.experiments().values()
            if experiment.declared.command and experiment.declared.command in command
        ),
        key=lambda experiment: experiment.id,
    )


def decide(command: str, store: Store, committed: object = None) -> GateDecision | None:
    """Return the gate's decision about ``command``, or ``None`` if it is not a harness run.

    Args:
        command: The shell command about to run.
        store: The record store to consult.
        committed: A callable ``(path, root) -> (committed, unmodified)``. Defaults to asking git.
            Passed in by the tests so the four states can be exercised without a repository.

    Returns:
        The decision, or ``None`` when the command runs no harness.
    """
    if not is_harness(command):
        return None

    if committed is None:
        from phos.genesis.cli_commands import committed_and_unmodified

        committed = committed_and_unmodified
    assert callable(committed)

    candidates = _declaring(store, command)
    if not candidates:
        return GateDecision(
            verdict="silent",
            headline="nothing declares this harness run",
            detail=(
                f"nothing in {RECORD_DIR} declares this command.\n"
                f"command: {command}\n"
                "declare it: scripts/genesis.py template experiment > e.json, fill it, "
                "`declare --from e.json`, then commit."
            ),
        )

    reasons: list[GateDecision] = []
    for experiment in candidates:
        path = store.path_for(experiment.id)
        is_committed, unmodified = committed(path, store.root)
        if not is_committed:
            reasons.append(
                GateDecision(
                    verdict="uncommitted",
                    headline="the declaration is not committed",
                    detail=(
                        f"{experiment.id} is declared but not committed — the run would come "
                        "first, which is what the contract forbids."
                    ),
                    experiment=experiment.id,
                )
            )
            continue
        if not unmodified:
            reasons.append(
                GateDecision(
                    verdict="tampered",
                    headline="the declaration was edited after it was committed",
                    detail=(
                        f"{experiment.id} has been edited since it was committed — the bars "
                        "could have moved to meet the result."
                    ),
                    experiment=experiment.id,
                )
            )
            continue
        if experiment.phase == "judged":
            reasons.append(
                GateDecision(
                    verdict="spent",
                    headline="that score is already spent",
                    detail=(
                        f"{experiment.id} is already judged. A second look is not available "
                        "(docs/rules/data-tiers.md)."
                    ),
                    experiment=experiment.id,
                )
            )
            continue
        tier = resolve(store.root, experiment.declared.corpus, declared=experiment.declared.tier)
        if tier.refused or tier.disagrees:
            reasons.append(
                GateDecision(
                    verdict="tier",
                    headline="the declared corpus and the data-tier rule disagree",
                    detail="\n".join(
                        line
                        for line in (f"{experiment.id}:", disagreement(tier), *tier.detail)
                        if line
                    ),
                    experiment=experiment.id,
                )
            )
            continue
        bars = "\n".join(
            f"bar {bar.id}: {bar.metric} {bar.comparator} {bar.threshold:g}"
            for bar in experiment.declared.bars
        )
        return GateDecision(
            verdict="allow",
            headline=f"declared by {experiment.id}",
            detail=(f"{experiment.declared.corpus} (tier {experiment.declared.tier})\n{bars}"),
            experiment=experiment.id,
        )

    worst = min(reasons, key=lambda decision: _SEVERITY[decision.verdict])
    if len(reasons) == 1:
        return worst
    return GateDecision(
        verdict=worst.verdict,
        headline=worst.headline,
        detail="\n".join(decision.detail for decision in reasons),
        experiment=worst.experiment,
    )


#: Which refusal to lead with when several declarations match one command. A spent score and an
#: edited declaration are reported ahead of a missing commit, because they are the two a host may
#: not soften. ``tier`` sits with them: a corpus the rule forbids reading is not a migration case.
_SEVERITY: Final[dict[str, int]] = {
    "spent": 0,
    "tampered": 1,
    "tier": 2,
    "uncommitted": 3,
    "silent": 4,
    "allow": 5,
}


def repo_root_from(path: Path) -> Path:
    """Return the repository root containing ``path``, by walking up to the ``.git`` entry.

    Args:
        path: Any path inside the checkout, typically the hook script's own location.

    Returns:
        The directory holding ``.git``, or ``path`` itself when none is found.
    """
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return path
