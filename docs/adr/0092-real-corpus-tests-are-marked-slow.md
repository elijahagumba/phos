# ADR 0092 — Real-corpus tests are marked slow, and the default suite omits them

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, test time
- **Depends on:** [ADR 0002](0002-pytest-imports-package-from-src.md)

## Context

A full `uv run pytest -q --durations=40` on this machine, with the fetched corpora on disk,
took **1731.75 s** (28 minutes 52 seconds): 3748 passed, and 2 failed. The two failures were
`test_the_part_2_package_is_unmodified_in_git` and
`test_the_reused_packages_are_unmodified_in_git`, and they failed because `src/phos/eval` was
dirty in that working tree. They pass on the committed tree. They are not slow.

The time is the real corpora. The two batch-distillation cases in
`tests/eval/test_real_dataset.py` are **541.07 s** and **530.93 s**. The same file's other
present corpora are the rest of the long tail (HAI train report round-trip 72.10 s, HAI train
end-to-end score 58.95 s, and a run of cases between about 5 s and 19 s). Those tests already
skip when the CSV is absent. On a machine that has fetched them, they run, and that is the
jump from a few minutes to half an hour.

## Decision

**A test is `slow` when this run spent at least five seconds in it and the time is a fetched
corpus.** A whole module is marked when that is what the module is, so the cases that shared
the file and landed just under five seconds move with it. `pyproject.toml` `addopts` gains
`-m "not slow"`. The command line replaces that expression. The full run is:

```bash
uv run pytest -m "slow or not slow"
```

`uv run pytest` is the default. `tests/eval/test_slow_marker.py` collects both ways and checks
that a real-corpus score is absent from the default and present in the full expression.

Moved, whole module:

| Module | Why |
|---|---|
| `tests/eval/test_real_dataset.py` | Every present corpus is loaded and scored. Batch-distillation end-to-end **541.07 s**, its report round-trip **530.93 s**. HAI, BATADAL and Data4Cyber cases in the same file are the next longest calls, down through 5.29 s. |
| `tests/atlas/test_hai_topology.py` | The whole module reads the real HAI files. The cold read of the training file was **17.37 s** on `test_the_hai_topology_is_total_over_the_corpus_it_describes`. After that one function was omitted, the same read showed up as **17.07 s** on `test_every_hai_signal_round_trips_through_its_subsystem`. The module moves so the cost cannot slide to the next reader. |
| `tests/atlas/test_real_corpora.py` | Joint model on the fetched corpora. Longest calls **11.82 s** and **5.85 s**. |
| `tests/reasoning/test_real_calibration.py` | Calibration on those corpora. HAI **27.70 s**, HAI evidence **7.14 s**. |
| `tests/sentiel/test_real_corpus.py` | The CERT r3.1 release. Longest calls **5.96 s** and **5.22 s**. |

Moved with the shared HAI vertical. Four tests in `tests/atlas/test_engine.py` call the cached `hai_vertical`: `test_the_whole_vertical_runs_on_hai_and_explains_a_real_subsystem_event` (**5.54 s** when it ran first), `test_grouping_leaves_an_operator_materially_fewer_things_to_investigate_on_hai` (**5.11 s** once it was the first), `test_grouping_on_hai_discards_no_evidence_at_all`, and `test_grouping_on_hai_keeps_every_attack_window_it_had_covered`. The cache only hides the cost from the tests that run after the first, so all four move.

Moved, one function:

| Test | Measured |
|---|---|
| `tests/sentiel/test_engine.py::test_the_vertical_runs_on_the_real_corpus` | **19.88 s** |

Left in the default run, on purpose: demo pipeline setup (**8.93 s** and **7.22 s**) is the
simulated plant, not a fetched corpus. `test_shipped_s0_s1_prepare_on_the_real_files` was
**4.16 s**, under the cut. `test_generating_everything_is_available_behind_one_flag` was
**4.13 s**, a generator.

No frozen row moves. Nothing is appended to `eval_runs/log.jsonl`.

## Consequences

A checkout with the corpora on disk no longer spends half an hour on `uv run pytest`. The
default run after this mark, on the same machine, was **120.18 s**: 3675 passed, 82
deselected. The longest calls left in it are the simulated-plant demo setups (6.75 s and
6.48 s). The corpus tests are still there, and they still skip when the files are absent.
CI's `pytest -q` uses the same default. A coverage or timing claim about those corpora has
to use the full expression.
