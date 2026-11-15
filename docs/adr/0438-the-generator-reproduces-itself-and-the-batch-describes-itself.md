# ADR 0438 — The generator reproduces itself, and the batch describes itself

- **Status:** Accepted
- **Date:** 2026-11-14
- **PART:** R5
- **Supersedes:** nothing
- **Depends on:** [0437](0437-events-happen-to-a-plant-on-four-layers-and-the-record-names-the-layer.md), [0436](0436-a-drawn-plant-is-refused-before-it-is-written.md), [0435](0435-a-family-draws-a-plant-and-one-family-is-sealed.md), [0434](0434-a-plant-is-a-document-and-its-physics-is-a-named-template.md), [0433](0433-physics-constrained-plant-randomisation-for-training-data.md), [0092](0092-real-corpus-tests-are-marked-slow.md)

## Context

PARTS R1–R4 built the generator: a plant is a document (R1), a seed draws one from a family (R2),
an invalid draw is refused before it is written (R3), and things happen to it on four labelled
layers (R4). PART R5 is the part that does not add a capability. It asks seven things, and six of
them are audits of what already exists: does the whole thing run end to end, does the same seed
really give the same bytes, does the telemetry still load through Atlas, what is actually in a
batch, how long does a day cost, and is the suite green with every skipped test accounted for.

The one thing it asks for that is not an audit is the seventh: "update ADR 0433 with anything that
changed during the build". That instruction cannot be followed as written, and Decision 3 below is
why.

## Decision 1 — The reproducibility audit runs in fresh processes, and asserts the converse too

`scripts/audit_reproducibility.py` generates a plant twice and compares the SHA-256 of every file.
Two decisions inside that are load-bearing.

**Separate processes, not two calls in one interpreter.** Two generations in one process share an
import-time cache, a module-level dictionary and anything else somebody forgot to reseed, so they
can agree for reasons that have nothing to do with determinism. Each generation here is its own
`python scripts/generate_plants.py` run, and the only thing the two share is the seed. That is also
why this is a script and not only a test: PART S6's exam will reproduce a plant from a seed months
after it was drawn, possibly on another machine, and this is the command that checks that machine.

**And the converse, which is the half that is easy to leave as decoration.** A generator that
returned the same bytes for every seed would pass a reproducibility check perfectly. So the audit
also generates seed + 1 and insists the plant is *structurally* different — a different signal
count, different parameters, a different first tag — read from `plant.json`, the plant's own
description, rather than from the digests. Digests would move on noise alone while the plant stayed
identical, which is exactly the failure this half is looking for. Determinism without variety is a
stored fixture wearing a generator's command line.

That claim is itself tested by pointing the audit at stub generators that fail on purpose: one that
ignores its seed, one that writes something different every run, one that crashes, and one that
writes nothing at all. Each is reported as the specific thing it is, and a crashed generator is an
`AuditError` rather than a reproducibility finding — confusing the two would send a reader looking
for a stray random stream when the message was on stderr.

## Decision 2 — The batch summary describes the data and has nowhere to put a score

`scripts/summarise_plants.py` reads a directory of generated runs and prints counts per family,
each structural parameter's range, the validity gate's refusal rate as draws per plant, event counts
by kind and by layer, the two measured facts tallied, and what fraction of a run each kind of event
covers. It reads the manifests and the label files only, and opens no payload.

**There is nowhere in it to put a detection, a recall, a false-alarm rate or a verdict, and that is
deliberate rather than unfinished.** A summary that could also grade something would be read as a
grade; PART S6's referee is the only thing in this programme entitled to produce one. The field sets
of `PlantRecord` and `Summary` are pinned by a test, so adding an `alerts` column has to be argued
for here rather than slipped in. The assertion is structural on purpose: a test searching the
printed text for "recall" would also fire on the caption explaining that nothing is scored.

Two smaller honesty points are in the printed output rather than only in this record. The fractions
by kind **are not a partition** — a maintenance window and an attack window may overlap, so they can
sum past one, and the caption says so, because a reader who assumed a partition would read two 60%
figures as an arithmetic error. And the denominator is "the stretch events were placed over" rather
than the run, because the labels file carries windows and not the run's length; the caption uses
those words.

## Decision 3 — ADR 0433 is left as written, and this record carries what changed

R5 asks for ADR 0433 to be updated. `docs/sim/recon.md` §2 and `docs/adr/README.md` both say a
record is immutable once accepted and a changed decision gets a new one. The repository wins, for
the reason the convention exists: editing an accepted record makes a decision read as though it had
always been made that way, which is the one thing the record is there to prevent. The conflict is
now a row in recon.md §6 beside the four S0 already recorded, and what changed is here.

**Three modules became ten.** ADR 0433 Decision 3 named `families.py`, `randomise.py` and
`validity.py`. The built generator is those three plus `plant_spec.py`, `templates.py`,
`plants/spec_build.py`, `families_sealed/`, `events.py` and `wire.py`, five family modules and five
family specifications. None of the additions contradicts 0433; the shape of the work was further
from a parameter sampler and closer to a document pipeline than the sketch assumed.

**The draw no longer acts on a `PlantDescription`.** 0433 Decision 1 says the draw acts on the
description and is finished before the first step is integrated. The second clause holds exactly.
The first does not: ADR 0434 introduced `PlantSpec`, a separate frozen document naming a registered
process template, which is rendered into a `PlantDescription`. A draw that edited a
`PlantDescription` directly could produce a description no template could implement, and the
validator would have nothing to refuse it against.

**Child streams are named, not indexed.** 0433 Decision 3 says streams are "spawned into named
child streams by index". ADR 0435 spawns on a `blake2b` hash of the stream's *name*
(`randomise.stream_key`), because indexing has the property 0433 was trying to avoid: inserting a
stream shifts every later one. `blake2b` rather than `hash`, which is salted per process and would
make a corpus irreproducible across runs — the failure Decision 1 of this record exists to catch.

**A family can be sealed.** ADR 0435 holds `gas_pressure` out of the registry, the listing and the
published bounds table. 0433 did not contemplate it.

**A refusal rate is a number now, not a principle.** 0433 Decision 2 says a high refusal rate is a
finding about the family. It was: running the gate exposed five sizing defects across R2's families,
and the fix was to put bounds on ratios and derive the absolute figures. Measured over fifteen
plants the gate now costs between 1.33 and 3.00 draws per plant depending on the family.

**The standing caveat and the prohibitions are unchanged**, which is the part of 0433 that most
needed not to drift. `MODEL_NOT_REALITY_CAVEAT` is on every manifest, nothing generated is
committed, no dependency was added, and nothing here is real plant data (ADR 0143).

## Decision 4 — The cost of a day is recorded as a measurement, not an estimate

R5 asks how long a 24-hour run takes per family on this machine. Measured on an Apple M4, Python
3.12.11, Darwin arm64:

| Family | Samples in 24 h | Scan period | Normal run | With one of every event |
|---|---|---|---|---|
| `thermal` | 815 | 106 s | 0.1 s | 0.2 s |
| `level_flow` | 1,200 | 72 s | 0.2 s | 0.4 s |
| `batch_mix` | 1,489 | 58 s | 0.2 s | 0.3 s |
| `power` | 14,400 | 6 s | 1.8 s | 2.6 s |
| `hybrid` | 12,342 | 7 s | 3.3 s | 5.5 s |

The spread is the **drawn scan period**, not the physics: a family's controller sample rate is a
drawn parameter, and an islanded generating set is polled seventeen times as often as a heated
vessel because that is what those plants do. The figures exclude the validity gate, which runs each
candidate for six hours by default and is the larger part of a generation. A day of a plant costs
seconds, so a batch of hundreds is practical and the reason not to commit one is the repository's
reproducibility claim rather than the clock.

## Decision 5 — The skipped tests are enumerated, not counted

R5's final audit asks for any skipped test to be listed with its reason. The default suite is
**6,526 passed, 27 skipped, 45 deselected**. Every one of the 72 is pre-existing; R1–R5 add no skip
and no `slow` marker.

The **45 deselected** are the `slow` marker: real-corpus runs of five seconds or more that need a
downloaded payload on disk. `addopts` carries `-m "not slow"` and ADR 0092 is the decision. They
are deselected rather than skipped, so a run with `-m slow` collects exactly those 45.

The **27 skipped** are four groups, and 23 of them are one reason:

- **The payload is not on this machine (22).** HAI 20.07 (4), CERT r3.1 and its answers archive
  (11), and one each for prepared BATADAL/HAI, hai-21.03, later HAI releases, daypsci-v1, the
  batch-distillation ZIP, data4cyber, and the S7 process parquet. Every one names the
  `scripts/fetch_datasets.py` command that would make it run. These are the right shape: a corpus
  this repository must not commit cannot be a hard test dependency, and a test that silently passed
  without its payload would be worse than one that says it did not run.
- **The external checkout is not present (1).** `tests/scripts/test_grfics_capture.py` hashes the
  GRFICS licence, which lives outside the repository by ADR 0144.
- **An optional tool is absent (1).** The public chart plates embed Inter, which needs `fonttools`.
- **A parametrised case that does not apply (3).** Three S7comm adversarial frames do not carry a
  length indicator, so the assertion about length indicators has nothing to make.

No `lab_only` test skipped in this run, which is correct: this is the lab, so the records those
tests read are present and they ran. They skip only in the public export.

Nothing from R1–R5 is among the 72. `tests/synth/test_golden_corpora.py`,
`tests/synth/test_audit_reproducibility.py` and the generator's end-to-end tests all run in the
default suite, because a safeguard the default suite deselects is a safeguard nobody runs.

## Consequences

**The simulator is finished as specified and can be driven by someone who did not build it.**
`docs/sim/README.md` carries every command, what each output file is, what the gate refuses and why,
the four layers, the timing table above, and a section on **what is not modelled** — one protocol,
no multi-site, no dynamics faster than the sample interval, lumped physics, controller tunings that
never change, and the standing point that these are models of plants.

**What PART S6 inherits.** A command that produces a labelled corpus from a family and a seed; a
manifest that regenerates it; an audit that proves the regeneration on any machine; and a summary
that says what a batch contains without grading it. The referee can therefore be written against a
corpus it did not generate and can regenerate one it was given a seed for.

**Two things stay known-open, both recorded before this.** The cross-parameter consistency check
ADR 0436 left open is still open: the gate catches a governor holding the wrong frequency through its
consequences, not two parameters that disagree about what the frequency is. Control-logic parameter
tampering and the operator self-corrected error stay deferred with ADR 0437's reasons, in
`docs/sim/coverage.md` as deferred rather than dropped.

**No measurement.** This record adds two audit scripts, their tests, a conflict row and a document
section. It opens no committed corpus, runs no harness, scores no detector, moves no frozen number,
and does not touch `.phos_roadmap_state.json` — `current_session` stays **P1**, the blocked human
conversation, with Intelligence, the API and the UI behind it. v1 stays **8 of 12**. The three public
surfaces have not moved because this branch is unmerged, which ADR 0044 exempts until it lands.
