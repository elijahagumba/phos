# ADR 0421 — The annotators said negligible, and the corpus never disagreed with itself

- **Status:** Accepted
- **Date:** 2026-11-04
- **PART:** C1 (corpus intake). A reading correction, not a measurement
- **Supersedes:** nothing. [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md) stands as written; this record withdraws the premise of its Decision 5
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md),
  [ADR 0082](0082-batch-distillation-label-classes-are-phases-and-only-the-anomalous-phase-is-scored.md)

## Context

A co-author of the `batch-distillation` descriptor paper was asked, by email, whether the plant has a
declared process map. She answered that it does, and pointed at the paper's P&ID, its instrumentation
tables and its supplementary equipment list.

Drafting the reply raised a question of courtesy that turned into a question of fact. The draft was
going to tell her that her dataset's two label sources disagree about which of its own experiments
are normal, because that is what this project's own record says: ADR 0024's title ends *"and two
label sources that disagree"*, its Decision 5 states that *"the corpus disagrees with itself about
which of its own experiments are normal"*, and the manifest lists the same thing under
**FOUND — the two label sources disagree on the training split**.

Before putting that sentence in a founder's name and sending it to the people who published the
data, it was checked against the payload.

It is false. The corpus says, in the files, what it means, and this project misread it.

## What was found

The payload is not committed (ADR 0006). These counts come from reading the v1.1.2 label modality
directly; anyone holding that archive can reproduce them with a YAML parse of the 119
`*_experiment_*.yaml` files and a scan of the 119 `*_experiment_*.csv` files beside them.

**1. Nineteen of the 38 training files hold a placeholder, not an anomaly.** Every one of the 38
`train_normal_experiment_*.yaml` files carries an `anomalies:` block. In 19 of them the entire
contents are:

```yaml
anomalies:
- class: None
```

That is an explicit *nothing here*, which a reader counting `anomalies:` blocks, or counting files
with a non-empty `anomalies` key, scores as an anomaly record. The other 19 files hold **55** real
records between them: 21 of class `ConfirmedAnomaly` and 34 of class `Anomaly`.

**2. All 55 of those records say the event was treated as normal.** Not some. Every record in every
one of the 19 files carries a `comment` field reading:

> This event was assessed as negligible and treated as normal; optional for anomalous set inclusion.

55 of 55, with no exceptions. The annotators anticipated exactly the question this project asked, and
answered it in the record beside the class. A typical one, with its cause intact:

```yaml
- class: ConfirmedAnomaly
  comment: This event was assessed as negligible and treated as normal; optional for
    anomalous set inclusion.
  hasCategory: recurrent
  Perturbation: Improperly sealed sample valve
  PerturbationMode:
    label: Leaking into system (air ingress)
```

**3. That comment is not boilerplate, and the check that would have excused the misreading is the
one that confirms it.** If every record in the corpus carried the sentence it would mean nothing. It
does not. Across the 81 `test_anormal_experiment_*.yaml` files there are **451** real records and
**40** carry it — 8.9%, against 100% on the training split. The annotators used the field
deliberately and selectively. It marks the events they decided to treat as normal, and it is
concentrated exactly where the file naming already says the data is normal.

**4. So the two sources agree.** The per-row CSV label column calls all 38 training experiments
clean. The YAML annotation calls the events it records in 19 of them negligible and treated as
normal. Those are the same statement in two notations. There is no disagreement on the training
split to find, to probe, or to report to the authors.

**5. The misreading cost a little under half the fit set.** ADR 0024 Decision 5 fitted the baseline
on the intersection of the two sources and recorded the price: *"34.81 of 62.54 normal hours survive
it."* ADR 0082's table records the same split inside the chosen mixture
`ternary_butan-1-ol+propan-2-ol+water` — 30.25 hours fitted as `train (dual-clean)` against 21.19
hours set aside as `contaminated train`. On the reading above, those 21.19 hours are normal operation
that the plant's own annotators called normal, excluded from the fit on a premise that was not there.

**6. The probe built on the premise was never run.** ADR 0024 Decision 5 kept the excluded
experiments as a held-out corpus on the grounds that *"experiments the label column calls normal and
the annotators call anomalous"* is a useful probe of whether Atlas sees what the annotators saw. No
such experiment exists, so the probe has no subject. It was prepared and never scored: ADR 0082's
table gives the `contaminated train` split 0 positive rows and 0 positive windows.

**7. One thing the record got right, now verified rather than asserted.** The manifest's ragged-file
finding holds exactly. Of the 119 label CSVs, **one** has a row count that disagrees with its
timestamp count: `batch_dist_binary_ethanol+propan-2-ol/operating_point_002/train_normal_experiment_002`
carries 8,334 data rows of which 7,118 carry a timestamp, and the trailing 1,216 are empty in both
the `Time` and the `Label (anomaly)` column. The last timestamped row reads `17:02:59`, which is the
last reading in the sensor file for the same experiment, so the tail is padding and nothing is
missing. The other 118 files match. A reader treating non-blank as anomalous would still turn 1,216
blank rows into anomalies inside a training file, which is why the quirk stays in the registry.

## Decision

**1. The premise of ADR 0024 Decision 5 is withdrawn.** The two label sources agree on the training
split. No claim in this project may describe the `batch-distillation` corpus as disagreeing with
itself about which of its training experiments are normal.

**2. ADR 0024 and ADR 0082 are not edited.** Both are Accepted and both stand as written, titles
included. ADR 0024's title is part of the record of what was believed on 2026-08-21, and a record
that is quietly retitled is a record that cannot be audited. This record is the correction, and it
is cited from the manifest.

**3. The manifest is corrected in place, as ADR 0024 Decision 4 requires.** It already carries
Correction 1 and Correction 2 from the same intake. This is Correction 3, written beside the trap it
replaces rather than deleting it, so the shape of the mistake stays legible.

**4. The baseline is not refitted in this record.** Refitting on 28 experiments instead of 15 is a
measurement. It needs its own declaration, naming the bars, before anything runs. Nothing here is a
score and nothing here authorises one.

**5. Every frozen distillation number stays frozen.** Ungated Mahalanobis **18.72** FP/hour and
every other figure measured on this corpus was honestly measured on the set it was honestly fitted
on, and this record moves none of them. A smaller fit set than was available is not a wrong number;
it is a number with a narrower basis than the record claimed.

**6. The contamination probe is retired.** It has no subject. The 21.19 hours stay prepared and
unscored until a declaration says what they are for.

**7. The descriptor paper is cited where its numbers are quoted.** The corpus is CC BY 4.0 and
attribution is a licence condition, not a courtesy. Until this change the paper's DOI appeared only
in `docs/data-campaign/manifests/batch-distillation.md`, while `README.md`, `encyclopedia/` and
`easy to reads/` quoted the corpus's numbers across roughly twenty files with one mention of the
institution and none of the paper.

## What is not claimed

- **Not that refitting would improve detection.** Whether a baseline fitted on 51.44 hours detects
  better, worse or identically to one fitted on 30.25 is unmeasured and unpredicted here.
- **Not that the corpus is flawless.** The ragged file is real, and finding 7 confirms it.
- **Not that the authors' judgement is adopted.** "Assessed as negligible" is their call. A future
  declaration may still exclude those experiments — but it must do so because it disagrees with their
  assessment and says so, not because it believes they never made one.
- **Not a measurement, a refit, or a corpus reopening.** No harness ran. No score was taken.
- **Not relevant to P1.** The plant has no control-network capture, so command-lead stays **0/16**
  and **1/4**, unpooled, and P1 stays the blocked human conversation.
- **Not an opening of brief H.** H2–H4 stay closed until after 6 January 2027 (ADR 0369, ADR 0420).

## Consequences

The record now says what the files say. One sentence was stopped before it reached the people who
published the data, which is the only reason the error was found at all: it had been written in a
manifest, carried into an ADR title, repeated in a second ADR's dependency chain, and acted on in a
prepared split, and none of that made it true.

The general lesson is narrow and worth keeping. The misreading came from counting a structured field
— `class` — without reading the prose field beside it that qualified every instance. A schema read
without its comments is a schema half read, and the annotators had already written the answer down.
