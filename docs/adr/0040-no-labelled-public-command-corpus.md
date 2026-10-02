# ADR 0040 — No labelled public command corpus: the files were read, and the gap is named

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Command-lead mechanical honesty, session 5 (licence-confirmed public command capture)
- **Supersedes:** nothing
- **Amends:** [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)
  on one clause only — Data4Cyber `pcapng` *is* the dpkt path (proved on the file). It does
  not amend what those corpora still cannot be as *labels*.
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md),
  [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)
  Decision 8,
  [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md),
  [ADR 0039](0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md)

## Context

Session 5's success is either (a) `discover_labelled_command_corpora` finds a real labelled
command capture Atlas already dissects, issuer kinds scored apart if both exist, with
`ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT` attached, or (b) an ADR refuses and names the exact
gap. Refusal is success. Completing sessions 1–5 does not earn the ≥70% cycle contract.

Frozen D2, scored apart, not remeasured, not pooled, not the cycle contract:

| Issuer kind | Unique led | Moved | n | ADR |
|---| ---: | ---: | ---: | --- |
| Known-station (`scada` / `hmi`) | **0** | 6 | 16 | 0038 / 0039 |
| Unknown-master (silent `engineering`) | **1** | 4 | 4 | 0038 / 0039 |

The **1 of 4** is a D2 diagnostic with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. FP/hour on
that synthetic corpus remains **1.1650**. Recall there is not detection.

`LABELLED_COMMAND_CORPUS_REQUIREMENTS` (ADR 0014 Decision 8) still names what would count:
Modbus/TCP capture Atlas already dissects; a separate attack-free learn stretch; at least one
control action by an attacker (operator-shaped write, not reconnaissance); ground-truth windows
with start and end; licence and provenance as `data/registry.json` records; ideally a labelled
legitimate operator action in the same capture.

Licence confirmation (ADR 0033) is not a measurement. Files win over papers.

## Decision

**There is still no labelled public command corpus.** `discover_labelled_command_corpora`
stays empty. `scripts/evaluate_command_detection.py` still prints the requirements instead of
a number. `test_this_repository_holds_no_labelled_command_corpus` still passes — the intended
tripwire, because no real command-action ground truth was added.

The three licence-confirmed campaign corpora were judged on their files, not their papers.

### Data4Cyber (Zenodo 19965384, CC-BY-4.0) — fetched, inspected, refused as a command corpus

Payload: `data4cyber_dataset.zip`, 134,034,872 bytes, MD5 `a540979c63120c9a0295ff974933580f`
(matches the record). Gitignored (ADR 0006). Not registered with `format="pcap"` and
`attack_intervals`.

**What the files do supply (so the refusal is not the wrong gap):**

- `dpkt.pcap.UniversalReader` / `read_frames` / `dissect_capture` open the shipped `.pcapng`.
  S0 `network_tap.pcapng`: 306,604 frames read, link type 1 (Ethernet), not truncated,
  `accounts_for_every_frame`. ADR 0033's clause that "pcapng is not yet the dpkt pcap path"
  is **false for this corpus**. This record amends that clause only.
- S0 is a separate attack-free stretch: CSV `attack_active=False` on all 1,798 rows
  (~30 min). The capture holds 187,442 Modbus messages. `192.168.1.20` (the attacker node
  in `ip_device_mapping.csv`) is absent. The EMS (`192.168.1.11`) issued 260 writes
  (function codes 6 and 16 to registers 40149 / 40151 / 40242 / 40246).
- S1 contains operator-shaped attacker writes: 520 Modbus function-code 16 requests from
  `192.168.1.20` to `192.168.1.88:502` at registers 40242 and 40246 (Fronius `p_set_percent`
  / `p_set_confirm` as `attacker_only_meta.json` lists). 516 of those 520 fall inside the
  publisher's span named "Industroyer Modbus command execution window".

**The exact gap — not command-action labels:**

- Ground truth is 1 Hz **process phases**. `dataset.csv` carries `attack_active` /
  `attack_phase` / `attack_phase_all`. `state.jsonl.gz` (IPAL) copies those row labels
  (`malicious`, `attack_active`, `attack_phase`) onto a process-state dictionary. It is
  not per-packet command ground truth.
- S1 `attack_phase` values on disk: `normal` 885, `s1_industroyer_active_solar_power` 902,
  `s1_reconnaissance_nmap_solar_power` 11. `attack_active` is True for recon and for
  manipulation. That column is not a command window.
- `attack-phases.json` names an "Industroyer Modbus command execution window" with a start
  and an end. Mapping that clock onto the pcapng does **not** invent command-action
  ground truth. Inside that same span the capture still holds 120 legitimate EMS writes
  and 82,315 Modbus messages (mostly function-code 3 polling). A wall-clock process phase
  is not "this write was the attacker's control action."
- `attacker_only.pcapng` is a **time slice** of those phases (notes in
  `experiment_overview.json`: "aligned to dataset timestamps"). It is not attacker frames.
  S1's file still has 41,117 Modbus sources at `192.168.1.11` versus 776 at
  `192.168.1.20`, and it begins at the nmap interval. Scoring it as a command-attack
  capture would mix reconnaissance, EMS polling, and attacker writes.
- 5,880 normal CSV seconds (~1.6 h) cannot be the false-positives-per-normal-hour ruler
  (ADR 0003). S3 is 1,800/1,800 attack rows. Do not quote a Data4Cyber FP/hour.

Using attacker identity (`192.168.1.20`) as a label would make unknown-master detection
tautological. It is not a labelled control-action window.

### s7-data-modification (Zenodo 15373938, CC-BY-4.0) — not a capture

`packets_dataset.parquet` remains a parsed packet **table**. Feeding it as a pcap would
bypass the dissector ADR 0012 is built around. Atlas's only `ProtocolDissector` is
Modbus/TCP. Adding S7comm was out of scope. Process parquet labels (`normal` /
`data_modification`) are Track A only, and textual.

### 3W Petrobras — faults, not attacks

Class labels 1–9 remain faults (abrupt BSW, slugging, hydrates, …). Collapsing them to
"attack" would be a false statement. No command capture.

## What this session did not do

- Did not edit `src/phos/atlas/templates.py`.
- Did not undo ADR 0036–0039.
- Did not pool D2 0/16 with 1/4, and did not quote either as ≥70%.
- Did not claim ≥70% on any public row: there is no public command-labelled row with an
  `n` and caveats.
- Did not expand `library/ot.py` or grow `08-water-unknown-master.toml`.
- Did not surface uncalibrated hypothesis confidence.
- Did not write payloads into git.

## Consequences

**Gained.** The shopping list is no longer "we have not looked." Data4Cyber is a Modbus
pcapng Atlas can read, with a silent attacker host on S0 and operator-shaped writes on S1.
The missing piece is **command-action ground truth**, not a dissector and not a licence.

**Cost.** The cycle command-lead contract stays **unearned**. Session 5 completing is not
a field rate and not ≥70%.

**Rejected:** registering `format="pcap"` with `attack_intervals` copied from CSV
`attack_active`, from `attack_phase`, or from `attack-phases.json` clocks; treating
`attacker_only.pcapng` as attacker frames; quoting Data4Cyber FP/hour; parquet-as-pcap;
an S7 dissector this session; collapsing 3W faults.

## When to revisit

When a licence-confirmed capture Atlas already dissects ships **command-action** windows
(which writes were the attacker's control, as start/end that do not have to be reverse-
engineered from 1 Hz process phases), with a separate attack-free learn stretch, and
issuer kinds can be scored apart if both exist. A new public row is a new key. It is never
pooled with D2 0/16 or 1/4. ≥70% is earned only on that row with `n` and caveats.
Silence remains allowed.
