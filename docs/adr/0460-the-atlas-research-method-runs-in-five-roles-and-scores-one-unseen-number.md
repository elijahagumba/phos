# ADR 0460 — The Atlas research method runs in five roles and scores one unseen number

- **Status:** Accepted
- **Date:** 2026-11-22
- **PART:** Method. Installs the research method and records its first scout pass. No code, no
  corpus, no measurement
- **Supersedes:** nothing
- **Depends on:** [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0285](0285-the-corpus-gains-a-coordinated-low-amplitude-class.md),
  [ADR 0420](0420-one-atlas-engineering-roadmap-and-the-rest-are-closed-or-parked.md),
  [ADR 0423](0423-h2-opens-for-declarations-only-and-the-scoring-still-waits-for-the-bid.md)

## Context

Since ADR 0412 the record can refuse an undeclared or a spent score instead of warning about it.
What it cannot do is stop one chat from building an idea, choosing the data it is judged on, and
judging it. The clearest evidence for separating those jobs is already on the record: the S7 lane
took five red-team rounds, and four of them found a real defect in a version a judge had already
passed ([ADR 0348](0348-s7comm-dissection-is-judged.md)). Every one was found by someone whose job
was to break the work.

On 22 November 2026 Elijah made a role-separated method the live way Atlas research is run, not a
trial. This record installs it and records what its first scout pass found.

## Decisions

1. **Five roles, one rule file each.** Scout, Builder, Breaker, Referee and Elijah, as
   `.cursor/rules/method-*.mdc` with `docs/rules/method-*.md` symlinks imported by `CLAUDE.md`, the
   convention of [ADR 0265](0265-the-always-apply-rules-load-themselves.md). Each agent role is its
   own chat, opened on its own checkout and never reused across roles or weeks. Builders work on
   development data only and write no verdict. The breaker never opens `src/phos/atlas/`. The
   referee holds the sealed data, scores once and never edits `src/`. Elijah's page lists what the
   agents hand to him instead of deciding: direction, programmes, partners, and anything needing a
   human or a real plant.

2. **No parallel machinery.** Ideas are declared with `scripts/genesis.py declare`, runs pass
   `scripts/genesis.py gate`, verdicts are computed by `scripts/genesis.py result`, tiers come from
   `docs/rules/data-tiers.md` through the gate's own resolver, the breaker's findings use the
   referee's existing findings registry, and the synthetic plants' sealed seeds stay in the
   referee's seed vault. The method adds roles and a calendar, not a second record.

3. **One number, unseen catch.** The attacks Atlas puts in front of the operator, within eight
   alerts a shift, on a sealed ICSSim batch, over the six classes ADR 0276 scored. Starting value
   **87 of 120**, with **6 of 40** harmless events drawing an alert, copied from ADR 0276 and not
   recomputed. A kept verdict needs all three: unseen catch above 87, harmless alerts 6 or fewer,
   and no class below its starting count. It is a new target under a new name, not A3 or any other
   v1 criterion. The proposed batch is `phos-icssim-heldout2` (ADR 0285), checked on 22 November
   2026 to have never been generated, committed or registered. The starting engine is not run on
   it, because ADR 0285 Decision 6 says lane 1 is not rescored there, so a candidate is compared
   with the copied figures and the difference between the batches is reported beside it.
   `docs/method/scoreboard.md` holds the number and the evidence.

4. **Two held-back halves are not called unseen.** The disk's access times show that every text
   file in `daypsci-v1-heldout` and `fdia-synthetic-microgrid-heldout`, with files in every other
   corpus folder including the never-tier ones, was read in one four-minute sweep on 17 November
   2026, after [ADR 0411](0411-both-splits-are-built-and-one-verification-glob-was-wrong.md) had
   recorded that none had been. No record states the cause. Neither half hosts the number, and
   neither is called unseen until Elijah establishes what ran.

5. **The week.** Declare by commit, build on development data, stop and commit, break, score once
   in a fresh chat, record every result including refusals, then land in one change.
   `docs/method/weekly-cycle.md` is the procedure. All of a week's work stays on branches until it
   lands, so the public surfaces of ADR 0044 move once a week, in the landing change, and that
   record's rule, that every advancement on `main` moves them, still holds.

6. **First scout pass.** `docs/method/scout-001.md`. The three weakest measured areas are frozen
   readings (3 of 20), maintenance look-alikes (5 of 20) and harmless alerts (6 of 40), all from
   ADR 0276. Ranked: the declared drain law of
   [ADR 0372](0372-the-physics-laws-are-declared-from-the-thirteen-tags-and-the-inlet-balance-is-refused.md)
   first, a booking check on forced valve modes second, and the controller-logic candidate, rules
   derived from a structured-text controller program and checked against recorded operation,
   third. Every live idea needs a decision only Elijah can take before a builder may start: the
   first because ADR 0423 keeps H2's scoring closed until after 6 January 2027 or a later record,
   the second because it is a new law outside an open programme, the third because H1 covers only
   the pinned ICSSim program. No builder work was started.

7. **Review at week 4.** After the fourth week lands, Elijah answers five questions and keeps,
   changes or stops the method: (a) did unseen catch move on a sealed batch, and did the kept result
   survive the breaker; (b) how many ideas ended on their own development falsifier before a
   sealed batch was spent; (c) did any role need to cross its boundary, and what stopped it, or did
   not; (d) is there a supply of sealed batches, since `heldout2` is spent by its first scoring;
   (e) has the 17 November sweep been explained. A change is a new record; this one is not edited.

## What this record does not do

- Run any scoring, open any held-out or never-tier data, or generate a corpus.
- Move a frozen number. v1 stays 8 of 12.
- Edit `src/phos/atlas/`, or any code.
- Open H2's scoring, H3 or H4 (ADR 0423), lift the plan's limits on new laws, reorder the one
  roadmap of ADR 0420, whose first item is still the ADR 0316 debt, or start any builder work.
- Add the method's roles to `swarm[]` in `.phos_roadmap_state.json`, whose only writer is
  `scripts/roadmap_state.py`. The file-scope guard therefore does not know them.

## Consequences

- The gate allows a committed, unjudged declaration's command for whoever runs it; it does not know
  which role is running. Builders and the breaker are kept from the sealed batch by its absence from
  their checkouts, so `scripts/build_lanes.sh`, which links every ignored data file, is not used
  for method worktrees. The builder rule gives a tier-checked recipe instead.
- Hooks load only when Cursor opens a checkout as its workspace root
  ([ADR 0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md),
  [ADR 0419](0419-the-gate-is-wired-where-cursor-looks-and-the-variable-is-gone.md)). A role chat
  opened on a parent folder has no gate and no guards.
- The tier resolver gives a spent corpus the same score-once tier as an unopened one, so the referee
  checks the rule's "spent" by hand.
- The first scoring needs Elijah: generating `heldout2` needs the ICSSim loopback addresses, which
  need an administrator password
  ([ADR 0274](0274-the-icssim-corpus-exists-and-its-held-out-half-is-sealed.md)).

## What would reverse this

Scoring a candidate on a batch a builder or the breaker could reach; rerunning a declared command
after seeing its result; moving a bar after a declaration is committed; leaving a refusal off the
scoreboard; running the starting engine on `heldout2`; calling either held-back half unseen before
the 17 November sweep is explained; or updating the public surfaces from work that has not landed.
