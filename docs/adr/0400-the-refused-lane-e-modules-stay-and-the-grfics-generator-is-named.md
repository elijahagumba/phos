# ADR 0400 — The two refused lane-E modules stay on disk undeclared, and the GRFICS generator is named

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Half A close-out, and the precondition for the GRFICS programme
- **Supersedes:** nothing. It closes no question ADR 0399 left open and opens none of its own
- **Depends on:** [ADR 0397](0397-an-exploratory-measurement-session-is-declared.md),
  [ADR 0398](0398-a-weak-episode-keeps-its-right-to-place-the-alert.md),
  [ADR 0399](0399-the-first-crossing-rule-is-refused-and-the-delay-splits.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md)

## Context

Half A of ADR 0397 is finished. ADR 0399 refused the first-crossing placement rule on three of four
bars and separated what belonged to the rule from what belonged to the statistic. Two modules now sit
in the tree carrying that history — `phos.atlas.drift_consistency` (lane 3) and
`phos.atlas.placement_consistency` (the rejected rule) — with their scripts and tests, neither
declared and neither imported by anything on the law page.

Two things must be settled before the GRFICS work starts, and neither is a measurement.

**One: what happens to the refused modules.** They are 23.4 KB of code with tests, in a tree whose
rule is that a refused lane does not quietly become infrastructure. Lanes 2 and 3 already sit
undeclared, and a third would make "undeclared" the normal state rather than a flag on it.

**Two: the GRFICS programme needs a generator that does not exist.** `data/registry.json` declares
twenty runs — ten development at 97201–97210, ten held back at 97301–97310 — with a pinned commit,
a hashed licence and a frozen design. `scripts/` contains `icssim/generate_corpus.py` and nothing for
GRFICS. ADR 0144 says the runs are generated *"in a separate testbed (Docker is the example)"* and
that *"a generator that cannot find that order stops"*. That generator has never been written, so the
corpus has `files: 0` and has never been opened.

A third item surfaced while checking the export gate and is recorded here rather than acted on, in
Decision 5.

## Decision

1. **Both refused modules stay on disk, undeclared, and are named as such.** `drift_consistency.py`,
   `placement_consistency.py`, `scripts/lane_e_drift.py`, `scripts/lane_e_placement.py` and their
   tests remain so that ADR 0286's and ADR 0399's numbers stay reproducible, exactly as the residual
   detectors remain so the frozen rows can be regenerated under their own names. **Neither is
   imported by `declared_law.py` or by any law predicate**, and a test asserts that. Neither may be
   promoted without a new declaration: ADR 0399's bar 2 defect, bar 3b and bar 4 all remain open,
   and a rule that passes on a development corpus would still need a held-out declaration before any
   result could leave this tier.

2. **Bar 3b's defect is recorded as a bar defect, not a detector defect, and is not fixed here.**
   ADR 0399 measured that the own-set median rises *because* recall rises — the 17 attacks the
   frozen engine misses have a median delay of 11.0 s alone, so no engine catching more of the
   accumulated classes can lower that figure on this corpus. Changing the bar after seeing that is
   rewriting a criterion to meet a result, which roadmap §5 forbids. **What must not happen is silent
   retirement.** If a later session wants a paired-only criterion, it writes a new bar with a new
   name, states why the old one measured the wrong thing, and reports the old reading beside it.
   That is the same shape as ADR 0290's handling of A3.

3. **The GRFICS generator is declared before it is written, and its rules are fixed here.**
   `scripts/grfics/generate_corpus.py` will:

   - read the run list from `data/registry.json`, not from a constant in the script, so the frozen
     design in ADR 0144 stays the single source;
   - **stop** if the pinned commit's engine does not list the four flows and three analysers in an
     order the generator can read, as ADR 0144 requires — a generator that guesses is refused;
   - write only generated data, to `data/grfics-dev/<seed>/`, and never copy, translate or vendor
     GRFICS source into this repository;
   - refuse to run at all for any `973xx` seed, because the held-back half is generated only against
     a declaration that names it;
   - carry the licence sha256 check (`605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad`)
     so a moved pin stops the run rather than silently changing the corpus.

4. **The first run is development only, and it is one seed, not ten.** `97201` — `physical`/`frozen`/
   `tank_level` — and `97206` — `cyber`/`frozen`/`tank_level` — are the pair this programme exists
   for: the same target, the same event shape, different cause. Scoring starts with that pair and
   nothing else. A ten-seed sweep before the pair is shown to be distinguishable would be spending
   the corpus to avoid the question.

5. **A gap in the export's money gate is recorded and not closed.** The content patterns match a
   currency symbol followed by a magnitude, and five named phrases. They do **not** match a sum
   written without a currency symbol, and they do not match the vocabulary of ownership outside
   those phrases — a record could reason about a cap table, a pre-money figure or a shareholding
   without tripping any of them. This record deliberately does not reproduce the patterns' own
   matched examples, because doing so trips the gate it is describing; that is the gate behaving
   correctly, and it is why the description here is prose. Closing the gap is a real change to the
   gate with its own false-positive risk against the whole export, and it is not done in a record
   whose subject is a corpus generator. It is named here so that the next session which writes a
   commercial record does not assume the gate would have caught it.

6. **Nothing is measured, and no frozen number moves.** No corpus is opened, `eval_runs/log.jsonl`
   is not appended, and v1 stays **8 of 12**. C2 remains unmet: it is a human time trial and its
   sheet is unfilled. P1 remains a blocked human conversation.

## Consequences

- The tree gains a generator and one declaration, and loses nothing. The two refused modules stay
  reproducible and stay out of the law page.
- **GRFICS becomes reachable for the first time.** The registry has named it since 17 October; this
  record is the first that says how the data would actually be produced.
- Bar 3b's problem is now on the record as a *criterion* problem. A future session that wants a
  paired-only bar has a template, and a future session that quietly drops 3b has a contradiction.
- **The honest limit of what GRFICS can say is unchanged.** It is an emulated plant. R4 and ADR 0143
  apply: any result is diagnosis, not proof, and no sentence from it may describe Atlas's strength
  or speed on a real plant.

## What would reverse this

Promoting `placement_consistency` or `drift_consistency` without a new declaration and a held-out
shot; deleting either module and losing ADR 0286's or ADR 0399's reproducibility; retiring bar 3b
without a new named criterion beside it; generating any `973xx` seed outside a declaration that names
it; committing GRFICS source, or any payload, to this repository; running the generator with a pin
whose licence sha256 does not match; or reporting a GRFICS result as anything but a simulated
diagnosis.
