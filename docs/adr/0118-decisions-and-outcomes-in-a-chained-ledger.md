# ADR 0118 — Decisions and outcomes in a chained ledger

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** learning engine S1
- **Depends on:** [ADR 0001](0001-ontology-value-objects-and-store-enforced-integrity.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md)

## Context

`docs/learning-engine.md` found that PHOS keeps no record of a decision once a run ends: the
`EvidenceStore` is in memory and a `Narrative` carries no detector name or commit. Nothing can be
learned from an outcome that cannot be attached to what was decided. The experiment log only ever
appends, but nothing stopped a hand edit of an earlier line. Elijah asked for every stage to be
built on 12 October.

## Decision

1. **`phos.eval.learning_records`** adds three frozen models:
   - `DecisionRecord`: detector, commit, config, what it was fitted on, the source and its ADR 0117
     role, the scored window and its sha256, the budget, every alert, and the narratives,
     hypotheses and evidence as emitted. It refuses a record whose narratives cite ids it does not
     carry.
   - `OutcomeRecord`: about a decision or a window (a miss has no alert); `kind` with `unknown` as a
     kind and never a default; `status`; `source`; when it happened and when PHOS learned it; what
     it supersedes; corroboration.
   - `AlertRow`.
2. **An operator's word alone cannot confirm an outcome.** `source="operator"` with
   `status="confirmed"` and no corroboration is refused.
3. **`LearningLedger`** is one append-only file, one JSON object per line, each line carrying the
   sha256 of the line before it. It has no update and no delete. Loading re-walks the chain and
   re-applies every rule, so an edited, removed, reordered or forged line is refused. An outcome
   must follow its decision in the file and cannot have been known before the decision was made. A
   correction supersedes one current outcome about the same thing; history is kept.
4. **The experiment log's first 185 lines are pinned** by sha256
   (`tests/eval/test_experiment_log_prefix.py`). Appending keeps the pin true; editing any pinned
   line breaks it.

No detector writes a ledger yet; the S2 record does, for the liar runs.

## Consequences

`tests/eval/test_learning_records.py` covers each refusal, the chain, tampering and a forged but
correctly chained rule break. Nothing is scored. No detector, default, frozen row or log line
changes.

## What would reverse this

A write path that edits or deletes a ledger line; an outcome appended before its decision; or an
operator-only outcome counted as confirmed.
