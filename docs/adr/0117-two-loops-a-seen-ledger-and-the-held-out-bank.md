# ADR 0117 — Two loops, a seen ledger, and the held-out bank

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** after v1 A2, the iteration loop
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md),
  [ADR 0102](0102-the-clean-hai-run-and-where-atlas-loses.md),
  [ADR 0114](0114-the-liar-measurement-is-assembled-and-held.md),
  [ADR 0116](0116-a2-status-four-of-five-beyond-chance.md)

## Context

The detector Atlas runs today came from one agent in one worktree, with 7 scored runs on HAI 20.07
and one held-out look at HAI 21.03 (ADR 0096). Elijah wants that loop run continuously and in
parallel, so that by September 2027 (`docs/phos-2027.md`) many candidates have been tried. ADR 0114
already states the rule informally: iterate on development seeds, spend held-out seeds once, after a
declaration.

Two facts constrain it. ADR 0116 records that `atlas-v1-consistency` has now been scored on all
five judging corpora, so no public corpus PHOS holds can judge a claim about unseen data. And
W1 needs a corpus the measured configuration was not developed on. The registry recorded licences
and files, but not which corpora had been seen. Elijah asked Claude to start on 12 October; the
choices in this record are Claude's, made at his request.

## Decision

### 1. Two loops

- **The fast loop** may run as often as anyone likes, by agents or by hand, on **development**
  data only. Its numbers are diagnosis. They are never reported as a result, and never appended to
  `eval_runs/log.jsonl`.
- **The slow gate** is the only way a number becomes a claim: declared by commit (the candidate's
  sha256 and the command), run once, published whichever way it goes. ADR 0102's rule stands: a
  second look needs a new command and a written reason.

### 2. Three tiers, recorded in the registry

`data/registry.json` (schema version 2) gives each usable corpus a `role` and lists every `seen`
record. `scripts/fetch_datasets.py` refuses an unknown role, and refuses a `held-out` corpus that
has a `seen` record.

| Role | Who may read its labels | Corpora today |
| --- | --- | --- |
| `development` | Anyone, any number of times | HAI 20.07, batch-distillation, Data4Cyber; the synthetic seeds in `phos.eval.liar_declaration.DEVELOPMENT_SEEDS` |
| `validation` | Only a promotion gate (§3). Seen, so it proves nothing new; kept from agents so it still catches over-fitting to development data | HAI 21.03 (and the integrated `hai` slice of it), HAI 22.04, HAI 23.05, BATADAL |
| `held-out` | Nobody, until a declaration; then scored once and moved to `validation` | **None for Atlas.** Synthetic seeds 94001–94020 stay reserved for T1 (ADR 0094, ADR 0114) |

HAI 20.07 stays the one development HAI edition because it is the one the current detector was
already built on. HAIEnd 23.05 has no role and is marked seen by proxy: it was recorded during the
same experiment as HAI 23.05, whose attack windows and scores are already read. BATADAL is a weak
validation corpus: at 8 alerts per 8 hourly rows, chance also catches 5 of 5 (ADR 0113).

A corpus is **seen** once any score of any PHOS detector on its test part has been read. Seen is
permanent and is not per detector: what was learned from one score shapes every later design.

### 3. Promotion: champion and challenger

The champion is `atlas-v1-consistency`. A challenger replaces it only when all of the following
hold, in this order:

1. It is declared by commit before the gate: file sha256, command, result name. It never reuses
   `atlas-v1-consistency`, which stays frozen.
2. The full lab suite is green on that commit.
3. On each `validation` corpus, at 8 alerts per shift and grouped the same way as the champion
   (ADR 0096), it catches no fewer attacks than the champion, and strictly more on at least one
   HAI edition. Where the champion is above every draw of ADR 0106's chance null, so must it be.
4. Elijah accepts the ADR that records the gate.

Each gate is one look at the validation corpora and is counted in its ADR. Repeated looks slowly
turn validation into development; when that count makes the margin unconvincing, the answer is a
new held-out corpus, not more gates. A promoted champion is not yet Atlas's engine detector:
entering the engine is a separate record, as ADR 0107 was. Roadmap §2 and the v1 verdict are
unchanged.

### 4. Refilling the held-out bank

A corpus enters the bank when its licence is confirmed on two independent surfaces, it is
registered with a sha256 for every file, and no detector output on its test part has been computed
or read. Reading its schema and its attack-free training part is allowed. It leaves the bank only
through a declared, single score.

W1 needs **attack-labelled process telemetry**. Of the known leads, only ICS-Flow and GRFICS carry
process state; the others are network-only and serve W3. In priority order:

| # | Source | Would judge | Blocker | Next action | Who |
| --- | --- | --- | --- | --- | --- |
| 1 | ICS-Flow (Kaggle `alirezadehlaghi/icssim`; arXiv 2305.09678) | W1, T2, W2 (emulated) | Licence unverified; may duplicate the Zenodo ICSSim manifest | Read both licence surfaces; settle the duplicate question | Claude |
| 2 | A new public process corpus released after October 2026 | W1 | None exists yet | Watch `icsdataset/hai` and the catalogues in `docs/data-campaign/hunt-2026-10.md` | Claude |
| 3 | GRFICSv3 (Fortiphyd Logic) | W2, W3, T1 on data PHOS did not design | Licence not found; it generates runs, so the generation must be declared first | Read the repository's licence | Claude |
| 4 | Westermo network traffic | W3 (fault against attack on the network) | Second licence surface | Read the *Data in Brief* paper | Claude |
| 5 | ICS-NAD (*Scientific Data*, February 2026) | W3, on real equipment | Licence unreadable; 246 GB; network only | Read the Science Data Bank record | Claude |
| 6 | A home OT lab | W2, W3 | Hardware | Price two PLCs and a mirroring switch; declare the capture protocol before recording | Elijah |
| 7 | A design partner's historian export | W1, W4, W9 | A plant saying yes | The data-only pilot offer | Elijah |

Captures PHOS makes itself (rows 3 and 6) are labelled "on a PHOS-built testbed" wherever they are
reported, never "public" or "real".

## Consequences

Nothing is scored here. No detector, constant, prior, frozen row or roadmap criterion changes. The
registry gains two optional fields and its schema version; entries without them load as before.
`tests/eval/test_seen_ledger.py` fixes the roles above and the two refusals. The arena itself
(`phos arena`, copying the frozen sandbox harness rather than editing it) is the next record and
reads these roles. Until row 1 or 2 of §4 lands, no Atlas result can be a W1 result.

## What would reverse this

Iterating on a `validation` corpus outside a gate; reading a score on a `held-out` corpus before its
declaration; giving a seen corpus the `held-out` role; or reporting a fast-loop number as a result.
