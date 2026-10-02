# ADR 0014 — Command evidence: the second boundary door, what commands discriminate, and the measurement PHOS cannot yet run

- **Status:** Accepted
- **Date:** 2026-08-14
- **PART:** P3 — Atlas packet adapter: integration and the measurement seam
- **Superseded in part by:** [ADR 0038](0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md),
  Decision 2's claim that there was nothing declared to group command evidence by. Co-movement
  remains refused. Per-feature inflation and interleave-by-time stand.
- **Builds on:** [ADR 0013](0013-command-behaviour-features-device-identity-and-the-command-graph.md)
  (the command features and the device-command graph this PART consumes),
  [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md) (the boundary a second door
  is added to), [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md)
  (the belief arithmetic the discrimination is computed in), and
  [ADR 0011](0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md) (the OT
  templates and the two limits it recorded, both of which move here).
- **Modifies outside the new modules:** `src/phos/reasoning/boundary.py` (a sibling promoter),
  `src/phos/reasoning/calibration.py` (one shared guard, extracted from a duplicate),
  `src/phos/atlas/templates.py` (a scope guard and two matcher changes),
  `src/phos/atlas/engine.py` (an optional second inlet, and a delegation),
  `src/phos/atlas/stability.py` (two stubs retired), plus re-export lines. No P1 or P2 module was
  edited.

## Context

P2 ended with Atlas able to describe command behaviour and to measure how the command graph had
changed, and with nothing consuming either. No engine read them, no explanation reasoned about
them, and the two `phos.atlas.stability` stubs that had named "a packet adapter" as their missing
prerequisite were still raising even though the prerequisite now existed.

P3 closes that loop. It also has to be honest about what closing it does and does not establish,
because the temptation here is specific and large. Atlas's headline claim about the packet adapter
is that **reading commands separates a legitimate operator action from an attacker's identical
one**. A working pipeline plus a hand-built fixture can be made to produce a recall figure in an
afternoon, and that figure would be a measurement of the author's own choices. The claim needs a
capture containing such an attack, labelled, and no such corpus exists in this project.

So this PART builds the loop, proves the mechanism, and stops at the data — and Decision 8 is about
making that stop structural rather than a note in a docstring.

## Decision 1 — A second door in the evidence boundary, not a bypass and not a reuse

**Decided:** `phos.reasoning.boundary` gains `evidence_from_relationship_change`, a sibling of
`evidence_from_deviation` producing `EvidenceKind.RELATIONSHIP_CHANGE`.

The obvious alternative — route the graph's findings through `evidence_from_deviation` — is
impossible without lying. That function requires a `Deviation`, a `Deviation` carries the
`ExpectedRange` it was judged against, and **a relationship that has never existed has no learned
band**. Manufacturing one so the existing door would accept it is exactly the fabrication the door
exists to prevent: the stored evidence would name a baseline nobody learned.

The other alternative — build the `Evidence` directly in Atlas — was rejected because the boundary's
value is that it is the *only* route in. Two routes means two places to enforce Constitution §3.3,
and one of them will eventually stop.

So: same module, same two refusals, one more kind.

| | `evidence_from_deviation` | `evidence_from_relationship_change` |
| --- | --- | --- |
| Input | an out-of-band `Deviation` + its `Observation` | a finding `Observation` |
| Refuses a non-event | value inside `[low, high]` | a measured change of `<= 0` |
| Refuses an uncalibrated weight | yes | yes |
| Third refusal | the deviation must describe *this* observation | the finding must name at least two entities |
| Produces | `DEVIATION` | `RELATIONSHIP_CHANGE` |

The zero-change refusal is the direct analogue of the in-band one, and it rests on the same
argument. `compare_to_graph` defines every finding so that a larger value means a larger departure,
so a value of zero *is* "nothing differed", and a hypothesis resting on it would look perfectly
well-supported while standing on a non-event.

The two-entity refusal is new and is about routing. A relationship holds *between* things, and a
one-entity observation is a reading. Without the check, a `command_count` observation shoved through
the wrong door would become structural evidence and would support the malicious explanation on the
strength of nothing structural at all. The mutation `one-entity-is-a-relationship` is that defect.

**`source_id` is the finding's own `Observation.id`.** The finding is an ordinary measurement whose
`context` names the frames, so evidence → finding → frames → capture is the same length of chain a
deviation gives, and `AtlasEngine` stores the finding so the first hop resolves.

## Decision 2 — Command evidence is not grouped, and the omission is the honest option

**Decided (P3):** `CommandEvidence` goes into the reasoning engine ungrouped, interleaved with the
subsystem events by time.

**Superseded in part (ADR 0038):** the clause below that there was *nothing declared to group by*
no longer holds for attachment. Graph findings now attach to a window's story by entity-reachability
from in-window command activity (unknown master or unexpected function), or as the unknown-master
finding itself. Co-movement remains refused. Several features of one act remain several facts.

5C's rule is *group before reason*, because reasoning over per-signal evidence counts one plant
event once per instrument. The same inflation exists here: a device whose commanding changes in
several ways at once produces one piece of evidence per feature. So why not group?

Because there is nothing declared to group by. `SubsystemMap` partitions a **plant's signals** into
physical units, sourced from process documentation. It says nothing about devices on a network, and
a HAI signal name and a `ent_10.0.0.9` share no vocabulary. The available alternatives were:

- **Group by device.** Plausible, and it collapses the per-feature inflation. Rejected as scope this
  PART was not asked for, and because it needs a decision about what a "device event" means that is
  better made with a real capture in hand.
- **Derive a grouping from co-movement.** Rejected outright — it is precisely the circularity
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md) refuses.

The inflation that remains is recorded as `UNGROUPED_COMMAND_EVIDENCE_CAVEAT`, and Decision 4 is
what stops it mattering yet: command-behaviour evidence is given no matcher, so it cannot accumulate
on an explanation at all.

**Recording a bundle is idempotent, and only the command path needs it to be.** `_promote` mints
fresh `Evidence` on every run, so re-running one corpus against one store can never collide. A
`CommandEvidence` bundle is built once by the caller and keeps the identity it was built with, so
without a duplicate check a store could accumulate one run and no more — and scoring a long capture
in overlapping slices, which is the obvious way to use one, would abort partway through with half
its evidence already written. This surfaced from a coverage gap rather than from a test: the
partial branches on `_record`'s guards were the store refusal nobody had exercised.

**The interleave is load-bearing and was nearly lost.** `ReasoningEngine` spawns a fresh hypothesis
when evidence arrives outside the correlation window of the last, so a structural change appended
after a run of readings is weighed as though it happened at the end and the story it belonged to no
longer holds it. Concatenating two already-sorted lists looks harmless and the whole suite stayed
green for it; see the mutation table.

## Decision 3 — Breadth is a claim about a plant unit, and the pattern now says so

**Decided:** `SubsystemBreadthPattern` gains `subsystem_events_only: bool = True`, tested with the
declared marker `phos.atlas.grouping.is_subsystem_event`.

This is a correctness fix that P3 *exposed* rather than caused. Before the packet adapter, every
`DEVIATION` the Atlas engine reasoned over was a grouped subsystem event, so "how many entities does
this fact name" and "how much of one unit departed" were the same question and the guard was
implicit and free.

Command-behaviour evidence breaks that. It is an ordinary `DEVIATION` naming one device —
deliberately, because Constitution §3.1 forbids a second evidence format — and it names one entity
*because a device is one device*, not because a single instrument on a pump failed. Read as breadth
it matches `_LOCALISED`, which means it would **argue against `unauthorised_control_activity`**: the
exact inversion reading the command stream exists to prevent. An attacker operates from one device.

Making the guard explicit turns an invariant that used to hold by accident into one that is checked,
which is the same move `AtlasEngine._require_fresh_measurement` makes for carried-forward cells. It
also keeps `overlaps` exact, so `HypothesisTemplate` can still refuse an ambiguous template at
construction: two banded patterns scoped to different evidence can never both match, because no fact
both carries the marker and lacks it.

## Decision 4 — Exactly what command evidence discriminates, and what it still cannot

The PART asks for this list explicitly, so it is a table rather than prose.

**What is now possible and was not:**

| Discrimination | How | Why it is a real claim |
| --- | --- | --- |
| `unauthorised_control_activity` vs `process_disturbance` | a `RELATIONSHIP_CHANGE` supports the first and contradicts the second | A real process upset moves readings. It does not make a workstation begin commanding a PLC, silence a link that always polled, or put an unfamiliar function code on the wire. The asymmetry is physical, not tuned. |
| `engineering_maintenance` gets its first real matcher | `_STRUCTURE_CHANGED` | 5C recorded that this template had no matcher worth the name and that only a change in the environment's *structure* would argue for a planned change. The command graph is that evidence. |

**What remains impossible, with commands:**

| Not possible | Why | Where it is asserted |
| --- | --- | --- |
| Maintenance vs an attacker | A commissioning engineer and an intruder leave behind the *same* new relationship. Both templates are supported by it; only the priors separate them. | `test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence` |
| Which *command feature* departed | `Evidence` names a kind and some entities and never a feature. No pattern in 4B's language can ask whether it was a write share, a polling rhythm or a register span. | `test_a_command_behaviour_departure_bears_on_no_ot_explanation` |
| Which of the three structural changes it was | Same reason: all three are `RELATIONSHIP_CHANGE`. A link going silent therefore argues for unauthorised control exactly as a brand-new link does, which is weaker than a human analyst would be. | recorded here; see "Consequences" |
| Anything about a *sensor* departure | Unchanged. Command evidence adds a stream; it does not re-interpret the old one. | `test_sensor_breadth_alone_still_cannot_separate_them` |

**A command-behaviour deviation therefore bears on no OT explanation at all.** It is still promoted,
stored and narrated — an operator looking at a story must see the device's commanding beside the
structural change — but it accumulates on nothing. Giving it a matcher that supported every
explanation equally would change no ordering and cost code; giving it one that supported some would
be a claim the pattern language cannot justify.

## Decision 5 — The stability stubs are retired, not implemented

**Decided:** `communication_timing_stability` and `protocol_state_stability` are removed.

Both raised `NotImplementedError` naming "a packet adapter" as the missing prerequisite. P2 supplied
it, so P3 had to decide. The PART allowed either outcome and asked for the reasoning.

The signal each stub stood for already exists, and exists **better**:

| Retired stub | Where the signal lives now |
| --- | --- |
| `communication_timing_stability` | `COMMAND_INTERVAL_MEAN_MS` and `COMMAND_INTERVAL_CV`, per device per window |
| `protocol_state_stability` | the per-function-code counts, and the graph's `UNEXPECTED_COMMAND_FUNCTION` — literally *"a function code never seen from that master"*, which is the example the stub's own docstring gave |

"Better" is a specific claim, not a preference. Each of those is an `Observation`, so it is baselined
by PART 3's models, judged against a learned `ExpectedRange`, promoted through the evidence boundary,
weighted by a fitted calibrator, and measured by the PART 2 harness. A bare float returned from
`stability` would have had **none** of that: no baseline, no band, no calibration, no provenance, and
nothing for Constitution §3.5 to say whether it was worth anything. Implementing the stubs would have
meant building a second, weaker path to a signal the adapter already carries properly.

Retirement is recorded in the module docstring rather than by deletion alone, so a reader looking for
"communication timing stability" finds where it went. Two tests hold that: one asserts the stubs are
gone, the other that the replacements are reachable — a retirement pointing nowhere is a deletion.

## Decision 6 — Two command detectors, not one

**Decided:** `CommandBehaviourDetector` and `CommandGraphDetector` are separate `Detector`s.

A measurement decision, not a stylistic one. `Detection.score` is what `EvalConfig.alert_threshold`
thresholds and what `sweep_thresholds` sweeps. A behaviour score is a magnitude in learned spreads;
a graph score is a count of commands. One threshold across both is one threshold across two unit
systems, and it means nothing at either end. Two detectors gives two rows, the way
`scripts/evaluate_atlas_vertical.py` gives a before row and an after row.

Both are thin adapters over `promote_command_behaviour` / `promote_graph_findings`, so the alerts the
harness scores are the *same* facts the reasoning engine receives — not a second scoring path that
could drift from it.

## Decision 7 — One calibrator across three differently-united graph findings

**Decided, reluctantly:** `promote_graph_findings` takes a single `FittedCalibrator`.

The three findings' values are a count of commands on an unknown link, a count of commands using an
unfamiliar function, and an *expected command volume* for a link that fell silent. A single monotone
score-to-probability map says the same thing about a score of 5 whichever feature produced it, and
that is very likely wrong.

A per-feature calibrator is the fix and was rejected only because **it cannot be fitted today**:
fitting three maps needs three labelled score sets, and the labelled corpus this whole path waits on
does not exist. Adding the API now would be an abstraction the PART did not ask for, serving a
capability nothing can exercise. The limit is recorded as `POOLED_GRAPH_CALIBRATION_CAVEAT` and
travels with every number the path produces.

## Decision 8 — The measurement seam is built and the refusal is structural

**Decided:** every piece of the command-detection measurement exists and is tested; the script that
would run it consults `discover_labelled_command_corpora`, finds nothing, and prints
`LABELLED_COMMAND_CORPUS_REQUIREMENTS` instead of a number.

The refusal is deliberately not a comment or a `TODO`. It is two guards, each with its own test:

1. **`require_labelled_intervals`** — a corpus with no ground truth cannot be scored. Every metric
   `evaluate` computes is defined against attack windows, and with none it answers "how often was
   the detector right about nothing".
2. **`discover_labelled_command_corpora`** — a `.pcap` on disk is not a corpus. A capture corpus
   whose manifest declares no attack windows, *or declares an empty list*, is skipped with a
   warning. The second spelling is there because the mutation run found that only the first was
   tested.

`test_this_repository_holds_no_labelled_command_corpus` asserts the fact P3 stops at. When a labelled
capture is added, that test fails — which is the correct way to be told the measurement can finally
be run.

**What the synthetic fixture establishes.** `--self-test` builds a capture of ordinary Modbus polling
with a rogue write injected from a device that has never commanded anything, and the seam carries it
end to end. That is a statement about plumbing: the signal was placed by the author, at a moment the
author chose, with a magnitude the author chose, and a pipeline that lost it would be broken rather
than merely insensitive. It says nothing about recall on real intrusions, nothing about the
false-positive rate on a real plant's ordinary day, and nothing about whether a calibrated confidence
from this path means what it says. The script prints that in a banner before it prints anything else.

## Decision 9 — One shared calibrator-output guard

**Decided:** `calibrated_probabilities` moves into `phos.reasoning.calibration`, and
`AtlasEngine._calibrated` is deleted in favour of it.

`FittedCalibrator` is a structural `Protocol`: it guarantees a `calibrate` method exists, not that
the method returns probabilities. Three call sites had grown the same range check. Extracting it is
a de-duplication rather than a new abstraction, and it is what let the command path reuse the
existing evidence-construction route instead of growing a fourth copy.
`CalibratedModelDetector` keeps its own copy, deliberately: it is PART 4 code this PART has no
mandate to touch, and changing it would put an untested edit under every calibration result already
in the experiment log.

## Ambiguities in the PART, and how they were resolved

| Ambiguity | Resolution |
| --- | --- |
| "indistinguishable in kind from sensor evidence" — how literally? | As the same type, kind, weight semantics and traceability; **not** as "matched by the same patterns". Decision 3 is the consequence. |
| "Extend the existing OT template set" — a sixth template? | No. Two existing matchers changed. `atlas_templates` still ships five and still has no mechanism for inventing a sixth (Constitution §3.6). |
| Where does the graph-finding score come from? | The finding's own value, which `compare_to_graph` already defines so that larger means a larger departure. |
| Should command evidence be grouped? | No — Decision 2. |
| Should the stubs be implemented or retired? | Retired — Decision 5. |
| What does "refuse to emit a headline number" mean concretely? | Exit non-zero, print the requirements, compute no metric. Two guards, both tested — Decision 8. |
| One detector or two? | Two — Decision 6. |

## Mutation testing — which injected defects the suite caught

`scripts/mutate_command_integration.py` copies `src/` to a temporary tree, injects one defect,
and runs the P3 suite against the mutant. A mutation counts as *caught* when the suite turns red.
Every mutation below is a defect a careful engineer could plausibly write, and — this is the
selection criterion — almost none of them raise. A mispaired weight is still a probability. Evidence
stamped a window late still stores, sorts and reasons.

**18 injected, 16 caught on the first run.** The two misses are the point of doing this at all.

| Mutation | Module | Caught by |
| --- | --- | --- |
| `graph-weights-mispaired` | `command_evidence` | `test_each_graph_finding_keeps_the_weight_computed_from_its_own_value` |
| `behaviour-weights-mispaired` | `command_evidence` | `test_each_command_departure_keeps_the_weight_computed_from_its_own_magnitude` |
| `zero-change-becomes-evidence` | `boundary` | `test_relationship_change_evidence_refuses_a_non_event` |
| `one-entity-is-a-relationship` | `boundary` | `test_relationship_change_evidence_refuses_another_engines_kind_of_measurement` |
| `calibrator-output-clipped-not-refused` | `calibration` | `test_calibrated_probabilities_refuses_a_value_that_is_not_a_probability` |
| `breadth-guard-dropped` | `templates` | `test_a_command_behaviour_departure_bears_on_no_ot_explanation` |
| `breadth-guard-inverted` | `templates` | `test_a_localised_event_argues_for_a_faulty_device_and_against_an_upset` |
| `scoped-patterns-overlap` | `templates` | `test_patterns_scoped_to_different_evidence_can_never_both_match` |
| `structural-change-supports-the-upset` | `templates` | `test_the_malicious_and_the_benign_upset_differ_only_where_commands_reach` |
| `structural-change-stops-supporting-the-attack` | `templates` | `test_the_malicious_and_the_benign_upset_differ_only_where_commands_reach` |
| **`commands-weighed-last`** | `engine` | **MISSED at first** — see below |
| `stream-grouped-by-kind` | `command_evidence` | `test_the_two_streams_are_interleaved_by_time_and_not_by_stream` |
| `finding-not-stored` | `engine` | `test_every_source_id_the_vertical_emits_resolves_inside_its_own_store` |
| `streams-crossed-silently` | `command_evidence` | `test_promoting_command_behaviour_refuses_a_graph_finding` |
| `unlabelled-corpus-scored` | `command_eval` | `test_an_unlabelled_corpus_cannot_produce_a_metric` |
| **`discovery-ignores-ground-truth`** | `command_eval` | **MISSED at first** — see below |
| `graph-score-is-a-flag` | `command_eval` | `test_the_graph_detector_scores_only_graph_findings` |
| `adapter-invents-a-comparison` | `command_eval` | `test_a_capture_becomes_a_labelled_dataset_the_harness_can_read` |

### The two misses, and the tests written for them

**`commands-weighed-last`** replaced the engine's timestamp-ordered merge with a plain concatenation
— cheaper, and both inputs are already sorted. Nothing caught it: the run completes, every fact is
stored, every link resolves, and a single accumulating hypothesis's confidence is order-independent
anyway. What it breaks is *which* hypothesis accumulates, because `ReasoningEngine` starts a fresh
one when evidence arrives outside the correlation window of the last. A structural change appended
after ten minutes of readings is weighed as though it happened at the end, and the incident it
belonged to no longer contains it.
`test_a_structural_change_is_weighed_with_the_readings_it_happened_among` makes it observable: two
surges ten minutes apart, a structural change stamped with the first, and an assertion that the
change and the first surge's event land on one hypothesis.

**`discovery-ignores-ground-truth`** weakened the label check from `not manifest.get(...)` to
`... is None`. The existing test built a manifest with no `attack_intervals` key at all, which both
spellings reject — so the test passed under the mutant. The shape that slips through is
`"attack_intervals": []`, which is exactly what a half-finished corpus looks like, and under it the
script stops refusing and prints a headline number with no ground truth behind it. That is the
single outcome this PART exists to prevent. The test is now parameterised over both spellings.

Both were re-run after the aimed tests were written: **18/18 caught.**

## Consequences

**Good.**

- Command evidence and sensor evidence are one stream to everything downstream. The store, the
  narratives, the belief arithmetic and eventually the API acquired no second case to handle.
- The two limits [ADR 0011](0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md)
  recorded both moved, in the direction it predicted, and the tests that recorded them were updated
  to state what survives rather than deleted.
- The measurement is *ready*. When a labelled capture appears, running it is a manifest and a
  command, not a project.

**Costs and limits, carried deliberately.**

- **No command-level detection result exists.** This PART ships a pipeline, not a number.
  `UNMEASURED_COMMAND_DETECTION_CAVEAT` says so and travels with every output.
- **The three structural changes are one evidence kind.** A link going silent argues for
  unauthorised control exactly as a brand-new link does. A human analyst would treat those very
  differently, and expressing that needs either a richer pattern language or a marker on the
  evidence — both of which are decisions better made once there is data to justify one.
- **A hypothesis confidence is still not calibrated** and still may not be surfaced (§3.3). Nothing
  in P3 changes that; the evidence *weights* are calibrated, the confidences built from them are not.
- **Command evidence is not collapsed**, so a device whose commanding changes in several ways
  contributes several pieces of evidence for what may be one act.
- **A `CommandCaptureAdapter` consumes its captures whole**, inheriting P2's non-incremental
  featuriser. A very large capture is held in memory.
