# ADR 0071 — Command-behaviour evidence reaches a template, and the tie stays tied

- **Status:** Accepted
- **Date:** 2026-08-31
- **PART:** Session (Atlas reasoning) — branch `experiment/ruflo`, not merged to `main`
- **Supersedes:** nothing.
- **Amends:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)
  Decision 4 on one clause only — "a command-behaviour deviation therefore bears on no OT
  explanation at all". Everything else Decision 4 records still stands, including the
  maintenance-vs-attacker tie, which this record reaches again from a different fact and again
  leaves unresolved.
- **Depends on:** [ADR 0070](0070-the-evidence-facet-replaces-summary-string-parsing.md) (the typed
  facet this pattern resolves through),
  [ADR 0057](0057-command-behaviour-is-a-stamp.md) (the stamp being read),
  [ADR 0027](0027-unknown-master-writes-are-not-maintenance.md) (the asymmetry this one does *not*
  imitate), [ADR 0040](0040-no-labelled-public-command-corpus.md) (why this is readiness and not a
  result)

## Context

Atlas has measured command behaviour since P2 and promoted it since P3. `featurise_commands`
emits a scalar per device per window per feature — a write share, a register span, a polling
interval and its coefficient of variation — `promote_command_behaviour` scores each against a
learned band and promotes the genuine departures through the evidence boundary, and Session D1
stamped each one with the feature that departed.

Then reasoning threw the meaning away. Every one of those facts arrived at the template library as
a bare `EvidenceKind.DEVIATION` naming one device, matched nothing, and accumulated on no
explanation. A device whose write volume tripled and a device whose polling rhythm collapsed were,
to the four Atlas explanations, the same non-event — and both were the same non-event as a fact
carrying no stamp at all. `test_a_command_behaviour_departure_bears_on_no_ot_explanation` pinned
that, deliberately, since P3.

ADR 0014 Decision 4 gave two reasons, and they have aged differently.

> Which *command feature* departed — `Evidence` names a kind and some entities and never a
> feature. No pattern in 4B's language can ask whether it was a write share, a polling rhythm or a
> register span.

That reason **is now false.** ADR 0070 added `facet_kind` / `facet` precisely because four
matchers needed to switch on a sub-kind, and `promote_command_behaviour` already sets
`(FacetKind.COMMAND_BEHAVIOUR, observation.feature)`. `command_behaviour_feature_of` already
resolves it, typed-first. The field ADR 0014 said did not exist exists, has a resolver, and had no
consumer. That is the whole of the gap this record closes: one missing consumer, not a new
capability.

The second reason still binds and is what constrains the shape of the answer:

> Giving it a matcher that supported every explanation equally would change no ordering and cost
> code; giving it one that supported some would be a claim the pattern language cannot justify.

ADR 0070 saw this coming and refused to take it: "Wiring a `CommandBehaviourPattern` is a separate
decision with its own evidence, and it is not taken here." This is that decision.

## Decision

### 1. `CommandBehaviourPattern` joins the pattern set, resolving through the typed facet

A fifth `EvidencePattern` subclass in `src/phos/atlas/templates.py`, alongside
`SubsystemBreadthPattern`, `GraphFindingPattern`, `UntypedStructurePattern`, `WorkOrderPattern`
and `CommandStructurePattern`. `matches` calls `command_behaviour_feature_of` and returns `False`
when it answers `None` — the same three-line shape `GraphFindingPattern` uses, reading the same
resolver, through the same typed-first channel.

**Nothing existing changed.** No pattern class, no resolver, no promoter, no boundary door, no
belief arithmetic, no prior. Two module-level tuples gained one entry each. The diff to reasoning
is a pattern and two names.

### 2. It supports the two control explanations and refuses the two process ones

| Template | Role | By construction |
|---|---|---|
| `engineering_maintenance` | **supporting** | A commissioning engineer alters how a device commands: that is what the work is. |
| `unauthorised_control_activity` | **supporting** | So does an attacker operating that device. |
| `process_disturbance` | *no relation* | Refused. See below. |
| `sensor_or_device_fault` | *no relation* | Refused. See below. |
| `insufficient_evidence` | *no relation* | The residual carries no patterns, by construction. |

This clears ADR 0014's second objection without inventing an asymmetry. Two of four is not "every
explanation equally": the fact lifts both control explanations relative to both process
explanations and relative to the residual, which is a real ordering change and is exactly the
meaning that was being discarded — **this was control activity, not a reading.** That is the one
thing a command-behaviour departure says that a sensor departure cannot, and it is why P2 measured
the command stream separately in the first place.

### 3. The refusal is the load-bearing half

`process_disturbance` and `sensor_or_device_fault` get **no relation at all**, and this is a
decision rather than an omission.

Calling a command departure evidence *against* a real process upset would be **false**. A closed
control loop answers a disturbance by acting: it writes more often, writes different values, and
its polling cadence shifts under load. `write_command_share`, `register_write_value_mean` and
`command_interval_mean_ms` all move during a genuine upset, for entirely benign reasons. This is
the one place where the graph's asymmetry does **not** transfer. ADR 0014 earned the structural
asymmetry from physics — "a real process upset moves readings, and it does not make a workstation
begin commanding a PLC" — and that argument is about *who commands whom*, which an upset cannot
change. It says nothing about *how much* an existing commander commands, which an upset changes
routinely.

Calling it evidence *for* an upset would be the opposite error: a claim about closed-loop
controller dynamics that nothing in Atlas has measured, on a plant Atlas has never been given.

Silence on those two is the honest reading. It is asserted by
`test_the_two_process_explanations_get_no_relation_at_all` so a later edit cannot quietly add
either relation to make a number move.

### 4. The maintenance-vs-attacker tie is reached again and left standing

Both control explanations get `SUPPORTING` from the same fact, and nothing separates them but
their priors — `engineering_maintenance` at 0.0577 against `unauthorised_control_activity` at
0.02, both from `prior_at_rank` and neither touched here.

This is the same tie ADR 0014 Decision 4 recorded for a function-code change on a known link — "a
commissioning engineer and an intruder leave behind the *same* new relationship. Both templates
are supported by it; only the priors separate them" — reached from a different fact for the same
underlying reason: **no command feature carries intent.** A write share of 0.9 is a write share of
0.9 whoever produced it.

Resolving it would have been the cheap move and the dishonest one. The only fact in Atlas that
legitimately breaks this tie is `UNKNOWN_COMMAND_RELATIONSHIP` — a device that has never commanded
this target beginning to — and it breaks it on identity, not on behaviour (ADR 0027). Behaviour
alone does not, and this record does not pretend otherwise.

### 5. No `features` field, unlike `GraphFindingPattern`

`GraphFindingPattern` enumerates features because P3 genuinely needed an unknown master told apart
from a known-link change, and ADR 0027 argues that separation from plant practice. Nothing here
needs a sub-selection. Any declared command-behaviour feature matches.

Adding the field "for later" would be an abstraction Constitution §2 forbids, and — worse —
populating it would mean deciding that a write-side departure is more suspicious than a
rhythm-side one, which is a tuning choice with nothing to tune against. ADR 0040 and the TU Wien
assessment both say the corpus that could justify it does not exist. When one arrives, the field
is a three-line addition with evidence behind it.

`test_every_command_behaviour_feature_routes_the_same_way` pins the equal treatment.

### 6. The subsystem-event guard is checked, not assumed

`_LOCALISED` **contradicts** `unauthorised_control_activity` and is scoped to
`EvidenceKind.DEVIATION` — the same kind this pattern reads. If a fact could satisfy both,
`HypothesisTemplate._check_patterns_are_unambiguous` would be right to refuse the template, and it
would be refusing a real ambiguity rather than a spurious one: matching `_LOCALISED` is precisely
the inversion ADR 0014 Decision 3 exists to prevent, because it would make a device's commanding
argue *against* unauthorised control.

Nothing promotes a grouped subsystem event carrying a command-behaviour facet. But "nothing does"
is an invariant holding by accident, which is the exact gap Decision 3 closed with
`subsystem_events_only`. So `matches` reads `phos.atlas.grouping.is_subsystem_event` and refuses a
grouped event outright. The disjointness `overlaps` then claims is a fact about a declared marker —
no evidence both carries it and lacks it — rather than a claim about what the promoters happen to
build. Same argument, same marker, same shape as the guard it mirrors.

`overlaps` is otherwise the base implementation: exact against the three relationship-change
patterns, which constrain a kind this one does not share, and deliberately **not** a blanket
refusal — a breadth band declared with `subsystem_events_only=False` genuinely could match the
same fact, and `test_the_pattern_still_overlaps_an_ungrouped_band_that_could_match_the_same_fact`
holds that it says so.

### 7. Three tests moved, and each states what survives rather than being deleted

ADR 0014's own convention: "the tests that recorded them were updated to state what survives
rather than deleted."

| Test | Was | Now |
|---|---|---|
| `test_templates_still_do_not_match_a_stamped_behaviour_departure` | no template matches a stamped departure | it reaches both control explanations, and neither process one |
| `test_a_stamped_behaviour_departure_still_bears_on_no_ot_explanation` | same, through the typed path | same, renamed to what it now pins |
| `test_a_command_behaviour_departure_supports_nothing_but_still_joins_the_story` | on no hypothesis's lists | on exactly the two control hypotheses, and still in the narrative |

`test_a_command_behaviour_departure_bears_on_no_ot_explanation` in `test_templates.py` **stays
green and stays.** Its fixture declares neither facet nor marker, so it still resolves to `None`.
Only its docstring moved, because what it pins is now narrower and worth saying exactly: an
*undeclared* deviation bears on nothing, and it is the declaration rather than the pattern
language that decides.

## What this does not change

- **No detection number, and no claim to one.** Every fixture is hand-built or promoted from
  hand-built observations. `discover_labelled_command_corpora` still finds nothing, and
  `test_this_repository_holds_no_labelled_command_corpus` still passes.
- **Known-station command lead stays 0/16 and unknown-master 1/4**, separate and unpooled
  (ADR 0039, ADR 0040). Nothing here was measured against either.
- **No prior, weight, threshold or belief rule moved.** `prior_at_rank` and its five rank
  arguments are untouched, pinned to twelve decimals by `TestReuseNotFork` and again here.
- **No frozen row moved.** No corpus was run, so `eval_runs/log.jsonl` gained no line;
  `tests/atlas/test_frozen_rows_untouched.py` holds 646.58 / 53.26 / 14071.07 in place.
- **The ontology is untouched.** No file under `src/phos/ontology` was opened, so the PART 6B
  freeze is not narrowed further and `_ONTOLOGY_OPENED_AFTER_6B` gains nothing.
- **Still five explanations.** A pattern is not a template. Constitution §3.6's "no mechanism for
  inventing a sixth" holds; `atlas_templates()` returns the same five in the same order.
- **Hypothesis confidence is still uncalibrated and still may not be surfaced** (§3.3). This
  record gives a fact somewhere to land; it does not make the number it lands on quotable.
- **The graph is still the only command signal that discriminates.** Behaviour now *routes*; only
  `UNKNOWN_COMMAND_RELATIONSHIP` still *separates*.

## Consequences

**Better.** Evidence Atlas already produces, already stamps and already stores now reaches the
explanations it bears on instead of being discarded at the reasoning boundary. An operator reading
a story where a device's write volume tripled sees that fact carried by the two hypotheses it
actually argues for, rather than floating in the narrative attached to nothing. The asymmetry
between control activity and process activity — the reason the command stream is measured at all
— is expressed in the template library for the first time.

**Worse.** `UNGROUPED_COMMAND_EVIDENCE_CAVEAT` now costs something it did not cost before. Command
evidence is not collapsed, so a device whose commanding changes in four ways at once contributes
four supporting facts for what may be one act — and until today those four accumulated on nothing,
which made the inflation harmless. It is no longer harmless. Grouping command evidence by device
was refused by ADR 0014 Decision 2 as "better made with a real capture in hand", and that
refusal now has a cost attached to it rather than only a rationale. It is the first thing to
revisit when a capture arrives.

**Readiness, not a result — stated plainly.** This makes reasoning *read* evidence Atlas was
already producing. It claims no new detection capability, no recall, no false-positive rate and no
calibration. Its value is gated entirely on a labelled command corpus arriving: one with a
separate attack-free learn stretch and at least one operator-shaped attacker control action with
start/end ground truth. ADR 0040 established no such public corpus exists, and the TU Wien Pilot
Factory assessment confirmed it again from the opposite direction — labels fine enough to name a
command action, and no attacker command action in the capture to label, because "the applicant did
not introduce a single Modbus/TCP packet himself". Until such a corpus exists, this routing is a
pipeline that has never been scored. `UNMEASURED_COMMAND_DETECTION_CAVEAT` continues to travel
with everything this path produces and applies to this record in full.

## Revisit when

A labelled command corpus lands and `discover_labelled_command_corpora` stops returning empty.
Then three questions this record could not answer become answerable and should be asked together:
whether command evidence should be grouped per device (ADR 0014 Decision 2's deferred question,
now with a cost); whether any command feature earns feature-level discrimination, which is when
`features` gets added; and whether supporting both control explanations equally is the right
weighting or merely the honest one in the absence of data.

Do not retune any of the three toward a dataset before that corpus exists. A new public row is a
new key and is never pooled with D2's 0/16 or 1/4.
