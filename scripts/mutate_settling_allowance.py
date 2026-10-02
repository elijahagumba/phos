#!/usr/bin/env python3
"""Inject deliberate defects into A-FIX-2's settling allowance and check the tests catch them.

The companion to `mutate_phase_conditional.py`, and it exists for a sharper reason. A settling
allowance is a *suppression*, so every defect in it fails in the same direction: it forgives more
than it should. Nothing raises, the ontology objects stay well-formed, the false-positive rate
*improves*, and Atlas quietly stops looking during the exact minutes an attacker would choose. A
test suite that only checks that the transient goes away would pass against every mutation below.

So the mutations are the ways this code could plausibly be written wrong while looking right:
forgiving on the strength of a *missing* judgement (`emit-k-not-zeroed`, which is a defect this
PART actually hit while prototyping), measuring elapsed time from the wrong instant, judging
against the phase already flagged, or letting the window run unbounded.

**One defect is deliberately absent, and its absence is the point.** ADR 0019 rejected forgiving
the convex *hull* of the two phases' bands rather than the bands themselves. That error cannot be
injected here, because it cannot be written: forgiveness is expressed by substituting the
outgoing phase's own band, and a reading is only forgiven when that band already contains it, so
widening the substituted band changes nothing a reader could observe. Both natural mutations for
it are inert. The rule the ADR chose on measurement is the only one this shape of code can
express, which is a stronger guarantee than a passing test.

**Nothing is mutated in place.** `src/` is copied to a temporary directory, the copy is edited, and
pytest is pointed at it with ``-o pythonpath=...`` so the mutant shadows the real package. The
working tree is never touched, so an interrupted run cannot leave a defect behind.

Usage::

    python scripts/mutate_settling_allowance.py
    python scripts/mutate_settling_allowance.py --list
    python scripts/mutate_settling_allowance.py forgive-everything
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

TEST_MODULES = ("tests/atlas/test_phased.py", "tests/breaking/test_harness.py")
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


PHASED = "phos/atlas/phased.py"

MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="forgive-everything",
        module=PHASED,
        old="            if explained is not None and explained.expected.contains(reading):",
        new="            if explained is not None:",
        why="Any moment near a phase change is settling, so the outgoing model's judgement of it "
        "is the one to report.",
        breaks="The allowance stops being conditional on the outgoing phase *explaining* the "
        "reading and becomes a blanket suppression for the whole window — precisely the "
        "attacker-triggerable blind window ADR 0019 was written to avoid. Nothing raises and the "
        "false-positive rate improves.",
    ),
    Mutation(
        name="outgoing-scored-over-the-whole-corpus",
        module=PHASED,
        old="            for deviation in judge.score(settling[phase]):",
        new="            for deviation in judge.score(observations):",
        why="Scoring everything once and looking up the moments that matter is simpler than "
        "assembling a bucket, and the extra rows are just discarded.",
        breaks="They are not discarded: the lookup is keyed by observation, so every moment in the "
        "corpus acquires an outgoing judgement and the allowance stops being bounded by the window "
        "at all. A reading that resembles some other phase is forgiven anywhere, at any distance "
        "from a transition — the unbounded variant ADR 0019 measured at 66.4% of attacked "
        "deviations suppressed.",
    ),
    Mutation(
        name="emit-k-not-zeroed",
        module=PHASED,
        old='            judge = self.per_phase[phase].model_copy(update={"emit_k": 0.0})',
        new="            judge = self.per_phase[phase]",
        why="The outgoing model is already fitted and configured; copying it just to change a "
        "threshold looks like redundant ceremony.",
        breaks="A cell the outgoing phase finds *perfectly ordinary* emits no candidate, so there "
        "is no band to test and the moment is never forgiven. The allowance then fails on exactly "
        "the readings most clearly explained by the phase being left, which is the opposite of "
        "what it is for. This is a defect this PART actually wrote while prototyping.",
    ),
    Mutation(
        name="window-unbounded",
        module=PHASED,
        old="            if observation.timestamp - moment.started_at >= self.settling_window:\n"
        "                continue",
        new="",
        why="The allowance already refuses anything the outgoing phase cannot explain, so the "
        "time bound looks like belt-and-braces.",
        breaks="The bound is load-bearing and ADR 0019 measured why: left unbounded the allowance "
        "suppresses 66.4% of the attacked corpus's out-of-band deviations, because two phases that "
        "resemble each other in a signal permanently widen its effective band.",
    ),
    Mutation(
        name="elapsed-from-corpus-start",
        module=PHASED,
        old="        if phase != last:\n            previous, started_at = last, timestamp",
        new="        if phase != last:\n            previous = last",
        why="`started_at` is set once from the first timestamp; a phase change only needs to "
        "record which phase was left.",
        breaks="Elapsed time is measured from the start of the corpus rather than from the phase "
        "change, so the allowance applies to the corpus's opening minutes and to nothing else. "
        "Every real transition is judged unforgivingly and the transient returns in full.",
    ),
    Mutation(
        name="window-boundary-inclusive",
        module=PHASED,
        old="            if observation.timestamp - moment.started_at >= self.settling_window:",
        new="            if observation.timestamp - moment.started_at > self.settling_window:",
        why="The window should surely include its own final instant.",
        breaks="Extends the allowance by one sample beyond the measured end of the transient. "
        "Small, silent, and in the direction that costs detection rather than false positives — "
        "which is the direction this PART is least willing to drift in.",
    ),
    Mutation(
        name="settle-against-the-entered-phase",
        module=PHASED,
        old="            if moment.previous in self.per_phase:\n"
        "                settling[moment.previous].append(observation)",
        new="            if moment.phase in self.per_phase:\n"
        "                settling[moment.phase].append(observation)",
        why="The moment belongs to the phase it is in, so that is the model to judge it with.",
        breaks="Re-judges the moment against the very phase that already flagged it, so nothing is "
        "ever forgiven and the allowance is dead code. The suite must not accept a fix that does "
        "nothing.",
    ),
    Mutation(
        name="unlearned-outgoing-uses-fallback",
        module=PHASED,
        old="            if moment.previous in self.per_phase:\n"
        "                settling[moment.previous].append(observation)",
        new="            settling[moment.previous].append(observation)",
        why="A phase with no learned model should still get the benefit of the pooled fallback "
        "rather than no allowance at all.",
        breaks="Raises a KeyError for an unlearned phase, or — worse in the variant that reaches "
        "for `self.fallback` — forgives against the pooled model this whole PART series exists to "
        "escape, which on this plant has bands wider than the signals they judge and would "
        "therefore forgive nearly anything.",
    ),
    Mutation(
        name="forgive-on-the-entering-band",
        module=PHASED,
        old="            if explained is not None and explained.expected.contains(reading):",
        new="            if explained is not None and deviation.expected.contains(reading):",
        why="The reading is being judged for the phase it is entering, so that is the band the "
        "forgiveness test should read.",
        breaks="Inverts the allowance. A reading already inside the entering band — an ordinary "
        "in-band candidate — gets the outgoing model's verdict substituted for it, which can put "
        "it *outside* that model's band. The allowance becomes a source of false positives instead "
        "of a cure for them, and the readings it was built for are never forgiven at all.",
    ),
    Mutation(
        name="outgoing-phase-never-recorded",
        module=PHASED,
        old="        if phase != last:\n            previous, started_at = last, timestamp",
        new="        if phase != last:\n            started_at = timestamp",
        why="`started_at` is what the elapsed test needs; `previous` is initialised already.",
        breaks="`previous` stays None for the whole corpus, so no moment ever has an outgoing "
        "phase and nothing is ever forgiven. The allowance is dead code that reports a settling "
        "window it does not apply.",
    ),
    Mutation(
        name="window-not-carried-to-the-fit",
        module=PHASED,
        old="            phase_feature=self.phase_feature,\n"
        "            settling_window=self.settling_window,\n"
        "            per_phase=learned,",
        new="            phase_feature=self.phase_feature,\n            per_phase=learned,",
        why="The fitted model has a sensible default for the window, so passing it through is "
        "just noise.",
        breaks="The configured window is dropped on the floor and every fitted model silently uses "
        "the default. A run configured to measure the allowance off would measure it on, which "
        "would corrupt the comparison rather than fail it.",
    ),
    Mutation(
        name="harness-drops-the-window",
        module="phos/breaking/harness.py",
        old="    return PhaseConditionalModel(\n"
        "        phase_feature=phase_feature, settling_window=settings.settling_window\n"
        "    )",
        new="    return PhaseConditionalModel(phase_feature=phase_feature)",
        why="The model's own default is the measured one, so the harness need not repeat it.",
        breaks="The run's recorded configuration and the model it actually fitted come apart. "
        "Every number in the breaking-point map would be produced by a setting the report does not "
        "name, which Constitution §3.7 says makes it not a measurement.",
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
    """Run the A-FIX-2 suite against ``source_root`` and report whether it passed.

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
        if line.startswith(("FAILED", "ERROR")):
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
            print(f"{mutation.name:<34} {mutation.module}")
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
