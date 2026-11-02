# ADR 0408 — The agreement tell is visible on the captured pair, and it is not a detection result

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS diagnosis, the verdict on ADR 0407
- **Supersedes:** nothing. ADR 0407's bar is unchanged and this record judges it as written
- **Depends on:** [ADR 0407](0407-the-agreement-tell-is-declared-as-a-diagnosis-on-the-pair.md),
  [ADR 0406](0406-the-pair-is-recaptured-and-the-gate-needed-three-attempts.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

ADR 0407 declared three bars over the captured pair and named what would refuse them. The analysis
was then written, tested, and run **once**. Nothing was adjusted after seeing the counts.

Report: `eval_runs/build/grfics/agreement-tell.md`. Reproduce with
`python scripts/grfics/agreement.py`.

**Credit:** GRFICSv3 is Fortiphyd's. Research use permitted by email; Fortiphyd asks for credit.

## The verdict

**Kept. All three bars passed.**

| tag | `97201` physical: live / HMI tracked | `97206` cyber: live / HMI tracked |
| --- | --- | --- |
| `PurgeValve` | yes / **yes** (479 changes) | yes / **no** (0) |
| `PurgeFlow` | yes / **yes** (479) | yes / **no** (0) |
| `ProductValve` | yes / **yes** (72) | yes / **no** (0) |
| `ProductFlow` | yes / **yes** (584) | yes / **no** (0) |
| `Pressure` | yes / **yes** (593) | yes / **no** (0) |
| `Level` | no / no | yes / **no** (0) |
| `AComp` | yes / **yes** (100) | no / no |
| `BComp` | yes / **yes** (594) | no / no |
| `CComp` | yes / **yes** (594) | no / no |
| `AValve`, `AFlow`, `BValve`, `BFlow` | no / no | no / no |

**Bar 1 — the physical run agrees.** Every tag live on the ICS side in `97201` (eight of them) had an
HMI that changed. None stayed frozen while its register moved.

**Bar 2 — the cyber run disagrees.** Every tag live on the ICS side in `97206` (six of them) had an
HMI that changed **zero** times across 1174 samples. None tracked its register.

**Bar 3 — no tag satisfies both.** The set of tags tracking in the physical run and the set tracking
in the cyber run are disjoint.

**In the design doc's words:** under the physical fault the operator's view and the PLC agreed; under
the read-path attack they disagreed. The tell is in the data.

## The row that needed explaining, and got it

`Level` is **not live on the ICS side in the physical run** (1 distinct register value) but **is live
in the cyber run** (181 distinct values), with its HMI frozen in both. ADR 0407 predicted this case
before the computation and it is not a defect:

- **Physical:** the fault froze the sensor at the source, so the register stopped moving too. The HMI
  froze with it. Everyone downstream was fooled identically — including this analysis, which can say
  nothing about `Level` in that run from the register alone, and correctly excludes it.
- **Cyber:** the register kept moving through 181 distinct values while the operator's view held one
  value for 1174 samples. That is the disagreement, recorded.

So the sharpest instance of **agreement** is not `Level` in the physical run but **`Pressure`** in it:
197 distinct register values, and an HMI that tracked them. The report says so rather than leaving a
reader to notice the asymmetry.

## Decision

1. **The verdict is kept, against the bars exactly as ADR 0407 wrote them.** No bar was widened, no
   threshold moved, and the analysis ran once.

2. **This is a diagnosis on an emulated plant and nothing more.** R4 and ADR 0143 apply. It says what
   the simulator's data carries, not what Atlas detects, not what a real plant would show, and not
   how fast any of it would be noticed. **No recall, rate, accuracy, confidence, budget or operating
   point is produced, and none may be quoted from the report.**

3. **`eval_runs/log.jsonl` is not appended.** No frozen row is read, no held-out seed is touched, and
   **v1 stays 8 of 12**. Nothing here is a measurement in the sense ADR 0049 means.

4. **No cross-zone claim.** One Docker bridge, no router, so no firewall, Suricata or arpmon evidence
   exists on this corpus (ADR 0401). The design doc's exercise leans on those; this pair poses the
   agreement tell and nothing else.

5. **The corpus is not widened.** Two runs captured, two analysed. The other eight development runs
   remain undriven, because a wider corpus would not make this question better answered.

6. **Fortiphyd is credited** here, in the report, and in the plain-English note.

## Consequences

- **The corpus stops being unused.** `grfics-v3-bridge` was registered a fortnight ago and captured
  this session; it now has a question asked of it and an answer that a reader can re-derive from the
  files.
- **The tell is checkable per tag, not just in aggregate**, because the recapture recorded all
  thirteen points. That is what ADR 0405 was for, and it earned its cost here.
- **The result is small and that is the point.** Eight tags agreeing in one run, six disagreeing in
  the other, on an emulated plant, with no rate attached. Anything larger would be a claim the corpus
  cannot carry.
- **The next honest step is a partner plant, not more seeds.** This pair shows the simulator can pose
  the question. It says nothing about whether a real plant's data would separate the same way, and no
  amount of further simulation changes that.

## What would reverse this

Quoting the report as a detection result; adding a rate, budget or operating point to it; reporting
the eight-and-six counts as a success rate; pooling `grfics-v3-bridge` with `grfics-v3`; claiming
cross-zone, firewall or IDS evidence; generalising the result to a real plant, to other faults, or to
other seeds; or driving further seeds under ADR 0407's declaration.
