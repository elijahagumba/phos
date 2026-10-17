# ADR 0094 — The liar measurement's seeds and pass share, before any run

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1, T1 declaration
- **Depends on:** [ADR 0017](0017-attack-injection-preserves-determinism-truth-from-true-state-benign-events-interleaved.md)

## Context

`docs/v1-five-moments.md` says M1 is measured on the liar, not on any pair of explanations,
and that the seeds and the pass share are fixed by a commit before the first liar run is
scored. That commit did not exist. No liar result is in this record. Roadmap §2 is not
edited. T1 judges nothing in §2.

## Decision

The declaration is `phos.eval.liar_declaration`. It does not generate a plant and it does
not call Atlas.

**Seeds.** `94001` through `94020`, twenty of them. They are disjoint from the library
seeds `71001`-`71003`, the library train seeds `80001`-`80003`, and the seeds already used
by the demo and the diagnostic scenarios (`11`-`30`, plus `1`, `3`, `7`, `8`, `77`, `99`,
`4242`).

**Plants.** `water-treatment`, `power-generation`, `batch-reactor`. That is every plant
whose library process pack already contains `AttackType.LIAR`. No plant is added.

**Magnitudes.** The graded dial already in `SUBTLETIES`: `0.0`, `0.2`, `0.4`, `0.6`,
`0.8`, `0.9`. `0.6` and `0.8` are `SUBTLE`. `0.9` is `NEAR_INVISIBLE`. A run is one plant,
one seed, one subtlety: **360** runs.

**Pass share.** Strictly greater than one half of those 360. 180 of 360 does not pass.

**What a pass is.** Judged from the true state, as ADR 0017 already requires. The unique
contentful leader, ordered by the existing `(-confidence, template_id)`, is
`sensor_or_device_fault`. A tie is not a pass. `insufficient_evidence` is not a pass. At
least one supporting evidence id on that leader has `Evidence.facet` equal to
`command_to_response_mismatch` or `cross_signal_mismatch`. The summary text does not
count. Those two facet strings are not emitted by this commit. Confidence is the rank key
only. It is not a reported probability.

The same share for Atlas without that citation, and an alert inside the window for each
checked opponent, are reported beside the pass share when a later run exists. They are not
this pass mark. `MIMIC` is not this declaration.

## Consequences

A later liar run uses these seeds, these plants, these magnitudes, and this predicate. It
does not drop `NEAR_INVISIBLE`, shrink the plant list, or move the share to a half that
the result happened to clear. Nothing here is a liar result. Nothing is appended to
`eval_runs/log.jsonl`.
