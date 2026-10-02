# ADR 0039 — Ranking-contract lock: undoing 0036–0038 must turn existing tests red

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Command-lead mechanical honesty, session 4 (ranking-contract lock)
- **Supersedes:** nothing
- **Depends on:** [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0037](0037-silence-is-judged-against-a-comparable-learned-stretch.md),
  [ADR 0038](0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md),
  [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md)

## Context

Sessions 1–3 named three mechanics and recorded them as ADRs. Session 3 landed at `3015ea7`.
The remaining honesty problem was not another ordinal on D2. It was that a later edit could
undo those mechanics — invert `template_id` so the attack wins a tie, smear silence across
the train, attach unrelated poller silence to a rogue write — and the suite would not be
asked, in a copy of `src/`, whether it noticed.

Session 3's unit tests already pin the mechanics. This session does not rewrite them. It
adds mutants that restore the named cheats into a throwaway copy of `src/`, and it fills
three report gaps that those unit tests do not cover.

Frozen, scored apart, not the cycle contract, not remeasured here:

| Issuer kind | Unique led | Moved | n |
| --- | ---: | ---: | ---: |
| Known-station (`scada` / `hmi`) | **0** | 6 | 16 |
| Unknown-master (silent `engineering`) | **1** | 4 | 4 |

The **1 of 4** is a D2 diagnostic with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. Only
`wt-unknown-master-near-invisible` uniquely leads. Subtle lists at rank 1 with non-empty
`tied_leaders` (two `unauthorised_control_activity` hypotheses); `leads` stays false. FP/hour
on that corpus remains **1.1650**. Do not pool. Do not claim ≥70%. Do not quote hostile
configs 04–07 as detection (ADR 0017); they were not run.

## Decision

**A change that undoes ADR 0036, 0037, or 0038 must turn an existing test red, in a copied
tree, before it can look like progress.**

Mutations live in `scripts/mutate_command_integration.py` and
`scripts/mutate_command_behaviour.py`. Nothing is mutated in place. `TEST_MODULES` includes
the suites that actually catch the cheats: command evidence, command grounding, packet graph,
reasoning engine, breaking commands, breaking report.

Caught on this session's run (`-x`, first failing test):

| Mutation | ADR | First test that goes red |
| --- | --- | --- |
| `leads-ignores-tied-leaders` | 0036 | `test_a_ceiling_tie_is_not_a_unique_leader` |
| `template-id-inverted-so-attack-wins` | 0036 | `test_a_ceiling_tie_is_not_a_unique_leader` |
| `ranked-template-id-inverted` | 0036 | `test_saturated_rivals_raise_insufficient_evidence_rather_than_an_alphabetical_winner` |
| `residual-counted-as-command-lead` | 0036 | `test_insufficient_evidence_listed_first_is_not_command_reasoning_lead` |
| `rank-one-tie-counted-as-unique-lead` | 0036 | `test_rank_one_with_tied_leaders_is_not_counted_as_a_unique_lead` |
| `issuer-kinds-pooled` | 0034/0037 | `test_known_station_and_unknown_master_lead_rates_are_not_pooled` |
| `attachable-always-true` | 0038 | `test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write` |
| `ingest-skip-dropped` | 0038 | `test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write` |
| `silence-always-attachable` | 0038 | `test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write` |
| `silence-smeared-rate-emits-every-quiet-minute` | 0037 | `test_a_multi_day_train_does_not_manufacture_silence_every_minute` |
| `silence-floor-dropped` | 0037 | `test_a_multi_day_train_does_not_manufacture_silence_every_minute` |

Three aimed tests fill gaps the session-3 suite did not cover. They are not copies of
attachment or occupancy tests:

- Rank 1 with non-empty `tied_leaders` is not counted as unique lead (the subtle window).
- `insufficient_evidence` listed first is not command-reasoning lead.
- Known-station 0/16 and unknown-master 1/4 are not rendered as one pooled "led in n of m".

`classify_command_issuer` remains a lookup on the learned graph, not `AttackType.ROGUE_COMMAND`.
`ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT` still travels with the command section.
`test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence` still passes.
Occupancy bins, `_TYPICAL_SILENCE_FLOOR`, `min_edge_commands`, and `LEAD_TIE_EPSILON` were
not retuned. `atlas/templates.py` matchers were not edited.

`edge-floor-off-by-one` in the behaviour script was retargeted: session 2's skip is
`command_count < min_edge_commands`, so the off-by-one cheat is `<=`, not a `>=` that no
longer exists. That is plumbing, not a ranking cheat.

## Consequences

**Gained.** Undoing a lead-tie refusal, a duration-matched silence judge, or entity-reachability
attachment fails a test that already existed, or one of the three report pins this session
added. The 0/16 and 1/4 headlines stay apart in the renderer.

**Cost.** Completing session 4 does not earn ≥70%. Unique unknown-master lead is still 1 of 4
on attacks we wrote. Hypothesis confidence remains uncalibrated. Session 5 is still a
licence-confirmed public command capture or a refusal that names the gap. Hostile-input
robustness remains a separate claim (ADR 0017).

## Alternatives considered

- **Rewrite session 3 unit tests as a second copy of the same assertions.** Forbidden. The
  lock is mutants against the tests that already pin the mechanics.
- **Remeasure D2 to grow unique unknown-master lead toward 4/4.** Forbidden. Collapse of the
  two `unauthorised_control_activity` hypotheses on the subtle window is the same fake unique
  winner ADR 0036 refused.
- **Run hostile configs 04–07 as session success.** ADR 0017: software surviving rubbish is
  not detection. Both breaking reports still say no input-hostile corpora were measured.
- **Invert `template_id` or put known-link unexpected function on maintenance-contradict.**
  Template cheat. The indistinguishability test remains the tripwire.
- **Count residual-first as command-reasoning lead.** Would make silence look like
  attribution. Forbidden.

## When to revisit

When session 5 scores a licence-confirmed public command capture with issuer kinds apart, or
refuses naming the exact label/protocol gap. Not when a mutant is added to chase a better D2
ordinal.
