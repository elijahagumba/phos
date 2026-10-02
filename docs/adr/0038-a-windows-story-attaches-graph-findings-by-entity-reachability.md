# ADR 0038 — A window's story attaches graph findings by entity-reachability, not by co-occurrence

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Command-lead mechanical honesty, session 3 (causal-graph reachability)
- **Supersedes:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)
  Decision 2, *only* the claim that there was nothing declared to group command evidence by.
  Co-movement remains refused (ADR 0010). Per-feature inflation remains: several changes on one
  act are still several facts. The interleave-by-time rule stands.
- **Depends on:** [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0037](0037-silence-is-judged-against-a-comparable-learned-stretch.md)

## Context

After session 2, live-capture graph findings fell ~1450 → 13. Unrelated silence could still
enter a window's story. `Narrative.causal_edges` was evidence→hypothesis co-occurrence: every
silent poller in the correlation window accumulated on `engineering_maintenance` for a rogue
write it had no path to. Untyped silence still supports maintenance (ADR 0014). That is
drowning, not plant causality.

Session 1 (ADR 0036) is closed: a ceiling or epsilon tie is a refusal; `leads` stays false when
the lead is tied. Session 2 (ADR 0037) is closed: silence is judged against a comparable
learned stretch. This record does not retune occupancy bins, `_TYPICAL_SILENCE_FLOOR`,
`min_edge_commands`, `LEAD_TIE_EPSILON`, or `atlas/templates.py` matchers. It does not reuse
`atlas/grouping.py` for devices.

Primary success is the attachment test, not D2 unique lead. Unique unknown-master lead 1 of 4
is a D2 diagnostic with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`, not a target to grow.

## Decision

**A graph finding may enter a window's story only if it shares an entity with in-window
command activity, or is the unknown-master finding itself.**

In-window command activity is `unknown_command_relationship` or `unexpected_command_function`.
Those findings always attach. A `silent_command_relationship` attaches only when its
`entity_ids` intersect that act's entities. The identities are declared on the finding — the
same ones the command graph already recorded. They are not inferred from co-movement.

- `ground_event` stays the co-occurrence table `{unauthorised, commanded, uncommanded}`. It is
  not a confidence and not a fourth score.
- `ReasoningEngine.ingest` does not weigh an unreachable silent finding onto a hypothesis. The
  fact remains in the working set, so it can be its own residual story. It does not support
  `engineering_maintenance` for a write it does not share an entity with.
- Chatty learned links that occupy comparable windows remain attachable when they share an
  entity with the command act. Power SCADA silence is real (ADR 0037). This session does not
  starve it.
- `causal_edges` remain the reconstructable evidence→hypothesis bearings already stored on
  each hypothesis (Constitution §3.2). They are not a P&ID. The store refuses an edge whose
  endpoints are not already on the narrative.
- Command evidence is still not collapsed per feature. `UNGROUPED_COMMAND_EVIDENCE_CAVEAT`
  now names reachability honestly and still records the counting inflation.

`grouping.py` is signal topology. It is not used here.

## Remeasure (seed 7, issuer kinds apart)

`leads` means `unauthorised_control_activity` is the unique strongest explanation after
commands (`tied_leaders` empty). It does not mean `insufficient_evidence` sorted first. HEAD
at measurement was `d9b3dce`; the reachability change was in the working tree.

### Known-station (`scada` / `hmi`)

Report: `eval_runs/breaking/breaking-report-known-station.md`.

Of **16** command attacks, structure moved the attack explanation **up in 6** and **led in 0**.
Command-evidence counts are unchanged from ADR 0037 (power in the hundreds; water 0–14).
Known-link unexpected function still supports both attack and maintenance (ADR 0014). Do not
pool with unknown-master.

### Unknown-master (silent `engineering`)

Report: `eval_runs/breaking/breaking-report-unknown-master.md`.

Of **4** unknown-master attacks, structure moved the attack explanation **up in 4** and made
it the unique leader in **1** (`wt-unknown-master-near-invisible`).
`wt-unknown-master-subtle` lists at rank 1 but `tied_leaders` is non-empty (two
`unauthorised_control_activity` hypotheses), so `leads` stays false — ADR 0036. Ranks after
commands: 2, 3, 1 (tied, not a unique lead), 1 (unique). Command-evidence counts: 9, 8, 14, 3.
FP/hour remains **1.1650** (21 FP / 18.02 normal hours). Do not quote this corpus's recall as
detection.

That **1 of 4** is unchanged from ADR 0037. It remains a D2 diagnostic with
`ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. It is not the ≥70% contract, not a field rate, and
not a reason to tighten reachability toward 4/4. Completing session 3 does not earn ≥70%.

## Consequences

**Gained.** A silent learned link with no path to the window's issuer does not support
maintenance for that window. The unit test
`test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write` is the
primary success. Same-entity silence on a chatty link still attaches. `ground_event` is
unchanged as a table. ADR 0036 and ADR 0037 still hold.

**Cost.** Reachability is entity-sharing, not physics. Silence on a learned link that shares
the commanded PLC with an unknown-master write still attaches. Unique lead on attacks we
wrote is still 1 of 4. Hypothesis confidence remains uncalibrated. Session 4's ranking
adversarial tests are unaddressed.

## Alternatives considered

- **Group devices by co-movement.** Circular; ADR 0010. Forbidden.
- **Reuse `atlas/grouping.py` for command-graph devices.** That module partitions signals from
  declared process documentation. Devices on a network are not signals. Forbidden.
- **Retune `_TYPICAL_SILENCE_FLOOR` or `min_edge_commands`.** Session 2. Forbidden.
- **Put known-link silence on maintenance-contradict, or invert `template_id` order.** Template
  cheat. Forbidden.
- **Collapse two `unauthorised_control_activity` hypotheses on `wt-unknown-master-subtle` to
  manufacture a unique lead.** ADR 0036 says that tie is a refusal. Forbidden.
- **Keep tightening reachability until unique lead is 4 of 4.** Session success is the
  attachment test, not a D2 rate. Forbidden.
- **Filter `CommandEvidence.evidence()` so unreachable silence is never stored.** Would hide
  a measured finding from the store. Weighing is skipped; the fact can still be its own story.
- **Turn `ground_event` into a confidence.** Constitution §3.3. Forbidden.

## When to revisit

Session 4 recorded the lock in [ADR 0039](0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md):
mutations that undo this attachment rule turn existing tests red. Revisit when a
licence-confirmed public command capture is scored with issuer kinds apart. Not when D2
`newly_leads` flips.
