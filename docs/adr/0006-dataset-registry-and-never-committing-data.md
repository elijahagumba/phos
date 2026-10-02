# ADR 0006 — A committed dataset registry, a fetch script, and data that is never committed

- **Status:** Accepted
- **Date:** 2026-07-29
- **PART:** none — infrastructure task between PART 3 and PART 4

## Context

After PART 3, PHOS could detect but had never been pointed at a real network. Every number in
`PROGRESS.md` came from a synthetic generator whose injected anomaly was 25 σ wide — a smoke test
of the machinery, not evidence of detection quality. The blocker was named in both PART 2 and
PART 3 as an "operator prerequisite": someone had to download a corpus by hand.

Doing that by hand does not scale past one corpus, and it loses the two things that actually
matter: **which licence permits the use**, and **what the label column really means**. Both are
per-corpus, both are discovered by reading the actual file, and both silently invalidate every
downstream metric when wrong.

## Decision

**1. A committed registry, `data/registry.json`, is the single source of truth about corpora.**
It records, per dataset: source URLs and sizes, the licence *with the evidence for it*, the
timestamp format, the label column and the exact values that mean attack, known quirks, and an
acquisition status. It is JSON rather than Python because it is data, not behaviour — and because
the one thing that genuinely needed to be code (a label predicate) was designed out; see decision 4.

**2. Data is never committed. The mechanism is `.gitignore`, and it is tested.**
`data/*` is excluded, then `data/*/` is re-included so git will descend, then `data/*/*` is
excluded again, then `data/*/manifest.json` is re-included. Ordering matters: git cannot re-include
a file inside an excluded directory. The result is that a dataset directory contributes exactly one
tracked file — its manifest — and no payload can be committed even from a nested subdirectory.
Verified with `git check-ignore` on real payload paths, and with `git add -An data/`, which offers
only the manifests.

**3. Only a positively established licence is downloadable, and the script enforces it.**
`FETCHABLE_STATUSES` is a whitelist. A corpus whose licence is unclear cannot be fetched by a
typo or a flag; it has to be reclassified in the registry, which is a reviewable diff. Applied,
this skipped two corpora that were on the target list — Morris / Mississippi State and
WUSTL-IIOT-2021. Both are publicly downloadable, widely cited, and state **no licence whatsoever**,
only a request to cite. "Publicly posted and everyone uses it" is not a grant, and the registry
records that judgement and its evidence rather than making it silently.

**4. Corpora are normalised at acquisition time, not at load time.**
Preparation writes a second CSV beside the raw download with: whitespace stripped from column
names, timestamps parsed with a **pinned** format and re-emitted as ISO-8601 UTC, the label reduced
to `1`/`0` by exact membership of the registry's `attack_values`, and leaking or non-numeric
columns dropped. The manifest points at the prepared file.

This is what kept `LabelledCsvAdapter` unmodified. It also removes the need for the custom
`attack_when` predicate that [ADR 0004](0004-first-real-dataset-and-the-operator-manifest.md)
anticipated: once `-999` has become `0` on disk, the shipped default is correct, and the manifest
stays declarative JSON instead of growing a callable. Each of the four transformations exists
because a real file demanded it — none is speculative:

| Transformation | The corpus that forced it | What it would have cost |
| --- | --- | --- |
| Strip column names | BATADAL names its test columns `" L_T1"` and its train columns `"L_T1"` | A model fitted on one and scored on the other matches no baseline and reports **silent zero recall** |
| Pin the timestamp format | BATADAL's `%d/%m/%y`: `04/07/16` infers month-first, `25/12/16` day-first | Ordering scrambled *within one column*; every time-based metric meaningless |
| Exact-match the label | BATADAL's `-999` = unlabelled, 3958 of 4177 rows | Corpus loads as **100 % attack, 0 h normal**; verified directly |
| Drop leaking columns | HAI's numeric `attack_P1..P3` | Three copies of the answer fed in as input signals |

**5. Manifests are generated, not hand-written, and are committed.**
`data/<name>/manifest.json` is the `LabelledCsvAdapter` field set at its top level — so
`model_validate` still works with no translation layer, preserving ADR 0004 decision 3 — with the
training corpus and full provenance (licence, URLs, sizes, SHA-256) on extra keys the adapter
ignores. Committing them means the integration test knows what *should* exist and can say so when
the payload is missing, instead of silently testing nothing.

**6. Any thinning of a corpus is recorded in the manifest, and therefore in every report.**
HAI at full resolution is 216 001 rows × 79 signals = 17 million `Observation` objects, which does
not fit in memory. It is prepared at `row_stride=10`. Rather than let that hide in a script, the
stride is written into the manifest's `source_note`, which `Dataset.source_note` copies onto every
`EvaluationReport`. Preparation also refuses a stride that would erase an attack window outright,
so ground truth cannot be thinned away silently.

## Reconciliation with ADR 0004

ADR 0004 listed "a download script" under **Alternatives considered — rejected**, on two grounds.
This ADR builds one, so both grounds have to be answered rather than ignored:

- *"The core is offline by Constitution §3.8 — a network call in the test path is exactly what that
  rules out."* Still true, and still honoured. `scripts/` is not part of the `phos` package, is
  never imported by it, and is run by hand. Nothing in `src/phos/` or in any test opens a socket;
  the test path reads local files only, exactly as before.
- *"Hardcodes a URL that will rot."* Correct, and it already happened — during this task. Every
  historical LANL `csr.lanl.gov/data/cyber1/*.gz` URL now returns 404, and the page has been
  reduced to a `mailto:`. The response is not to pretend URLs are stable but to make rot **loud and
  reviewable**: URLs live in one committed JSON file with a `verified_on` date, a broken fetch
  fails immediately and by name, and LANL has been reclassified to `operator-provided` with the
  evidence recorded. A rotted URL in a registry is a visible diff; a rotted URL in a README is
  folklore.

ADR 0004 decision 2 ("no download URL appears anywhere in the codebase") is therefore superseded.
Its underlying intent — that no *column name* is ever assumed and the adapter fails loudly naming
what it found — is untouched and still holds.

## Consequences

- The operator prerequisite carried since PART 2 is **closed**. `scripts/fetch_datasets.py --all`
  reproduces both corpora from scratch, and `scripts/evaluate_corpora.py` reproduces every number.
- `tests/eval/test_real_dataset.py` went from 3 skipped to 16 passing across 4 corpora, and gained
  a regression test for the label trap that no amount of code review would have caught.
- The registry is a maintenance surface. Sizes and URLs drift; `verified_on` says how stale the
  claims are, and a size mismatch triggers a re-fetch rather than trusting a truncated file.
- Two corpora on the target list were skipped for licensing. That is a real capability loss —
  WUSTL-IIOT-2021 in particular is a single labelled CSV that would have integrated immediately.
  The decision is recorded in the registry and is reversible by one status change if the operator
  judges the citation request sufficient.
- Preparation means the corpus PHOS scores is not byte-identical to the corpus as published. This
  is the main cost of decision 4. It is mitigated by keeping the raw download beside the prepared
  file, recording the SHA-256 of the raw file in the manifest, and deriving every transformation
  from the committed registry — so the derivation is reproducible and auditable, not ad hoc.

## Alternatives considered

- **Add `dayfirst` / `attack_when` / `drop_columns` options to `LabelledCsvAdapter`.** Rejected:
  it grows PART 2's public contract to absorb the quirks of individual corpora, and every future
  corpus would add another option. Normalising once at acquisition keeps the adapter's contract at
  "a clean labelled CSV" permanently.
- **Registry as `data/registry.py`.** Rejected: a Python module inside a data directory is a
  structural oddity, and it would have to be excluded from coverage and packaging by hand. The one
  argument for it — that label predicates are code — was dissolved by decision 4.
- **Commit a small labelled sample.** Rejected again, as in ADR 0004, and for the same reason: a
  sample small enough to commit makes the false-positive-per-normal-hour denominator meaningless.
- **Download the bulk LANL and CERT corpora (~104 GB) now.** Rejected on the operator's explicit
  instruction and on merit: neither is a labelled CSV time series, so nothing can read either until
  PART 6 builds an enterprise adapter. Only their small ground-truth files were taken, so PART 6
  can be written against a real label schema instead of a guess.
