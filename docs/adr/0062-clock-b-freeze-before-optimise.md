# ADR 0062 — Clock B: freeze the ruler before anyone tunes against it

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Clock B / PHOS Benchmark v1
- **Supersedes:** nothing
- **Depends on:** [ADR 0031](0031-distillation-budget-refused-without-declared-phase.md),
  [ADR 0032](0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

Clock A (command-lead sessions 1–5) is complete. Known-station unique lead is **0/16**.
Unknown-master unique lead is **1/4**, a D2 diagnostic with
`ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. There is still no labelled public command corpus
(ADR 0040). Distillation 2–3 alerts/day is refused (ADR 0031). CERT 6B at 48 alerts remains
precision **0.104**; `:precision` **0.083** is a measured loss. Hypothesis confidence is
uncalibrated.

The architectural spine is real. What a serious reader still cannot say is: this stack is
better under a protocol that was locked **before** anyone tuned it.

P1 (design-partner ICD) remains a **human** conversation. Clock B is research: eval contracts,
adapters, and models. It does not skip P1 by building Intelligence, FastAPI, UI, or a TAP
inside `src/phos`.

## Decision

**1. Freeze PHOS Benchmark v1 before new detector work.**

The protocol lives in `docs/eval/phos-benchmark-v1.md` and `phos.eval.benchmark`. Cited cells
copy already-published public rows (HAI Mahalanobis **646.58** FP/hour, distillation ungated
**18.72**, CERT 6B **0.104**). REFUSED cells are measurements: the files cannot support the
claim. Seed **11** (HAI public split) is not a search dimension. Threshold search on this
split is forbidden.

**2. Clock B does not touch command-lead freeze keys.**

Known-station **0/16** and unknown-master **1/4** stay unpooled. Completing Wave 0 does not
earn ≥70%. Do not write "we will hit 70% / 10× / 2–3/day."

**3. P1 stays blocked on a human conversation.**

`current_session` is **P1**. `clock_b.status` is **open**. Partner data is the only honest
path to a staffable 2–3 pages/day conversation and to command-action labels public ZIPs do
not have.

**4. Ablation profiles are names, not a licence to retune public knobs.**

Gaussian → … → reachability (Atlas) and counts → … → aggregation with peer context retired
(Sentiel) may be scored on fixtures. Their counts must never be copied onto public log names.

## Consequences

**Gained.** A single table that can publish wins, losses, and refusals. Transfer HAI→BATADAL
is REFUSED until a declared shared plant-state schema exists. That refusal is success.

**Cost.** Wave 3 models may lose to Mahalanobis. If they do, Mahalanobis wins. No PyTorch
unless a later ADR says a reconstructable model must compete on this frozen bench.

Command-lead remains unearned. Intelligence / API / UI remain forbidden.

## Alternatives considered

- **Skip P1 and start product surface.** Rejected. A TAP without a partner map is theatre.
- **Remeasure HAI inside the benchmark CLI.** Rejected. The public rows are already logged.
  Recopying them as CITED is the freeze. Searching thresholds on seed 11 would unfreeze them.
- **Pool 0/16 with 1/4 so the table has one command number.** Rejected. ADR 0034 / 0035.
