#!/usr/bin/env python3
"""Inject deliberate defects into P2's command-behaviour code and check the tests catch them.

This is the reproducible proof behind PART P2's claim that its test suite has teeth. P1 learned the
lesson the expensive way: after `modbus.py`'s fuzz suite went green, eight bugs were injected one at
a time to see whether the suite could actually detect them. Seven were caught, one was not, and
chasing the miss exposed a real defect nobody had noticed. **A green suite you have not tried to
fool is not evidence.**

So each mutation below is a defect a careful engineer could plausibly write — an off-by-one at a
window edge, a denominator taken from the wrong stream, a set membership tested against the graph
instead of against one edge — and each is chosen so the wrong behaviour is a *different number*
rather than an exception. A defect that crashes gets found on the first run; these are the ones
that would not.

**Nothing is mutated in place.** `src/` is copied to a temporary directory, the copy is edited, and
pytest is pointed at it with ``-o pythonpath=...`` so the mutant shadows the real package. The
working tree is never touched, so an interrupted run cannot leave a defect behind.

Usage::

    python scripts/mutate_command_behaviour.py
    python scripts/mutate_command_behaviour.py --list
    python scripts/mutate_command_behaviour.py window-tail-kept
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
    "tests/atlas/packet/test_commands.py",
    "tests/atlas/packet/test_behaviour.py",
    "tests/atlas/packet/test_graph.py",
    "tests/atlas/packet/test_command_adversarial.py",
)
"""The suite under examination. A mutation is *caught* when running these turns red.

``tests/atlas/packet/test_graph.py`` is the suite that catches an ADR 0037 undo (smeared rate
emitting a silence finding every quiet live minute).
"""

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
        name="window-tail-kept",
        module="phos/atlas/packet/commands.py",
        old="    count = int((end - start) / duration)",
        new="    count = int((end - start) / duration) + 1",
        why="Why throw away the last few seconds of a capture? Keep the partial window.",
        breaks="The final window is short, so every device's command volume reads low there — "
        "indistinguishable from a device going quiet, and baked into any baseline learned from it.",
    ),
    Mutation(
        name="undirected-treated-as-command",
        module="phos/atlas/packet/commands.py",
        old="    if result.direction is Direction.UNKNOWN:\n"
        "        stats.undirected += 1\n"
        "        return None\n",
        new="",
        why="Be permissive: if the transport could not settle direction, assume the sender acted.",
        breaks="A command is attributed to whichever end happened to send the bytes, so an "
        "arbitrary end of every ambiguous conversation acquires behaviour it never had.",
    ),
    Mutation(
        name="identity-truncated",
        module="phos/atlas/packet/commands.py",
        old='    return f"{ENTITY_PREFIX}_{ip}"',
        new='    return f"{ENTITY_PREFIX}_{ip[:8]}"',
        why="Keep entity ids short and fixed-width, the way `new_id` does.",
        breaks="10.0.0.1 and 10.0.0.10 collapse into one entity, averaging two devices' behaviour "
        "into a baseline that describes neither.",
    ),
    Mutation(
        name="tail-functions-earn-zeros",
        module="phos/atlas/packet/behaviour.py",
        old="        index = window_index(event.timestamp, windows)\n"
        "        if index is None:\n"
        "            continue\n"
        "        grouped.setdefault((index, event.issuer), []).append(event)\n"
        "        functions_by_device.setdefault(event.issuer, set()).add(event.function_code)",
        new="        functions_by_device.setdefault(event.issuer, set()).add(event.function_code)\n"
        "        index = window_index(event.timestamp, windows)\n"
        "        if index is None:\n"
        "            continue\n"
        "        grouped.setdefault((index, event.issuer), []).append(event)",
        why="The device's function set is a property of the device, so build it from every "
        "command seen rather than only from the ones inside a window.",
        breaks="A function seen only in the dropped tail puts a measured zero into every earlier "
        "window, on the strength of traffic nothing ever measured.",
    ),
    Mutation(
        name="min-commands-off-by-one",
        module="phos/atlas/packet/behaviour.py",
        old="        if len(window_events) < policy.min_commands:",
        new="        if len(window_events) <= policy.min_commands:",
        why="A slip of the comparison while reading the floor as exclusive.",
        breaks="Every device sitting exactly on the floor is silently dropped, so the sparsest "
        "real devices vanish from the corpus without anything saying so.",
    ),
    Mutation(
        name="interval-floor-counts-commands",
        module="phos/atlas/packet/behaviour.py",
        old="    if len(intervals) >= policy.min_intervals:",
        new="    if len(events) >= policy.min_intervals:",
        why="Commands and intervals are nearly the same count; reuse the one already to hand.",
        breaks="Timing features are emitted one command early, so a rhythm is claimed from fewer "
        "gaps than the policy demands.",
    ),
    Mutation(
        name="cv-is-raw-spread",
        module="phos/atlas/packet/behaviour.py",
        old="            emit(COMMAND_INTERVAL_CV, math.sqrt(variance) / mean, events)",
        new="            emit(COMMAND_INTERVAL_CV, math.sqrt(variance), events)",
        why="Report the standard deviation directly — it is in milliseconds, which is readable.",
        breaks="Rigidity stops being scale-free, so a device polling every 10 s looks far more "
        "erratic than one polling every 100 ms with identical relative jitter.",
    ),
    Mutation(
        name="write-means-register-write",
        module="phos/atlas/packet/behaviour.py",
        old="    writes = [event for event in events if is_write(event.function_code)]",
        new="    writes = [event for event in events if is_register_write(event.function_code)]",
        why="Value features already use the register-write set; use one definition throughout.",
        breaks="Coil writes stop counting as writes, so a device that only actuates coils reports "
        "a write share of zero — the plant-changing traffic becomes invisible.",
    ),
    Mutation(
        name="write-provenance-widened",
        module="phos/atlas/packet/behaviour.py",
        old="        emit(WRITE_ADDRESS_MIN, float(min(addresses)), addressed)",
        new="        emit(WRITE_ADDRESS_MIN, float(min(addresses)), events)",
        why="All the window's frames are the context; pointing at the whole window is simpler.",
        breaks="A write feature cites frames it was not computed from, so the audit trail leads "
        "an investigator to reads that had nothing to do with the value.",
    ),
    Mutation(
        name="function-known-anywhere",
        module="phos/atlas/packet/graph.py",
        old="    learned = set(edge.function_codes)",
        new="    learned = {code for e in graph.edges for code in e.function_codes}",
        why="The graph knows which functions are used on this network; check against that.",
        breaks="An intruder's write is waved through because some legitimate station also writes "
        "— the finding disappears exactly when the network has a legitimate writer, which is "
        "every real network.",
    ),
    Mutation(
        name="silence-reported-once",
        module="phos/atlas/packet/graph.py",
        old="        observations.extend(_judge_silent(graph, window, active, expected))",
        new="        if window.index == 0:\n"
        "            observations.extend(_judge_silent(graph, window, active, expected))",
        why="A link that is down is down; reporting it every window is noise.",
        breaks="A link that dies part-way through a capture is never reported at all, which is "
        "the case the feature exists for.",
    ),
    Mutation(
        name="rate-from-window-not-span",
        module="phos/atlas/packet/graph.py",
        old="    learned_seconds = (graph.learned_span[1] - graph.learned_span[0]).total_seconds()",
        new="    learned_seconds = policy.window.total_seconds()",
        why="The expectation is per window, so measure the count against a window.",
        breaks="The expected volume is scaled by the wrong denominator, so a silent link reports "
        "a plausible-looking number that is wrong by the ratio of capture length to window.",
    ),
    Mutation(
        name="direction-collapsed-on-compare",
        module="phos/atlas/packet/graph.py",
        old="    edge = graph.edge(issuer, target)",
        new="    edge = graph.edge(issuer, target) or graph.edge(target, issuer)",
        why="These two devices are known to talk; the arrow is a detail of who asked first.",
        breaks="A PLC that starts commanding its engineering station is treated as a known "
        "relationship, which inverts the one fact that made it worth reporting.",
    ),
    Mutation(
        name="unknown-edge-is-a-flag",
        module="phos/atlas/packet/graph.py",
        old="                float(len(events)),\n"
        "                window,\n"
        "                pair,\n"
        "                events,\n"
        '                {"function_codes": ",".join(str(code) for code in codes)},',
        new="                1.0,\n"
        "                window,\n"
        "                pair,\n"
        "                events,\n"
        '                {"function_codes": ",".join(str(code) for code in codes)},',
        why="A relationship either is new or is not; the count adds nothing.",
        breaks="One probe and a sustained flood on a new link report the same value, so nothing "
        "downstream can order them by severity.",
    ),
    Mutation(
        name="span-from-the-ends",
        module="phos/atlas/packet/commands.py",
        old="    timestamps = [result.timestamp for result in results]\n"
        "    return (min(timestamps), max(timestamps))",
        new="    return (results[0].timestamp, results[-1].timestamp)",
        why="A capture is in capture order, so the first and last results bound it. Cheaper than "
        "scanning every timestamp.",
        breaks="A capture with any out-of-order record — merged captures, a clock step, a tool "
        "that writes late — gets a span that is too short or inverted, moving every window edge.",
    ),
    Mutation(
        name="window-index-rounds",
        module="phos/atlas/packet/commands.py",
        old="    index = int((moment - first.start) / duration)",
        new="    index = round((moment - first.start) / duration)",
        why="Rounding reads as the careful choice next to a bare int cast.",
        breaks="Everything in the second half of a window is filed under the next one, so counts "
        "split roughly evenly across two windows and no single number is obviously wrong.",
    ),
    Mutation(
        name="frame-bounds-overwritten",
        module="phos/atlas/packet/commands.py",
        old="        low, high = bounds.get(event.source.capture, (index, index))\n"
        "        bounds[event.source.capture] = (min(low, index), max(high, index))",
        new="        bounds[event.source.capture] = (index, index)",
        why="Frames arrive in order, so the last write holds the range.",
        breaks="Every provenance range collapses to its final frame, so the audit trail points at "
        "one packet out of thousands and looks perfectly well-formed doing it.",
    ),
    Mutation(
        name="observation-stamped-at-window-end",
        module="phos/atlas/packet/behaviour.py",
        old="                timestamp=window.start,\n"
        "                domain=Domain.ATLAS,\n"
        "                context=_context(window, evidence),",
        new="                timestamp=window.end,\n"
        "                domain=Domain.ATLAS,\n"
        "                context=_context(window, evidence),",
        why="The measurement is complete at the end of the window, so stamp it there.",
        breaks="Every feature is reported one window late, so command behaviour no longer lines "
        "up with the sensor telemetry it would be correlated against.",
    ),
    Mutation(
        name="sort-key-drops-the-feature",
        module="phos/atlas/packet/behaviour.py",
        old="    observations.sort(key=lambda o: (o.timestamp, o.entity_ids[0], o.feature))",
        new="    observations.sort(key=lambda o: (o.timestamp, o.entity_ids[0]))",
        why="Window and device are what a reader groups by; the feature order is incidental.",
        breaks="Output order becomes generation order within a device, so two runs agree but the "
        "result is no longer the sorted sequence anything downstream may rely on.",
    ),
    Mutation(
        name="share-provenance-narrowed",
        module="phos/atlas/packet/behaviour.py",
        old="    emit(WRITE_COMMAND_SHARE, len(writes) / len(events), events)",
        new="    emit(WRITE_COMMAND_SHARE, len(writes) / len(events), writes or events)",
        why="Match the other write features and cite the write frames.",
        breaks="A ratio cites only its numerator's frames, so the denominator cannot be "
        "recomputed from the stored evidence. This was the real defect mutation testing found.",
    ),
    Mutation(
        name="edge-window-minmax-swapped",
        module="phos/atlas/packet/graph.py",
        old="        self.first_seen = min(self.first_seen, event.timestamp)\n"
        "        self.last_seen = max(self.last_seen, event.timestamp)",
        new="        self.first_seen = max(self.first_seen, event.timestamp)\n"
        "        self.last_seen = min(self.last_seen, event.timestamp)",
        why="A copy-paste slip between two adjacent lines.",
        breaks="An edge reports the period it was seen over backwards, so anything reading the "
        "edge window to date a relationship dates it wrongly.",
    ),
    Mutation(
        name="edge-floor-off-by-one",
        module="phos/atlas/packet/graph.py",
        old="        if edge.command_count < policy.min_edge_commands",
        new="        if edge.command_count <= policy.min_edge_commands",
        why="A slip of the comparison while reading the floor as exclusive.",
        breaks="Links sitting exactly on the floor never earn an expectation, so their silence "
        "goes unreported without anything saying it was skipped.",
    ),
    # -- ranking-contract lock (session 4): undoing ADR 0037 --------------------------------
    Mutation(
        name="silence-smeared-rate-emits-every-quiet-minute",
        module="phos/atlas/packet/graph.py",
        old=(
            "        counts = _counts_for_horizon("
            "edge.horizon_counts, graph.horizon, policy.window)\n"
            "        if counts:\n"
            "            expected_count = sum(counts) / len(counts)\n"
            "            typical_count = float(median(counts))\n"
            "        else:\n"
            "            expected_count = edge.command_count / learned_seconds * window_seconds\n"
            "            typical_count = expected_count"
        ),
        new="        expected_count = edge.command_count / learned_seconds * window_seconds\n"
        "        typical_count = 1.0",
        why="The expectation is a rate: commands over the train, times the live window. A "
        "learned link that exists typically commanded, so a quiet minute is silence.",
        breaks="A five-day train with twelve commands per poller manufactures a silence finding "
        "every quiet live minute. Occupancy bins and the typical-stretch floor are bypassed. "
        "ADR 0037's duration match is gone.",
    ),
    Mutation(
        name="silence-floor-dropped",
        module="phos/atlas/packet/graph.py",
        old="        if horizon.typical < _TYPICAL_SILENCE_FLOOR:\n            continue\n",
        new="",
        why="If the link earned an expectation, a quiet window is silence, even when a "
        "comparable stretch was typically empty.",
        breaks="Median occupancy of zero still emits. A multi-day train floods every quiet "
        "minute again. The typical-stretch guard ADR 0037 added is gone.",
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
    """Run the P2 suite against ``source_root`` and report whether it passed.

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
            print(f"{mutation.name:<32} {mutation.module}")
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
