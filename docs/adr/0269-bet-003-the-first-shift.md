# ADR 0269 — Bet 003: the first shift, and why A3's fraction was the wrong instrument

- **Status:** Accepted. **The bars are frozen by Elijah's decision of 20 October 2026**, taken on
  the shape proposed here and before any `atlas-first-shift` measurement exists. From here, a bar
  changed after a measurement it judges is a new bar with a new name, reported beside the frozen
  one. The freezing commit is recorded at the end of this file. Nothing here moves a v1 row.
- **Date:** 2026-10-20
- **PART:** after v1; a new named bar reported beside the frozen criteria, never in place of one
- **Depends on:** [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md),
  [ADR 0164](0164-the-held-back-maintenance-check-is-declared.md),
  [ADR 0212](0212-a3-queue-rank-is-declared.md),
  [ADR 0230](0230-v1-stands-at-six-of-twelve.md),
  [ADR 0234](0234-the-familiarity-queue-gate-is-not-run.md)

## Context

A3 is recorded as not met: 57 of 203 attacks had a true alert in the top 10% of their shift's
queue, against a bar of 102 (ADR 0212). ADR 0234 fixes that verdict whatever a later look finds.
Two attempts have been made at it: ADR 0068 scored three severity keys and refused all three, and
ADR 0233's `familiarity` reorder did not beat the champion.

This record re-read the committed result file, `eval_runs/build/v1/atlas/a3-queue-rank.json`. No
corpus was opened, nothing was scored, nothing was appended to `eval_runs/log.jsonl`. The file
carries each attack's rank, its shift's queue length, and the top-slot count the fraction produced.
Those three columns say something the pass count does not:

| What the file says | Number |
| --- | ---: |
| Attacks with a true alert in their start shift | **172 of 203** |
| Attacks with no true alert in their start shift | **31 of 203** |
| Median rank of a true alert, where one exists | **3** |
| 90th percentile of that rank | **5** |
| Worst such rank across all five corpora | **9** |
| Attacks whose true alert was the loudest of its shift | 48 of 203 |
| Median attack-shift queue length | **7 alerts** |
| Attack-shifts whose whole queue is 8 alerts or fewer | **67%** |
| Attacks for which top 10% meant exactly one slot | **81%** |

The operator budget is 8 alerts a shift (`docs/v1-roadmap.md` §2.0, frozen). The median attack
shift carries 7. **The queue is shorter than the budget**, so the operator reads all of it, and
every attack that alerted in its start shift at all did so within the first 9 alerts.

A3 asked for the top 10% of that queue. On a 5-alert shift that is one slot; on 81% of attacks it
was one slot. The criterion therefore demanded that the attack be the single loudest alert of its
shift, which is a far stricter thing than the budget it was written to express. Worse, as a
fraction of a queue the detector itself sizes, **it is easier to pass with a noisier detector**: a
longer queue buys more top slots. A bar that rewards raising the alert count points away from the
product.

Two attempts have now been spent engineering against an instrument that was measuring the wrong
thing. The misses, meanwhile, were never the subject of a bar at all: 31 attacks produced no true
alert in the shift they began in, and no reordering can reach them.

## Decision

**Bet 003 is `atlas-first-shift`.** Frozen as the four bars below. One question, in units an operator feels: *when an attack
begins, does the shift it began in contain it, and can the person on duty act on what they are
handed?* Four measurements, each its own result name, none of them overwriting a frozen row.

| Key | Result name | Today | Proposed bar |
| --- | --- | ---: | --- |
| Coverage | `atlas-first-shift:coverage` | 172 of 203 | at least **187 of 203** (halve the 31 misses) |
| Position | `atlas-first-shift:position` | median 3, p90 5, max 9 | no attack's first true alert beyond **8**, the frozen budget, on any corpus |
| Story | `atlas-first-shift:story` | not built | **one entry per attack**, carrying its competing set and the one fact that would settle it, every sentence citing a stored evidence id |
| Load | `atlas-first-shift:load` | median 7 | the median attack-shift queue **does not rise** on any corpus |

Coverage and load are judged together, and that is the point of the bet: recall bought by
lengthening the queue fails, and a short queue bought by missing attacks fails. Position replaces
A3's fraction with the absolute count the budget is written in. Story is the unattempted part.

**What this retires.** The top-10%-of-queue fraction is retired as an instrument, with the reason
above on the record. It is not retried, and no number here is compared to 57 of 203.

**What this does not do.** v1's A3 stays **not met** (ADR 0212, ADR 0230, ADR 0234). This is a new
bar with new names reported beside the frozen criteria. v1 stays 8 of 12. Nothing in Bet 003 is a
v1 criterion and no v1 row moves on its result.

**Where severity would come from.** ADR 0068 named three candidates and said none was started:
persistence of an event across windows, coincidence across subsystems, and the absence of a
covering work order. Two months on, `RANKING_KEYS` is still `("magnitude", "weight", "breadth")`
and `src/phos/atlas/queue.py` imports neither `work_orders` nor `consistency`. Meanwhile A5 built
the work-order inlet (158 of 180 maintenance alerts close with a citation, 0 of 80 attack alerts
close, ADR 0164) and lane D built consistency evidence that separates explanations on 20 of 20
development and 20 of 20 held-back seeds. **The evidence ADR 0068 asked for now exists in the
reasoning layer, and the queue cannot see it.** That wiring, and the narrative unit it makes
possible, is the engineering this bet buys.

**Tiers.** Develop on `hai-20.07`, `phos-icssim-dev`, `batch-distillation`, `data4cyber` and newly
declared synthetic seeds, per `docs/rules/data-tiers.md`. The five-corpus score is **one look**: it
needs its own declaration ADR committed first, and Elijah's one-look exception for HAI 21.03,
22.04, 23.05 and BATADAL, exactly as ADR 0234 required for the familiarity gate.

**The risk this bet carries, named.** The misses are not where we may look. Of the 31, **15 are
in HAI 23.05, 10 in HAI 21.03 and 5 in HAI 22.04 — 30 of 31 in corpora that must never be iterated
on. HAI 20.07 holds one and BATADAL none.** So the shapes the coverage bar is about cannot be
studied directly without spending validation looks, and spending them is how a bar stops being a
bar. The mechanism must therefore be built where we may look: the synthetic plants, which can be
made to produce a first-shift miss deliberately, plus `phos-icssim-dev` and HAI 20.07's single
case. A coverage bar set this way is a genuine bet, not a target we can creep up on. If Elijah
would rather not bet blind, the honest alternative is to declare coverage as a **measurement with
no bar** on the one look, and set the bar afterwards for a second look on a corpus not yet
registered.

**Order.** A7's regenerating command first, because a v2 claim nobody outside can recompute is not
a claim; then the severity sources on development tier; then the narrative unit; then one declared
look.

## Consequences

If this passes, Atlas has the first operator queue the project has been able to hand over: a shift
whose whole list is readable, containing the attack, as stories rather than rows. If it fails, the
refusal is the result, three more severity candidates are eliminated by measurement, and the 31
misses are named as a detection problem rather than a ranking one.

The programme order does not change. P1 stays the blocked human conversation, and Intelligence,
API and UI stay forbidden until a partner queue is staffable.

## What would make this bet meaningless

Tuning anything on the four validation corpora. Buying coverage with a longer queue, or a short
queue with misses. Counting one attack's narrative twice to make the story bar pass. Surfacing an
uncalibrated hypothesis confidence in a queue entry. Quoting any `atlas-first-shift` number as an
A3 pass, as a 2 to 3 pages a day claim (refused, ADR 0048), or as a real-plant result.

## What would reverse this

A bar restated as a fraction of a queue the detector sizes. Editing the champion, `grouping.py`,
`_shrink`, `joint_k`, `dwell_samples` or `templates.py` priors to move a number here. Running the
one look before its declaration is committed.

## Freeze record

The bars in the table above were frozen by the commit that changed this record's status from
Proposed to Accepted: **`f5257c732fcd8bdfb9af69054b23e32d97b95301`**, recorded in the commit that follows it. No
`atlas-first-shift` number existed on either commit. A declaration ADR for the one look, naming
the command, the result files and the one-look exception, comes separately and later.
