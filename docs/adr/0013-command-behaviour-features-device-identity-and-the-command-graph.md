# ADR 0013 — Command behaviour: what a device *is*, what a feature may claim, and the command graph

- **Status:** Accepted
- **Date:** 2026-08-14
- **PART:** P2 — Atlas packet adapter: command-behaviour features and the device-command graph
- **Builds on:** [ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md) (P1's
  message stream and its traceability contract), [ADR 0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md)
  (the per-key model path these features must fit through unchanged), and
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md) (declared-not-inferred,
  whose boundary Decision 7 argues the graph sits outside of).
- **Modifies outside the new modules:** `src/phos/atlas/packet/__init__.py` and
  `src/phos/atlas/__init__.py` — re-export lines, and docstring sentences that P2 made false (both
  said the behavioural layer did not exist). New fixtures were appended to
  `tests/atlas/packet/conftest.py`, which is where P1 deliberately put shared builders so no test
  module has to import a sibling. No behaviour of any existing module changed.

## Context

P1 gave Atlas the ability to read commands one message at a time, each traceable to its frame. That
is necessary and it settles nothing. *"Write 1 to coil 17"* is either a routine setpoint change or
the moment a pump was stopped, and **the bytes are identical**. Nothing in a single message
separates them.

What separates them is behaviour over time: how often this device commands, which functions it
uses, which registers it writes and with what values, how rigid its rhythm is, and which other
devices it normally talks to at all. P2 builds that layer. Its entire job is to turn a message
stream into quantities that PHOS's existing models can baseline — and to be *disciplined about what
a quantity is allowed to claim*, because every number here will eventually stand behind a sentence
an operator acts on.

## Decision 1 — A device is its network address, and the id says so out loud

**Decided:** `device_entity_id(ip)` returns `ent_<ip>` — `ent_10.0.0.9`, `ent_2001:db8::4`.

Three properties, each load-bearing:

1. **Deterministic** (Constitution §3.7). `Observation.entity_ids` needs an `EntityId`, and
   `new_id()` mints a fresh uuid per call, so keying features by a minted id would give a different
   answer on every run over one capture. The id has to be a *function* of the device.
2. **Readable, not opaque.** A hash would be equally deterministic and would destroy the audit
   path: a feature keyed to `ent_a3f81c` names nothing an engineer can check. `phos.models`
   already ships `FEATURE_LEVEL_ENTITY_ID = "ent_featurelevel"`, so a readable sentinel in the
   ontology's id shape is established practice rather than a new liberty.
3. **Reversible.** The address is the id, so nothing is lost. The IP is also carried in
   `Observation.context["device_ip"]` for consumers that would rather not parse an id.

**The honest limits, which travel in the module docstring.** An IP is not a device. NAT hides many
behind one, DHCP moves one between many, and a Modbus gateway fronts several units behind a single
address. Only the gateway case is visible from here, so `CommandEvent.unit_id` **preserves the
sub-address without folding it into identity**. Folding it in was rejected: it is more precise for
Modbus and unusable in general, because a second protocol carries a different notion of
sub-address and identities whose *shape* varied by protocol could not be compared across a mixed
capture. Refining device granularity properly needs a **declared** device map — the
`phos.atlas.topology` pattern — which is a later PART's decision and not P2's to make.

## Decision 2 — No `Entity` objects are minted

**Decided:** P2 emits entity *ids* and creates no `Entity`.

An `Entity` requires an `EntityType`. Deciding from traffic alone that 10.0.0.9 is an
`ENGINEERING_WORKSTATION` rather than an `HMI` is an inference of exactly the kind ADR 0010 refuses,
and `EntityType`'s industrial half has no member meaning *"a device nobody has told us the type
of"*. The alternatives were to guess a type, to borrow the enterprise `DEVICE` member across a
taxonomy split the enum's own docstring calls deliberate, or to widen the ontology — and P2 has no
business doing any of the three. `InMemoryEvidenceStore.add_observation` does not require the
entity to exist, so nothing is blocked: whoever is actually *told* what the devices are can create
them later against ids that already match.

## Decision 3 — Fixed windows anchored on the span, and the partial tail is dropped

**Decided:** windows of `CommandFeaturePolicy.window` (one minute by default) tile the stream from
the first message. **A trailing window the span does not fully cover is discarded**, and every
observation is stamped with its **window's start**.

*Why the tail goes.* A device polling once a second, measured over the last eleven seconds of a
one-minute window, reports a command count of eleven where every other window says sixty. That is
not a quiet device; it is a window that ended early. Emitted, it is indistinguishable from the
silence P2 exists to detect, and — worse — a baseline learned from a corpus of such windows carries
the artefact permanently. Discarding it is the same choice `phos.atlas.vectorise` makes for a row
it cannot fill honestly, and the cost is stated rather than hidden: **a capture shorter than two
windows yields at most one, and one shorter than a single window yields none at all.**

*Why the span comes from every result, not from the commands.* Unparsed traffic and refused frames
are still evidence the wire was live at that instant. A span drawn from commands alone would end at
the last command, making a device that fell silent at the end of a capture look as though the
capture ended with it.

*Why the start timestamp.* Every feature of every device in a window shares one instant, which is
what lets `vectorise` place them on a single row rather than a ragged scatter. Stamping the end
would report every measurement one window late and misalign command behaviour against the sensor
telemetry it will be correlated with.

## Decision 4 — What the features are, and three things they refuse to say

Eleven feature families, each answering a distinct behavioural question: command volume; a count
per function code; write-target count and address span; register-write value range and mean;
read/write balance; and the mean command interval with its coefficient of variation.

Three choices in that list are not obvious.

**(a) `write_command_share`, not a read/write ratio.** The PART asked for a ratio; a ratio is
unbounded. A device that stops reading entirely gives it an infinite value, which cannot be
baselined, serialises to JSON `null`, and would break traceability the moment it was stored —
exactly the failure `phos.models.MAX_MAGNITUDE` exists to prevent one layer up. The share carries
identical information in `[0, 1]`.

**(b) Value features cover register writes only.** Function 6 and 16 carry 16-bit register values.
Function 5 carries the raw field `0x0000`/`0xFF00`, and function 15 carries bits unpacked to
`0`/`1` — both meaning "on" or "off", in two encodings three orders of magnitude apart. A value
range computed over the pair would describe neither. Coil write *activity* remains fully visible in
the per-function counts and the address features; only the meaningless number is withheld.

**(c) One feature per function code, not one averaged feature.** A baseline is keyed
`(entity, feature)`, so a device's read rate and its write rate must be separate signals. Averaged
into one, a collapse in polling could be masked by a rise in writing — which is the shape of the
event most worth catching.

**And the three refusals.** Below `min_commands` in a window, a device gets no features at all —
four commands do not describe a rhythm, and this is the same policy `PerKeyBehaviouralModel`
applies through `min_samples`. Below `min_intervals` gaps, the timing features are withheld while
the volume features are kept, because one interval has no spread and a coefficient of variation
over it is a rigidity claim with no evidence behind it. And nothing is computed from a field the
wire did not carry: a write whose address P1 left `None` contributes to no address feature rather
than being placed at register 0.

## Decision 5 — A measured zero and an absence are different outputs

**Decided:** for a window a device was *active* in, every function code it issued anywhere inside
the tiling gets a count, **including zero**. For a window it sent nothing in, **nothing at all is
emitted**.

The distinction is the whole point. "This device wrote nothing this minute" is something we looked
at and saw; it is what makes the one window where it *does* write visible as a change, and
emitting nothing there would hide a stopped poller behind a gap. "This device does not appear in
this window" is not a measurement — a device off the wire cannot be told from a device that has
gone quiet, and the *relationship* falling silent is a question `graph` is equipped to answer and
`behaviour` is not.

One consequence is deliberately narrow: the function-code set is built only from commands that
landed **inside** a window. A code seen solely in the dropped tail was never measured, and claiming
a zero for it in every earlier window would put a count against traffic nothing describes.

## Decision 6 — Provenance is per-feature, and a ratio must cite its denominator

**Decided:** `Observation.context` carries `frames` as per-capture index ranges —
`/captures/plant.pcap:60-119`, joined by `;` across captures — plus `frame_count`, the device
address, the window bounds and the protocol.

A *range* rather than a list, because a busy window holds thousands of frames and the range with
the window bounds is enough to recompute the value exactly. **Per capture** rather than pooled,
because a frame index means nothing without the file it counts within.

The part that took a correction: **provenance is computed from the events that actually justify
each feature**, not from the window wholesale. A write-address feature cites the write frames. A
zero count cites the whole window — those are the frames that were examined and did not contain
that function, which is precisely what justifies saying zero.

`write_command_share` was originally written to follow the other write features and cite the write
frames. **That was a defect**, found by mutation testing (Decision 9). A share is a *ratio*: an
auditor handed only the numerator's frames can recompute the numerator and nothing else, which is
not a reconstructable value (Constitution §3.2). It now cites the whole window. The general rule
this establishes: **a derived quantity's provenance is the evidence for the whole computation, not
for its most interesting part.**

## Decision 7 — The graph is learned, and that is not the thing ADR 0010 forbids

**Decided:** `learn_device_command_graph` infers command relationships from traffic.

This deserves an explicit defence, because ADR 0010 refuses to infer which signals share a pump and
the two decisions look contradictory. They are not, and the difference is circularity. Grouping
exists to answer *"did these deviations share a cause?"*; deriving membership from co-movement and
then counting co-movement as one event on the grounds that they are grouped is a loop, and the
reduction would be real in the log and meaningless in the plant.

Nothing loops here. The graph is learned from one corpus and compared against a **different** one,
and it never feeds back into what it learned from. It also is not an inference in the same sense:
the arrow between two devices is what the wire literally said, not a statistical association.

What the graph is emphatically **not** is a claim about wiring, routing, process design or
authorisation. An edge means *"this device was seen commanding that one in this capture"* and
nothing more. That limit bites harder than the equivalent one for features: a device's *rate*
degrades gracefully as a capture shortens, but its *relationships* are all-or-nothing, so a link
exercised once a shift is either in the graph or reported as new the first time it appears.

## Decision 8 — Findings are observations, and their values are quantities

**Decided:** `compare_to_graph` returns ordinary `Observation`s. There is no `GraphFinding` type.

Constitution §3.1 forbids an engine inventing a private alert format, and the ontology already
models this exactly: `Observation.entity_ids` takes more than one entity precisely "when the feature
describes a relationship, e.g. traffic between a workstation and a PLC". Entities are ordered
`[issuer, target]`, so `phos.models.model_key` attributes the observation to the device that
*acted*.

Each feature's value is a **quantity**, chosen so a larger number always means a larger departure:

| Feature | Value |
| --- | --- |
| `unknown_command_relationship` | commands seen on the never-before-seen link |
| `silent_command_relationship` | commands the learned rate implies the link should have carried |
| `unexpected_command_function` | commands using the unlearned code |

A flag would have been simpler and is wrong: one probe and a sustained flood on a new link would
report the same value, and nothing downstream could order them.

Four supporting choices. *Silence is judged per window*, so a link that dies part-way through a
capture is caught — the case the feature exists for. *Its expectation comes from the learned span*,
never the live one, and a graph learned over a zero-length span supports no expectation at all,
because a rate over zero seconds is not a large number but not a number. *An edge below
`min_edge_commands` earns no expectation*, because calling the absence of a link seen twice in a
whole capture "evidence" manufactures a finding from a sampling accident. And *a link that is both
unknown and carrying an unfamiliar function reports only as unknown* — the whole relationship is
new, and two observations would count one change twice for anything that later weighs them.

**Promoting any of this to `Evidence` is P3's.** Nothing here reasons, scores a confidence or
writes a template. Whether a finding is maintenance, misconfiguration or an intruder is a question
this layer is not equipped to answer and does not pretend to.

## Decision 9 — The suite was tested against deliberate defects, and it found a real one

**Decided:** `scripts/mutate_command_behaviour.py`, 22 injected defects, reproducible.

P1's lesson was that a test suite which has never caught anything is unproven, and that the defects
that matter hide where several fields must agree in exactly the wrong way. P2 applied it from the
start: `tests/atlas/packet/test_command_adversarial.py` was written to aim at those cases rather
than to sample randomly, and then the aim itself was checked.

Each mutation is a defect a careful engineer could plausibly write, chosen so the wrong behaviour is
a **different number** rather than an exception. Nothing is mutated in place: `src/` is copied to a
temporary directory, the copy is edited, and pytest is pointed at it with `-o pythonpath=…`, so an
interrupted run cannot leave a defect in the working tree. A mutation whose target text does not
appear exactly once aborts the run — a mutation that silently applied nowhere would be reported as
caught by every test, which is the precise false reassurance the script exists to prevent.

**All 22 caught.** The first 15 were the classes the aimed tests were written against; the last
seven were added afterwards specifically to attack behaviour no test had been written *for*:

| Mutation | Caught by |
| --- | --- |
| `window-tail-kept` — keep the partial trailing window | `test_windows_tile_the_span_from_its_start` |
| `undirected-treated-as-command` — assume the sender acted | `test_an_undirected_message_is_not_a_command` |
| `identity-truncated` — fixed-width entity ids | `test_distinct_addresses_never_collide` |
| `tail-functions-earn-zeros` — function set from the whole stream | `test_a_function_seen_only_in_the_dropped_tail_earns_no_zeros` |
| `min-commands-off-by-one` | `test_too_few_intervals_drops_the_timing_features_and_keeps_the_rest` |
| `interval-floor-counts-commands` | `test_the_interval_count_is_one_fewer_than_the_command_count` |
| `cv-is-raw-spread` — drop the scale-free divisor | `test_a_jittery_device_has_a_positive_coefficient_of_variation` |
| `write-means-register-write` — coil writes stop being writes | `test_a_coil_write_reports_its_address_but_not_a_value_range` |
| `write-provenance-widened` | `test_a_write_feature_traces_only_to_the_write_frames` |
| `function-known-anywhere` — membership against the graph, not the edge | `test_a_function_known_on_another_link_is_still_unexpected_here` |
| `silence-reported-once` | `test_a_normally_chatty_link_that_stops_is_surfaced` |
| `rate-from-window-not-span` | `test_a_normally_chatty_link_that_stops_is_surfaced` |
| `direction-collapsed-on-compare` | `test_direction_is_not_collapsed_when_a_link_is_compared` |
| `unknown-edge-is-a-flag` | `test_a_device_commanding_one_it_never_has_is_surfaced` |
| `edge-floor-off-by-one` | `test_the_floor_is_configurable` |
| `span-from-the-ends` — assume capture order | `test_the_span_covers_every_result_not_just_the_commands` |
| `window-index-rounds` — round instead of floor | `test_a_timestamp_maps_to_the_window_holding_it` |
| `frame-bounds-overwritten` — last write holds the range | `test_the_frame_range_matches_the_window` |
| `observation-stamped-at-window-end` | `test_a_known_rhythm_yields_the_hand_computed_counts` |
| `sort-key-drops-the-feature` | `test_output_is_ordered_by_window_then_device_then_feature` |
| `share-provenance-narrowed` | `test_a_ratio_cites_the_frames_behind_its_denominator_too` |
| `edge-window-minmax-swapped` | `test_a_single_relationship_is_learned_with_its_function_codes` |

**One of those rows is a real defect this process found, not a hypothetical.**
`share-provenance-narrowed` reads as a mutation and is in fact the *original* code:
`write_command_share` cited only the write frames. No test existed for it, because the aimed tests
had checked provenance precision on the write-address features and the same reasoning looked like
it transferred. It does not — a ratio needs its denominator's evidence — and the fix plus its test
are Decision 6. Writing out *why each mutation is plausible* is what exposed it: the argument for
the mutation was better than the argument for the code.

The honest reading of 22/22: the first 15 measure that the aimed tests hit what they aimed at, which
is worth less than it sounds. The last seven are the real result, and one of them was a hit.

## Decision 10 — Two caveats travel with every number

**Decided:** `COMMAND_BASELINE_CAVEATS`, constants rather than prose, following
`ATLAS_VERTICAL_CAVEATS`.

`SHORT_CAPTURE_CAVEAT` — a command baseline describes the capture it was learned from, not the
plant. A short capture sees fewer windows, so normal looks narrower than it is and every later
deviation is inflated. **This does not fail loudly**: the numbers look identical either way, which
is exactly why the constant has to travel with them rather than live in a docstring.

`UNREPRESENTATIVE_TRAFFIC_CAVEAT` — a capture taken during one plant mode contains only that mode's
behaviour. A shift change or a batch changeover will look like a departure because it is absent
from what was learned, not because it is abnormal, and nothing here can tell the two apart. Only a
capture spanning the modes can.

`featurise_commands` also logs a warning when a capture yields fewer than ten whole windows, and
another when it yields none, because that is the moment the first caveat stops being theoretical.

## Ambiguities resolved

| Ambiguity in the PART | Resolution | Where |
| --- | --- | --- |
| What "the issuing device" is, as an ontology entity | The source IP, as `ent_<ip>`; no `Entity` minted | D1, D2 |
| Window length, and what happens to the remainder | Configurable, one minute by default; partial tail dropped | D3 |
| Which timestamp an aggregate feature carries | The window's start, shared across devices | D3 |
| "Read/write ratio", which is unbounded | `write_command_share` in `[0, 1]` | D4a |
| Whether coil writes contribute to value features | No — two encodings, one number would describe neither | D4b |
| Whether a device's absence from a window is a zero | No. Active-window zeros yes, absence no | D5 |
| How a window aggregate "traces back to frames" | Per-capture index ranges, computed per feature | D6 |
| What shape a graph finding takes | An `Observation`; no private type | D8 |
| What a graph finding's *value* means | A count or an expected count, never a flag | D8 |
| Whether a new link also reports its function code | No — one change, one observation | D8 |
| Whether P2 should fill the `stability` stubs it unblocks | No. They are `phos.atlas` modules and P2 modifies none | below |

## Consequences

**Good.** Command behaviour reaches PART 3's baselines and 5A's joint models through the existing
path with no special-casing, proved by fitting `GaussianBaseline` on the emitted observations and
by `vectorise` producing one complete row per window. Every value walks back through a
`FrameSource` to specific frames in a specific file. The three graph changes the PART named are all
surfaceable, as quantities rather than flags. 100% line and branch coverage on the new modules, and
the suite is proved able to catch 22 deliberate defects.

**Costs, accepted.** `featurise_commands` and `compare_to_graph` **consume their stream whole**,
unlike everything in P1: a window's features cannot be computed before the window closes, and the
tiling cannot be laid out before the span is known. Memory is bounded by commands rather than by
frames; the graph learner is incremental and bounded by *links*, not commands, but the featuriser
is not. A capture too large to featurise in one pass would need chunking that P2 does not build.

**Known limits.** A device that never reaches `min_commands` in any window is described nowhere,
and only `CommandStreamStats` shows it existed. Every learned link going quiet at once — a device
off the network — produces one silence observation per link per window, which is true and noisy;
whether that noise is tolerable is a measurement P3 must make. Interval features never cross a
window boundary, so a device commanding in short bursts at the start of each window reports the
rhythm *within* the burst and nothing about the gap between them. And the `phos.atlas.stability`
stubs for communication-timing and protocol-state stability name a packet adapter as their missing
prerequisite; P2 now supplies it, but filling them means editing an existing Atlas module, which
this PART forbids — so the decision, and the question of whether these features are the right
input for them, is left to P3 deliberately rather than by omission.
