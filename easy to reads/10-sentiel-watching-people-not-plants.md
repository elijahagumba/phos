# Sentiel: watching people, not plants

**What this is:** the enterprise engine — behaviour of **people** (and their roles and hosts),
scored as claims about a person-day, then explained with a competing set.

**Why it exists:** Atlas’s idea of normal is a recipe. An office’s idea of normal is a workforce.
Sentiel was built **data-first** so it would not repeat Atlas’s mistake of growing a reasoning
layer before a real labelled corpus existed.

## Catch the right person, not “someone in the building”

CERT Insider Threat r3.1 (CMU/SEI) is a large synthetic organisation: about **1,000 users**,
**17 months**, **two labelled insiders**. If you only ask “did we alert *sometime today* in this
company?”, a detector that pings **everyone** would look like it “caught” the insider while being
wrong 99.8% of the time.

So ground truth is **entity-scoped**: the alert has to name the **same person** the label names,
in the same window. Analogy: catching a thief means identifying *who*, not noting that a theft
occurred somewhere on campus.

The files also disagreed with their own documentation (email headers without a `user` column, and
so on). **The file header wins.** That discipline is the same as industrial intake.

## Comparing you to your past — and not leaking the future

Starter features are simple daily counts (logons, after-hours, files copied to removable media,
and similar). **Enrichment** adds: how today’s count sits against *your own* recent history, whether
the trend is rising, and a little about new counterparties.

History is **causal**: today’s score cannot include today’s data in its own baseline. That would be
marking your own exam.

A wide feature set without a new scoring shape **exploded false alarms** — each extra thermometer
is another chance to shout on a quiet day. That negative result is kept.

## One score per person-day, not one alarm per feature

The scoring change that made a wide set operable: **aggregate** many feature contributions into
**one score per person per day**, with caps so a single clamped feature cannot dominate.

On CERT r3.1, that shape reached much quieter budgets than alerting on every feature. At a budget
of **48 alerts**, precision was about **10%**, catching **one of the two** labelled insiders
(414× a naive floor at that volume). The narrower starter counts were still ahead at some louder
budgets. None of this is a deployable SOC product. The contract remains **≤30–50 alerts/day**
with recall actually earned.

## Peers: nurses compared with nurses

**Peer groups** are cut from a **declared** attribute (role), never inferred from behaviour
(“these people email alike, so they are a team”). Inferring groups from the same activity you then
score would be circular.

Each person is compared with **other members’ past**, leave-one-out, so you do not sit in your own
peer average.

**Measured result: peer features did not improve detection** on r3.1. CERT’s own scenario text
describes both insiders as departures from **their own past**, not from their colleagues’. The
corpus contains **no labelled peer-relative positive**. The claim is **retired in place** until a
corpus can test it. A later probe of CERT r4.2 found **zero** peer-relative positives there either;
what r4.2 *would* unlock is a cleaner test of **compromised account vs insider**, because some
labelled cases are “the account holder is not the actor.”

## Reasoning: one person at a time

The shared reasoning spine identified a hypothesis by template only — correct for **one plant**.
Sentiel watches **many people**. Without a fix, colleague A’s faint oddity and insider B’s loud
week merged into **one** “compromised account” story.

The fix: **one reasoning pass per entity**. Untouched explanations stay on the report at their
prior (losers remain visible). A competing set with the losers deleted is a **verdict**, and is
forbidden.

The five explanations:

| Template | Everyday meaning |
| --- | --- |
| `benign_role_change` | Legitimate change of job or access |
| `peer_anomaly` | Unusual versus declared colleagues |
| `compromised_account` | Someone else is driving this account |
| `insider_misuse` | The real person is misusing access |
| `insufficient_evidence` | Refuse to pick |

Hypothesis confidences remain **uncalibrated** and must not be surfaced as probabilities. Stories
leave `overall_confidence` unset
([ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md)). When two
contentful explanations sit at the same ceiling, Sentiel **raises insufficient evidence** rather
than naming `benign_role_change` because it sorts first — the same rule Atlas uses
([ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)). 6C changed
**explanation**, not the detection ranking from 6B.

## Busy days should not lead the queue

Equal-weight scoring still treats a backup, a Saturday login, and a first thumb-drive connect as
the same size of shout. An opt-in **precision policy** down-ranks volume, off-hours, “unlike me
but like my team,” and single-family days — without inventing a contradictory template CERT
cannot support, and without moving the 10% reference row.

That policy has now been **measured on CERT r3.1**. At 48 alerts it **lost** to the 6B scorer
(precision **0.104 → 0.083**, still one of two insiders). 6B remains the headline.
`:precision` is an experiment name, not the SOC contract. See
[ADR 0032](../docs/adr/0032-precision-policy-lost-on-cert-at-48.md).

A second opt-in, **chronic volume decay**, treats a backup *week* as one pattern rather than
eight tickets. Day one is unchanged; a thumb-drive onset is never decayed. On a 48-person
fixture we wrote, `:precision` cut false positives from 420 to 240 and left recall at 8/8;
adding chronic decay **did not move** that operating point. Those numbers are not CERT. See
[quieter queues](13-quieter-queues-and-honest-ranking.md) and
[the dataset library](14-the-dataset-library-is-not-a-public-corpus.md).

## What this is not

- Sentiel has reused PART 3 models for baselines; it is not a finished custom enterprise detector.
- The precision policy **lost** to 6B on CERT r3.1 at 48 alerts (0.104 → 0.083). Chronic-volume
  decay is a scoring lever, not a CERT operating point. A library fixture row is not a CERT row.
  Peer matching still has **no labelled peer-relative positive**. r4.2 can test compromised
  account vs insider (scenario 3) once its events are on disk; it still cannot test peers.
- No live company data. CERT’s payload licence also disagrees with the page licence; both are
  recorded; PHOS does not redistribute the files.
- PHOS Intelligence (cross-engine correlation) is still unbuilt.

## Where to read more

- Decisions: [ADR 0020](../docs/adr/0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md),
  [ADR 0021](../docs/adr/0021-sentiel-feature-enrichment-a-causal-trailing-history-and-the-budget-that-bounded-it.md),
  [ADR 0022](../docs/adr/0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0023](../docs/adr/0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0028](../docs/adr/0028-precision-policy-volume-peer-match-and-the-family-gate.md),
  [ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md),
  [ADR 0032](../docs/adr/0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md)
