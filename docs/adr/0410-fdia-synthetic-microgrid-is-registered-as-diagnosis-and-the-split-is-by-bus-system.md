# ADR 0410 — FDIA-SyntheticMicroGrid is registered as diagnosis, and the split is by bus system

- **Status:** Accepted (a declaration; nothing here is a score)
- **Date:** 2026-11-02
- **PART:** corpus registration. No build lane
- **Supersedes:** nothing
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0058](0058-public-command-corpus-still-absent.md)

## Context

*FDIA-SyntheticMicroGrid: Complex Spatio-Temporal False Data Injection Attack (FDIA) Dataset for
Microgrid Systems* is a Mendeley Data corpus, dataset id `4gb62c72sx`, **version 1**, DOI
`10.17632/4gb62c72sx.1`, published 2026-07-13. The contributors are at Charles Darwin University.

The publisher's own description states the two facts that govern every use of this corpus:

> "The dataset contains two million rows of data generated for the IEEE-5, IEEE-9, IEEE-14, and
> IEEE-30 bus architectures… The dataset was generated using the MATLAB-based MATPOWER power flow
> simulation environment."

**Every row is simulation output.** There is no plant, no PLC, no network capture and no adversary.
This is the strongest single caveat in this record: **no detection claim can rest on this corpus
alone.** A number computed here says what a detector does against MATPOWER power-flow states with
labels placed by construction. It says nothing about a substation, an RTU, or a real microgrid, and
it cannot be substituted for one.

### The archive, verified before this record was written

| | |
| --- | --- |
| File | `4gb62c72sx-1.zip` |
| Bytes | 458,159,522 (436.9 MB) |
| sha256 | `6ac69417421ec204b1d76031091b368c5d9d4d4398f580d31e7b1d2e8df5b618` |
| `unzip -t` | clean: "No errors detected in compressed data" |
| Members | 5 files — four per-bus CSVs and one legend |
| Uncompressed | 3,767,255,476 bytes |

The archive was hashed and tested on the local copy at
`/private/tmp/claude-501/…/ics-downloads/fdia-synthetic-mendeley-4gb62c72sx/4gb62c72sx-1.zip`.
458,159,522 bytes exceeds `size_confirm_threshold_bytes` (314,572,800), so
`scripts/fetch_datasets.py` would refuse it unattended. **The human approved this size in chat before
this record was written**, together with the DAYPSCI size; the approval covers both and is recorded
here and in ADR 0409.

### The licence, and the identifier behind the CC BY sentence

- The Mendeley page `https://data.mendeley.com/datasets/4gb62c72sx/1`, read 2026-11-02, states
  **"Creative Commons Attribution 4.0 International"** and, in the licence blurb,
  **"CC BY license, and indicate if changes were made"**.
- The Mendeley public API, `https://data.mendeley.com/public-api/datasets/4gb62c72sx`, returns
  `data_licence.id = 01d9c749-3c4d-4431-9df3-620b2dcfe144` with the description: *"You can share, copy
  and modify this dataset so long as you give appropriate credit, provide a link to the CC BY license,
  and indicate if changes were made…"* — the CC BY 4.0 grant in Mendeley's own wording. It also warns:
  *"further permission may be required for any content within the dataset that is identified as
  belonging to a third party."* Nothing in the dataset is marked as third-party content; the
  simulation is the contributors' own.

That is two surfaces — the human-readable page and the API — and they agree. `permits_research_use`
is true; CC BY 4.0 also permits commercial use with attribution. The DOI is pinned to **`.1`**, the
version, not the concept DOI.

### What the archive contains, and the exact folder names

The publisher's own member list, which is also the split unit:

```
FDIA-SyntheticMicroGrid Complex Spatio-Temporal Fa/
    legend_label.txt                          1,121 bytes
    IEEE-5 Bus Dataset/measurements_5bus_multi.csv     232,613,069 bytes
    IEEE-9 Bus Dataset/measurements_9bus_multi.csv     430,954,170 bytes
    IEEE-14 Bus Dataset/measurements_14bus_multi.csv   826,024,760 bytes
    IEEE-30 Bus Dataset/measurements_30bus_multi.csv 2,277,662,356 bytes
```

Note the top-level folder name is **truncated mid-word** at `Fa` — it is not
`…Spatio-Temporal False Data Injection Attack` spelled out. The extraction commands below quote it
exactly, because a glob that assumes the untruncated name silently matches nothing.

The four bus folders match `IEEE-<N> Bus Dataset` exactly, so the declared split applies without
interpretation:

- **Development:** `IEEE-5 Bus Dataset`, `IEEE-9 Bus Dataset`.
- **Held back:** `IEEE-14 Bus Dataset`, `IEEE-30 Bus Dataset`.

### The labels, as `legend_label.txt` states them

The legend is a 31-line integer-to-class map, which is the publisher's label semantics verbatim:

| `label` | Meaning |
| ---: | --- |
| 0 | normal |
| 1–10 | **additive** injection — 5 behavioural patterns (`step`, `ramp`, `pulse`, `random`, `replay`) × 2 node strategies (`random_node`, `vulnerable_node`) |
| 11–20 | **deductive** injection — same 5 × 2 |
| 21–30 | **combined** injection — same 5 × 2 |

So a non-zero `label` is one of thirty FDIA classes, and their names are three axes the publisher
chose: injection method (additive / deductive / combined), node strategy (random / vulnerable), and
behavioural pattern (step / ramp / pulse / random / replay). Column names inside the CSVs were not
read: the header is a measurement file's first line, and the payload is unpacked only after this
record is committed. The registry therefore records the legend, which is a documentation file, and
records the CSV schema as **not yet verified**.

## Decision

1. **Two corpus entries.** `fdia-synthetic-microgrid` is `development` and
   `fdia-synthetic-microgrid-heldout` is `held-out`; both `status: declared`. Both record the same
   single archive, for the same reason as ADR 0409: the halves are member sets inside one published
   zip, and inventing two downloads would misdescribe the source.

2. **The split is by bus system, fixed now.**

   | Half | Folder | Members | Uncompressed bytes |
   | --- | --- | --- | ---: |
   | Development | `IEEE-5 Bus Dataset` | `measurements_5bus_multi.csv` | 232,613,069 |
   | Development | `IEEE-9 Bus Dataset` | `measurements_9bus_multi.csv` | 430,954,170 |
   | **Held back** | `IEEE-14 Bus Dataset` | `measurements_14bus_multi.csv` | 826,024,760 |
   | **Held back** | `IEEE-30 Bus Dataset` | `measurements_30bus_multi.csv` | 2,277,662,356 |

   `legend_label.txt` belongs to **both** halves and is copied to each. It is documentation, it
   carries no sample, and withholding it from the held-back half would make the held-back labels
   unreadable rather than unspent.

   Bus count is the right axis because it is a change of *system*, not of sample: a model fitted on a
   5-bus network is not the same model carried to a 30-bus one, so the held-back half asks the
   question PHOS actually cares about — does an expectation learned on one system survive on another
   — instead of interpolating within one.

3. **The exact commands that build the two sets**, run from the repository root after this record is
   committed:

   ```bash
   ZIP="/private/tmp/claude-501/-Users-elijahedoigiawerie-dev-phos/1709eed0-8915-4aef-b313-e075604097d6/scratchpad/ics-downloads/fdia-synthetic-mendeley-4gb62c72sx/4gb62c72sx-1.zip"
   TOP="FDIA-SyntheticMicroGrid Complex Spatio-Temporal Fa"

   mkdir -p data/fdia-synthetic-microgrid data/fdia-synthetic-microgrid-heldout

   unzip -q "$ZIP" "$TOP/legend_label.txt" \
                    "$TOP/IEEE-5 Bus Dataset/*" \
                    "$TOP/IEEE-9 Bus Dataset/*" \
                    -d data/fdia-synthetic-microgrid.dev

   unzip -q "$ZIP" "$TOP/legend_label.txt" \
                    "$TOP/IEEE-14 Bus Dataset/*" \
                    "$TOP/IEEE-30 Bus Dataset/*" \
                    -d data/fdia-synthetic-microgrid-heldout.intake

   mv "data/fdia-synthetic-microgrid.dev/$TOP/IEEE-5 Bus Dataset" \
      "data/fdia-synthetic-microgrid.dev/$TOP/IEEE-9 Bus Dataset" \
      "data/fdia-synthetic-microgrid.dev/$TOP/legend_label.txt" \
      data/fdia-synthetic-microgrid/

   mv "data/fdia-synthetic-microgrid-heldout.intake/$TOP/IEEE-14 Bus Dataset" \
      "data/fdia-synthetic-microgrid-heldout.intake/$TOP/IEEE-30 Bus Dataset" \
      "data/fdia-synthetic-microgrid-heldout.intake/$TOP/legend_label.txt" \
      data/fdia-synthetic-microgrid-heldout/

   rmdir "data/fdia-synthetic-microgrid.dev/$TOP" data/fdia-synthetic-microgrid.dev
   rmdir "data/fdia-synthetic-microgrid-heldout.intake/$TOP" data/fdia-synthetic-microgrid-heldout.intake

   ls data/fdia-synthetic-microgrid/*.csv | wc -l            # must print 2
   ls data/fdia-synthetic-microgrid-heldout/*.csv | wc -l    # must print 2
   ```

   Those two counts are the verification, and a count other than 2 and 2 stops the run.

4. **The result name is `atlas-fdia-microgrid`, development half only.** No held-back result name is
   declared here; the held-back half is spent by a later declaration with its own configuration,
   command and result.

5. **The bar, phrased on the development half only.** A later report must satisfy all five, or be a
   refusal:

   1. **`label = 0` is normal; `label ∈ 1..30` is an FDIA.** Recall is reported against that
      positive set. A binary attack/normal collapse is permitted, but the thirty-class confusion the
      legend makes possible must be reported beside it or the collapse is refused — the corpus's
      whole design is the three axes, and throwing them away silently discards what it was built for.
   2. **The two development bus systems are reported separately.** A pooled figure across IEEE-5 and
      IEEE-9 is refused, for the same reason the held-back split is by bus: they are different
      systems, and pooling them would answer a question about neither.
   3. **Every number is labelled a diagnosis.** The corpus is MATPOWER output, so any result is a
      statement about simulated power-flow states. **No detection claim can rest on this corpus
      alone**, and it may not be pooled with a real-plant corpus, with HAI, with BATADAL, or with a
      D2 issuer-kind rate. A record that quotes a figure from here without that sentence is refused.
   4. **The row count is stated before it is trusted.** The publisher's description says two million
      rows, **0.5 million per bus system**. The first read of each CSV's header and line count
      establishes the actual figure, and a discrepancy with 500,000 is recorded as the result rather
      than reconciled. The published description is a claim about the data, not a measurement of it.
   5. **Nothing here is called a false-positive rate per hour.** The generator's sample interval is
      not stated on the record page, so a per-hour rate would rest on an assumption about a
      simulation clock. A per-sample or per-row denominator is used, and its unit is named.

6. **The held-back half is not opened, not scored and not counted until its own declaration.** This
   record extracts the files and counts them. It reads no CSV header from either half and produces no
   number. `eval_runs/log.jsonl` is not appended.

7. **The registry carries the simulation caveat in `caveats`, not only here**, so a reader who never
   opens this record still cannot mistake the corpus for plant data.

8. **`DECLARED_HELD_OUT` grows by one name, `fdia-synthetic-microgrid-heldout`**, in registry order,
   for the reason ADR 0409 gives: two tests pin that tuple to the registry's `held-out` entries, and a
   bank that omits a registered held-out corpus is a wrong bank.

## Consequences

- **The corpus can pose a cross-system question cheaply and cannot pose a plant question at all.**
  Development is 663.6 MB of CSV across the 5- and 9-bus networks; held back is 3.1 GB across the 14-
  and 30-bus networks.
- **The publisher's row count is unverified**, and this record says so rather than repeating 0.5
  million as though it had been counted.
- **The CSV schema is unverified.** The registry records `legend_label.txt` exactly and leaves the
  measurement columns for the first read after this commit.
- **Power-system telemetry is not OT network traffic.** There is no protocol here, no command, no
  session. A result from this corpus exercises the statistical layer of Atlas and says nothing about
  its command graph.
- **ADR 0044's done-check is not met by this commit.** Per the operator's instruction for this run,
  `encyclopedia/`, `easy to reads/` and `README.md` are not moved, so this advancement is not to be
  described as complete until a later change updates those three surfaces.
- **P1 is not advanced.** A simulated microgrid is not a design partner.
- **v1 stays 8 of 12.** No measurement exists.

## What would reverse this

Scoring a held-back bus system before its own declaration; quoting a number from this corpus as a
detection result without the simulation caveat; pooling it with a real-plant corpus or with either D2
issuer kind; reporting a per-hour rate on an assumed sample interval; treating the published 0.5
million rows per bus as measured; or committing any payload.
