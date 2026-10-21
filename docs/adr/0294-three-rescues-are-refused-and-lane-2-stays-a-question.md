# ADR 0294 — Three rescues are refused, and lane 2 stays a question

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Build brief E, the four continuations
- **Supersedes:** nothing
- **Depends on:** [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0285](0285-the-corpus-gains-a-coordinated-low-amplitude-class.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0288](0288-the-linear-predictors-misfit-is-load-bearing.md),
  [ADR 0293](0293-step-0284-would-reproduce-the-frozen-alerts-on-a-process-table.md)

## Context

The brief says a lane that loses is recorded as a loss and its idea is not carried into step
0283. Lane 1 passed and the gain is attribution, shallow by its own record (ADR 0276). Lane 2
tied because the corpus could not ask its question (ADR 0285). Lane 3 caught more attacks and
failed the delay half of its bar (ADR 0286). Lane 4 got quieter and caught fewer (ADR 0288).
Four continuations were left as scope choices.

The rule those choices are made under is the one the programme already uses. A bar with two
halves is failed when either half fails. The reading taken before a result is the honest one.
An attack is not defined by the detector that is supposed to catch it. A simulated result is a
diagnosis. The frozen detector is not edited.

## Decision

**The three ways of keeping a loss are refused. The one unasked question stays unasked until
it has its own declaration.**

1. **Step 0283 is not assembled.** The only lane that passed already has a name,
   `atlas-command-consistency`, and a held-out result. A second name with the kept lane inside
   it would be the "significantly stronger" claim. One shallow lane is not that claim. 0283
   stays unwritten.
2. **Step 0284 is not taken.** ADR 0293: on a process table the kept lane reproduces the frozen
   alerts. The seen corpora stay unopened. 0284 stays unwritten, so a later declaration can
   still spend it if the question has actually changed.
3. **The delay-aware placement rule is not built.** It would exist to make lane 3's 53 of 70
   declarable after the delay half had already failed. That moves the bar to meet the result.
   0279 and 0280 stay unwritten. ADR 0286 stands.
4. **Lane 4's two scores are not both kept.** The bend caught fewer attacks. Keeping the linear
   column beside it would hide that loss, and an appended column is the case ADR 0286 already
   decided. 0281 and 0282 stay unwritten. ADR 0288 stands.
5. **Lane 2's plant-model attacker is the only continuation that asks something new, and this
   record does not build it.** The lane is untested, not refuted. The next record, committed
   before any generation, defines the class on the plant's own level-flow relationship, in
   plant units, with the champion's threshold not mentioned, on new seeds, without adjusting
   any magnitude in ADR 0285. This repository does not contain that relationship as a formula,
   and inventing one here would be the forbidden attack written in different units. 0277 and
   0278 stay unwritten until that declaration exists.

Nothing was generated. No corpus was opened. No detector was edited.

## Consequences

The programme's result stays what was measured. Lane 1 is kept, as attribution, on a simulated
plant. Lanes 3 and 4 are refusals. Lane 2 has no class that can ask its question. v1 stays 8
of 12. `eval_runs/log.jsonl` was not appended.

## What would reverse this

A second lane that passes the bar as that bar was written, which is what 0283 is for. A
declaration, on a corpus that lane has not been scored on, written before any number from the
new rule, for a placement function or for both of lane 4's scores. An assembler that builds
command messages from the process columns, which is the condition ADR 0293 already names for
reopening 0284. Or the plant-ratio declaration described above, after which lane 2 may be
generated and, only then, judged.
