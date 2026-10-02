# ADR 0082 — Batch-distillation label classes are phases, and only the anomalous phase is scored

- **Status:** Accepted
- **Date:** 2026-09-23
- **PART:** C1 (corpus intake, revisited)
- **Supersedes:** nothing. Resolves the label question ADR 0024's Consequences deferred to the
  descriptor paper.
- **Depends on:** [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md)

## Context

A co-author of the batch-distillation corpus, Indra Jungjohann, pointed PHOS at Zenodo record
`22250958` under the name "noBOOM" and asked for it to be taken in. The brief said intake was needed,
gave a meaning for the four label classes, and called class 2 "the attack-equivalent label".

Record `22250958` is not a new corpus. It is version 1.1.3 of Zenodo concept `17395543`, the same
deposit (same authors, same Scientific Data paper) that ADR 0024 registered as `batch-distillation`
from version 1.1.2 (record `21535243`). That entry has status `integrated`, has prepared splits, and
is used by ADRs 0025, 0026 and 0048. A second registry entry would give one corpus two names and two
sets of numbers.

What the referral does add is the thing ADR 0024 left open: "The meaning of label classes 1, 2 and 3
needs the descriptor paper."

## Decision 1 — The referral updates the existing entry; it does not create one

`noBOOM` is recorded as provenance on the `batch-distillation` entry (`referral`), not as a new entry
and not as an alias. The name does not appear in the Scientific Data paper or on the Zenodo record,
and the registry does not record names it cannot source. If a citable source for the name turns up,
adding the alias is a one-line change.

The referral is recorded as *provenance*, not as *how the corpus came in*. The intake route was the
data campaign under ADR 0024, a month earlier, and history is not rewritten to credit the referral.

## Decision 2 — The four classes are verified from the paper and agree with the files

The descriptor paper's section *Anomalies* calls the blind phase phase "1" in the label modality,
the anomalous phase phase "2", and the recovery phase phase "3". Zero is the fault-free default.

| Class | Phase | Meaning |
| --- | --- | --- |
| 0 | normal | fault-free operation |
| 1 | blind | perturbation introduced, not yet observable in the recorded data |
| 2 | anomalous | deviation observable in the recorded data |
| 3 | recovery | perturbation removed, effects still observable |

ADR 0024 Decision 4 says the files win where they and the paper disagree. Here they agree. Of the
23,087 class-1 rows, 22,891 fall outside every YAML observation window, which is what a phase that
is not yet observable should look like. The registry's `unverified_multiclass_meaning` flag is now
`false`, and the classes and their evidence are recorded under `labels.classes` and
`labels.classes_evidence`.

## Decision 3 — Only class 2 is scored; classes 1 and 3 are unscored, not normal

Class 2 is the only positive class. Classes 1 and 3 are **unscored**: they are neither recall
targets nor normal time.

- **Class 1 is not a positive** because nothing in the data can see it yet. Scoring it rewards a
  detector for alerting before any signal moves, and penalises every honest one for missing it.
- **Class 3 is not a positive** because the cause has already been removed. It is aftermath, and
  counting it credits a detector for a late alert.
- **Neither is normal.** A perturbation is present during class 1, and its effects are visible
  during class 3. Counting that time as normal would put perturbed operation into the
  false-positive denominator and charge every alert raised there as a false alarm. This is why
  BATADAL's precedent (`-999` mapped to 0) is not followed.

## Decision 4 — Unscored time is a first-class part of ground truth

A binary label cannot say "neither", so the evaluation layer now can.

- **`Dataset.unscored_intervals`.** `normal_duration()` subtracts these intervals, merged with the
  attack intervals so no second is removed twice. `window_recall` never sees them.
- **`metrics.py`.** An alert inside an unscored interval that is not already a true positive is
  dropped from every count: false positives, precision, the reliability table and the Brier score.
  A true positive keeps precedence: an alert that the tolerance forgives into an attack window is
  still a hit. Unscored bounds are not widened by the tolerance, because forgiving more alerts
  would only flatter the false-positive rate.
- **Splits.** `phos.reasoning.prefix_split` stops the attack-free training prefix at the first
  unscored interval as well as the first attack (a blind phase is not verified normal), and
  carries unscored intervals into the test half. It delegates to `phos.models.train_test_split`
  rather than editing it, because `phos.models` is frozen since PART 6B
  (`tests/sentiel/test_engine.py::TestReuseNotFork`). With no unscored intervals it returns exactly
  what `train_test_split` does. The three-way split uses it, carries unscored intervals into its
  calibration and test slices, and does not count unscored points as normal. The prefix protocols
  in `scripts/evaluate_atlas.py` and `scripts/evaluate_corpora.py` use it too. Calibration skips
  candidates in unscored time.
- **Report.** `EvaluationReport` gains `n_unscored_intervals` and `n_unscored_alerts` (default 0,
  so older log lines still load). True positives, false positives and unscored alerts add up to
  `n_alerts`, so a set-aside alert is visible rather than silently missing.
- **Adapter.** `LabelledCsvAdapter.unscored_label_values` names label cells that become unscored
  intervals. The check runs before `attack_when`, which would otherwise read the sentinel as an
  attack. The designed protocol in `scripts/evaluate_atlas.py` and `scripts/evaluate_corpora.py`
  refuses a training corpus that carries unscored intervals.

A corpus that declares no unscored values gets an empty list, and its metrics are unchanged.

## Decision 5 — Preparation writes the phases explicitly and pools labels across the stride

`src/phos/eval/batch_distillation.py::_prepared_label` replaces `_binarize`. Class 2 becomes
prepared label `1`, classes 1 and 3 become `-1` (`UNSCORED_LABEL`), and class 0 stays `0`. An
unmapped class is refused rather than guessed. The classes are pinned in the registry `join` block
(`positive_label_values`, `unscored_label_values`). The manifest declares
`unscored_label_values: ["-1"]` on all three adapter blocks.

The stride had to change too. The first re-preparation under the old stride guard refused:
`operating_point_001/test_anormal_experiment_004` would have lost 3 of 12 unscored windows. In the
prepared mixture at 1 Hz, 33 of 69 blind-phase runs and 4 of 127 anomalous-phase runs are shorter
than the 10-row stride. Sampling every tenth row's own label would drop those seconds, and they
would be counted as normal. Plain sampling also loses one positive window (127 to 126).

Each kept row therefore stands for the ten seconds that start at it, and it takes the most severe
label in that block: positive over unscored over normal. Pooling cannot erase a window, so the old
count-based stride guard is removed. What pooling can do is merge two runs of one class that sit
less than a stride apart, or fold a short unscored run into a neighbouring positive block. That is
why window counts fall.

## Decision 6 — Class 2 is the perturbation-observable phase, never "attack-equivalent"

The brief's phrase is not adopted. ADR 0024 Decision 7 still holds. The operators performed
engineered process perturbations on their own plant, so recall on class 2 is perturbation recall and
is never reported as attack recall. The registry note says so in these terms.

## Decision 7 — Version 1.1.3 is recorded, not pinned

The two versions were compared file by file.

- **Labels archive:** byte-identical (same MD5).
- **Sensors archive:** different checksum, and 2 of 357 CSVs changed. Both belong to
  `batch_dist_binary_ethanol+propan-2-ol/operating_point_002/train_normal_experiment_002` (Startup
  and Operation), the ragged file already in the registry's quirks. Version 1.1.2 has values about a
  thousand times too large in that experiment; for example, FT703 reads `3` where 1.1.3 reads
  `0.003`.

That experiment is in the binary mixture, and the prepared splits use only the ternary water mixture,
so nothing prepared is affected. Pinning 1.1.3 now would make the registry's MD5s disagree with the
1.1.2 archives in `data/batch-distillation/raw/`. The entry therefore records 1.1.3 under
`version.newer_version_seen` and keeps the 1.1.2 pin until the raw payload is re-acquired. The
record's licence is still `cc-by-4.0`.

## Consequences

**What is now true.** The re-prepared splits (v1.1.2 payload, mixture
`ternary_butan-1-ol+propan-2-ol+water`, stride 10) load as follows through the manifest's adapter
config.

| Split | Rows | Label 1 (positive) | Label −1 (unscored) | Positive windows | Unscored windows | Span (h) | Normal hours (FP denominator) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train (dual-clean) | 10,918 | 0 | 0 | 0 | 0 | 30.25 | 30.25 |
| contaminated train | 7,652 | 0 | 0 | 0 | 0 | 21.19 | 21.19 |
| test | 39,664 | 8,377 | 5,091 | 126 | 115 | 109.86 | 73.12 |

Before this change the test split had 13,355 positive rows in 131 windows, covering 36.73 hours,
with 73.13 normal hours. Positive time falls to 22.92 hours, and 13.82 hours are now unscored.
Normal hours barely move, because blind and recovery time moved from "positive" to "unscored"
rather than into normal. Mapping classes 1 and 3 to 0 instead would have added that 13.82 hours to
the denominator.

**Resolution limit.** A window's interval runs from its first to its last kept row. Up to nine
seconds after the last kept row of each window therefore fall into the normal span, and up to nine
seconds of normal before a block that begins mid-block are counted as labelled. This is a property
of the stride, not of the class mapping, and it applied to attack windows before this change too.

**What this change breaks, deliberately.** Every `eval_runs/log.jsonl` row for batch-distillation
was logged under "classes 1, 2 and 3 are positive, sampled stride". None was rewritten. Numbers
logged before and after this ADR must not share a row in any comparison table, and no Atlas run
has been made under the new scoring.

**What this record does not claim.** No detection number.

## Alternatives considered

- **Register `noBOOM` as a new entry pinned to 1.1.3.** Rejected. It duplicates an integrated corpus
  under a name no source uses, and it would let the same data produce two sets of numbers.
- **Keep scoring classes 1, 2 and 3, and only record their meaning.** Offered and declined. It leaves
  logged numbers comparable, but it keeps crediting blind-phase and recovery-phase alerts as
  detections.
- **Map classes 1 and 3 to normal (the BATADAL precedent).** Rejected. It adds 13.82 hours of
  perturbed operation to the false-positive denominator and charges every alert there as a false
  alarm.
- **Drop class 1 and 3 rows from the prepared CSV.** Rejected. The gap between the remaining rows
  would still be counted as normal span by `normal_duration`. The time has to be declared, not
  deleted.
- **Score classes 2 and 3.** Rejected. Recovery is aftermath of a perturbation that has already been
  removed.
- **Prepare at full 1 Hz resolution instead of pooling.** Rejected for now. It removes the
  resolution limit, but it multiplies the scored observations tenfold and changes the corpus every
  earlier protocol was measured on (ADR 0025).
- **Repin to 1.1.3 now.** Rejected until re-acquisition. The pinned MD5s would stop matching the
  archives on disk, for a change confined to an experiment outside the prepared mixture.
