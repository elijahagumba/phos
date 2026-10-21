# ADR 0049 — Split scorecard: public files vs partner site

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C0
- **Supersedes:** the single-stamp reading of
  cycle-eom-targets (lab record, not published) that treated
  ≤2–3 Atlas pages/day, ≥70% command lead on every public capture, and ≥10×
  joint reduction on every dataset as this cycle's pass/fail on public ZIPs.
  Frozen measurements (0/16, 1/4, CERT 6B, distillation 18.72, ADR 0040/0046/0047/0048)
  are **not** superseded.
- **Depends on:** [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0048](0048-distillation-declared-phase-is-louder.md),
  category-defining roadmap (lab record, not published)

## Context

The speech contract is still the product: competing explanations, reconstructable
evidence, silence when the data cannot support a call, Atlas for OT-normal and
Sentiel for org-normal.

The cycle *numbers* treated public ICS and CERT files as if they were a staffed
plant: long attack-free baselines, command-action labels, enough incidents to
calibrate, a recipe dense enough to identify a mode. They are not.

Measured:

- Distillation 2–3/day is refused even after the declared `Executing step` was
  joined (ADR 0048): phase-conditional is louder than pooled 18.72 FP/hour.
- Command ≥70% on every public capture with network traffic has no labelled
  public command corpus (ADR 0040). Known-station unique lead is **0/16** by
  indistinguishability, not by a missing ranker. Unknown-master **1/4** is a
  D2 diagnostic.
- Joint reduction is **8.6×** (distillation) and **6.6×** (Data4Cyber), not a
  10× stamp on every file.
- CERT at 48 alerts is precision **0.104**. Peer-group advantage is retired.

Keeping those stamps as "the contract" trained agents to chase figures the files
cannot honestly give.

## Decision

### Decision 1 — Two scorecards, one speech contract

**Public files.** Success is honest measurement, including refusal. Joint vs
univariate is a **table** per corpus, not a 10× stamp. Command ranking stays
split: known-station 0/16 frozen; unknown-master 1/4 stays a diagnostic until a
labelled public command corpus exists. Distillation 2–3/day stays refused on
the public ZIP. CERT r3.1 6B @ 48 remains the Sentiel ruler. 3W is faults.
Data4Cyber is process-phase. S7 process parquet is unlabelled.

**Partner / estate.** Success is a characterised queue, not a pre-committed
2–3 or 30–50. Those numbers remain the conversation in
`docs/design-partner-brief.md`. High-confidence 0.6 only when held-out precision
supports it.

The speech contract does not soften. Insufficient evidence stays honourable.
Templates stay locked against matcher/prior retune to chase a headline.

### Decision 2 — Activate the category-defining programme at Session C1

Session C0 is this record. `.phos_roadmap_state.json` `current_session` becomes
**`C1`**. Command-lead `sessions_completed` remains `[1, 2, 3, 4, 5]`. Those
frozen keys do not move.

Next engineering action is Session C1: make the current joint-model assumptions
executable. It is not "hit 70%," not "2–3/day on distillation," and not
Intelligence / API / UI.

### Decision 3 — What 70% and 10× are now

- **≥70% unique command lead** is not a public-ZIP pass/fail. It remains a
  possible later measurement on a labelled command corpus with issuer kinds
  apart and the standing caveat. It is **forbidden** as a target on known-station
  D2 writes (indistinguishable evidence). Completing command-lead sessions 1–5
  still does not earn it.
- **10× joint vs univariate** is not a stamp. Publish the ratio per corpus.
  8.6× and 6.6× stay quoted as measured, with "not 10×" attached.

## Consequences

**Gained.** Agents are no longer instructed to earn impossible ZIP stamps.
Clock A of `docs/category-defining-roadmap.md` can start at C1.

**Cost.** Quiet-queue and high-reliability explanation separation stay
partner-gated. That was already true; this record says so in the lock files.

**Unchanged.** 0/16, 1/4, CERT 6B, ungated distillation 18.72, ADR 0040 refuse,
template lock, no Intelligence/API/UI, no pooling, no surfacing uncalibrated
hypothesis confidence.
