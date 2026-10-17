# ADR 0144 — The October build is declared before any new file is opened

- **Status:** Accepted (a declaration; nothing here is a score)
- **Date:** 2026-10-17
- **PART:** build brief `docs/build-brief-2026-10.md`, Step 0
- **Depends on:** [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

The October build needs fresh seeds and corpora that no detector has been scored on. ADR 0117's
rule is that a split is committed before any file of a new corpus is opened, and that a held-back
batch is spent once, after a declaration. This record is that commitment. It does not download,
generate, or score anything.

TU Wien's pilot factory is not in this record. The brief's later instruction puts its registration
in a lane D ADR (0160–0169), before any of its files is opened.

## Decision

### 1. Seeds

`phos.eval.build_declaration` names four new blocks. A test checks that each is disjoint from the
others and from every used set: T1's 94001–94020, `DEVELOPMENT_SEEDS`, the library seeds,
`ARENA_LIAR_SEEDS`, `RED_TEAM_SEEDS`, `CONFIRM_SEEDS`, `CONFIRM_SEEDS_2`, `CONFIRM_SEEDS_3`, and
the ICSSim seeds 96001–96003, 96011–96020 and 96101–96120.

| Block | Seeds | What it is for |
| --- | --- | --- |
| Build development | 97001–97020 | Synthetic plants. Iterate freely. |
| Build held back | 97101–97120 | Synthetic plants. One score, after a declaration. |
| GRFICS development | 97201–97210 | One declared run each. Generate later, outside this repo. |
| GRFICS held back | 97301–97310 | Not generated, and not opened, until a score declaration. |

### 2. Kelmarsh and Penmanshiel

Zenodo version records 16807551 and 16807304 (not the concept DOIs). The record API says
`license.id = cc-by-4.0`, and the same record's description says Cubico released the data under
CC BY 4.0. That is one surface, restated. It is not claimed as two independent publishers.
`permits_research_use` is true because CC BY 4.0 allows it. Status is `declared`, so the fetch
script will not download them on its own. Each file's size and md5 are the API's. No file was opened.

Kelmarsh's SCADA zips mix all six turbines, so the split is by year file, not by turbine:

- Development (`kelmarsh`): SCADA 2016–2022, plus the static sheet, the signal map and the kmz.
- Held back (`kelmarsh-heldback`): SCADA 2023 and 2024, and the PMU and grid-meter archives,
  whose names do not separate those years.

Penmanshiel's publisher already split the files. The description says there is no WT03.

- Development (`penmanshiel`): every WT01–10 file, including that group's 2023 files, plus schema.
- Held back (`penmanshiel-heldback`): every WT11–15 file, plus the site PMU and grid archives.

These are real turbines. A false-alarm count on them is not a detection claim, and it is not
evidence that the plant map detects attacks (ADR 0143).

### 3. 4SICS

The page `https://www.netresec.com/?page=PCAP4SICS`, read 2026-10-17, asks for credit to CS3Sthlm
and a link back if the captures are redistributed or used in training. It has no SPDX. The build
brief states a separate permission by email from Erik Hjelmvik, with credit and a link required.
That message is not in this repository. The three days were not downloaded. The page's megabyte
figures are approximate, so `size_bytes` is 0 and no sha256 is invented. Record both on download,
before use.

- Development (`netresec-4sics-ics-pcap`): `4SICS-GeekLounge-151020.pcap` and `151021.pcap`.
- Held back (`netresec-4sics-heldout`): `151022.pcap`.

The captures are unlabelled. They are not a command corpus (ADR 0040).

### 4. GRFICSv3

Pinned at `Fortiphyd/GRFICSv3` commit `37bdf101f3ad0706a7595bd01d696ce7b84db436`. The code licence
was read twice and the tree was not copied: GitHub's API reports SPDX `GPL-3.0`, and that commit's
`LICENSE` file hashes to `605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad`.
`.cursor/rules/data-tiers.mdc` at commit `70c524e` records that Fortiphyd permitted research use
by email and asks for credit, and that Elijah has told them PHOS is a company. The message is not
in this repository. Commercial tiers are not used.

Runs are generated in a separate testbed (Docker is the example). Only the data they produce is
kept, under `data/grfics-dev/` and, later, `data/grfics-heldout/`. Each run is 10 quiet minutes,
then 20 minutes of the named event. `flow_1`–`flow_4` and `analyzer_a`–`analyzer_c` mean the four
flows and three analysers in the order that commit's engine lists them. A generator that cannot
find that order stops.

| Seed | Cause | Mode | Target |
| --- | --- | --- | --- |
| 97201 | physical | frozen | tank_level |
| 97202 | physical | frozen | tank_pressure |
| 97203 | physical | drift | flow_1 |
| 97204 | physical | noise | analyzer_a |
| 97205 | physical | dropout | flow_2 |
| 97206 | cyber | frozen | tank_level |
| 97207 | cyber | noise | tank_pressure |
| 97208 | cyber | stuck | product |
| 97209 | quiet | none | none |
| 97210 | physical | frozen | analyzer_b |
| 97301 | physical | frozen | flow_3 |
| 97302 | physical | drift | analyzer_c |
| 97303 | physical | noise | flow_4 |
| 97304 | physical | dropout | tank_level |
| 97305 | cyber | frozen | flow_1 |
| 97306 | cyber | dropout | analyzer_a |
| 97307 | cyber | drift | tank_level |
| 97308 | cyber | stuck | f1 |
| 97309 | quiet | none | none |
| 97310 | physical | frozen | flow_4 |

97201–97210 are development. 97301–97310 are held back. The modes are the ones the pinned
repository's own design note marks as implemented. Nothing has been generated.

### 5. The scorecard

Every lane report uses these names, and only a measurement may fill one in:
catches within budget, margin over the best simple rival, margin over chance, falsified-sensor
passes, naming right, naming wrong, reconstruction error, maintenance closures, calibration,
false alerts per shift, runtime. `SCORECARD` in `phos.eval.build_declaration` is that list.

### 6. The held-out bank

`role: held-out` is now `phos-icssim-heldout`, `kelmarsh-heldback`, `penmanshiel-heldback`,
`netresec-4sics-heldout` and `grfics-v3-heldout`, in that registry order. None has a `seen`
record. `atlas-v1-consistency`, frozen rows, priors and `eval_runs/log.jsonl` are untouched.

## Consequences

- Lanes may iterate on the development halves and on seeds 97001–97020. They may not open a
  held-back file, generate a held-back GRFICS run, or score seeds 97101–97120 until a declaration
  names the configuration, the command and the result.
- GRFICS code stays out of this repository. A result on it is diagnosis (R4).
- TU Wien is still unregistered. Lane D registers it before opening it.

## What would reverse this

Opening a held-back file before a declaration. Copying GRFICS source into the lab. Treating a
Kelmarsh or Penmanshiel false-alarm count as a detection claim. Filling a scorecard cell in this
record with a number.
