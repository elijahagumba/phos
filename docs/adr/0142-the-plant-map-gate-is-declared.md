# ADR 0142 — The plant map's gate is declared: one look at the validation corpora

- **Status:** Accepted (a declaration; run once on 16 October, result in [ADR 0143](0143-the-plant-map-fails-the-gate.md))
- **Date:** 2026-10-15
- **PART:** ADR 0117 §3 for `atlas-plant-map-v1`
- **Depends on:** [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0137](0137-smooth-weights-and-a-third-confirmation.md),
  [ADR 0140](0140-the-plant-map-survives-the-fourth-set.md),
  [ADR 0141](0141-role-files-for-the-later-hai-editions.md)

## Context

ADR 0140 made attempt 6 of the `plant-map` arena task a candidate for ADR 0117's gate, as a
detector. ADR 0141 gave the HAI validation editions role files. ADR 0117 §3.1 requires the gate to
be declared by commit before it runs: file sha256, command, result name. This is that record. It
contains no score. **This is the first gate under ADR 0117, so its look is look 1 on HAI 21.03,
22.04, 23.05 and BATADAL as validation corpora.**

## Decision

**1. What is scored.**

- Champion: `atlas-v1-consistency`, frozen, as `phos.atlas.consistency` fits and scores it.
- Challenger, result name `atlas-plant-map-v1`: `experiments/arena/plant-map/plant-map-v1/candidate-6.json`,
  `{"detector": "atlas-plant-map-v1", "map": {"naming_rules": "adr-0135", "calibrator": "platt"}}`,
  unchanged since ADR 0137.

The two settings choose the naming rule and the evidence calibrator. **Neither changes which alerts
the detector raises**, so at this gate attempt 6 alerts exactly as the map with its default
settings would. The gate judges the detector's alerts; naming and reconstruction stay off
(ADR 0129) and are not scored here.

**2. The pinned files.** `scripts/gate.py` refuses to run unless these files, hashed in this
order (each file's path, a zero byte, its bytes, a zero byte), give
`b6d384ace4b835843a62c06a8daf7db2ddc86f40a25f47a72e64e535adf70d60`:

- `src/phos/atlas/consistency.py`, `consistency_windows.py`, `plant_map_detector.py`,
  `plant_map_fit.py`, `plant_map_model.py`, `plant_map_select.py`, `signal_roles.py`;
- `experiments/arena/plant-map/plant-map-v1/candidate-6.json`;
- `data/hai-21.03/roles.toml`, `data/hai-22.04/roles.toml`, `data/hai-23.05/roles.toml`.

`scripts/gate.py` sha256 `210d4235829f537030035c79abe330a9ece1e4d02e21cf1e798d2dbde62967bd`. The scorer's files (`scripts/arena.py`'s
`scorer_sha256`) hash to `eef2850a55fa628f8e1fbac3ecebdf4ee84acbcb65687af017cabe8851ce6449`, and
the record carries that value. It differs from attempt 6's arena record (`ab82a1f6…`) because
ADR 0139's forward rule was added to `phos.breaking.liar_arena` afterwards; the HAI and BATADAL
scoring path (`phos.eval.baseline_table`) is unchanged. Tests check both pinned values against
the files.

The script also refuses to run if `src`, `scripts`, `experiments`, `data`, `pyproject.toml` or
`uv.lock` differ from the checked-out commit, and it records that commit. So the gate runs on a
committed tree, and the lab suite (§3.2) is the suite on that commit.

**3. The command, run once, on a machine that holds the four corpora:**

`uv run python scripts/gate.py`

**4. How it reads and scores.** It uses the readers, windows and scorer the champion's published
rows used:

- HAI 21.03 through `scripts/measure_a2_status.py`'s sources;
- HAI 22.04 and 23.05 through `scripts/measure_clean_hai.py`'s `_load` (ADR 0104);
- BATADAL through its prepared train and test files, with ADR 0112's windows for 3600 s
  (ADR 0113).

Both detectors keep 8 alerts per 8-hour shift with their own event grouping (ADR 0096). The
challenger groups the same way, because it hands its events to the champion's `budget_alerts`.
The chance null is ADR 0106's 500 draws at `CHANCE_SEED`, drawn as the published rows drew it:
HAI 21.03 and BATADAL each from a fresh generator (`scripts/measure_a2_status.py`), HAI 22.04
and then 23.05 from one shared stream (`scripts/measure_candidate_checks.py`).

**5. Two passes, so a broken reader cannot spend the look.**

- *Pass 1.* For every corpus: read it, check that its role file declares every column the reader
  returns, and score the champion and the chance null. Each must equal its published row in
  `eval_runs/v1/a2-status.json`:

  | Corpus | Champion | Attacks | Chance max |
  | --- | ---: | ---: | ---: |
  | HAI 21.03 | 42 | 50 | 8 |
  | HAI 22.04 | 53 | 58 | 9 |
  | HAI 23.05 | 36 | 52 | 8 |
  | BATADAL | 5 | 5 | 5 |

  If any differs, the script writes nothing and stops before the challenger is fitted, and the
  look has not happened.
- *Pass 2.* Fit and score the challenger on each corpus, apply the rule, and write
  `eval_runs/gates/plant-map-gate.json` once. No challenger number is printed before the record
  is written, so a crash part-way reveals nothing and running again after it is not a second
  look. The script refuses to run if that file exists.
  Nothing appends `eval_runs/log.jsonl`.

**6. The rule (ADR 0117 §3.3), applied by `verdict`.**

- On every corpus the challenger catches at least as many attacks as the champion.
- On at least one HAI edition it catches strictly more.
- Wherever the champion is above every chance draw (all three HAI editions), the challenger is
  too.

BATADAL has no role file (ADR 0141), so there the challenger is the champion and ties.

**7. After the run.** The result, whatever it is, is recorded in the next ADR with the record's
numbers, and that ADR goes to Elijah for acceptance (§3.4). A pass makes `atlas-plant-map-v1` the
champion. It does not put it in the engine; that is a separate record, as ADR 0107 was. A fail
leaves `atlas-v1-consistency` the champion, and this candidate is not taken to these corpora again.

## Amendment, before the look (15 October)

The first run of the declared command stopped in pass 1, as §5 intends. HAI 21.03 and 22.04
reproduced in full. On HAI 23.05 the champion reproduced (36/52) but the chance maximum was 9, not
the published 8: the published row drew 23.05 from the same stream after 22.04, and the gate had
seeded each corpus afresh. The challenger had not been fitted, no challenger number existed, and
nothing was written. The only numbers seen were the champion's published rows and one chance
maximum.

The fix draws the clean editions from one stream in their published order (§4). It changes only
`scripts/gate.py`, whose sha256 above is the amended file's; the pinned files and their sha256 are
unchanged. The look has still not happened. The run that found this used the HAI files fetched
from the corpus authors' repository at the registry's pinned commit, each matching its registered
sha256.

## What to expect, stated before the run

The champion already catches 42/50, 53/58 and 36/52, so a gain has 8, 5 and 16 attacks of room.
The plant map's held-back gains came mostly from the water plant, where the champion caught
nothing; on HAI 20.07 the challenger caught 37/38, as the champion does. A tie on every HAI
edition, which fails §3.3, is a real outcome. So is a loss.

## What would reverse this

Running the gate before this record is committed; running it twice; changing a pinned file or
`scripts/gate.py` after this record and running anyway; or reading a validation score outside the
gate.
