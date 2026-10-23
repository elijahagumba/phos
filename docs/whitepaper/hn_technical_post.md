# The operator gets eight alerts. An unbooked PLC program change keeps one of them.

PHOS Atlas is a behavioural detector for industrial control. It does not ship a signature list, and it does not ship a confidence you are allowed to read. The live constraint is smaller and ruder than a model: a shift is eight hours, a person can read eight alerts, and when those eight slots are already full, an unbooked program transfer still stays. The process hit leaves.

That priority is not a product slogan. It is `shift_page` in `src/phos/atlas/program_transfer.py` and `shift_brief` in `src/phos/atlas/shift_brief.py`. The source never uses the word "sovereign". The behaviour is the word. An unbooked transfer is not removed to save another alert. Booked transfers occupy nothing. If the unbooked transfers themselves exceed eight, the earliest eight stay and everything else is gone. The page does not grow a ninth slot. Eviction here is non-admission: the function returns a new tuple. It does not pop a heap, and it does not call the frozen score allocator.

This is a record of what the repository contains on 23 October 2026. Fixture arithmetic is not a plant. A simulated score is not a field rate. Several things you would expect a security product to have are absent on purpose, and a few were built and then refused.

## The fatigue is a counting problem, and the severity score made it worse

Signature detection is the wrong instrument for a credentialed operator at a legal console. A well-formed setpoint write breaks no signature. The alternative, "model normal and flag departures", produces a different failure, and we measured it.

On the frozen HAI row `atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` the grouped rate is 53.26 false positives per normal hour, window recall 1.00, 424 alerts. The same run is 424 subsystem events over 7.89 normal hours, of which 6 overlap a labelled attack window. An operator reading that queue front to back reads 424 things to find 6. "53 an hour" and "your shift contains 424 items" are the same fact told to two different people. The ungated Mahalanobis cell on that corpus is 646.58 false positives per normal hour. Those two log names stay. They are not retuned into something kinder.

Build 1 asked the question a rate cannot answer: rank the 424 and cut to a budget a person could work. Three keys, seed 11, threshold search forbidden (`eval_runs/atlas/hai-operator-queue.md`, ADR 0068):

| Key | Distinct scores | Where the 6 true alerts sit, of 424 | True positives in the first 48 |
| --- | ---: | --- | ---: |
| `magnitude` | 424 | 187, 204, 255, 320, 348, 359 | 0 |
| `weight` | 1 | every cut is the same tie | refused |
| `breadth` | 4 | 285, 286, 340, 341, 350, 351 | 0 |

A random draw of 48 expects 0.68 true positives. Magnitude finds 0. The loudest 96 alerts contain no attack. The true alerts sit in the back half. That is not "precision is low". The severity signal points away from the incidents, so no threshold on it repairs the order.

Weight is worse than compressed. All 424 events carry the same number, `0.03375934410417169`, the isotonic calibrator's ceiling. Only 140 of 4,249 calibration candidates fall in attack windows, so the calibrator tops out near 0.034 and, on this queue, carries zero ranking information. With a 424-way tie the cut is timestamp order. HAI's attacks happen to fall early in the test slice, which would print precision 0.1250 at budget 48. That figure is the tiebreak's number. `cut_is_arbitrary` refuses it. Do not quote `atlas-queue:weight`. Do not compare it to anything.

So the honest state of the joint vertical, after grouping, is: the attacks are in the queue, and none of the numbers Atlas already carries will put them in front of a person. Grouping was a counting change. On HAI, 5,123 per-signal alerts became 424 subsystem events, 12.1× fewer things to investigate, with both attack windows still covered. HAI's declared topology could not be partitioned below process level, so that reduction shows the collapse is implemented. It does not show the collapse is correctly resolved. A coarse group can also hide a second fault inside the first. That is a recall risk, not a win.

## What the engine actually is

Atlas is a pipeline with the order fixed, because the order is the claim. `AtlasEngine.run` in `src/phos/atlas/engine.py` owns no detector and no belief arithmetic.

- **Vectorise.** Ontology observations become a time-by-signal matrix. A missing cell is carried forward or the timestamp is dropped. A zero is never invented to fill a hole.
- **Score jointly.** `PcaResidualModel` reconstructs a reading from the plant's learned correlation structure. Motion along that structure reconstructs and is quiet. Motion that breaks it does not. `MahalanobisModel` asks the same question with the covariance: a combination of ordinary values that is jointly impossible. The deviation names the signal and the range the rest of the plant implied. "Given everything else, this should have read 42.1 ± 0.4" is the sentence. "Something is unusual" is not.
- **Promote.** Only an out-of-band candidate crosses the evidence boundary, with a calibrated weight. That weight is a calibrated probability of the deviation. It is not a probability that an explanation is true.
- **Group, then reason.** Ten instruments on one pump are one subsystem event. Membership comes from a `SubsystemMap` declared from process documentation. It is never inferred from co-movement. Inferring it that way would answer "did these share a cause?" with the same statistic that raised the alarm. Reasoning before the collapse would count one pump once per instrument, and every confidence downstream would be inflated by how many transmitters the unit has. The grouped weight is the max of the members. A max of calibrated probabilities is not itself calibrated. It is biased upward by the size of the instrumentation.
- **Explain from a fixed library.** Five handwritten templates, and no mechanism for a sixth. The code says so, because the constitution forbids pretending this is open-ended reasoning. The set is equipment fault, engineering maintenance, process disturbance, unauthorised control, and `insufficient_evidence`, which is always present. Priors are computed from the pruning floor and from one piece of fully trusted evidence, so the ordering (fault ≫ maintenance ≈ upset ≫ attack) is a derivation. They are conditional on a departure already having been raised. They are not measured base rates. Hypothesis confidence built on them is uncalibrated and must not be shown to a user. Evidence weights may be. Those are different objects, and mixing them up is how a dashboard lies.

There is a second inlet. `phos.atlas.packet` dissects a pcap into typed ICS messages. Command behaviour over time (volume, function mix, write targets, polling rhythm) becomes ordinary observations. A learned graph records who commands whom, and three departures from it: a relationship never seen, a learned one gone silent, an unfamiliar function on a known link. The physical claim, which is not a tuned weight, is that a real process upset moves readings and does not make a workstation begin commanding a PLC.

That claim has a limit, and the limit is enforced. An unexpected function on a known station supports maintenance and unauthorised control equally. A commissioning engineer and an intruder can leave the same link. A marked unknown master is narrower: a device that has never commanded this target begins to write. On the graded battery those two issuer kinds are scored apart. Known-station unique lead is 0 of 16. Unknown-master unique lead is 1 of 4, on attacks we wrote, with an explicit caveat that an attribution rank is not a rate. They are not pooled. "≥70%" is not a pass/fail on these files. There is still no labelled public command-attack capture. `discover_labelled_command_corpora` is empty. The evaluation script's job, when the corpus is missing, is to refuse to print a metric.

The detector that actually posts the public testbed numbers is a different file, `src/phos/atlas/consistency.py`, result name `atlas-v1-consistency`. Each signal is predicted from every other signal, now and at lags of 5, 15, 30 and 60 samples, one ridge regression per signal from one shared Gram matrix. Absolute error is divided by its 99.99th percentile on attack-free training. A range score sits beside it. Both are detrended against their own median over the previous hour, then scaled by the third-largest attack-free episode peak, so a signal that thrashes in normal operation is trusted less. Episodes chain into events. `budget_alerts` keeps, inside each shift, the strongest events, at most eight.

```python
# src/phos/atlas/consistency.py
SHIFT_SECONDS: Final = 8 * 3600
#: Alerts an operator can read per shift.
ALERTS_PER_SHIFT: Final = 8
```
