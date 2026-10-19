# ADR 0150 — A maintenance alert closes only when a work order is cited

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane B, A5 / W4
- **Depends on:** [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md),
  [ADR 0144](0144-the-october-build-is-declared.md)

## Context

A5 asks Atlas to settle an alert from a maintenance export and to cite the settling fact. The
pass mark is at least 70% of maintenance-caused alerts closed with a cited work order, and no
attack-caused alert closed, including `MIMIC`.

`covering_order` already answers whether a sanctioning window contains an asset at a time. Using
that as a closure would clear an attack that happens to sit inside a real job, which is the case
ADR 0069 refuses to call innocence. The templates already let a work-order fact support
maintenance and contradict unauthorised control. This ADR does not retune those matchers or their
priors.

## Decision

1. **`phos.atlas.maintenance_closure` closes an alert only by citation.** The job log may stamp
   one or more `(order id, feature)` claims on the alert. A claim resolves when the feature is
   the alert's feature, the order id is among the sanctioning rows
   `load_work_order_export` kept, and that row covers the alert's asset at the alert's time.
   Exactly one resolving order closes the alert. The closure stores `schema:order_id`.

2. **Overlap does not close.** An alert with no stamp stays open, including when a sanctioning
   order covers the same asset, feature, and instant. That is the `MIMIC` case: the move can
   look like the job, and the job log did not cite an order.

3. **These leaves stay open.** A stamp whose order the loader dropped (draft, cancellation,
   unknown id). A stamp outside the window, or on a different asset (`P-101` does not cover
   `P-1010`). A stamp for a different feature. Two resolving orders (`ambiguous`). A repeated
   order id in the export is refused rather than picked.

4. **A closure is not a score.** Nothing here changes a detection score, `atlas/templates.py`,
   a known-link matcher, a prior, or `EVIDENCE_STRENGTH`. No confidence is computed or shown.
   Nothing is appended to `eval_runs/log.jsonl`. `atlas-v1-consistency` is not modified.

5. **`close_on_overlap` is the rival, not the product.** It closes on window overlap and ignores
   the stamp. The harness reports the margin against it. The engine does not call it.

6. **A forged stamp is out of scope.** If an attack alert carries a real sanctioning order's id,
   on that order's asset and feature, inside the window, the closer accepts it. ADR 0069 already
   says a forged export is a forged export. The harness does not forge stamps. `MIMIC` in the
   harness carries an empty citation.

## Consequences

The inlet from ADR 0069 now has a decision in front of it: fetch the export row the job log
named, and close only when that row sanctions this alert. Losers stay in the record as open
alerts with a reason, rather than disappearing.

What would reverse this: treating window overlap as closure, or hiding a detection-score change
inside the closer.
