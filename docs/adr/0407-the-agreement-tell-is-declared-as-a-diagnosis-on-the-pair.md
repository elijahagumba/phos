# ADR 0407 — The agreement tell is declared as a diagnosis on the captured pair, and it may be refused

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS diagnosis. Question asked of `97201` and `97206` on `grfics-v3-bridge`
- **Supersedes:** nothing. ADRs 0402–0406 stand. No capture is re-run
- **Depends on:** [ADR 0406](0406-the-pair-is-recaptured-and-the-gate-needed-three-attempts.md),
  [ADR 0403](0403-both-grfics-runs-were-captured-and-the-pair-disagrees-as-predicted.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

Two captures exist and nothing has used them. GRFICSv3's own design document states the diagnostic
tell this corpus exists to pose:

> "A physical field-device fault corrupts data at the source, so the PLC and HMI are fooled
> identically and agree with each other (both wrong, together). A read-path cyber attack only
> corrupts the HMI's view, so the PLC and HMI **disagree**."

This record declares the single question that asks whether the captured data carries that structure,
**before** it is computed. It is a **diagnosis**, not a detection claim.

Credit: GRFICSv3 is Fortiphyd's. Research use permitted by email; Fortiphyd asks for credit.

### Two confounds found while scoping the question, and how they are handled

Both were found by inspecting the captures before writing the bar, and both change its shape.

**1. The HMI polls every ~2 s; the harness samples every 1 s.** Measured on the physical run: the
gaps between `Pressure` changes on the HMI are 2.01, 2.01, 2.01, 2.02, 2.01 s. So a tag that tracks
its register perfectly still records only ~600 changes across 1180 samples, not 1180. **A ratio of
"changes per sample" is therefore invalid**, and any bar phrased as a proportion would be measuring
the poll period. The bar below uses **"changed at least once"**, where the measured gap is ~600 versus
**0** — a difference no polling artifact can produce.

**2. The plant was in a different state in the two runs.** `%IW111` and `%IW112` moved on the ICS side
in the physical run (1165 and 1158 distinct values) and were **static** in the cyber run (1 distinct
value each). That is plant state, not mechanism. **A comparison across runs, tag by tag, is
confounded by it.** The tell is therefore tested **within each run**, comparing the HMI against its
own register at the same sample. The runs are compared only at the level of *whether the HMI tracked
its register*, which is exactly what the design doc's words describe.

## The hypothesis

**H1.** In both runs, for every tag whose PLC register moved during the event, the HMI's tracking of
that register differs by cause:

- **Physical (`97201`)**: the HMI **tracked** its register — the freeze entered at the source, so the
  operator's view and the PLC agreed.
- **Cyber (`97206`)**: the HMI **did not track** its register — the freeze entered downstream of the
  PLC, so the operator's view and the PLC disagreed.

Restated as the design doc states it: **agreement under a physical fault, disagreement under a
read-path attack**, with both sides recorded at the same instant.

## The bars, declared before the computation

The analysis window is the event phase **past the transition window** (`TRANSITION_SAMPLES = 10`,
already declared in `capture.py` before the recapture). A tag counts as **live on the ICS side** when
its register held more than one distinct value in that window.

For each run, and for each tag live on the ICS side:

1. **Bar 1 — the physical run agrees.** For every such tag in `97201`, the HMI changed at least once.
   A tag that stayed frozen while its register moved is a **disagreement in the physical run**, and
   falsifies H1 for that tag.
2. **Bar 2 — the cyber run disagrees.** For every such tag in `97206`, the HMI changed **zero** times.
   A tag that moved while its register moved is a **tracking HMI in the cyber run**, and falsifies H1
   for that tag.
3. **Bar 3 — the separation is complete.** No tag is live-on-ICS in both runs and satisfies both
   "changed at least once in physical" and "changed at least once in cyber". If even one tag does, the
   tell does not separate the causes on this pair and the verdict is **refused**, not reported as a
   partial success.

**Tags not live on the ICS side in a run are excluded from that run, with the reason recorded.** They
carry no evidence either way, and ADR 0406 already established that `AValve`, `AFlow`, `BValve` and
`BFlow` never move even in a healthy quiet phase.

**One case is expected and is not a confound.** `Level` is live on the ICS side in the cyber run (its
register moved) but **not** in the physical run, because the physical fault froze the sensor at the
source and therefore froze the register too. That is the physical case doing exactly what the design
doc says — everyone downstream fooled identically. It is reported as the sharpest single instance of
agreement, not as a missing row.

## Decision

1. **`scripts/grfics/agreement.py` computes this and writes a report**, once, to
   `eval_runs/build/grfics/agreement-tell.md`. It reads only the two captured run directories.

2. **The verdict is kept, or refused, against the three bars as written.** A refusal is a result. If
   bar 3 fails, the record says the tell does not separate these two runs.

3. **No detection number is produced.** There is no recall, no false-positive rate, no accuracy, no
   confidence, no budget, no operating point. Nothing in the report may be quoted as a detection
   result, and `eval_runs/log.jsonl` is not appended. **v1 stays 8 of 12.**

4. **Every number in the report is computed from the captured files**, and the report names the
   command that produces it, so a reader can re-derive it without a container.

5. **It is a diagnosis on an emulated plant.** R4 and ADR 0143 apply: this says what the simulator's
   data carries, not what Atlas would detect on a real plant. It does not advance P1 and is not a
   substitute for a partner's plant.

6. **The corpus is not widened.** The other eight development runs are not driven, and no `973xx` seed
   is touched. The question is whether the pair separates, not how many seeds exist.

## What would count as a refusal

- Any live-on-ICS tag whose HMI moved in `97206`.
- Any live-on-ICS tag whose HMI was frozen in `97201`.
- Too few live-on-ICS tags to reach a conclusion (the report must state the count and refuse rather
  than conclude from one tag).

## Consequences

- **The corpus stops being unused.** Either the tell is visible in the data or the record says it is
  not; both are more useful than an unread file.
- **The bar is immune to the two confounds above**, which is why it was written after inspecting the
  data but before computing the verdict. The inspection changed the *form* of the bar (counts, not
  ratios; within-run, not across-run) and did not touch its direction.
- **No product claim follows.** A visible tell on an emulated plant is a diagnosis. It is not a
  detector, not a benchmark, and not something to put in front of a partner as a result.

## What would reverse this

Quoting the report as a detection result; adding a rate, budget or operating point to it; widening a
bar after seeing the counts; pooling `grfics-v3-bridge` with `grfics-v3`; treating a per-tag
agreement count as evidence about a real plant; or driving further seeds under this record.
