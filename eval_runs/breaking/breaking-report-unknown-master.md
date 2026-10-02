# Atlas — the breaking harness (PART D3)

**Run:** 2026-08-22T15:43:48.881300+00:00 · **Commit:** `d9b3dcea9a97b603135ff21550dcdcd5eaa18dff` ·
**Seed:** 7 · **Corpora:** synth-attack-water-unknown-master

> These are attacks WE designed against a MODEL of a plant. A blind spot found here is real and worth fixing — the map's value is in its misses. But Atlas performing well here shows that it handles our adversary against our simulation, a necessary step toward handling a real adversary against a real plant and is not evidence of it. No number in this report may be quoted as a detection rate for Atlas in the field.

---

## 1. Where Atlas goes blind

**Read no detection claim off `synth-attack-water-unknown-master`.** It posts 1.2 false positives per normal hour (21 over 18.0 hours, 115 subsystem events). A corpus whose false-positive load is this high has not 'caught' its attacks in any useful sense: it alerted on so much of the corpus that landing inside an attack window was close to unavoidable. Recall and a false-positive rate must be read together, and a recall row from a saturated corpus supports no claim about detection at all.

**Where the clean types break, per plant:**

- `water-treatment` / `ROGUE_COMMAND` — breaks between 0.40 and 0.75.

**No zero-magnitude control produced an alert**, which is the anti-fingerprint check passing on the detection side: Atlas is not finding the injection itself.


---

## 2. The breaking-point map — clean results

These are attacks whose mechanism D2's anti-fingerprint discipline covers, so a detection here is
evidence about Atlas. This is the headline map and the only part that supports the sentence *"Atlas
detects plant attacks down to this subtlety"*.

| Plant | Type | Caught to | Missed from | Boundary | Caught | Missed | Danger | Inert |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `water-treatment` | `ROGUE_COMMAND` | 0.40 | 0.75 | breaks between 0.40 and 0.75 | 2 | 2 | 0 | 0 |


## 3. The breaking-point map — fingerprint-caveated results

This attack falsifies the reading of an instrument that carries calibration drift. D2's pseudo-noise reproduces the instrument's measurement noise but NOT its slow drift, whose phase is drawn from the plant's setup generator and cannot be reconstructed from outside, so the injected signal is drift-free where a genuine one wanders. A detection here may be Atlas seeing that artefact rather than the danger, and must not be read as clean evidence of genuine detection. The artefact is strongest at low subtlety, where the reading is fully synthetic, and fades toward the near-invisible end, where most of the genuine signal — drift included — is still present.

**These rows are not folded into the map above and must not be quoted beside it.**

_No attacks of this kind were measured._


---

## 4. False-positive load and detection latency

The denominator is hours of *normal* operation, so an attack-dense corpus cannot flatter the rate.
Every number here is `phos.eval`'s own.

| Corpus | Fitted on | Normal hours | False positives | FP / hour | Events | Narratives |
| --- | --- | --- | --- | --- | --- | --- |
| `synth-attack-water-unknown-master` | `synth-water-treatment-train` | 18.02 | 21 | 1.1650 | 115 | 4 |

| Corpus | Windows detected | Fastest (s) | Median (s) | Slowest (s) |
| --- | --- | --- | --- | --- |
| `synth-attack-water-unknown-master` | 2 | 30 | 30 | 30 |

The behavioural model is fitted on a separate D1 normal corpus of the same plant, not on the attacked corpus. The calibrator is cross-fitted over two time folds, so every attack is scored in the fold whose calibration slice excluded it. A detection result is therefore a statement about Atlas given a well-fed baseline; a deployment fitted on four hours of a plant with a daily cycle would do worse, and that is a different measurement.

---

## 5. Did reading the commands move the explanation?

Known-station writes and unknown-master writes are **scored apart**. A write from a device already on the learned graph tests whether a new function on a known link can outrank maintenance (it cannot, by design: ADR 0014). A write from a device absent from that graph tests the unknown-master split (ADR 0027). Pooling the two lead rates would credit a template change the battery never exercised.

### Known-station issuers

Issuer already commanded someone in the baseline capture.

_None measured._

### Unknown-master issuers

Issuer never commanded anyone in the baseline capture.

Of 4 command attack(s), reading the control network moved `unauthorised_control_activity` up the ordering in **4** and made it the leading explanation in **1**.

| Attack | Issuer | Subtlety | Rank on sensors | Rank with commands | Moved | Command evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `wt-unknown-master-obvious` | `engineering` | 0.00 | not raised | 2 | yes | 9 |
| `wt-unknown-master-moderate` | `engineering` | 0.40 | not raised | 3 | yes | 8 |
| `wt-unknown-master-subtle` | `engineering` | 0.75 | not raised | 1 | yes | 14 |
| `wt-unknown-master-near-invisible` | `engineering` | 0.99 | not raised | 1 | yes | 3 |


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
