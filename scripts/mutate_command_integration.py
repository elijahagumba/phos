#!/usr/bin/env python3
"""Inject deliberate defects into P3's integration code and check the tests catch them.

The reproducible proof behind PART P3's claim that its suite has teeth, and the third run of a
discipline that has now paid for itself twice. P1 injected eight defects after its fuzz suite went
green and found one the suite could not see. P2 injected twenty-two and found a real defect in
`write_command_share`'s provenance. **A green suite you have not tried to fool is not evidence.**

P3's seams have a particular shape, and the mutations below are chosen for it. Almost nothing here
crashes. A weight paired with the wrong finding is still a probability; evidence stamped a window
late still stores, still sorts and still reasons; a breadth pattern that reads command evidence
still returns a role. Each mutation is a defect a careful engineer could plausibly write, and each
one leaves every surface an engineer would glance at looking exactly right.

**Nothing is mutated in place.** ``src/`` is copied to a temporary directory, the copy is edited,
and pytest is pointed at it with ``-o pythonpath=...`` so the mutant shadows the real package. The
working tree is never touched, so an interrupted run cannot leave a defect behind.

Usage::

    python scripts/mutate_command_integration.py
    python scripts/mutate_command_integration.py --list
    python scripts/mutate_command_integration.py graph-weights-mispaired
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

TEST_MODULES = (
    "tests/reasoning/test_boundary.py",
    "tests/reasoning/test_calibration.py",
    "tests/atlas/test_templates.py",
    "tests/atlas/test_stability.py",
    "tests/atlas/test_command_evidence.py",
    "tests/atlas/test_command_grounding.py",
    "tests/atlas/test_command_eval.py",
    "tests/atlas/test_command_integration_adversarial.py",
    "tests/atlas/test_engine.py",
    "tests/reasoning/test_engine.py",
    "tests/breaking/test_commands.py",
    "tests/breaking/test_report.py",
)
"""The suite under examination. A mutation is *caught* when running these turns red.

Session 4 appends command_grounding, reasoning/test_engine, and the breaking ranking/report
suites so undoing ADR 0036 or 0038 is visible. P3 plumbing mutations still fail on the modules
listed first.
"""

logger = logging.getLogger("mutate")


@dataclass(frozen=True)
class Mutation:
    """One deliberate defect, and the reasoning for why it is worth injecting.

    Attributes:
        name: Short identifier, used to run one mutation on its own.
        module: Path of the file to break, relative to ``src/``.
        old: The exact source text to replace. Must appear exactly once, or the run aborts — a
            mutation that silently applied nowhere would be reported as caught by every test.
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
    # -- the weight/measurement pairing --------------------------------------------------------
    Mutation(
        name="graph-weights-mispaired",
        module="phos/atlas/command_evidence.py",
        old="    weights = calibrated_probabilities("
        "calibrator, [finding.value for finding in ordered])",
        new="    weights = calibrated_probabilities("
        "calibrator, [finding.value for finding in findings])",
        why="The scores are the same numbers either way; calibrate the argument as it arrived.",
        breaks="Every piece of evidence carries a probability computed from a DIFFERENT finding "
        "whenever the caller's order is not time order. The count is right, every weight is in "
        "range, the output is sorted, and each source_id resolves.",
    ),
    Mutation(
        name="behaviour-weights-mispaired",
        module="phos/atlas/command_evidence.py",
        old="    departures.sort("
        "key=lambda pair: (pair[1].timestamp, pair[1].feature, pair[1].id))\n"
        "    weights = calibrated_probabilities(\n"
        "        calibrator, [deviation.magnitude for deviation, _ in departures]\n"
        "    )",
        new="    weights = calibrated_probabilities(\n"
        "        calibrator, [deviation.magnitude for deviation, _ in departures]\n"
        "    )\n"
        "    departures.sort("
        "key=lambda pair: (pair[1].timestamp, pair[1].feature, pair[1].id))",
        why="Calibrate first, then sort for presentation — the sort is only about output order.",
        breaks="The same mispairing as above, on the behaviour stream: a mild departure inherits a "
        "severe one's confidence and vice versa, and nothing about the result looks wrong.",
    ),
    # -- the boundary's refusals ---------------------------------------------------------------
    Mutation(
        name="zero-change-becomes-evidence",
        module="phos/reasoning/boundary.py",
        old="    if finding.value <= 0.0:",
        new="    if finding.value < 0.0:",
        why="A count of zero is a perfectly good measurement; only a negative one is impossible.",
        breaks="A structural change of nothing becomes evidence a hypothesis rests on — the "
        "relationship-change analogue of promoting an in-band deviation, which is the exact thing "
        "the boundary exists to refuse.",
    ),
    Mutation(
        name="one-entity-is-a-relationship",
        module="phos/reasoning/boundary.py",
        old="    if len(finding.entity_ids) < _RELATIONSHIP_ENDS:",
        new="    if len(finding.entity_ids) < 1:",
        why="Observation already guarantees at least one entity; the second check is redundant.",
        breaks="A reading of one device is promoted as a change in the structure BETWEEN devices, "
        "so a command-count observation could be routed through the wrong door and would then "
        "support the malicious explanation on the strength of nothing structural at all.",
    ),
    # -- the calibration contract ---------------------------------------------------------------
    Mutation(
        name="calibrator-output-clipped-not-refused",
        module="phos/reasoning/calibration.py",
        old="    if lowest < -_PROBABILITY_TOLERANCE or highest > 1.0 + _PROBABILITY_TOLERANCE:\n"
        "        raise ValueError(",
        new="    if False:  # noqa: SIM223\n        raise ValueError(",
        why="Everything is clipped to [0, 1] two lines later anyway, so the check is belt and "
        "braces.",
        breaks="A calibrator that is not returning probabilities is silently rescued into looking "
        "like one, so an uncalibrated confidence reaches a user (Constitution §3.3) with nothing "
        "anywhere recording that it happened.",
    ),
    # -- the breadth scope guard ----------------------------------------------------------------
    Mutation(
        name="breadth-guard-dropped",
        module="phos/atlas/templates.py",
        old="        if is_subsystem_event(evidence) is not self.subsystem_events_only:\n"
        "            return False\n",
        new="",
        why="Breadth is just how many entities a fact names; the extra condition looks like "
        "defensive clutter.",
        breaks="A per-device command departure is read as one device's worth of a plant unit, so "
        "it ARGUES AGAINST unauthorised control activity — the exact inversion the command stream "
        "was built to prevent.",
    ),
    Mutation(
        name="breadth-guard-inverted",
        module="phos/atlas/templates.py",
        old="        if is_subsystem_event(evidence) is not self.subsystem_events_only:",
        new="        if is_subsystem_event(evidence) is self.subsystem_events_only:",
        why="A slip of the comparison while reading the flag as an exclusion.",
        breaks="The four OT explanations stop seeing subsystem events entirely, so the sensor "
        "path's own reasoning silently goes quiet while everything still runs.",
    ),
    Mutation(
        name="scoped-patterns-overlap",
        module="phos/atlas/templates.py",
        old="        if (\n"
        "            isinstance(other, SubsystemBreadthPattern)\n"
        "            and other.subsystem_events_only is not self.subsystem_events_only\n"
        "        ):\n"
        "            return False\n",
        new="",
        why="`overlaps` already compares kinds and bands; the scope is a matching detail.",
        breaks="`HypothesisTemplate` loses the ability to prove a template unambiguous at "
        "construction for scoped patterns, so a template could declare one fact both supporting "
        "and contradictory and only be discovered at match time.",
    ),
    # -- the discrimination itself ---------------------------------------------------------------
    Mutation(
        name="structural-change-supports-the-upset",
        module="phos/atlas/templates.py",
        old="            contradicted_by=(_LOCALISED, _STRUCTURE_CHANGED),",
        new="            contradicted_by=(_LOCALISED,),",
        why="A process upset does not preclude a maintenance change happening at the same time, so "
        "calling a structural change evidence AGAINST it is too strong.",
        breaks="The one asymmetry commands buy is gone. The malicious and benign explanations "
        "differ only by their priors again, so the ordering never reverses and the whole packet "
        "adapter changes no conclusion.",
    ),
    Mutation(
        name="structural-change-stops-supporting-the-attack",
        module="phos/atlas/templates.py",
        old="            supported_by=(_BROAD, _STRUCTURE_CHANGED),",
        new="            supported_by=(_BROAD,),",
        why="Maintenance already covers structural change; two explanations claiming one fact "
        "looks like double counting.",
        breaks="A command relationship that has never existed no longer argues for unauthorised "
        "control at all, which is the single finding the adapter exists to surface.",
    ),
    # -- ordering and storage --------------------------------------------------------------------
    Mutation(
        name="commands-weighed-last",
        module="phos/atlas/engine.py",
        old="    return sorted(\n"
        "        [*events, *from_commands], key=lambda item: "
        "(item.timestamp, item.kind.value, item.summary)\n"
        "    )",
        new="    return [*events, *from_commands]",
        why="Two already-ordered lists; concatenating them is cheaper than a full sort.",
        breaks="Every structural change is weighed after every reading in the run, so a change "
        "that happened early falls outside the correlation window of the events around it and "
        "starts a story of its own instead of joining theirs.",
    ),
    Mutation(
        name="stream-grouped-by-kind",
        module="phos/atlas/command_evidence.py",
        old="        merged.sort(key=lambda item: (item.timestamp, item.kind.value, item.summary))",
        new="        merged.sort(key=lambda item: (item.kind.value, item.timestamp, item.summary))",
        why="Group the two streams so a reader sees all the departures and then all the "
        "structural changes.",
        breaks="The streams stop being interleaved, so the reasoning engine sees a whole capture's "
        "behaviour before any structural change, and which hypothesis a change joins depends on "
        "the alphabet rather than on when it happened.",
    ),
    Mutation(
        name="finding-not-stored",
        module="phos/atlas/engine.py",
        old="        for change in commands.changes:\n"
        "            if self._store.get_observation(change.finding.id) is None:\n"
        "                self._store.add_observation(change.finding)\n",
        new="",
        why="The finding is already inside the GraphChange the caller holds; storing it again is "
        "duplication.",
        breaks="Relationship evidence names a source_id nothing in the store resolves, so an "
        "operator drilling into the one finding that reordered the explanations arrives nowhere.",
    ),
    # -- the two streams crossed -----------------------------------------------------------------
    Mutation(
        name="streams-crossed-silently",
        module="phos/atlas/command_evidence.py",
        old="    _refuse_graph_findings(observations)",
        new="",
        why="The caller filters already, and a model with no baseline for a graph feature scores "
        "nothing anyway — so the guard can only ever be redundant.",
        breaks="A relationship finding scored as behaviour is attributed to its ISSUER alone and "
        "judged against whatever baseline that device happened to hold, so a structural fact "
        "becomes a per-device deviation and is counted twice.",
    ),
    # -- the refusals that keep the measurement honest ---------------------------------------------
    Mutation(
        name="unlabelled-corpus-scored",
        module="phos/atlas/command_eval.py",
        old="    if not dataset.attack_intervals:",
        new="    if dataset.attack_intervals is None:",
        why="`attack_intervals` is always a list, so the truthiness check is really an emptiness "
        "check that a None check states more precisely.",
        breaks="A capture nobody labelled is scored, and the harness reports a recall of 0.00 and "
        "a false-positive rate over the whole corpus — numbers that look like a poor result "
        "rather than like no result.",
    ),
    Mutation(
        name="discovery-ignores-ground-truth",
        module="phos/atlas/command_eval.py",
        old='        if not manifest.get("attack_intervals"):',
        new='        if manifest.get("attack_intervals") is None:',
        why="Same reasoning as above: a manifest either declares the key or it does not.",
        breaks="A capture corpus with an empty label list is discovered and run, so the script "
        "stops refusing and prints a headline number that no ground truth stands behind — which "
        "is the single outcome PART P3 exists to prevent.",
    ),
    Mutation(
        name="graph-score-is-a-flag",
        module="phos/atlas/command_eval.py",
        old="                score=change.finding.value,",
        new="                score=1.0,",
        why="A relationship either changed or it did not; the count adds nothing to a detection.",
        breaks="One probe and a sustained flood on a new link score identically, so the harness's "
        "threshold sweep collapses to a single operating point and severity stops being orderable.",
    ),
    Mutation(
        name="adapter-invents-a-comparison",
        module="phos/atlas/command_eval.py",
        old="            if self.graph is not None:",
        new="            if self.graph is not None or True:",
        why="Comparing against an empty graph is harmless — nothing was learned, so nothing "
        "differs.",
        breaks="Comparing against an empty graph makes EVERY live relationship unknown, so a "
        "corpus loaded without a baseline reports the whole plant as new structure.",
    ),
    # -- ranking-contract lock (session 4): undoing ADR 0036 / 0038 -------------------------
    Mutation(
        name="leads-ignores-tied-leaders",
        module="phos/breaking/commands.py",
        old="        if self.tied_leaders:\n"
        "            return None\n"
        "        if self.templates:\n"
        "            return self.templates[0]",
        new="        if self.templates:\n            return self.templates[0]",
        why="The listing is already strongest-first; the first template_id is the leader. "
        "tied_leaders is only a note.",
        breaks="A ceiling or epsilon tie becomes a unique winner. The unknown-master subtle "
        "window (rank 1, two unauthorised_control_activity hypotheses) would newly_leads. "
        "ADR 0036 said that is a refusal.",
    ),
    Mutation(
        name="template-id-inverted-so-attack-wins",
        module="phos/breaking/commands.py",
        old="    relevant.sort(key=lambda item: (-item.confidence, item.template_id))",
        new="    relevant.sort(key=lambda item: "
        "(-item.confidence, tuple(-ord(c) for c in item.template_id)))",
        why="When confidences saturate, pick the attack name rather than maintenance — that is "
        "the explanation we are trying to measure.",
        breaks="Alphabetical order is inverted so unauthorised_control_activity lists first on "
        "a ceiling tie and rank becomes 1. The fake winner ADR 0036 forbade.",
    ),
    Mutation(
        name="ranked-template-id-inverted",
        module="phos/reasoning/engine.py",
        old="            key=lambda h: (-h.confidence, h.template_id, position[h.id]),",
        new="            key=lambda h: (-h.confidence, tuple(-ord(c) for c in h.template_id), "
        "position[h.id]),",
        why="Same as above, on the engine listing the operator sees.",
        breaks="Saturated rivals still raise the residual, but the tied pair under it lists "
        "the attack before maintenance — the other fake winner.",
    ),
    Mutation(
        name="residual-counted-as-command-lead",
        module="phos/breaking/commands.py",
        old="        return self.unique_leader == ATTACK_TEMPLATE_ID",
        new='        return self.unique_leader in {ATTACK_TEMPLATE_ID, "insufficient_evidence"}',
        why="Raising insufficient_evidence is the system deciding; count it as the command path "
        "winning the window.",
        breaks="A residual-first listing is scored as unauthorised_control_activity uniquely "
        "leading. Session 2 forbade that: leads means unique attack, never residual-first.",
    ),
    Mutation(
        name="rank-one-tie-counted-as-unique-lead",
        module="phos/breaking/report.py",
        old="    leads = sum(1 for result in results if result.newly_leads)",
        new="    leads = sum(1 for result in results if result.with_commands.rank == 1)",
        why="Rank 1 is the leader; tied_leaders is a footnote the headline should not wait on.",
        breaks="wt-unknown-master-subtle (rank 1, tied_leaders non-empty) is counted as a unique "
        "unauthorised lead. ADR 0036 said leads stays false.",
    ),
    Mutation(
        name="issuer-kinds-pooled",
        module="phos/breaking/report.py",
        old="    lines.extend(\n"
        "        _issuer_kind_block(\n"
        '            "Known-station issuers",\n'
        "            tuple(item for item in results if item.issuer_kind is "
        "CommandIssuerKind.KNOWN_STATION),\n"
        '            "Issuer already commanded someone in the baseline capture.",\n'
        "        )\n"
        "    )\n"
        "    lines.extend(\n"
        "        _issuer_kind_block(\n"
        '            "Unknown-master issuers",\n'
        "            tuple(item for item in results if item.issuer_kind is "
        "CommandIssuerKind.UNKNOWN_MASTER),\n"
        '            "Issuer never commanded anyone in the baseline capture.",\n'
        "        )\n"
        "    )",
        new="    lines.extend(\n"
        "        _issuer_kind_block(\n"
        '            "All command issuers",\n'
        "            tuple(results),\n"
        '            "Known-station and unknown-master writes scored together.",\n'
        "        )\n"
        "    )",
        why="One headline is easier to quote than two; the battery is one measurement.",
        breaks="Known-station 0/16 and unknown-master 1/4 render as one pooled 'led in n of m', "
        "mixing ADR 0014's remaining indistinguishability with ADR 0027.",
    ),
    Mutation(
        name="attachable-always-true",
        module="phos/reasoning/engine.py",
        old="        return graph_finding_is_attachable(fact, act)",
        new="        return True",
        why="Every stored graph finding is a fact about this window; reachability is a second "
        "filter the promoter already applied.",
        breaks="A silent learned poller with no path to the rogue write accumulates on "
        "engineering_maintenance. ADR 0038's attachment rule is gone.",
    ),
    Mutation(
        name="ingest-skip-dropped",
        module="phos/reasoning/engine.py",
        old="            if not self._attachable(fact):\n"
        "                logger.debug(\n"
        '                    "graph finding %s does not share an entity with in-window command '
        'activity; "\n'
        '                    "not attaching it to this story\'s explanations",\n'
        "                    fact.id,\n"
        "                )\n"
        "                continue\n",
        new="",
        why="_attachable is a predicate for tests; ingest should weigh everything the store "
        "already accepted.",
        breaks="Unreachable silence is weighed onto this window's explanations even when "
        "_attachable would have refused it. Same drowning ADR 0038 named.",
    ),
    Mutation(
        name="silence-always-attachable",
        module="phos/atlas/command_grounding.py",
        old="        return bool(act_entities & set(fact.entity_ids))",
        new="        return True",
        why="Untyped silence still supports maintenance (ADR 0014); sharing an entity is extra.",
        breaks="A silent unrelated poller belongs to a rogue write it has no path to. The "
        "command_grounding tests that pin ADR 0038 go red.",
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
    """Run the P3 suite against ``source_root`` and report whether it passed.

    Args:
        source_root: The ``src`` directory to import ``phos`` from. Overrides the ini setting, so a
            mutant shadows the working tree rather than competing with it.

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
            return False, line.split(" ")[0] + " " + line.split("::")[-1].split(" ")[0]
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
            print(f"{mutation.name:<40} {mutation.module}")
        return 0

    selected = MUTATIONS
    if arguments.name:
        selected = tuple(m for m in MUTATIONS if m.name == arguments.name)
        if not selected:
            print(f"no mutation named {arguments.name!r}; try --list")
            return 2

    print("Baseline: the suite must be green before any mutation means anything.")
    passed, detail = run_suite(SOURCE_ROOT)
    if not passed:
        print(f"  the unmutated suite is already failing ({detail}); fix that first")
        return 2
    print("  green\n")

    print(f"Injecting {len(selected)} deliberate defect(s):")
    caught = sum(check(mutation) for mutation in selected)
    print(f"\n{caught}/{len(selected)} caught.")
    if caught != len(selected):
        print(
            "A missed mutation is not a failure of this script. It is the suite telling you which "
            "behaviour nothing actually checks — write the aimed test, then run this again."
        )
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())
