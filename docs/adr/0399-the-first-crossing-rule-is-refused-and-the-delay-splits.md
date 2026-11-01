# ADR 0399 — The first-crossing rule is refused, and the delay splits between the rule and the statistic

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Exploratory. Half A of ADR 0397, the verdict
- **Supersedes:** nothing. ADR 0286 is not edited and its finding stands
- **Depends on:** [ADR 0398](0398-a-weak-episode-keeps-its-right-to-place-the-alert.md),
  [ADR 0397](0397-an-exploratory-measurement-session-is-declared.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

ADR 0397 asked whether lane 3's delay failure is a property of the accumulator **statistic** or of
the **alert-placement rule** it was fed through. ADR 0398 declared one alternative placement rule and
froze the four bars from ADR 0397 unchanged. This record judges it. **The command was run once**, after
ADR 0398 was committed, into `eval_runs/build/lane-e/lane-placement-development.md`. Nothing was
re-run and nothing was tuned after seeing it.

The frozen and lane 3 columns in that report reproduce `lane3-development.md` exactly — 32 of 70 with
5 of 20 benign, and 53 of 70 with a paired median of 5 s and an own-set median of 13 s — so the only
difference in the new column is where the alert is placed.

## Decision

**Refused. One of the four bars is met.** The module stays on disk, tested and undeclared, beside
lane 2 and lane 3. `atlas-placement-consistency` is not a champion, not a frozen row, and not a claim.

| Bar | As frozen | Result | |
| --- | --- | --- | --- |
| 1. Strictly more than 32 of 70 caught | > 32 | **49** | met |
| 2. No frozen catch lost, paired ≥ 32 | ≥ 32 | **30** | **failed, short by 2** |
| 3. Median delay no worse, both readings | ≤ 0.85 s paired **and** own | **0.80 s paired, 6.10 s own** | **failed on the own-set reading** |
| 4. Benign no higher than 5 of 20 | ≤ 5 | **8** | **failed, short by 3** |

Per class, against the frozen engine and lane 3: `liar_freeze` 1 → 10 → **9**; `rogue_command`
4 → 10 → **9**; `replay` 5 → 7 → **6**; `mimic_maintenance` 2 → 6 → **5**; `creep_many` 10 → 10 →
**10**; `liar_offset` 10 → 10 → **10**; `recon` 0 → 0 → **0**. Benign: `maintenance` 4 → 8 → **7**,
`setpoint` 1 → 0 → **1**.

### The separation, which is the point of the session

**ADR 0286's diagnosis was right and incomplete.** The placement rule really was responsible for part
of the failure, and replacing it recovers that part outright: the paired median delay goes from lane
3's **5 s** to **0.80 s**, better than the frozen engine's 0.85 s on the same 30 attacks, with 8 of
them moved earlier and none moved later. That half is the rule's, and it is now established by
measurement rather than by argument.

The rest is not.

- **Bar 4 is the statistic's.** Benign is **8 of 20 before and after**. The rule re-timed several
  benign alerts — one `maintenance` moved from +0.3 s to outside its window, one `setpoint` moved in
  — and the count did not move. Four of the eight sit on a per-signal column crossing at a member
  peak of 1.04–1.11 and four on a saturated accumulator. Placement can re-time an alert; it cannot
  make a saturated column quieter.
- **Bar 3b is the statistic's.** The own-set median reads 6.10 s over the 49 the rule catches against
  0.85 s over the 32 the frozen engine catches — two different sets. The 17 attacks the frozen engine
  misses are the slow accumulated ones, and their median delay alone is **11.0 s** (`liar_freeze` to
  183.8 s, `mimic_maintenance` 58.6 s). The own-set figure rises *because* the statistic catches what
  it was built to catch. **On this corpus no engine that catches more of the accumulated classes can
  bring its own-set median down**, because the number it must beat is measured over a set that
  excludes exactly the attacks it adds.
- **Bar 2 is the new rule's own fresh defect, and it is the mirror of the old one.** The frozen rule
  can place an alert too **late**, by skipping a weak member. The first-crossing rule can place one
  too **early**, by crediting a member that crossed `THRESHOLD` long before the attack began. Both
  losses are that shape. `mixed2-96213`'s `rogue_command` (window 1335.4–1461.4 s) takes its placed
  alert at **957.0 s**, 378.4 s early, on a group whose first member is an accumulator column with a
  peak of 1.81 chained to the real departure at 1342.0 s inside a 300 s `event_window`.
  `mixed2-96217`'s `replay` (window 1412.8–1579.8 s) takes its placed alert at **1372.0 s**, 40.8 s
  early, on a per-signal member with a peak of 1.07. A rule that only ever moves earlier must
  eventually move earlier than the event, and an early alert spends one of the eight slots that would
  have carried an in-window alert.

**So the answer to ADR 0397's question is: both, and the rule's share is not enough.** A delay
failure that a placement change cannot fix was never only a placement failure.

### What was deliberately not done

No look-back limit, no minimum member peak, no cap on how far before a group's strongest peak an
alert may sit. Each is a new constant and a new dial, and adding one after seeing these two losses is
tuning on the result — the thing ADR 0397 forbids and ADR 0286 already paid for. A bounded rule is a
different rule and needs its own declaration, written before it runs. It is not declared here.

Nothing frozen moved. `phos.atlas.consistency` still hashes to
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911` and
`phos.atlas.drift_consistency` to `c5c163970e4edde178227e2e9e52901bb062040a1d0716a23504597c8316e345`,
the digests ADR 0398 recorded before the run. `atlas/templates.py`, every prior and
`EVIDENCE_STRENGTH` are untouched. `eval_runs/log.jsonl` was not appended. No held-out corpus, no HAI
edition, no BATADAL and no T1 seed set was opened; `phos-icssim-dev2` is development.

## Consequences

Lane 3's refusal stands, and now stands on a better reason: two of its four failures are its own and
one is a defect in the first replacement rule rather than in replacement as an idea. The paired-set
delay question ADR 0286 left open is **closed** — a new placement rule does recover it — while the
own-set reading and the benign count are shown to belong to the statistic, which no placement change
touches.

The next session that wants this has two honest doors, both of which need a declaration first: a
bounded first-crossing rule with its constant declared in advance, or a partner conversation about
whether 17 more attacks at an 11 s median is worth having (`docs/design-partner-brief.md`, P1). Neither
is opened by this record.

This is a finding on a simulated plant. R4 and ADR 0143 make it diagnosis and not proof, and no
sentence here says anything about Atlas's timeliness on a real plant.

## What would reverse this

Re-running the declared command after tuning, or adding a look-back limit, a minimum member peak or
any other dial and reporting the result under this declaration. Reporting bar 3a as met while 3b
failed, or calling 49 of 70 a win. Rewriting bar 3b's definition after seeing that the extra catches
raised it. Claiming the placement rule does not help when the paired median fell 5 s to 0.80 s, or
claiming it fixes the lane when three of four halves failed. Editing `phos.atlas.consistency`,
`phos.atlas.drift_consistency`, `atlas/templates.py`, a prior or `EVIDENCE_STRENGTH`. Opening a
held-out corpus, reading a red-tier corpus, or appending `eval_runs/log.jsonl`.
