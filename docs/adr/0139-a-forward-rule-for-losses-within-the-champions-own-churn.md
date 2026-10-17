# ADR 0139 — A forward rule: a challenger may lose only what the champion loses to its own noise

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123 §9.3, for future scores only
- **Depends on:** [ADR 0121](0121-the-first-learning-lifecycle-and-its-control-arm.md),
  [ADR 0134](0134-red-team-and-the-trusted-map-first-results.md),
  [ADR 0138](0138-three-confirmations-the-same-answer.md)

## Context

ADR 0123 §9.3 lets a challenger survive the red team only if it loses none of the champion's
passes. Under that rule `atlas-plant-map-v1` failed three held-back sets (ADR 0138), each time
more than doubling the champion's passes and losing two. On 15 October Elijah asked for what is
better and what PHOS would do.

**This record is written after those three failures, and it says so.** It does not re-judge
them: their verdicts stay "fails". A rule changed after seeing results and applied to those same
results is the thing PHOS exists to refuse. What it may do is say, with evidence that does not
come from the challenger, why the old rule asks for more than the champion itself can deliver,
and fix a rule for the next unseen score.

**The evidence.** ADR 0134 found that regenerating the red-team corpora in another environment,
with the champion and its scorer unchanged, changed the champion's own passes. Three of the 52 it
passed in ADR 0121 did not repeat, and four new ones appeared. So "no pass lost" asks a
challenger to be more stable against the champion than the champion is against itself. The
measured churn is 3 of 52.

## Decision

**1. The forward rule** (`phos.breaking.liar_arena.within_churn`). On a held-back set never
scored before, a challenger survives when:

- it loses at most `floor(3/52 × the champion's passes on that set)` of them, the champion's own
  measured churn; and
- it passes more than the champion by more than that same allowance, so a gain must exceed the
  noise it is allowed.

Every lost run is listed in the record, as before.

**2. Where it applies.** Only to `CONFIRM_SEEDS_3` (development seeds 95401–95410, disjoint from
every other set; a test checks), through `scripts/arena_red_team.py plant-map --confirm 6
--confirm-set 3`, for attempt 6 exactly as it was scored (ADR 0137): no setting, rule or code in
the detector changes. ADR 0123 §9.3's rule stays the rule for every earlier set and verdict.

**3. Run once.** Whatever it finds is the result.

**4. What survival would mean, and would not.** It would make `atlas-plant-map-v1` (attempt 6) a
candidate for ADR 0117's gate as a **detector**: one look at the validation corpora (HAI 21.03,
22.04, 23.05, BATADAL), catching no fewer attacks than the champion on each and more on one HAI
edition, recorded in an ADR that Elijah accepts. Those corpora are not in this build container.
Naming and reconstruction stay off everywhere (ADR 0129) until they clear §9.7 and §9.9. The water
plant's naming result is a finding, not a product claim.

## The cost, stated

A rule that allows losses lets a challenger forget some things the champion knew. The bar is the
champion's own instability, so the challenger is held to the champion's standard, not a looser
one. If the champion's churn is later measured differently, this allowance changes only by its
own record, before a score.

## What would reverse this

Applying this rule to `RED_TEAM_SEEDS`, `CONFIRM_SEEDS` or `CONFIRM_SEEDS_2`; scoring
`CONFIRM_SEEDS_3` more than once, or with a changed candidate; or moving the allowance after its
score.
