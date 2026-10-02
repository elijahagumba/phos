# ADR 0004 — HAI is the first real corpus, reached through an operator manifest

- **Status:** Accepted — **corpora placed and scored on 2026-07-29**; the table below is now
  filled. Decision 3 (operator-written manifest) is extended by
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md), which generates manifests from a
  committed registry rather than requiring the operator to hand-write one. Decision 2 (no download
  script, no URL in the repository) is **superseded** by ADR 0006 — see its "Reconciliation with
  ADR 0004".
- **Date:** 2026-07-28 (amended 2026-07-29)
- **PART:** 2 — Evaluation Harness & Dataset Adapters

## Context

PHOS is a defensive system and the Constitution is unambiguous about how it is tested: published
labelled datasets only, no attack tooling, no generated attack traffic. So the harness needs a real
corpus — synthetic data proves the code runs, not that it works.

Three constraints pull against each other:

- **§3.7 reproducibility** requires the exact corpus, version and columns behind any reported
  number to be recorded.
- **A fresh clone must be green.** The unit suite cannot depend on a multi-gigabyte download, and
  CI cannot be gated on one.
- **Nothing may be invented.** Hardcoding a download URL rots, and guessing column names produces
  a corpus that loads successfully and scores meaninglessly — the worst failure mode available,
  because it is silent.

## Decision

**1. The first real corpus is HAI (HIL-based Augmented ICS Security dataset).**
Chosen over the alternatives on four counts: it is public with no request form or licence
negotiation; it is already CSV with a timestamp column and an explicit attack label, so it needs no
bespoke parser; it is process telemetry from a hardware-in-the-loop ICS testbed, which is the Atlas
domain rather than an IT dataset borrowed into an OT setting; and its attacks are labelled as time
ranges, which is what window-level recall ([ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md))
needs. Documented fallbacks, in order: the Morris / Mississippi State power-system datasets, then
any labelled Modbus/OT CSV the operator already holds.

**2. No download URL and no column name appears anywhere in the codebase.**
`data/README.md` names the corpus and tells the operator how to search for it; `LabelledCsvAdapter`
introspects the file's actual header. A missing configured column raises an error that lists the
columns actually found, so a typo is diagnosed in one run instead of producing an empty dataset.
Non-numeric value columns are refused rather than coerced, and rows with unparseable values are
skipped rather than silently zeroed.

**3. The corpus is registered by an operator-written `data/manifest.json`, which is git-ignored.**
The manifest is *literally the field set of `LabelledCsvAdapter`* — name, path, timestamp column,
label column, value columns, source note, domain. There is deliberately no second schema, no
loader, and no translation layer to drift out of sync; the test does
`LabelledCsvAdapter.model_validate(manifest)`. `data/manifest.example.json` is the committed
template. This closes PART 1's deferred "`data/` manifest" item.

**4. The integration test skips when the corpus is absent, and only then.**
`tests/eval/test_real_dataset.py` is guarded on both the manifest existing *and* the CSV it names
existing. When present it exercises the whole path — load, detect, score, round-trip — and asserts
every reported metric is in range. The unit suite never touches it. A fresh clone is green with
three skips.

**5. Timestamps without a timezone are read as UTC, never as local time.**
A corpus that scored differently on a laptop in London and a laptop in Seoul would violate §3.7 in
the least visible way possible.

## Consequences

- Swapping corpora is an edit to one git-ignored JSON file; no code changes, and every report
  carries `dataset_name` and `source_note` so log lines from different corpora stay distinguishable.
- The operator is on the critical path for the first real number. This is deliberate — the
  alternative is the codebase guessing, and a guessed column is a silently wrong result.
- Auto-detection takes *every* numeric column, which on some corpora includes a row index or a
  constant. `data/README.md` calls this out as one of three things to confirm before trusting a
  number; the harness cannot detect it.
- The default label rule is *non-zero and non-blank means attack*. A corpus that spells out
  `"Normal"` / `"Attack"` would mark every row an attack under that rule. This is documented, and
  the escape hatch is passing a custom `attack_when` predicate in code — deliberately not
  expressible in the manifest, because a predicate in JSON is a small programming language.

## The corpora that were actually integrated

Filled on 2026-07-29. Two corpora were integrated, not one: HAI as planned, and BATADAL, which
turned out to be smaller, cleaner to acquire and a better first target. Both carry an explicit
Creative Commons licence, which is why they were chosen over the documented fallbacks — the Morris
/ Mississippi State datasets named above as fallback #1 state **no licence at all**, only a
citation request, and were therefore skipped (ADR 0006).

| Field | HAI | BATADAL |
| --- | --- | --- |
| Corpus and version | HAI 21.03 | BATADAL, 2017 release |
| Licence | CC BY-SA 4.0 (README "## License") | CC BY 4.0 (footer of batadal.net/data.html) |
| Files | `hai-21.03/train1.csv.gz`, `test1.csv.gz` | `BATADAL_dataset03.csv`, `BATADAL_dataset04.csv` |
| Timestamp column | `time`, `%Y-%m-%d %H:%M:%S` | `DATETIME`, `%d/%m/%y %H` (**day-first**) |
| Label column | `attack` | `ATT_FLAG` (` ATT_FLAG` in the test file) |
| Value columns used | 79 process signals, auto-detected after preparation | 43 signals, auto-detected after preparation |
| Label value meaning "attack" | `1` | `1` — and **only** `1` |
| Rows loaded / observations | 21601 train + 4321 test @ stride 10 → 1.71 M + 341 k obs | 8761 train + 4177 test → 377 k + 180 k obs |
| Attack windows in test | 5 | 5 |
| Commit at first scored run | see `eval_runs/log.jsonl` | see `eval_runs/log.jsonl` |

**Three of this ADR's predictions came true, and it is worth recording that they did**, because
each would have produced a plausible, complete, entirely wrong report:

1. *"Auto-detection takes every numeric column."* HAI ships `attack_P1`, `attack_P2` and
   `attack_P3` — numeric per-process copies of the answer. Left to auto-detection they would have
   been fed in as signals.
2. *"A corpus that spells out Normal/Attack would mark every row an attack."* The real trap was
   worse and numeric: BATADAL uses `-999` for *unlabelled* across 3958 of 4177 test rows. Under
   the shipped `default_attack_when` (non-zero means attack) the corpus loads as **100 % attack,
   with zero normal seconds** — verified directly, and now guarded by
   `test_real_dataset_labels_are_not_degenerate`.
3. *"Timestamps without a timezone."* Worse again: BATADAL's `%d/%m/%y` dates are *ambiguous*, not
   merely naive. Left to pandas' inference `04/07/16` parses month-first and `25/12/16` day-first,
   in the same column, silently scrambling the ordering every metric depends on.

The escape hatch this ADR specified — "pass a custom `attack_when` predicate in code" — was **not**
used. ADR 0006 explains why normalising the label during preparation was preferred.

## Alternatives considered

- **Vendor a small labelled sample into the repo.** Rejected: redistribution terms vary by corpus,
  and a sample small enough to commit is too small for the FP-per-normal-hour denominator to mean
  anything.
- **A download script.** Rejected: hardcodes a URL that will rot, and the core is offline by
  Constitution §3.6 — a network call in the test path is exactly what that rules out.
- **Infer the timestamp and label columns heuristically.** Rejected: the failure is silent. A
  corpus that loads with the wrong label column produces a complete, plausible, entirely wrong
  report, and nothing downstream can detect it. Explicit configuration with a loud error is worth
  the friction.
- **Write the manifest into `pyproject.toml` or a committed config.** Rejected: paths are
  machine-specific, and committing one operator's layout makes every other clone fail.
