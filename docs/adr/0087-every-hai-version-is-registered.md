# ADR 0087 — Every HAI version is registered, and none of the new files are fetched

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, step 1
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md)

## Context

The integrated entry named `hai` records two files of HAI 21.03, `train1.csv.gz` and
`test1.csv.gz`. The publisher's tree at `icsdataset/hai` holds four dataset versions plus
HAIEnd, and 21.03 itself holds eight CSV files. Week 1 of `docs/v1-roadmap.md` starts by
registering every version and file, with the licence read the way the existing entries were
read. The frozen HAI measurements stay on the integrated name.

The tree was read at `icsdataset/hai` commit `2a814cebc9a66b06c9e5cd545e2d72e65d383737`
on 2026-10-04. That commit is the publisher's head and it is not in this repository; it is
the pin every HAI entry uses.
`graph/`, `hai_dataset_technical_details.pdf` and `graph/graph_analysis.ipynb` are testbed
documentation, not a dataset version, and are not entries.

## Decision

**1. Five entries, none of them fetchable.** `hai-20.07`, `hai-21.03`, `hai-22.04`,
`hai-23.05` and `haiend-23.05` have status `registered-not-fetched`, which is outside
`FETCHABLE_STATUSES`. `scripts/fetch_datasets.py --all` will not download them.

- `hai-20.07` is four plain git objects. The header and first row of each file were read.
  The separator is a semicolon and the row ends in CR. The comma preparer used for
  integrated `hai` would see one column. HAI 1.0 (February 2020) is not a separate tree;
  the README calls 20.07 the bug-fixed release of it. The README table's second row repeats
  the names train1 and test1; the files are `train2.csv.gz` and `test2.csv.gz`.
- `hai-21.03` lists all eight files, including the two the integrated entry already
  prepared. Headers of the other six match that entry: 84 comma-separated columns, last
  four `attack`, `attack_P1`, `attack_P2`, `attack_P3`, first row `attack` 0. Their attack
  windows were not enumerated. Fetching them under the integrated name would rewrite
  `data/hai/manifest.json`.
- `hai-22.04` CSV blobs are Git LFS pointers. `.gitattributes` at this commit lists
  `hai-23.05/**/*` and `haiend-23.05/**/*` only. The summary texts are ordinary files and
  were read: the label column they name is `Attack`, train summaries say 0 attacks, and
  the test summaries say 7, 17, 10 and 24. The CSVs themselves were not read.
  `size_bytes` and `sha256` are the pointer's size and oid.
- `hai-23.05` and `haiend-23.05` are Git LFS throughout, including the summaries. No
  payload was read. The README's HTML anchors swap the two directory names; the entries
  follow the directory names and the prose that calls HAIEnd the boiler DCS internal-logic
  tags. The two label files and the two summary texts of HAIEnd have the same oid as the
  HAI 23.05 files of those names. The series files do not.

**2. The licence heading wins, and the metadata table is recorded as a disagreement.**
The `## License` section says CC BY-SA 4.0. There is no `LICENSE` file. The same README's
schema.org table says CC BY 4.0. That table is not a second confirming surface. The
integrated `hai` entry already treats the heading as authoritative, and these entries do
the same, with the disagreement in `license.evidence`. One statement covers every version.

**3. The integrated entry is untouched.** Its two files, its prepare block (`row_stride`
10, drop `attack_P1`..`attack_P3`) and its licence evidence string stay as they were.
Frozen HAI rows are not recomputed here.

## Consequences

A later prepare step for 20.07 has to split on semicolons. A later fetch of 22.04, 23.05
or HAIEnd needs Git LFS, not `raw.githubusercontent.com`, and for 22.04 it may also need
an attribute the file does not currently have. Label columns for 23.05 and HAIEnd are
unknown until a payload is read. Nothing in this record is a detection measurement, and
nothing in §2 of the v1 roadmap is applied.

## What would reverse this

A publisher correction of the licence table, or a payload read that contradicts a summary,
gets its own entry or a dated note on these ones. It does not rewrite the integrated `hai`
evidence string unless that string itself becomes false.
