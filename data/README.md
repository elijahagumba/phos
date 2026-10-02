# Datasets

Dataset files are **never committed**. `registry.json`, this file, `manifest.example.json` and each
`<name>/manifest.json` are; everything else here is git-ignored, so a corpus is pinned by its
manifest and a result can be re-created (Constitution §3.7).

PHOS is a defensive system tested against **published, labelled datasets only**. Do not generate
attack traffic to test it.

---

## The short version

```bash
python scripts/fetch_datasets.py --list     # every registered corpus, its licence, its size
python scripts/fetch_datasets.py --all      # download, prepare and write manifests
python scripts/evaluate_corpora.py          # score a GaussianBaseline on each, log the reports
```

This downloads only corpora whose licence was positively established, prepares each into a CSV the
adapter reads correctly, and writes `data/<name>/manifest.json`. It is idempotent — a file already
present at its registered size is not fetched again — and it refuses anything over ~300 MB without
explicit consent. `data/registry.json` is the catalogue it works from and the place to add a
corpus; see [ADR 0006](../docs/adr/0006-dataset-registry-and-never-committing-data.md).

Two corpora are integrated today: **BATADAL** (CC BY 4.0) and **HAI 21.03** (CC BY-SA 4.0).
A third, **batch-distillation** v1.1.2 (CC BY 4.0), is integrated as one mixture family; see
[ADR 0024](../docs/adr/0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md)
and [ADR 0025](../docs/adr/0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md).
**Data4Cyber** (CC BY 4.0) is integrated as Track A process telemetry (S0 fit, S1 score); FP/hour
is refused as a control-room budget and it is not a command corpus
([ADR 0046](../docs/adr/0046-data4cyber-track-a-is-process-phase-telemetry-not-a-control-room-ruler.md)).
The S7 process table is licence-confirmed and **unlabelled** (13,912 rows, no label column);
labelled Track A is refused
([ADR 0047](../docs/adr/0047-s7-process-parquet-is-unlabelled-track-a-refused.md)).


**Why preparation exists.** Every real corpus so far ships at least one trap that makes it load
successfully and score meaninglessly — a label sentinel of `-999` that means *unlabelled*, dates
that parse month-first on one row and day-first on the next, a train file and a test file that
disagree on column names, label columns duplicated as numeric signals. The fetch script normalises
these once, on disk, from the registry. `LabelledCsvAdapter` is therefore never modified, and the
manifest stays declarative.

---

## Registering a corpus by hand

The rest of this file describes the manual path, which still works and is what
`manifest.example.json` documents. Use it for a corpus you already hold, or one the registry cannot
reach (anything behind a request form).

## What to download

The first real adapter, `LabelledCsvAdapter`, reads a **labelled CSV time series**: one row per
timestamp, one column per measured signal, and one column saying whether that row was under
attack. Recommended, in order of least friction:

1. **HAI (HIL-based Augmented ICS Security dataset)** — public, CSV, timestamped process
   telemetry from a realistic hardware-in-the-loop ICS testbed, with labelled attacks. No request
   form. Search for "HAI Security Dataset"; it is published on GitHub by the affiliated Korean
   national research body and mirrored on Kaggle.
2. **Morris / Mississippi State power-system datasets** — public, labelled, CSV. Also fine.
3. **Any labelled Modbus/OT CSV capture you already have.** If it has a timestamp column, at
   least one numeric column, and a label column, it will load.

No download URL is hardcoded anywhere in the codebase, and no column name is assumed. The adapter
introspects the file's real header and fails loudly, naming the columns it actually found, rather
than guessing.

---

## Where to put it

```
data/
  README.md                 <- this file (committed)
  manifest.example.json     <- template (committed)
  manifest.json             <- YOUR config (git-ignored; create this)
  hai/                      <- YOUR data (git-ignored; any layout you like)
    hai-23.05/train1.csv
```

## How to register it

Copy `manifest.example.json` to `manifest.json` and edit it to describe your file. The manifest
is exactly the set of fields `LabelledCsvAdapter` takes, so there is no second format to learn:

```json
{
  "name": "hai-23.05-train1",
  "path": "hai/hai-23.05/train1.csv",
  "timestamp_column": "timestamp",
  "label_column": "Attack",
  "value_columns": null,
  "source_note": "HAI 23.05, train1.csv, columns auto-detected",
  "domain": "ATLAS"
}
```

| Field | What it means |
| --- | --- |
| `name` | Recorded on every report this corpus produces. Include the version. |
| `path` | CSV location, **relative to `data/`**. |
| `timestamp_column` | Column holding the row timestamp. Naive values are read as UTC, never as local time, so a run is reproducible on any machine. |
| `label_column` | Column holding ground truth. |
| `value_columns` | `null` auto-detects every numeric column except the timestamp and label. Or list the subset you want — one `Observation` is produced per row per column, so a 80-column corpus at 1 Hz gets large quickly. |
| `source_note` | Free text provenance: corpus, version, file. Copied onto every report. |
| `domain` | `ATLAS` for industrial/OT, `SENTIEL` for enterprise/cloud. |

### Three things to confirm before you trust a number

Open the CSV and check, because getting any of these wrong silently invalidates every metric:

1. **Which column is the timestamp**, and whether it carries a timezone. If it does not, it is
   read as UTC.
2. **Which columns are real signals.** Auto-detection takes every numeric column, which will
   include things like a row index or a constant if the corpus has them.
3. **Which value in the label column marks an attack.** The default rule is *non-zero, non-blank
   means attack*; blank means normal. If your corpus instead spells out `"Normal"` and
   `"Attack"`, the default would mark **every** row an attack — pass a custom `attack_when`
   predicate in code rather than via the manifest.

Once the manifest and the file are both present, the guarded integration test in
`tests/eval/test_real_dataset.py` stops skipping and exercises the whole path — load, detect,
score. Record the dataset name, version, and columns you settled on in an ADR under `docs/adr/`.
