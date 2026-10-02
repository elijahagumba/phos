#!/usr/bin/env python3
"""Inject deliberate defects into A-FIX-1's phase-conditional code and check the tests catch them.

This is the reproducible proof behind PART A-FIX-1's claim that its test suite has teeth, and it
matters more here than usual. The fix is a *routing* change, and routing defects are quiet: send
every moment to the pooled fallback and the code still runs, still emits well-formed `Deviation`s,
still passes any test that only checks shapes — and Atlas is blind again, exactly as D3 found it.
The `all-to-fallback` mutation below is that failure, and the suite must not survive it.

So each mutation is a defect a careful engineer could plausibly write — a truncation where a round
was meant, a `get` narrowed to a subscript, a guard that looked redundant — and each is chosen so
the wrong behaviour is a *different number* rather than an exception. A defect that crashes gets
found on the first run; these are the ones that would not.

**Nothing is mutated in place.** `src/` is copied to a temporary directory, the copy is edited, and
pytest is pointed at it with ``-o pythonpath=...`` so the mutant shadows the real package. The
working tree is never touched, so an interrupted run cannot leave a defect behind.

Usage::

    python scripts/mutate_phase_conditional.py
    python scripts/mutate_phase_conditional.py --list
    python scripts/mutate_phase_conditional.py all-to-fallback
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT / "src"

TEST_MODULES = ("tests/atlas/test_phased.py",)
"""The suite under examination. A mutation is *caught* when running these turns red."""

logger = logging.getLogger("mutate")


@dataclass(frozen=True)
class Mutation:
    """One deliberate defect, and the reasoning for why it is worth injecting.

    Attributes:
        name: Short identifier, used to run one mutation on its own.
        module: Path of the file to break, relative to ``src/``.
        old: The exact source text to replace. Must appear exactly once, or the run aborts —
            a mutation that silently applied nowhere would be reported as caught by every test.
        new: What to replace it with.
        why: The plausible reasoning a real engineer might have had for writing it this way.
        breaks: What goes wrong, in the numbers rather than in an exception.
    """

    name: str
    module: str
    old: str
    new: str
    why: str
    breaks: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="all-to-fallback",
        module="phos/atlas/phased.py",
        old="            model = self.per_phase.get(phase, self.fallback)",
        new="            model = self.fallback",
        why="The fallback is fitted on everything, so it must be the safest of the models to use.",
        breaks="Routing stops happening. Every moment is judged by the pooled model — which is "
        "precisely the model D3 measured as blind on this plant — while the fitted per-phase "
        "models sit unused. The whole PART is undone and nothing raises.",
    ),
    Mutation(
        name="phase-truncated-not-rounded",
        module="phos/atlas/phased.py",
        old="        observation.timestamp: round(observation.value)",
        new="        observation.timestamp: int(observation.value)",
        why="`int()` reads as the obvious way to turn a float register into an ordinal.",
        breaks="A register reading 0.98 of phase 1 truncates to phase 0, so noisy moments near "
        "every phase transition are judged against the wrong baseline — worst exactly at the "
        "boundaries, where a batch process actually changes.",
    ),
    Mutation(
        name="unseen-phase-goes-silent",
        module="phos/atlas/phased.py",
        old="            model = self.per_phase.get(phase, self.fallback)\n"
        "            scored.extend(model.score(by_phase[phase]))",
        new="            model = self.per_phase.get(phase)\n"
        "            if model is None:\n"
        "                continue\n"
        "            scored.extend(model.score(by_phase[phase]))",
        why="If no model was learned for a phase, we have nothing to say — so say nothing.",
        breaks="A phase the training corpus never contained becomes a permanent blind spot. An "
        "attacker who can write any unrecognised value to the register buys silence across the "
        "whole plant for as long as it is held.",
    ),
    Mutation(
        name="unrouted-moments-dropped",
        module="phos/atlas/phased.py",
        old="        if unrouted:\n"
        "            scored.extend(self.registerless_fallback.score(unrouted))\n",
        new="",
        why="Every moment in these corpora reports a phase, so the branch looked like dead code.",
        breaks="An instant whose register reading is missing is scored by nothing at all. A sensor "
        "that drops the phase register — or is made to — takes the entire plant's judgement with "
        "it for that moment.",
    ),
    Mutation(
        name="empty-phase-model-kept",
        module="phos/atlas/phased.py",
        old="            if fitted.signal_space.size == 0:",
        new="            if False:",
        why="`fit` already handles a thin corpus by returning an empty model, so re-checking it "
        "here looked redundant.",
        breaks="A phase with too few samples is stored as a model spanning no signals, which "
        "scores nothing and — because it is present in `per_phase` — shadows the fallback that "
        "would otherwise have judged it. A rare phase silently stops being watched.",
    ),
    Mutation(
        name="knobs-not-propagated",
        module="phos/atlas/phased.py",
        old="        return self.inner.model_copy(\n"
        "            update={\n"
        '                "min_samples": self.min_samples,\n'
        '                "band_k": self.band_k,\n'
        '                "emit_k": self.emit_k,\n'
        "            }\n"
        "        )",
        new="        return self.inner",
        why="The inner model already carries sensible defaults for all three.",
        breaks="Configuring the wrapper stops configuring anything. A caller who narrows `band_k` "
        "to tighten the boundary gets the inner model's default instead, and the number in the "
        "run's configuration record no longer describes the run.",
    ),
    Mutation(
        name="fallback-fitted-on-one-phase",
        module="phos/atlas/phased.py",
        old="            fallback=_narrow(inner.fit(observations)),",
        new="            fallback=_narrow(inner.fit(by_phase[max(by_phase)])),",
        why="A copy-paste slip while reaching for a corpus to fit the fallback on.",
        breaks="The fallback is fitted inside a single phase, so it no longer spans the phase "
        "register (constant there, dropped by the zero-variance filter) and judges every "
        "unroutable moment against one arbitrary phase's normal.",
    ),
    Mutation(
        name="scored-order-not-restored",
        module="phos/atlas/phased.py",
        old="        return sorted(scored, key=lambda deviation: deviation.timestamp)",
        new="        return scored",
        why="Each inner model already returns its own deviations in timestamp order.",
        breaks="Deviations come back grouped by phase rather than by time. Anything downstream "
        "that assumes a time series — grouping into subsystem events stamps an event at its "
        "earliest member — reads the corpus out of order.",
    ),
    Mutation(
        name="routing-off-by-one",
        module="phos/atlas/phased.py",
        old="            model = self.per_phase.get(phase, self.fallback)",
        new="            model = self.per_phase.get(phase + 1, self.fallback)",
        why="An off-by-one while reconciling a zero-based register with a one-based recipe step.",
        breaks="Every moment is judged against the *next* phase's normal, which is the exact "
        "failure the PART exists to remove — a reading held to a baseline from a different part "
        "of the batch — dressed up as a working router.",
    ),
    Mutation(
        name="registerless-fallback-spans-register",
        module="phos/atlas/phased.py",
        old="            registerless_fallback=_narrow(\n"
        "                inner.fit([o for o in observations if o.feature != self.phase_feature])\n"
        "            ),",
        new="            registerless_fallback=_narrow(inner.fit(observations)),",
        why="Two fits over one corpus looked like duplication; the second fallback can surely "
        "just be the first.",
        breaks="The registerless fallback now spans a register the moments it exists for never "
        "carry, so `vectorise` drops every one of their rows and they are scored by nothing — the "
        "branch runs, returns an empty list, and the blind spot is invisible.",
    ),
    Mutation(
        name="register-excluded-from-fallback",
        module="phos/atlas/phased.py",
        old="            fallback=_narrow(inner.fit(observations)),",
        new="            fallback=_narrow(\n"
        "                inner.fit([o for o in observations if o.feature != self.phase_feature])\n"
        "            ),",
        why="The register is the router's key, not a process signal, so it looked out of place "
        "inside a model of the plant.",
        breaks="Nothing in the fitted model spans the phase register any more, so a falsified or "
        "out-of-range phase value is unjudgeable by construction — the one guard the design has "
        "against its own routing key.",
    ),
)


def apply_mutation(mutation: Mutation, tree: Path) -> None:
    """Edit one file in a copied source tree.

    Args:
        mutation: The defect to inject.
        tree: The copied ``src`` directory to edit.

    Raises:
        SystemExit: If the target text is absent or appears more than once. Either would make the
            run report a mutation as caught when it was never actually applied, which is precisely
            the false reassurance this script exists to prevent.
    """
    path = tree / mutation.module
    original = path.read_text(encoding="utf-8")
    occurrences = original.count(mutation.old)
    if occurrences != 1:
        raise SystemExit(
            f"mutation {mutation.name!r}: target text appears {occurrences} time(s) in "
            f"{mutation.module}, expected exactly 1. The source has moved; update the mutation."
        )
    path.write_text(original.replace(mutation.old, mutation.new), encoding="utf-8")


def run_suite(source_root: Path) -> tuple[bool, str]:
    """Run the A-FIX-1 suite against ``source_root`` and report whether it passed.

    Args:
        source_root: The ``src`` directory to import ``phos`` from. Overrides the ini setting, so
            a mutant shadows the working tree rather than competing with it.

    Returns:
        ``(passed, first failing test name or "")``.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *TEST_MODULES,
            "-x",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-o",
            f"pythonpath={source_root}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True, ""
    for line in completed.stdout.splitlines():
        if line.startswith("FAILED") or line.startswith("ERROR"):
            return False, line.split("::")[-1].split(" ")[0]
    return False, "(no FAILED line; see pytest output)"


def check(mutation: Mutation) -> bool:
    """Inject one mutation into a throwaway copy of the source and report whether it was caught."""
    with tempfile.TemporaryDirectory(prefix="phos-mutant-") as workspace:
        tree = Path(workspace) / "src"
        shutil.copytree(SOURCE_ROOT, tree)
        apply_mutation(mutation, tree)
        passed, detail = run_suite(tree)

    if passed:
        print(f"  MISSED   {mutation.name}")
        print(f"           plausible because: {mutation.why}")
        print(f"           what it breaks:    {mutation.breaks}")
        return False
    print(f"  caught   {mutation.name}  ({detail})")
    return True


def main() -> int:
    """Run every mutation, or one named on the command line, and report the tally."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="run only the mutation with this name")
    parser.add_argument("--list", action="store_true", help="list the mutations and exit")
    arguments = parser.parse_args()

    if arguments.list:
        for mutation in MUTATIONS:
            print(f"{mutation.name:<32} {mutation.module}")
        return 0

    selected = MUTATIONS
    if arguments.name:
        selected = tuple(m for m in MUTATIONS if m.name == arguments.name)
        if not selected:
            print(f"no mutation named {arguments.name!r}; try --list")
            return 2

    print(f"injecting {len(selected)} mutation(s) into a copy of {SOURCE_ROOT}")
    caught = sum(check(mutation) for mutation in selected)
    missed = len(selected) - caught
    print(f"\n{caught}/{len(selected)} caught, {missed} missed")
    return 1 if missed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    raise SystemExit(main())
