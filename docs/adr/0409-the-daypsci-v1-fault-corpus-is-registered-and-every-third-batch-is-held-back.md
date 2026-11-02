# ADR 0409 — DAYPSCI v1 is registered, and the held-back half is every third batch

- **Status:** Accepted (a declaration; nothing here is a score)
- **Date:** 2026-11-02
- **PART:** corpus registration. No build lane
- **Supersedes:** nothing
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0056](0056-three-w-is-faults-not-attacks.md),
  [ADR 0058](0058-public-command-corpus-still-absent.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

DAYPSCI v1 (*Detection of Anomalies and Protection of Industrial Cyber-Physical Systems*) is a
Spanish university corpus of a PLC-controlled part-marking station. It is published by the
Universidad de Burgos through its institutional repository, RIUBU, handle `10259/11686`, version 1,
DOI `10.71486/2drf-1g53`, generated 2026-05-19.

Two files were read to establish what the corpus is, and neither is a measurement file:

- `readmev1.txt`, the repository's own dataset description (19,017 bytes).
- `DAYPSCI_v1/README.md` inside the archive (17,076 bytes), the user-facing technical description
  plus a per-batch folder for each experiment.

Three properties decide how the corpus may be used, and all three are stated by the publisher rather
than inferred:

1. **The labels are faults, not attacks.** The publisher's abstract says the data include "normal
   operation and fault conditions generated through controlled fault injection, specifically
   targeting sensors and actuators (e.g., solenoid valves)". There is no attack, no adversary and no
   compromise anywhere in the corpus. This puts it in the same class as 3W (ADR 0056): a fault
   corpus, not an attack corpus, and not a labelled command corpus (ADR 0058).
2. **The network captures are PROFINET, and PHOS has no PROFINET dissector.** `src/phos/atlas/packet/`
   holds `modbus.py` and nothing for PROFINET; Modbus/TCP is the only dissector (ADR 0344). The
   `.pcapng` members are therefore recorded and **not parsed**. They are not evidence of anything.
3. **The data are event-based, not sampled.** Each row is a state change with an inter-event time
   `delta_time_ms`, a PLC scan identifier `scan_id` and an intra-scan order `event_order`. There is
   no fixed sample rate, and idle time is not represented by rows. A false-alert *rate per hour*
   therefore cannot be computed from this corpus, and the bar below does not ask for one.

### The archive, verified before this record was written

| | |
| --- | --- |
| File | `2026_Martin_DAYPSCI_v1.zip` |
| Bytes | 1,589,755,935 (1516.1 MiB) |
| sha256 | `8e3400e748f4c1e60d4a28453b26e3e92c71e855b2cc770ef725998c952176b2` |
| `unzip -t` | clean: "No errors detected in compressed data" |
| Members | 34 files in 11 batch folders plus a top-level `README.md` |
| Uncompressed | 1,589,749,327 bytes |

The archive was hashed and tested on the local copy at
`/private/tmp/claude-501/…/ics-downloads/daypsci-v1-riubu-11686/2026_Martin_DAYPSCI_v1.zip`.
The payload is **not** copied into this repository and never will be; the registry records where it
came from.

**Size approval.** 1,589,755,935 bytes exceeds `size_confirm_threshold_bytes` (314,572,800) in
`data/registry.json` by 5.1×, so `scripts/fetch_datasets.py` would refuse it unattended. **The human
approved this size in chat before this record was written**, and that approval is what authorises the
registration at this size. No other corpus in this record needed it.

### The licence, as three surfaces state it

- The RIUBU record page `https://investigacion.ubu.es/documentos/6a0f3d1b88a62d224222b247`, read
  2026-11-02, carries in its JSON-LD `"license": "https://creativecommons.org/licenses/by/4.0/legalcode"`
  and, in the item view, the Spanish sentence **"Documento(s) sujeto(s) a una licencia Creative
  Commons Atribución 4.0 Internacional"**.
- The bundled `readmev1.txt` §"ACCESS INFORMATION" states: **"Dataset Creative Commons License"** /
  **"Creative Commons Attribution 4.0 International (CC BY 4.0)"**.
- The bundled `DAYPSCI_v1/README.md` links `https://riubu.ubu.es/handle/10259/11686` as the official
  description.

CC BY 4.0 permits research use, redistribution and commercial use with attribution, so
`permits_research_use` is true. The three surfaces agree and none of them is a publisher's
restatement of another.

### What the corpus contains, by the publisher's own file naming section

The convention is `pn_<condition>_<variant>_batchXX.<format>`, and the batch table is:

| Batch | Condition | Variant |
| --- | --- | --- |
| 01 | baseline (no injected anomaly) | — |
| 02–07 | sensor anomaly | T1–T6 |
| 08–10 | solenoid-valve anomaly | T1–T3 |
| 11 | combined sensor + valve | T1 |

The fault taxonomy is the publisher's (§6 of the bundled README): sensor T1 stuck-at-0, T2 stuck-at-1,
T3 temporal delay, T4 stochastic noise, T5 glitch, T6 temporal degradation; valve T1 stuck OFF,
T2 stuck ON, T3 actuation delay.

The label columns, as §10 of the bundled README states them:

- `anomaly`: **0** normal, **1** anomaly in sensors (perception layer), **2** anomaly in solenoid
  valves (execution layer), **3** anomaly in both, **4** propagated anomaly.
- `fault`: a process-fault indicator generated by the control system (a transition such as GEMMA
  `D2`), **not** the same thing as `anomaly`.
- `FSx`, `TFSx`, `FCVx`, `TFCVx`: the injected-fault plan — which component, which fault type.
- `gemma`: the numerically encoded operating state (0 = A1 initial, 1 = F1 automatic, 2 = A2,
  3 = D1, 4 = F4, 5 = A5, 6 = A6, 7 = D2 fault).

The publisher is explicit that **fault activation is not anomaly onset**: *"The activation of a fault
(e.g., via FSx or FCVx) does not necessarily coincide with when its effects become observable in the
system."* That sentence governs the bar below.

### One folder does not match the naming pattern, and is recorded rather than re-ruled

Ten of the eleven batch folders match `pn_<condition>_<variant>_batch<N>` exactly. The eleventh is:

```
DAYPSCI_v1/pn_baseline__batch01/
```

The variant segment is **empty**, so the name carries a double underscore. Its files inside are
`pn_baseline_batch01.csv`, `pn_baseline_batch01.pcapng` and `README.md`, and `pn_baseline_batch01`
is precisely the example the publisher's own naming section prints for a baseline batch. Its batch
number is therefore unambiguous — `01` — and `01` is not divisible by 3.

The split rule was fixed before the archive was opened and is applied as written: the number in the
folder name decides. `pn_baseline__batch01` is **development**, because its N is 01. No new rule is
invented for the empty variant segment, and the deviation is recorded here so a reader comparing the
folder list to the published convention finds the answer instead of a gap.

## Decision

1. **Two corpus entries, one archive.** `daypsci-v1` is `development` and `daypsci-v1-heldout` is
   `held-out`; both are `status: declared`, so `scripts/fetch_datasets.py` will not download either
   on its own. Both record the same single zip, because the publisher ships one archive and the halves
   are member sets inside it rather than separate downloads. Neither entry is fetchable, so the
   duplicate `files` record costs nothing and the alternative — inventing a second archive that does
   not exist — would be a lie.

2. **The split is by batch number, fixed now, and the membership is written out in full.**
   Held back is every batch whose `N` is divisible by 3.

   | Half | Folder | Batch | Scenario |
   | --- | --- | ---: | --- |
   | Development | `pn_baseline__batch01` | 01 | baseline, no injected anomaly |
   | Development | `pn_sensor_T1_batch02` | 02 | sensor stuck-at-0 |
   | Development | `pn_sensor_T3_batch04` | 04 | sensor temporal delay |
   | Development | `pn_sensor_T4_batch05` | 05 | sensor stochastic noise |
   | Development | `pn_sensor_T6_batch07` | 07 | sensor temporal degradation |
   | Development | `pn_valve_T1_batch08` | 08 | valve stuck OFF |
   | Development | `pn_valve_T3_batch10` | 10 | valve actuation delay |
   | Development | `pn_combined_T1_batch11` | 11 | combined sensor + valve |
   | **Held back** | `pn_sensor_T2_batch03` | **03** | sensor stuck-at-1 |
   | **Held back** | `pn_sensor_T5_batch06` | **06** | sensor glitch |
   | **Held back** | `pn_valve_T2_batch09` | **09** | valve stuck ON |

   Eight folders to development, three to held back. **The held-back half contains no baseline
   batch**, because batch 01 is not divisible by 3. That is a consequence of the rule and is stated
   rather than corrected: a later held-back score must fit its normal model on the development half
   and carry it to the held-back batches, which is what a fit/score split means anyway. It also means
   the held-back half shares no scenario type with the development half in only one respect — the
   combined and delay families sit entirely on the development side — and that asymmetry is recorded
   for the reader rather than smoothed.

3. **The exact commands that build the two sets.** Run from the repository root after this record is
   committed, with `ZIP` set to the verified archive. They extract only `pn_*` members, partition by
   the table above, and then verify the counts. Nothing is copied into git: `data/*/*` is ignored.

   ```bash
   ZIP="/private/tmp/claude-501/-Users-elijahedoigiawerie-dev-phos/1709eed0-8915-4aef-b313-e075604097d6/scratchpad/ics-downloads/daypsci-v1-riubu-11686/2026_Martin_DAYPSCI_v1.zip"

   unzip -q "$ZIP" 'DAYPSCI_v1/pn_*' -d data/daypsci-v1.intake
   mkdir -p data/daypsci-v1 data/daypsci-v1-heldout

   mv data/daypsci-v1.intake/DAYPSCI_v1/pn_baseline__batch01 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T1_batch02 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T3_batch04 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T4_batch05 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T6_batch07 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_valve_T1_batch08 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_valve_T3_batch10 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_combined_T1_batch11 \
      data/daypsci-v1/

   mv data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T2_batch03 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_sensor_T5_batch06 \
      data/daypsci-v1.intake/DAYPSCI_v1/pn_valve_T2_batch09 \
      data/daypsci-v1-heldout/

   rmdir data/daypsci-v1.intake/DAYPSCI_v1 data/daypsci-v1.intake

   ls -d data/daypsci-v1/pn_* | wc -l           # must print 8
   ls -d data/daypsci-v1-heldout/pn_* | wc -l   # must print 3
   ```

   The two `ls | wc -l` lines are the verification. A count other than 8 and 3 means the split was
   not built as declared and the run stops rather than being reconciled afterwards.

4. **The result name is `atlas-daypsci-v1`, and it names a development-half measurement only.**
   **No held-back result name is declared in this record.** The held-back half is spent once, by a
   later declaration that names its own configuration, command and result; naming it here would be
   the pre-authorisation this programme exists to prevent.

5. **The bar, phrased on the development half only.** A later session that reports on this corpus must
   satisfy all five of these, or the report is a refusal:

   1. **Every one of the 8 development batches is reported separately.** An aggregate without the
      eight-row table beside it is refused. The batches differ by injected fault type, and a mean
      across them describes no scenario the publisher ran.
   2. **The positive class is `anomaly ∈ {1, 2, 3, 4}`; `anomaly = 0` is normal.** Recall is
      reported against `anomaly`, never against `fault`. The publisher states that fault activation
      and anomaly onset are temporally decoupled, so reporting `fault` as the label would measure a
      different event from the one the corpus is labelled for. `anomaly = 4` (propagated) counts as
      positive and is reported as its own column, because it is the publisher's fourth class and not
      a rounding of the first three.
   3. **The false-alert denominator is normal `part_id` sequences, not hours.** The corpus is
      event-based with a variable `delta_time_ms` and no fixed rate, so a false-alert rate per hour is
      not computable from it. A per-hour figure on this corpus is refused.
   4. **The `.pcapng` members are not parsed, and no result may depend on them.** PHOS has no
      PROFINET dissector (ADR 0344). A result that claims network-layer evidence from this corpus is
      refused until such a dissector exists and has its own declaration.
   5. **Nothing is called attack detection.** These are faults. A number from this corpus is a fault
      result, and quoting it as attack detection, or pooling it with a D2 issuer-kind rate or with
      3W, is refused (ADR 0056, ADR 0058, ADR 0143).

6. **The held-back half is not opened, not scored and not counted, until its own declaration.** This
   record builds the folders and counts them. It reads no held-back CSV, not even a header, and
   produces no number of any kind. `eval_runs/log.jsonl` is not appended: this is not a harness row.

7. **The registry entry carries the split in `status_note` and in `caveats`, not only here.** A reader
   who runs `python scripts/fetch_datasets.py --list` learns what the corpus is for and what it may not
   be quoted as, without finding this record.

8. **`DECLARED_HELD_OUT` grows by one name, `daypsci-v1-heldout`, in registry order.** The tuple in
   `src/phos/eval/build_declaration.py` is pinned by
   `tests/eval/test_build_declaration.py::test_held_out_bank_is_exactly_the_declared_corpora` and
   `tests/eval/test_seen_ledger.py::test_the_held_out_bank_is_the_declared_list`, so a held-out entry
   that is absent from it turns both red. The bank is the record of what may be spent once; adding a
   corpus to the registry without adding it to the bank would make the bank wrong.

## Consequences

- **The corpus can support a fault result and nothing else.** Event-based labels, eight development
  scenarios, no attack anywhere in it.
- **The held-back half is real, and asymmetric on purpose.** Three batches, no baseline among them,
  covering sensor stuck-at-1, sensor glitch and valve stuck-ON. Any future held-back score has to say
  it fitted elsewhere.
- **PROFINET coverage is not advanced.** The captures exist and are 1.42 GB of the archive's 1.59 GB;
  they are recorded, not read. A dissector is a separate declaration with its own lane.
- **This record does not land anything on `main` except the registration.** Per the operator's
  instruction for this run, `encyclopedia/`, `easy to reads/` and `README.md` are **not** moved, so
  ADR 0044's done-check is not met by this commit and the advancement is not to be described as
  complete until a later change updates those three surfaces.
- **P1 is not advanced.** A public university corpus is not a design partner with a control room.
- **v1 stays 8 of 12.** No measurement exists.

## What would reverse this

Scoring a held-back batch before its own declaration; quoting a number from this corpus as attack
detection or as catches; pooling it with 3W or with either D2 issuer kind; reporting `fault` as the
label; reporting a false-alert rate per hour from an event-based log; parsing the `.pcapng` members
without a declared dissector; committing any payload; or reading the held-back CSVs in this or any
session before a score declaration.
