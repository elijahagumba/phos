# ADR 0418 — the sequential column catches all nine walks, and the record calls that a refusal

- **Status:** Accepted
- **Date:** 2026-11-03
- **GENESIS:** E-0001, serving Q-0001
- **Verdict:** **refused**, computed from the measured values against the bars declared on 2026-11-03


## Context

The declaration was committed before the run: commit `96b055339ba13915954a81eb8b223431356d2f7a`. The command was `uv run python scripts/lane_sequential_walk.py --corpus data/phos-icssim-dev4-walk` on `phos-icssim-dev4-walk`, measured from commit `96b0553` and reported in `eval_runs/build/lane-daily/day1-sequential-walk.md`.

Q-0001 asks a question with two answers, and they are exclusive: either the 1-of-9 miss ADR 0313 and
ADR 0315 both record is an artefact of thresholding a per-sample score under an already-saturated
calibration, or it is a property of the walk class that no per-sample comparison can see. ADR 0315
named the mechanism for the first — a full valve error is `ONSET_LEVEL` before a divisor of
2.000000 taken from three training peaks, so the calibrated score sits exactly on a threshold that
requires strictly above 1 — and left open whether that exhausts the miss. The column was retired
rather than diagnosed.

This experiment separates the branches with a statistic that reads order instead of magnitude: how
many samples in a row a commanded setpoint has been moving. `tank_level_max` is a register a write
moves and physics does not, so a legitimate operation changes it once and holds, while the walk moves
it at every sample for 720 samples. The threshold is learned, not chosen: the longest run that
three attack-free runs produced was **1 sample**, one legitimate setpoint write.

**The denominator had to be rebuilt first.** ADR 0315 reports a miss against "1 of 9" but no
committed file names the nine per walk. They were reconstructed from committed code —
`schedule()` in `scripts/icssim/phos_icssim.py` is a pure function of the seed, and the `subfloor`
scenario is unchanged since the generation commit `1c448d7` — and the reconstruction gives **nine
walks over eight runs**, because `subfloor-96815` drew two. That matches both the `events.json`
written by generation and the count the report printed. What it does **not** recover is *which* walk
was missed; that is still not on the record and the champion score may not be re-run to find out.

## Decision

**The result is refused.**

- b1. The order-blind half had something to see: at least one sample in the nine walk windows lies outside the range the three attack-free runs recorded for `tank_level_max`. At 0, every walk was entirely inside what training had already seen, so a per-sample value comparison was not merely miscalibrated — it had no departure to compare, and Q-0001's second branch is the only one left standing. (`walk_samples_outside_range >= 1`) — measured **2331**, met
- b2. The sequential column misses exactly the same single walk ADR 0315's per-sample column missed, and no more. Equal is the result that makes the two statistics directly comparable: with b1 satisfied, a per-sample comparison did have samples outside training, and an order statistic that also misses one walk shows the miss is not simply about which samples crossed a line. (`walk_misses_sequential == 1`) — measured **0**, missed
- b3. The sequential column misses no walk at all, which is the branch where the miss is entirely an artefact of per-sample thresholding and order recovers all nine. This bar and b2 are deliberately incompatible: exactly one of them can be met, so the verdict names which branch the corpus fell on instead of reporting a number that both branches could satisfy. (`walk_misses_sequential <= 0`) — measured **0**, met
- b4. The sequential column's false-alert rate over the eight test runs is no higher than the champion's committed 1.187500 per hour. This is ADR 0301's second bar, applied unchanged: a column that catches more walks by alerting more often has not earned the comparison. (`walk_false_alerts_per_hour_sequential <= 1.1875`) — measured **0**, met
- b5. The corpus scored here holds the nine `subfloor_walk` events ADR 0313's report counted. This is the denominator check. ADR 0315 reports a miss count against a denominator no committed file names per walk, so the first thing this run has to prove is that it scored the same nine and not a different count that happens to be printed under the same name. (`walk_events == 9`) — measured **9**, met
- b6. The denominator ADR 0313 committed to is nine, read back from the record rather than restated from memory. This is a check on the experiment, not on the detector: it is here so that a reader can see the corpus count and the record count agreeing inside one measurement rather than inferring it. (`walk_denominator_committed == 9`) — measured **9**, met

**Failure cases and unexpected results.**

bar b2 is missed: the declaration asserted the sequential column would miss exactly the one walk the per-sample column missed, and it missed none. The hypothesis that the sequential statistic merely matches the per-sample column on this corpus is refuted. No bar was moved and the run was not repeated.

**Notes.**

The learned threshold was 1 sample, the longest run on tank_level_max across three attack-free runs. Zero false alerts is structural rather than earned: a setpoint event in this generator is a single write, so its run is 1 and the strict > at threshold 1 excludes it. The order-blind count of 2331 (minimum 258 of 720 per walk) is close to guaranteed by construction, since the walk spans the declared band 6.5-7.5 while three normal runs holding six setpoint draws recorded only [6.600000, 7.240000]. The nine walks were reconstructed from committed schedule() code, not from a report; no committed file names which one the champion missed, and that gap remains.

## Consequences

**What the corpus answered.** The sequential column caught **9 of 9** and raised **0** budgeted alerts
over 57600 s, against the per-sample column's 1 of 9 and 1.187500 per hour. Read naively that is the
first branch: order recovered every walk the per-sample score missed, so the miss was a thresholding
artefact rather than an invisible class. This record does not make that claim, for the two reasons in
the report: the zero false-alert count is close to structural in this generator (a `setpoint` event is
a single write, so its run is 1, which the strict `>` at a learned threshold of 1 excludes), and the
order-blind count of 2331 was predictable from declared constants before the run (the walk spans the
whole band 6.5–7.5 while three normal runs carrying six setpoint draws recorded only
`[6.600000, 7.240000]`). Neither number is evidence that the column is quiet or accurate on a real
plant.

**What the corpus did not answer, and the record cannot express.** Q-0001's two branches are
mutually exclusive, and the verdict model has two values, `kept` and `refused`. So the declaration
had to encode the fork as two bars over the same metric — b2 asserting one miss, b3 asserting none —
which are incompatible by construction. The run landed on b3. **That verdict could not have been
`kept` for any measured value**: at 0 misses b2 fails, at 1 miss b3 fails, and at 2 or more both
fail. The record therefore reports **refused** for an experiment whose declared discriminating bar
was *met*, and calls an answer to Q-0001 a refusal. The substantive outcome — the branch Q-0001 asked
about — is in b3 being met, and a reader who sees only `outcome: refused` loses it. `inconclusive`
would not have fixed this either; the run was not inconclusive, it was decisive and mislabelled.

**The denominator is the second strain.** A bar measured against a denominator no committed file
reconstructs is not a bar, and ADR 0315's "1 of 9" was exactly that. Rebuilding it from `schedule()`
worked, but only because the generator happens to be deterministic and unchanged; had either changed,
the nine would have been unrecoverable and this cycle would have had to stop at STEP 1. The record
retained the number and discarded the identities.

**Not a detection claim, not a daily leap.** Simulated diagnosis (ADR 0073). `M_champion` stays 1 and
ADR 0313's champion score is not replaced or re-run. `atlas-sequential-consistency` is a name, not a
promotion. Held-out stays unopened. v1 stays 8 of 12. Nothing here is a field rate, nothing is ≥70%,
and no confidence is calibrated or surfaced.

---

## Where GENESIS was awkward

Answering STEP 7 from what happened in this cycle, not from the proposal.

**A bar failed to be evaluable, and `refused` mislabelled a non-result.** This is the strongest
strain found and it is structural, not cosmetic. `Verdict.outcome` is `Literal["kept", "refused"]` and
`compute_verdict` returns `kept` only when *every* bar is met. A fork — two mutually exclusive
hypotheses, which is what Q-0001 is — cannot be expressed without one hypothesis's bar failing, so
every forked experiment is guaranteed to record `refused` no matter which branch the data lands on.
The bar that carried the answer (b3) is recorded as met, but only inside `per_bar`, and no rendered
section says "this experiment answered the question". The proposal's `inconclusive` (§162/§405) would
not have helped here either, because the run was not inconclusive: it was decisive and the schema had
no word for "decisive, and the thing decided was one of two".

**The refs needed to be typed.** Q-0001's `refs` are eight bare strings, and this cycle needed three
different things from them: read a commit's file at a revision (`1c448d7` for the generator), read a
report's numeric content (`day1-walk.md`), and resolve a citation for `audit_evidence.py`. A bare
path cannot say which. The reconstruction in the Context section depended on knowing that
`scripts/icssim/phos_icssim.py` at `1c448d7` is the generator that produced the corpus, and nothing
in Q-0001's refs says so; that was established by reading `git diff 1c448d7 HEAD --`. Three typed
refs — `{kind: revision, sha}`, `{kind: report, path}`, `{kind: source, path}` — would have made the
denominator check mechanical instead of investigative.

**The rendered ADR was rewritten by hand in three places.** The Context section (the fork, the
mechanism, and the denominator reconstruction), the Decision's surrounding prose, and the whole
Consequences section. The renderer filled the metadata, the six bar lines with measured values, the
failure case and the notes — all of which were correct and saved transcription. It did not, and by
its own docstring should not, write the branch interpretation. What it *could* do without inventing a
conclusion is render `per_bar` as a sentence, because "b3 met, b2 missed" is data, not judgement.

**What there was nowhere to put.** Four things. First, the reconstruction of the nine walks: it is
load-bearing for b5 and b6 and it has no field, so it lives in the report and the Context section as
prose. Second, the note that zero false alerts is structural in this generator — a caveat that
changes how the headline number should be read, and which the `notes` string carries only because
`Measurement.notes` is free text. Third, the prediction that the order-blind count was near-guaranteed
by declared constants: it is a *pre-run* observation, and it was written into the declaration's
`why_it_might_be_wrong` only because that field happens to be prose. Fourth, and most awkwardly, the
fact that no committed record names which walk was missed — a gap in ADR 0313's own evidence that
this cycle discovered and could only record as a limitation.

**Two smaller things, found by doing it.** The rule says a measurement is added "by writing a new
record, never by editing the one that was committed", but `genesis result` writes the measurement
into `E-0001.json` in place. Read literally those disagree. What actually happened is the reading
that makes both true and is worth stating: the `declared` block is byte-identical across the commit
(verified by diff), and only `phase`, `measured`, `verdict` and `declaring_commit` were filled. So
"frozen" means the declaration is frozen, not the file. That should be said in the rule, because a
reader checking the rule against the diff finds a contradiction that is not one.

And the gate had no opinion on the command until the declaration existed, but it also would not have
*stopped* anything: this session ran unguarded by construction, because the Cursor hook file lives on
this branch and Cursor reads its wiring from the workspace root (ADR 0417). The one check in this
repository that refuses was therefore absent for the one cycle that most needed it to be present, and
the declaration was committed before the run because this session read the rule and not because
anything enforced it. That is the honest description of what protected this result.

---

Rendered by `scripts/genesis.py adr E-0001`. A refusal is a result; it is recorded the same way a kept result is, and is not removed from the record later.
