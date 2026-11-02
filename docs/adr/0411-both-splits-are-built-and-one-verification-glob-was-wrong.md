# ADR 0411 — Both splits are built, both counts hold, and one verification glob in ADR 0410 was wrong

- **Status:** Accepted (a build record; nothing here is a score)
- **Date:** 2026-11-02
- **PART:** corpus registration, step after [ADR 0409](0409-the-daypsci-v1-fault-corpus-is-registered-and-every-third-batch-is-held-back.md)
  and [ADR 0410](0410-fdia-synthetic-microgrid-is-registered-as-diagnosis-and-the-split-is-by-bus-system.md)
- **Supersedes:** nothing. Both declarations stand as written; the correction below is a defect in
  one shell glob, not a change of decision
- **Depends on:** [ADR 0409](0409-the-daypsci-v1-fault-corpus-is-registered-and-every-third-batch-is-held-back.md),
  [ADR 0410](0410-fdia-synthetic-microgrid-is-registered-as-diagnosis-and-the-split-is-by-bus-system.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md)

## Context

ADR 0409 and ADR 0410 were both committed before either archive was unpacked, which is the order
`docs/rules/data-tiers.md` requires. The declared commands were then run once each, in the declared
order. This record states what the runs produced and corrects one line of ADR 0410 that does not do
what it says.

## Decision

### 1. Both archives unpacked as declared, and both count checks passed

**DAYPSCI v1.** `unzip -q "$ZIP" 'DAYPSCI_v1/pn_*' -d data/daypsci-v1.intake` produced 11 batch
folders, which is every batch the publisher ships. They were then moved, by name, into the two halves
ADR 0409's table declares:

| Half | Folders | `ls -d …/pn_* \| wc -l` |
| --- | --- | ---: |
| `data/daypsci-v1/` | `pn_baseline__batch01`, `pn_combined_T1_batch11`, `pn_sensor_T1_batch02`, `pn_sensor_T3_batch04`, `pn_sensor_T4_batch05`, `pn_sensor_T6_batch07`, `pn_valve_T1_batch08`, `pn_valve_T3_batch10` | **8** |
| `data/daypsci-v1-heldout/` | `pn_sensor_T2_batch03`, `pn_sensor_T5_batch06`, `pn_valve_T2_batch09` | **3** |

8 and 3 are the declared figures, so the verification passed and nothing was reconciled after the
fact.

**FDIA-SyntheticMicroGrid.** The two `unzip` calls, splitting on the publisher's folder names, produced:

| Half | Folders | CSV count |
| --- | --- | ---: |
| `data/fdia-synthetic-microgrid/` | `IEEE-5 Bus Dataset`, `IEEE-9 Bus Dataset` | **2** |
| `data/fdia-synthetic-microgrid-heldout/` | `IEEE-14 Bus Dataset`, `IEEE-30 Bus Dataset` | **2** |

`legend_label.txt` is present in both halves, as Decision 2 of ADR 0410 requires. The top-level folder
name is the truncated `FDIA-SyntheticMicroGrid Complex Spatio-Temporal Fa`, quoted exactly as the
archive carries it; the extract matched on that string and on nothing else.

### 2. One verification line in ADR 0410 was wrong, and the wrong line failed loudly rather than silently

ADR 0410 Decision 3 ends with:

```bash
ls data/fdia-synthetic-microgrid/*.csv | wc -l            # must print 2
ls data/fdia-synthetic-microgrid-heldout/*.csv | wc -l    # must print 2
```

**These are wrong.** The CSVs sit one level deeper, inside the `IEEE-<N> Bus Dataset` folders, so the
glob matches nothing. Run under `zsh` on this machine it printed:

```
(eval):10: no matches found: data/fdia-synthetic-microgrid/*.csv
       0
```

A count of `0` is a failed verification by the record's own rule, and it was treated as one: the
run did not proceed on the strength of it. The correct lines, which were run and which print 2 and 2,
are:

```bash
ls data/fdia-synthetic-microgrid/*/*.csv | wc -l            # prints 2
ls data/fdia-synthetic-microgrid-heldout/*/*.csv | wc -l    # prints 2
```

The defect is recorded rather than edited into ADR 0410, because an accepted record is immutable
(`docs/adr/README.md`). It is worth recording rather than shrugging at for one reason: the failure mode
was a *false refusal*, not a false pass. A glob that under-matches stops an honest run; it does not
let a wrong split through. Had it printed `2` for the wrong reason, that would have been the dangerous
direction, and it did not.

ADR 0409's own verification lines (`ls -d data/daypsci-v1/pn_* | wc -l`) used a directory glob that
is correct at its depth, and printed 8 and 3 with no error.

### 3. The payloads are ignored, and no byte of either corpus entered git

`git check-ignore` confirms `.gitignore:38` (`data/*/*`) covers a DAYPSCI CSV member, a DAYPSCI batch
folder's contents, and an FDIA CSV. `git status` shows no untracked file under `data/`. The archives
stay where they were, outside the repository, and were not modified.

### 4. No held-back file was read, not even a header

Neither half's CSVs were opened. The only reads of either corpus were documentation:
`readmev1.txt`, `DAYPSCI_v1/README.md`, one batch-level `README.md`
(`pn_valve_T1_batch08/README.md`), and FDIA's `legend_label.txt` — all before or beside the
declarations, none of them a measurement file. `eval_runs/log.jsonl` was not appended. No harness ran.

### 5. `DECLARED_HELD_OUT` grows by two names, and that is the only edit `src/phos/eval` receives

ADR 0409 Decision 8 and ADR 0410 Decision 8 both require the bank to name the new held-out halves.
The tuple is pinned from two directions:

- `tests/eval/test_build_declaration.py::test_held_out_bank_is_exactly_the_declared_corpora`
  compares it to the registry's `held-out` entries.
- `tests/eval/test_seen_ledger.py::test_the_held_out_bank_is_the_declared_list` does the same for
  the ATLAS subset.

So a registered held-out corpus that the tuple omits turns both red, and a tuple entry with no
registry entry does the same. `daypsci-v1-heldout` and `fdia-synthetic-microgrid-heldout` are
appended in registry order. Nothing else in `src/phos/eval` is touched: `build_declaration.py` gains
two string literals and no logic.

Two tests in `tests/sentiel/` assert that `src/phos/eval` is byte-identical to `HEAD` —
`test_part_2s_labelled_interval_was_not_taught_about_entities`'s neighbour,
`test_the_part_2_package_is_unmodified_in_git`, and
`test_the_reused_packages_are_unmodified_in_git[src/phos/eval]`. Both run `git diff HEAD -- src/phos/eval`,
so they are red *while the edit is uncommitted* and green once it lands, which is what they are
for: they catch a Sentiel session editing the PART 2 harness mid-flight, not a later declaration
adding a corpus to a declared list. The edit here is the second kind, and the commit that carries it
is the evidence. This is recorded rather than left for a reader to discover as a red suite.

## Consequences

- **The four registry entries describe a split that exists on disk**, with the counts this record
  states, not a split that was merely declared.
- **A later held-back score has a correct verification line to copy.** ADR 0410's is wrong by one path
  segment and this record says so in the place a reader will look.
- **Nothing here is a measurement.** No number in this record is about a detector.

## What would reverse this

Reading a held-back CSV before its own score declaration; committing a payload; treating the
`…/*.csv` glob's `0` as a passed check; or describing either corpus as scored.
