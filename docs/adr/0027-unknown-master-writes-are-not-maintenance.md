# ADR 0027 — Unknown-master writes are not maintenance

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Atlas OT core (cycle contract: command ranking ≥70% top-ranked)
- **Supersedes:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)
  Decision 4, *only* the claim that every structural change supports maintenance and an
  attacker equally, and the claim that the three graph findings cannot be told apart. Known-link
  findings (unexpected function, silent relationship) and unmarked fixtures are unchanged.
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0011](0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md)

## Context

The cycle contract asks that unauthorised / anomalous control commands be the **top-ranked**
explanation in ≥70% of confirmed command-attack windows, on every public corpus with network
traffic. The breaking harness is that measurement: same corpus twice, sensors then sensors plus
the capture, and `unauthorised_control_activity`'s position in the ordering.

The structure of the path was already in place (P3). The ranking was not. On the labelled
command-attack set the structure *moved* the attack explanation up in 12 of 16 windows and
**led in 0**. Two facts produced that:

1. `_STRUCTURE_CHANGED` (any `RELATIONSHIP_CHANGE`) sat on both `unauthorised_control_activity`
   **support** and `engineering_maintenance` **support**. Maintenance's prior is one rank higher.
   After a broad process event plus one graph finding, the two explanations often tied.
2. `ExplanationRanking` breaks ties on `template_id`. `engineering_maintenance` sorts before
   `unauthorised_control_activity`, so the tie was a maintenance win.

ADR 0014 Decision 4 recorded that a commissioning engineer and an intruder leave behind the
*same* new relationship, and that all three graph findings are one `EvidenceKind`, so a template
could not ask which. Both statements are still true of an **untyped** relationship change and of
a function-code change on a **known** link. They are not true of an **unknown master**: a device
that has never commanded this target beginning to write is not how a plant's engineering
station works.

`Evidence` still has no feature field (Constitution §3.1). The finding type has to be a
declared property of the fact itself, the same way a subsystem event declares itself with a
`source_id` marker.

## Decisions

### Decision 1 — Stamp the graph finding into the summary at promotion

**Decided:** `promote_graph_findings` prefixes the operator sentence with
`graph-finding:{feature}:`. `graph_finding_feature_of` reads it back. `source_id` remains the
finding's observation id (ADR 0014 Decision 1, traceability).

Forging the prefix on unrelated evidence would make a template match a fact nobody measured;
tests pin that an unmarked summary is not an unknown master.

### Decision 2 — Split structure matchers so a template can contradict unknown masters

**Decided:** three patterns, disjoint by construction:

| Pattern | Matches |
| --- | --- |
| `UntypedStructurePattern` | `RELATIONSHIP_CHANGE` with no marker (fixtures, any promoter that has not stamped) |
| `GraphFindingPattern(unknown_command_relationship)` | a marked unknown master |
| `GraphFindingPattern(silent, unexpected)` | a marked change on a known link |

`HypothesisTemplate` refuses overlapping support and contradict patterns. Putting
`_STRUCTURE_CHANGED` on maintenance support and unknown-master on maintenance contradict is
therefore impossible — a marked unknown master *is* a relationship change. The split is what
makes the next decision expressible.

`overlaps` between a marked finding and untyped structure is `False`. That is the same exactness
ADR 0014 already required of breadth vs ungrouped evidence.

### Decision 3 — Unknown masters contradict maintenance; known-link changes still support both

**Decided:**

- `engineering_maintenance` is supported by untyped structure and by known-link findings, and
  **contradicted** by a marked unknown master.
- `unauthorised_control_activity` is still supported by every `RELATIONSHIP_CHANGE` (including
  unknown masters).
- `process_disturbance` is still contradicted by every `RELATIONSHIP_CHANGE`.

Arithmetic at weight 1.0, after a broad subsystem event: maintenance's odds are divided by
three and the attack's are multiplied by three, on top of the event that only the attack (and
the upset) received. The alphabet tie is gone. The attack leads.

The remaining honest limit is unchanged: a new function code on a station that already
commanded this PLC still supports both explanations. Mimic-from-a-known-master is that case.
The ≥70% target is a claim about *unknown-master* command attacks, which is what a rogue
issuer on the wire actually is, not a claim that every mimic is distinguishable from
maintenance.

Unmarked fixtures keep supporting both, so `test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence` still holds for that shape.

### Decision 4 — Grounding is a co-occurrence table, not a second score

**Decided:** `ground_event(event, command_evidence, window)` returns one of
`{unauthorised, commanded, uncommanded}` from stored command evidence in the window.

- Unknown master → `unauthorised`, even if a known station also moved.
- Command-behaviour departure or unexpected function on a known link, and no unknown master →
  `commanded`.
- Nothing, or only a learned link going silent → `uncommanded`.

This is not a calibrated confidence and must not be surfaced as one (Constitution §3.3). It
exists so a test (and later a UI) can ask "was there a valid operator command in this window?"
without re-deriving the answer from hypothesis order.

## Consequences

**Gained.** The ranking the cycle contract measures can now go the right way on unknown-master
writes, for a physical reason rather than a prior tweak. The three graph findings are named on
the evidence, so a template can tell them apart without `Evidence` growing a feature field.

**Cost.** A mimic that uses a learned engineering station still cannot be told from
maintenance by evidence alone. Claiming 70% on a corpus of only those attacks would be a
lie. The breaking harness remains the measurement; this record does not quote a lead rate in
advance of a run.

**Unchanged.** Command-behaviour deviations still bear on no OT template (ADR 0014). Distillation
CSV telemetry still has no command path. Hypothesis confidence is still uncalibrated.
