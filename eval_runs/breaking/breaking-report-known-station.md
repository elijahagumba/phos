# Atlas — the breaking harness (PART D3)

**Run:** 2026-08-22T15:43:07.439577+00:00 · **Commit:** `d9b3dcea9a97b603135ff21550dcdcd5eaa18dff` ·
**Seed:** 7 · **Corpora:** synth-attack-power-generation-graded, synth-attack-water-treatment-graded

> These are attacks WE designed against a MODEL of a plant. A blind spot found here is real and worth fixing — the map's value is in its misses. But Atlas performing well here shows that it handles our adversary against our simulation, a necessary step toward handling a real adversary against a real plant and is not evidence of it. No number in this report may be quoted as a detection rate for Atlas in the field.

---

## 1. Where Atlas goes blind

**Read no detection claim off `synth-attack-power-generation-graded`.** It posts 134.5 false positives per normal hour (6217 over 46.2 hours, 15903 subsystem events). A corpus whose false-positive load is this high has not 'caught' its attacks in any useful sense: it alerted on so much of the corpus that landing inside an attack window was close to unavoidable. Recall and a false-positive rate must be read together, and a recall row from a saturated corpus supports no claim about detection at all.

**Whole attack types Atlas never saw, at any subtlety including the most blatant:** `MIMIC_COMMAND` on `water-treatment`. Not boundaries but whole categories the engine is deaf to on that machine, and the first thing to fix.

**Where the clean types break, per plant:**

- `water-treatment` / `STEALTH_DRIFT` — ragged between 0.00 and 0.75: missed at 0.00 yet still caught at 0.75, so the boundary is a range with holes rather than a point.

- `water-treatment` / `BLATANT` — ragged between 0.40 and 0.99: missed at 0.40 yet still caught at 0.99, so the boundary is a range with holes rather than a point.

- `water-treatment` / `MIMIC` — breaks between 0.40 and 0.75.

- `water-treatment` / `ROGUE_COMMAND` — breaks between 0.40 and 0.75.

**Types the shipped battery never broke:** `BLATANT` on `power-generation` *(saturated — see above)*, `MIMIC` on `power-generation` *(saturated — see above)*, `MIMIC_COMMAND` on `power-generation` *(saturated — see above)*, `ROGUE_COMMAND` on `power-generation` *(saturated — see above)*, `STEALTH_DRIFT` on `power-generation` *(saturated — see above)*. The honest reading is 'not broken below the hardest subtlety tested', not 'always caught' — the dial would have to go further to find the limit. And where the row is marked saturated, it is not a detection result at all.

**1 attack(s) drove the true state outside anything unattacked operation produced, while Atlas reported all-clear.** Judged from D1's true-state record, not from the telemetry, because for a falsified reading the telemetry is exactly what cannot be trusted:

- `wt-rogue-write-near-invisible` (ROGUE_COMMAND, subtlety 0.99) — true state left its envelope by 0.0191 on `chlorine_residual_mgpl`.

**No zero-magnitude control produced an alert**, which is the anti-fingerprint check passing on the detection side: Atlas is not finding the injection itself.


---

## 2. The breaking-point map — clean results

These are attacks whose mechanism D2's anti-fingerprint discipline covers, so a detection here is
evidence about Atlas. This is the headline map and the only part that supports the sentence *"Atlas
detects plant attacks down to this subtlety"*.

| Plant | Type | Caught to | Missed from | Boundary | Caught | Missed | Danger | Inert |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `power-generation` | `BLATANT` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `power-generation` | `MIMIC` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `power-generation` | `MIMIC_COMMAND` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `power-generation` | `ROGUE_COMMAND` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `power-generation` | `STEALTH_DRIFT` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `water-treatment` | `BLATANT` | 0.99 | 0.40 | ragged between 0.40 and 0.99: missed at 0.40 yet still caught at 0.99, so the boundary is a range with holes rather than a point | 3 | 1 | 0 | 0 |
| `water-treatment` | `MIMIC` | 0.40 | 0.75 | breaks between 0.40 and 0.75 | 2 | 2 | 0 | 0 |
| `water-treatment` | `MIMIC_COMMAND` | — | 0.00 | blind at every subtlety tested, including 0.00 — no breaking point, the whole type is unseen | 0 | 4 | 0 | 0 |
| `water-treatment` | `ROGUE_COMMAND` | 0.40 | 0.75 | breaks between 0.40 and 0.75 | 2 | 2 | 1 | 0 |
| `water-treatment` | `STEALTH_DRIFT` | 0.75 | 0.00 | ragged between 0.00 and 0.75: missed at 0.00 yet still caught at 0.75, so the boundary is a range with holes rather than a point | 2 | 2 | 0 | 0 |


## 3. The breaking-point map — fingerprint-caveated results

This attack falsifies the reading of an instrument that carries calibration drift. D2's pseudo-noise reproduces the instrument's measurement noise but NOT its slow drift, whose phase is drawn from the plant's setup generator and cannot be reconstructed from outside, so the injected signal is drift-free where a genuine one wanders. A detection here may be Atlas seeing that artefact rather than the danger, and must not be read as clean evidence of genuine detection. The artefact is strongest at low subtlety, where the reading is fully synthetic, and fades toward the near-invisible end, where most of the genuine signal — drift included — is still present.

**These rows are not folded into the map above and must not be quoted beside it.**

| Plant | Type | Caught to | Missed from | Boundary | Caught | Missed | Danger | Inert |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `power-generation` | `CORRELATION_BREAK` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `power-generation` | `LIAR` | 0.99 | — | caught at every subtlety tested, down to 0.99; the battery did not reach its limit | 4 | 0 | 0 | 0 |
| `water-treatment` | `CORRELATION_BREAK` | 0.40 | 0.75 | breaks between 0.40 and 0.75 | 2 | 2 | 0 | 0 |
| `water-treatment` | `LIAR` | 0.99 | 0.00 | ragged between 0.00 and 0.99: missed at 0.00 yet still caught at 0.99, so the boundary is a range with holes rather than a point | 1 | 3 | 0 | 0 |


---

## 4. False-positive load and detection latency

The denominator is hours of *normal* operation, so an attack-dense corpus cannot flatter the rate.
Every number here is `phos.eval`'s own.

| Corpus | Fitted on | Normal hours | False positives | FP / hour | Events | Narratives |
| --- | --- | --- | --- | --- | --- | --- |
| `synth-attack-power-generation-graded` | `synth-power-generation-train` | 46.23 | 6217 | 134.4943 | 15903 | 2 |
| `synth-attack-water-treatment-graded` | `synth-water-treatment-train` | 46.23 | 18 | 0.3894 | 598 | 12 |

| Corpus | Windows detected | Fastest (s) | Median (s) | Slowest (s) |
| --- | --- | --- | --- | --- |
| `synth-attack-power-generation-graded` | 28 | 0 | 0 | 30 |
| `synth-attack-water-treatment-graded` | 12 | 0 | 255 | 10020 |

The behavioural model is fitted on a separate D1 normal corpus of the same plant, not on the attacked corpus. The calibrator is cross-fitted over two time folds, so every attack is scored in the fold whose calibration slice excluded it. A detection result is therefore a statement about Atlas given a well-fed baseline; a deployment fitted on four hours of a plant with a daily cycle would do worse, and that is a different measurement.

---

## 5. Did reading the commands move the explanation?

Known-station writes and unknown-master writes are **scored apart**. A write from a device already on the learned graph tests whether a new function on a known link can outrank maintenance (it cannot, by design: ADR 0014). A write from a device absent from that graph tests the unknown-master split (ADR 0027). Pooling the two lead rates would credit a template change the battery never exercised.

### Known-station issuers

Issuer already commanded someone in the baseline capture.

Of 16 command attack(s), reading the control network moved `unauthorised_control_activity` up the ordering in **6** and made it the leading explanation in **0**.

| Attack | Issuer | Subtlety | Rank on sensors | Rank with commands | Moved | Command evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `pg-rogue-write-obvious` | `scada` | 0.00 | 3 | 4 | no | 365 |
| `pg-mimic-write-obvious` | `hmi` | 0.00 | 3 | 3 | no | 358 |
| `pg-rogue-write-moderate` | `scada` | 0.40 | not raised | 3 | yes | 363 |
| `pg-mimic-write-moderate` | `hmi` | 0.40 | not raised | not raised | no | 355 |
| `pg-rogue-write-subtle` | `scada` | 0.75 | 3 | 5 | no | 355 |
| `pg-mimic-write-subtle` | `hmi` | 0.75 | 3 | 3 | no | 339 |
| `pg-rogue-write-near-invisible` | `scada` | 0.99 | not raised | 3 | yes | 355 |
| `pg-mimic-write-near-invisible` | `hmi` | 0.99 | not raised | not raised | no | 347 |
| `wt-rogue-write-obvious` | `scada` | 0.00 | not raised | 3 | yes | 14 |
| `wt-mimic-write-obvious` | `hmi` | 0.00 | not raised | not raised | no | 0 |
| `wt-rogue-write-moderate` | `scada` | 0.40 | not raised | 3 | yes | 8 |
| `wt-mimic-write-moderate` | `hmi` | 0.40 | not raised | not raised | no | 6 |
| `wt-rogue-write-subtle` | `scada` | 0.75 | not raised | 3 | yes | 6 |
| `wt-mimic-write-subtle` | `hmi` | 0.75 | not raised | not raised | no | 0 |
| `wt-rogue-write-near-invisible` | `scada` | 0.99 | not raised | 2 | yes | 6 |
| `wt-mimic-write-near-invisible` | `hmi` | 0.99 | not raised | not raised | no | 4 |

### Unknown-master issuers

Issuer never commanded anyone in the baseline capture.

_None measured._


> The command-attribution result is an ORDINAL RANK MEASURED AGAINST OUR OWN MATERIAL, and it may not be cited as a real-world detection rate. What it compares is where one named explanation sat before and after Atlas could read the commands — our attack library, run against our plant model, judged by our template set. Three things follow. It is not a rate: 'moved in n of m' counts attacks in a hand-written battery, so its denominator is a property of what we chose to write and carries no population behind it. It is not calibrated: only the direction the ordering moved is read, never the confidence attached to it. And it is not transferable: a real commissioning engineer leaves behind the same new device relationship an intruder does, so no movement here says the two can be told apart in the field. Known-station writes and unknown-master writes must not be pooled into one lead rate: they test different template splits (ADR 0014 vs ADR 0027). Quoting this number as a detection rate would claim a measurement against reality that was never made.


The hypothesis confidences behind the command-reasoning section are NOT calibrated probabilities and are not surfaced as any (Constitution §3.3). Only the ORDERING of competing explanations is read, and only the direction it moved.

---

## 6. Input-hostile robustness — a separate claim

An input-hostile case tests whether Atlas's SOFTWARE survives malformed, out-of-range, truncated or poisoned input without crashing, corrupting its baseline or producing silently wrong output. Passing it is not evidence that PHOS is secure against a real-world attacker. That claim needs a live deployment, an exposed attack surface and an adversary who did not read this file, none of which exist here. An input-hostile case is never labelled as a plant attack and never appears in a corpus's attack intervals.

_No input-hostile corpora were measured._


---

## 7. The boundary on all of it

1. These are attacks WE designed against a MODEL of a plant. A blind spot found here is real and worth fixing — the map's value is in its misses. But Atlas performing well here shows that it handles our adversary against our simulation, a necessary step toward handling a real adversary against a real plant and is not evidence of it. No number in this report may be quoted as a detection rate for Atlas in the field.
2. Detection results and input-hostile results are measured and reported separately and are NEVER combined. Detection results support only 'Atlas detects plant attacks down to this subtlety'. Input-hostile results support only 'Atlas's software survives hostile input'. Neither, alone or together, supports any claim that PHOS is secure against an attacker.
3. These are attacks WE designed. Atlas catching them shows that Atlas handles our imagination, not a real adversary's: the library was written by someone who could read the detector, and an attack nobody here thought of is not in it. Two consequences follow and both are load bearing. A detection rate measured here is an upper bound on this library, never a lower bound on reality. And if Atlas ever scores suspiciously well, the first hypothesis is a leaked fingerprint — some incidental tell in timing, formatting, ordering or numerical precision that lets the detector find the injection rather than the attack — and not brilliance. Rule that out before believing the number.
4. An input-hostile case tests whether Atlas's SOFTWARE survives malformed, out-of-range, truncated or poisoned input without crashing, corrupting its baseline or producing silently wrong output. Passing it is not evidence that PHOS is secure against a real-world attacker. That claim needs a live deployment, an exposed attack surface and an adversary who did not read this file, none of which exist here. An input-hostile case is never labelled as a plant attack and never appears in a corpus's attack intervals.
5. This attack falsifies the reading of an instrument that carries calibration drift. D2's pseudo-noise reproduces the instrument's measurement noise but NOT its slow drift, whose phase is drawn from the plant's setup generator and cannot be reconstructed from outside, so the injected signal is drift-free where a genuine one wanders. A detection here may be Atlas seeing that artefact rather than the danger, and must not be read as clean evidence of genuine detection. The artefact is strongest at low subtlety, where the reading is fully synthetic, and fades toward the near-invisible end, where most of the genuine signal — drift included — is still present.
6. The hypothesis confidences behind the command-reasoning section are NOT calibrated probabilities and are not surfaced as any (Constitution §3.3). Only the ORDERING of competing explanations is read, and only the direction it moved.
7. The command-attribution result is an ORDINAL RANK MEASURED AGAINST OUR OWN MATERIAL, and it may not be cited as a real-world detection rate. What it compares is where one named explanation sat before and after Atlas could read the commands — our attack library, run against our plant model, judged by our template set. Three things follow. It is not a rate: 'moved in n of m' counts attacks in a hand-written battery, so its denominator is a property of what we chose to write and carries no population behind it. It is not calibrated: only the direction the ordering moved is read, never the confidence attached to it. And it is not transferable: a real commissioning engineer leaves behind the same new device relationship an intruder does, so no movement here says the two can be told apart in the field. Known-station writes and unknown-master writes must not be pooled into one lead rate: they test different template splits (ADR 0014 vs ADR 0027). Quoting this number as a detection rate would claim a measurement against reality that was never made.
8. The behavioural model is fitted on a separate D1 normal corpus of the same plant, not on the attacked corpus. The calibrator is cross-fitted over two time folds, so every attack is scored in the fold whose calibration slice excluded it. A detection result is therefore a statement about Atlas given a well-fed baseline; a deployment fitted on four hours of a plant with a daily cycle would do worse, and that is a different measurement.
9. A corpus whose false-positive load is this high has not 'caught' its attacks in any useful sense: it alerted on so much of the corpus that landing inside an attack window was close to unavoidable. Recall and a false-positive rate must be read together, and a recall row from a saturated corpus supports no claim about detection at all.
