# ADR 0045 — Sentiel ranking shares ADR 0036; narrative confidence stays unset

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Structural remediation (ranking contract + Constitution §3.3)
- **Supersedes:** the clause in
  [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md) that set
  `Narrative.overall_confidence` to the leading hypothesis's uncalibrated confidence; the clause
  in [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md) that copied the
  residual's confidence onto `overall_confidence`. Ranking itself is not superseded.
- **Depends on:** [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)

## Context

ADR 0036 made a ceiling or epsilon tie a refusal on the **reasoning engine** and the **breaking
harness**. Session 1 updated `ReasoningEngine._ranked` and `rank_explanations`. It did not update
`SentielEngine._completed`.

ADR 0023 had restated ranking in a private Sentiel `_ranked` because `ReasoningEngine._ranked` was
private. That copy sorted `(-confidence, template_id, index)` and **never called** `tied_lead_ids`.
On a saturated competing set, `benign_role_change` could uniquely lead because it sorts before
`compromised_account`. Encyclopedia volume 09 claimed Sentiel followed Atlas tie discipline. The
claim was false.

Separately, both engines copied the leading hypothesis's confidence onto
`Narrative.overall_confidence`. Hypothesis confidence is still uncalibrated (`EVIDENCE_STRENGTH`
and template priors are placeholders). Constitution §3.3 forbids surfacing it. Caveats on reports
did not remove the number from the object an operator would read.

This record does not retune `atlas/templates.py`. It does not remeasure known-station **0/16** or
unknown-master **1/4**. It does not earn ≥70%.

## Decision

**1. One ranking function for the narrative path.**

`phos.reasoning.belief.rank_hypotheses` is the ADR 0036 listing for stories:

- sort `(-confidence, template_id, insertion)`
- if `tied_lead_ids` is non-empty and `insufficient_evidence` is in the set, raise the residual
  to the front
- keep the tied rivals listed underneath in the same deterministic order

`ReasoningEngine._ranked` and `SentielEngine._completed` both call it. Sentiel no longer keeps a
local alphabetical ranker.

The breaking harness is unchanged: it still records `tied_leaders` and keeps `leads` false without
inserting the residual into `templates` (ADR 0036, ordinals stay comparable).

**2. `Narrative.overall_confidence` is unset until hypothesis confidence is calibrated.**

The field is `float | None`, default `None`. Engines write `None`. A later calibrated probability
may occupy `[0, 1]`. Hypothesis `confidence` remains on each explanation for ranking and for
`reconstruct_confidence`. It is not copied onto the narrative.

## Consequences

**Gained.** A Sentiel ceiling tie cannot uniquely crown `benign_role_change` by alphabet.
`tests/sentiel/test_engine.py::TestCeilingTieIsARefusal` turns red if `_completed` returns to a
local sort. The ontology object an operator would read no longer carries an uncalibrated
probability. `tests/library/test_evaluate.py` covers the previously untested library runner
without quoting library numbers as CERT or distillation.

**Cost.** Stories no longer expose a single narrative confidence number. Title still names the
leading template (including the residual when it is raised). Traceability of *ranking* is the
hypothesis list, not `overall_confidence`.

The PART 6C reuse freeze still pins intake, featurisation, peers, and models against the 6B
commit. Two ontology files are named exceptions: `store.py` (already opened on main by ADR 0038
causal-edge integrity) and `narratives.py` (this record). The rest of `src/phos/ontology/` stays
frozen.

Known-station unique lead **0/16** and unknown-master unique lead **1/4** are untouched. The cycle
command-lead contract remains unearned.

## Alternatives considered

- **Keep copying residual confidence onto `overall_confidence`.** Honest about a tie, still an
  uncalibrated number on the operator-facing object.
- **Invert Sentiel `template_id` so a malicious explanation wins ties.** Forbidden. Same fake
  winner ADR 0036 refused on Atlas.
- **Retune Sentiel templates.** Out of scope. No CERT contradiction is invented (ADR 0023).

## When to revisit

When labelled explanation data exists to calibrate hypothesis confidence (ADR 0008). Not when a
Sentiel fixture's unique leader looks better after a template edit.
