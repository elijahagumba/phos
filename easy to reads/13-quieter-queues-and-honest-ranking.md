# Quieter queues, unknown masters, and busy days

**What this is:** the work after the first distillation baseline — three structural changes aimed
at the cycle contracts, and the measurements that **refuse** to say those contracts are met.

**Why it exists:** [the first distillation number](12-batch-distillation-todays-work.md) was honest
and unusable: about **449 alerts per day-equivalent** on a real batch column. Sentiel, at a
48-alert SOC budget, was about **10% precision**. Command reasoning moved the attack explanation
**up** on labelled windows and **led in none**. The next step was not a smaller threshold. It was
to change **what counts as an alert**, **which command facts argue for maintenance**, and **which
person-days belong at the front of a queue**.

## The orchestra is still in key — stop paging every flute

The joint model already asked “is this *chord* rare?” Then the ruler counted **every instrument**
that was a bit loud. A moment slightly off the learned piece became one alert per sensor.

The fix is a **gate on the whole moment**. Atlas still computes Mahalanobis distance \(D_M\) —
“how unusual is this combination?” Per-signal explanations are emitted only if that distance
reaches a high quantile of **training** moments (0.995 here). The **actionable** unit is then one
detection **per timestamp**, not per instrument. Analogy: if the orchestra is still in key, you do
not page the first violin because one note was a little bright.

Default Mahalanobis is **ungated**, so the 18.72/hour row stays comparable. Gating is opt-in
(`--gated` on the eval script).

Same designed distillation protocol as the first number. **Perturbation recall, never attack
recall.**

| Detector | Perturbation recall | False alarms per normal hour | ~alerts/day |
| --- | ---: | ---: | ---: |
| Mahalanobis (ungated) | 0.60 | 18.72 | ~449 |
| Joint-gated, still per-signal | 0.29 | 3.56 | ~85 |
| **Joint-gated, one alert per moment** | **0.29** | **2.04** | **~49** |

Quieter by about **9×** on the moment unit. **Recall halved** (0.60 → 0.29). **~49/day is still
about 16–25× the 2–3/day contract.** Distillation still has **no declared phase** Atlas may route
on, so this is a pooled envelope with a distance gate, not [one model per recipe step](09-when-the-recipe-changes.md).

Re-run: `uv run python scripts/evaluate_atlas.py batch-distillation --protocol designed --gated`.

## A stranger with a key is not the plant engineer

On sensors alone, “attacker wrote a setpoint” and “process upset” look the same. A **new commander**
on the wire is supposed to break that tie.

It did not, for a bookkeeping reason that must not be read as a verdict. Every
“who-commands-whom changed” fact on a **known** link still supported **both** unauthorised control
**and** engineering maintenance. Maintenance’s prior is higher. After a broad plant event the two
often **tied at the ceiling**. The ranker used to break that tie alphabetically — so maintenance
**looked** like the unique winner. That was a fake leader. PHOS now **records the tie and raises
“insufficient evidence”** instead of naming a winner
([ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)). The listing
order is still reproducible; it is not a unique lead. Structure still moved the attack story
**up** in most labelled command windows. Unique lead remains **0 of 16** on known-station writes
and **1 of 4** on unknown-master writes we designed — a diagnostic, not the contract.

The honest split: a **device that has never commanded this PLC**, and now writes, is not how a
plant’s engineering station works. That finding now **contradicts** maintenance and **supports**
the attack. A new function on a **known** station, or a relationship change that never declared
*which* finding it was, still supports both — a commissioning engineer and an intruder can leave
that shape.

Analogy: a new badge at a door that never used that door is not “the usual technician with a
new tool.” The usual technician using a new tool **is** still indistinguishable from an insider
who stole that technician’s habits.

`ground_event` answers a narrower question an operator actually asks: in this window, was the
process event **unauthorised** (unknown master), **commanded** (known-link activity), or
**uncommanded** (nothing on the wire, or only a learned link going silent)? That is a
co-occurrence table, **not** a probability.

The ≥70% “attack explanation leads” contract is **not quoted here**. Distillation has no packet
capture. Last harness rows: known-station writes **uniquely led in 0 of 16**; unknown-master
writes **moved up in 4 of 4** and **uniquely led in 1 of 4**. The 1/4 is a D2 diagnostic, not a
field rate. The two numbers must not be pooled
([ADR 0034](../docs/adr/0034-command-lead-rate-zero-on-known-link-writes.md),
[ADR 0035](../docs/adr/0035-unknown-master-writes-still-do-not-lead.md),
[ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md),
[ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)).
ADR 0036 does not rewrite those counts. It stops reading an alphabetical first place as a unique
lead. What changed after the 0/4 row is how silence is judged and **who belongs in the story**:
[silence, clocks, and who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md).

## A backup is not a theft — stop putting it at the front of the SOC queue

Sentiel’s score is a sum of many small “this feature was unusual” terms, one person-day. Equal
weight meant a bulk file copy, a Saturday login, and a first thumb-drive connect all shouted as
loudly. At **48 alerts**, precision sat near **10%**, catching one of two labelled insiders.

The templates cannot say “this is *not* an insider” without a sanction record CERT does not
carry. So the lever is **scoring**, not a new contradictory story:

- Busy-inbox / many-hosts / off-hours stems are **down-weighted**, not deleted.
- If we **measured** the person’s peers and they **matched**, while they left their **own** past,
  the whole day is ranked down (“new job, same team”).
- A day whose unusual evidence sits in **one** behaviour family (only logons, or only files) is
  ranked down unless a **second** family fires — or a thumb-drive onset, which CERT itself names
  as a start.

Default scoring is unchanged, so the 10% row stays on the log. The opt-in policy is
`--precision-policy`; detector names gain `:precision` so they cannot overwrite the reference.

**CERT r3.1 at 48 alerts, seed 7:** 6B peer-set precision **0.104**; `:precision` **0.083**;
both window-recall 0.5. The policy lost. 6B remains the headline
([ADR 0032](../docs/adr/0032-precision-policy-lost-on-cert-at-48.md)).

## One flicker is not a page; a backup week is not eight tickets

~49/day is still a flicker budget: a single off-manifold sample pages. A control room waits to
see whether the chord **holds**. `dwell_samples` is how many consecutive jointly-unusual moments
are required before the first alert of that run. Default **1** leaves the distillation row
comparable. Dwell-4 (two minutes at 30 s sampling) is opt-in. The counter resets when the plant
returns inside the envelope — two isolated spikes never add up.

Sentiel’s precision policy still treats each busy day independently. A backup that runs for a
week is one administrative pattern. Optional **chronic volume decay** multiplies repeated
file/host volume on consecutive person-days; day one is unchanged; a thumb-drive onset is never
decayed. Default **off** leaves PART 6B numbers comparable. `:precision-chronic` is a different
log name so it cannot overwrite `:precision`.

Both levers are persistence, not signatures
([ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md)). What they **measure** on
packed plants and personas we designed is
[the dataset library](14-the-dataset-library-is-not-a-public-corpus.md) — including that chronic
decay did not move the library operating point at threshold 1.25, and that a 2.2/day *mean*
across dwell rows is not the 2–3/day contract.

## What this number does not license

- Not 2–3 Atlas alerts/day. Not 10× false-alarm reduction on every dataset. Not attack recall.
- Not ≥70% command-window ranking on a public capture.
- Not a SOC-ready Sentiel precision. CERT `:precision` **lost** to 6B at 48 alerts (0.104 → 0.083).
  Not a peer-group detection advantage (retired: r3.1 and r4.2 have no labelled peer-relative positive).
- Not calibrated hypothesis confidence. Not a live plant or a live company.

## What you can assume exists now

- Joint gate and moment detector: `src/phos/atlas/multivariate.py`; [ADR 0026](../docs/adr/0026-joint-distance-gating-and-the-actionable-alert-unit.md)
- Unknown-master vs maintenance: `src/phos/atlas/templates.py`, `command_grounding.py`; [ADR 0027](../docs/adr/0027-unknown-master-writes-are-not-maintenance.md), [ADR 0035](../docs/adr/0035-unknown-master-writes-still-do-not-lead.md)
- Lead-tie refusal: `src/phos/reasoning/belief.py` (`tied_lead_ids`, `rank_hypotheses`); Atlas and
  Sentiel stories share it ([ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md))
- Comparable-stretch silence and story attachment: [easy to reads/15](15-silence-stretch-and-who-belongs-in-the-story.md); [ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md), [ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)
- Precision policy: `src/phos/sentiel/scoring.py` (`precision_policy`); [ADR 0028](../docs/adr/0028-precision-policy-volume-peer-match-and-the-family-gate.md)
- Dwell and chronic volume: same Atlas/Sentiel modules; [ADR 0030](../docs/adr/0030-moment-dwell-and-chronic-volume-decay.md)
- Packed synthetic measurement: [the dataset library](14-the-dataset-library-is-not-a-public-corpus.md)
- Engineering log: `PROGRESS.md` cycle sections after PART C2
