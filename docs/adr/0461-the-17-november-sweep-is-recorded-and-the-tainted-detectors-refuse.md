# ADR 0461 — The 17 November sweep is recorded, and the tainted detectors refuse

- **Status:** Accepted
- **Date:** 2026-11-23
- **PART:** Method. Records an integrity event and stops the code that fitted on forbidden corpora. No scoring.
- **Supersedes:** nothing
- **Depends on:** [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0411](0411-both-splits-are-built-and-one-verification-glob-was-wrong.md),
  [ADR 0460](0460-the-atlas-research-method-runs-in-five-roles-and-scores-one-unseen-number.md)

## Context

On 17 November 2026 the disk's access times show one sweep across this machine's checkouts. ADR 0460 recorded that the two held-back halves were read and that no record named the cause. This record names what was read, what it costs, and what the code now does about the detectors built the same day from corpora the tier rule forbids.

No file under `data/` was opened to write this record. The counts come from access times (`stat` and `find -newerat`) and from git. An access time on this volume moves only when it is not already later than the file's modification time, so the counts are a floor: a file read that day whose access time had already moved later would leave no mark.

## What was read

The window is 18:59:11 to 19:02:50 UTC, with two files at 19:03:26. The sweep read **14,985 files** across the checkouts under the home directory's `dev`, not only `data/`. Inside `phos` that is 8,495 files, including `src`, `tests`, `docs`, `scripts` and `eval_runs` as well as the corpora. The other checkouts with marks in the window are `phos-h2` (1,543), `phos-wt-overnight` (1,420), `phos-wt-on-ingest` (865), `phos-wt-on-w5-calibration` (865), `phos-wt-on-w1-detector` (864), `phos-share` (465), `phos-vault` (465) and `phos-overnight-data` (3). `phos-g-dnp3` and `phos-public` have none.

The signature is that every visible file was read and every dot-directory was skipped: `.git`, `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.claude`, `.codex`, `.agents`, `.cursor`, `.github`, `.swarm`, `.ruv-swarm`, `.claude-flow`, `.gstack`, and `.DS_Store`. No code in `src/`, `scripts/`, `tests/` or `public/` walks the whole data folder. Nothing was written during the window. The cause is still not identified. A backup, a sync client, an index, or an agent with filesystem access would all look like this, and this record does not pick one.

### Never-tier files read (40)

`docs/rules/data-tiers.md` says never to read, score or iterate on `hai`, `hai-21.03`, `hai-22.04`, `hai-23.05` and `batadal`. These 40 files in those folders were read:

- `data/hai-22.04`: `train1.csv` through `train6.csv`, `test1.csv` through `test4.csv`, `roles.toml`, and the ten `summary/summary(*.csv).txt` files. That is 21 of 21.
- `data/hai-23.05`: `hai-train1.csv` through `hai-train4.csv`, `hai-test1.csv`, `hai-test2.csv`, `label-test1.csv`, `label-test2.csv`, `roles.toml`, `summary_label1.txt`, `summary_label2.txt`. That is 11 of 11.
- `data/hai`: `hai-21.03-test-prepared.csv`, `hai-21.03-train-prepared.csv`, `topology.toml`.
- `data/hai-21.03`: `roles.toml`.
- `data/batadal`: `BATADAL_dataset03.csv`, `BATADAL_dataset04.csv`, `batadal-test-prepared.csv`, `batadal-train-prepared.csv`. `manifest.json` was not read.

### What is spent, and what is not unseen

`data/phos-icssim-heldout` had **180 of 220** files read. That batch is spent. Lane 1 already spent it (ADR 0276). The read means it is not unseen and it is not reopened.

`daypsci-v1-heldout` (6 of 9 text files; the three captures were not read) and `fdia-synthetic-microgrid-heldout` (3 of 3) are not unseen. Neither held-back half, and no red corpus, is to be treated as unseen. ADR 0460 Decision 4 already said the two halves are not called unseen. This record extends that to every red corpus whose files were in the sweep.

Nothing in git shows that the swept bytes were copied into a later commit. Nothing shows they were not. A read into a chat leaves no line in the repository. That limit stays.

## The five commits, and their descendants

Five commits on `main` the same day, all earlier than the sweep, build detectors around HAI and BATADAL attack patterns, and one of them adds a SWaT factory. SWaT is never-use by licence in the same rule file. Each is an ancestor of commit `0c6b43d`, the tip of `main` when this record was written, so every commit from these five forward to that tip carries the code:

| Commit | Time (UTC) | What it did | Rule it breaks |
|---|---|---|---|
| commit `627ca3b8a71db2d4b8204a7cafdae08023491c08` | 07:48 | `hai_detector()` fits on `data/hai/hai-21.03-train-prepared.csv`. `batadal_detector()` fits on `data/batadal/batadal-train-prepared.csv`. | Never read, score or iterate on `hai` and `batadal` |
| commit `427bd001beffdb5fbb0d007c304dd4110fa0606c` | 11:34 | `swat_detector()` is the consumption path for SWaT, and ADR 0453 quotes never-tier detection counts as a reason to reopen it | Never use SWaT (licence). The quoted counts also break the never-read rule |
| commit `b4addce71dce40b11ef2308c0704a469221dd875` | 11:56 | `_build_batadal_code_law_detections()` is built around BATADAL pump attacks | Never read, score or iterate on `batadal` |
| commit `d3272ead7aa53ad1e1a2a1223feca80a2188c4e1` | 13:25 | Flow and HAI builders, plus scripts that score both corpora and print the result | Never read, score or iterate on `batadal` and `hai` |
| commit `59bae23fd284abd14cfc0f30f9bc99e9f4e39d13` | 15:29 | Replaces HAI thresholds to target that corpus's labelled attacks | The same rule, and it is iteration: thresholds moved after seeing the attacks |

The commit messages say the lint and the type check were clean. They were not. That is recorded in the progress log for this change and is not repaired here. History is not rewritten. The messages stay.

## The starting number is unaffected

**87 of 120** is copied from `eval_runs/build/lane-e/lane1-heldout.json`: `"lane1": 87` at line 92, over `"attacks": 120` at line 87. ADR 0276 and `docs/method/scoreboard.md` cite that file. The file is a committed result of the synthetic ICSSim batch, not a recomputation from the files the sweep read. The sweep does not move it. v1 stays 8 of 12.

## Decisions

1. **The event is recorded here, and the cause stays open.** Neither held-back half and no red corpus is treated as unseen. `phos-icssim-heldout` stays spent. The scoreboard's 87 of 120 stays the copied value.

2. **Six entry points refuse before they open a path.** `hai_detector`, `batadal_detector`, `swat_detector`, `_build_batadal_code_law_detections`, `_build_batadal_flow_anomaly_detections` and `_build_hai_code_law_detections` raise `QuarantinedCorpusError` (`phos.referee.quarantine`) as their first act. `AtlasDetector.run` no longer calls the three builders, so a synthetic exam does not trip the refusal. The old bodies remain in git history. They are not deleted from history, and they no longer run.

3. **Five scripts move to `experiments/quarantine-2026-11-17/`.** `evaluate_batadal.py`, `evaluate_batadal_hai.py`, `evaluate_hai.py`, `test_hai_detector.py` and `test_csv_detectors.py`. Each carries a header saying why. `experiments/` is already outside the linter. They are evidence, not entry points.

4. **A guard test** uses the tier resolver. Every name the rule marks never-read is refused, and the referee package does not fit one. The six entry points raise, and they do it before a path opens.

5. **Two resolver gaps close, and the role field stays ignored.** The iterate-freely bullet already says "the synthetic plants" and "the declared development half of any new corpus". The parser only saw backtick names, so `synth` was refused as unknown, and a registered development half fell through to "any newly registered unseen corpus" (score once). `resolve` now reads those two phrases from the rule text. `synth` is iterate. A registered name is iterate when the registry also lists that name with `-heldout` or `-heldback` appended, which is the committed split, not the `role` field. A name the rule already places in never-read stays never-read, checked first. Held-back names stay score once. On the registry as it stands, the names that move from score once to iterate are `daypsci-v1`, `fdia-synthetic-microgrid`, `grfics-v3`, `kelmarsh`, `penmanshiel` and `tu-wien-pilot-factory`. A development corpus with no paired held-back name stays score once. `dtu-lab` is that case, and ADR 0394 already says it has no held-back half.

6. **CI runs the linter and the type check as separate steps, and the type check always runs.** The job still fails if either is red. The errors already on `main` are not fixed in this change.

## What this record does not do

- It does not identify the program that read the files.
- It does not score anything, open a corpus, or append `eval_runs/log.jsonl`.
- It does not rewrite history or remove the five commits.
- It does not lift ADR 0067. ADR 0462 voids ADR 0453's reopening argument.
- It does not move 87 of 120, and v1 stays 8 of 12.

## Consequences

- Calling any of the six entry points is a refusal, not a result.
- Builders still must not link red corpora into a checkout. This refusal is the backstop for the referee package, not a lock on the disk.
- The access times remain fragile. A later read can erase them. A hash manifest of the sealed files is still the right next step and is not done here.

## What would reverse this

Naming the program that swept the disk, in a later record, does not by itself make a red corpus unseen. Making one unseen again needs its own record and Elijah. Replacing a quarantined body needs a declaration that does not fit on a never-read corpus and does not use SWaT.
