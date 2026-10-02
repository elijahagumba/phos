# PHOS Benchmark v1

Frozen **before** Clock B model work ([ADR 0062](../adr/0062-clock-b-freeze-before-optimise.md)).
Cited cells copy already-published public rows. REFUSED cells are measurements: the files cannot
support the claim.

This document is the protocol. The assembler is `phos.eval.benchmark`. The CLI is
`scripts/evaluate_phos_benchmark.py`. The first frozen table is
`eval_runs/benchmark/phos-benchmark-v1.md`.

## What this protocol is for

A serious reader should be able to say: this stack was scored under a ruler that was locked
before anyone tuned it. Wins, losses, and refusals come from the same table.

It is **not** a licence to overwrite HAI Mahalanobis **646.58** FP/normal hour, distillation
ungated **18.72**, or CERT 6B precision **0.104** at 48 alerts. It is **not** a skip of P1
(design-partner ICD). It does not earn ≥70% command lead.

## Locked knobs

| Knob | Value |
|---|---|
| Protocol id | `phos-benchmark-v1` |
| Seed (HAI public three-way split) | **11** |
| Threshold search on this split | **forbidden** |
| Atlas public dwell | `dwell_samples=1` |
| Atlas public logs | ungated Mahalanobis; gated joint-moment |
| Sentiel public ruler | CERT r3.1 **6B** identity aggregation at 48 alerts |
| Known-station unique lead | **0/16** (unpooled) |
| Unknown-master unique lead | **1/4** (D2 diagnostic, unpooled) |
| Public labelled command corpus | **absent** (ADR 0040) |

## Row families (do not smear)

| Family | Allowed corpora today | What the row may mean | What it must refuse |
|---|---|---|---|
| Atlas process (cyber labels) | HAI, BATADAL | window recall, FP/hour, FP/day, precision at operator budget | 2–3/day; command attribution |
| Atlas process (perturbation) | batch-distillation | same metrics with `PERTURBATION_RECALL_IS_NOT_ATTACK_RECALL` | attack recall; 2–3/day |
| Atlas command (public) | none | — | any lead rate until ADR 0040 is superseded by a real capture |
| Atlas command (D2 diagnostic) | synth water/power/unknown-master | ordinal rank **apart** by issuer kind | ≥70%; pooled lead; field rate |
| Sentiel | CERT r3.1 | 6B ruler; abstention; identity-layer diagnostics | peer advantage; `:precision` headline |
| Transfer | only after ≥2 comparable plants | train A/B, test unseen C | quoting HAI→BATADAL as transfer without a declared shared schema |

## Cell statuses

- **CITED** — copied from a frozen public harness row. Not remeasured here.
- **REFUSED** — the files cannot support the claim. Silence is the measurement.
- **DIAGNOSTIC** — scored on attacks we wrote, with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. Not a field rate.

## Ablation ladders (names, not retunes)

Atlas: `gaussian` → `ewma` → `mahalanobis` → `+topology` → `+declared_phase` → `+grouping` → `+command_evidence` → `+reachability`.

Sentiel: `counts` → `self-history` → `temporal` → `aggregation` → `peer-context-retired`.

Fixture false-positive counts on the 2-d toy must never be copied onto public log names.

## How to print the table

```bash
uv run python scripts/evaluate_phos_benchmark.py
uv run python scripts/evaluate_phos_benchmark.py --write --output-dir eval_runs/benchmark
uv run python scripts/evaluate_phos_benchmark.py --write --ablation --adversary --research --output-dir eval_runs/benchmark
```

`--write` still only reprints the frozen table. `--ablation`, `--adversary`, and `--research` write
*extra* files beside it (`ablation-fixture.md`, `adversary-catalogue.md`, `clock-b-research.md`).
Those files are not public log names. Fixture counts must not be copied onto HAI 646.58.

Do not search thresholds. Do not add a `trained-joint` transfer row. Do not pool 0/16 with 1/4.

ADR 0063 records a **new** log name for declared-role BATADAL→HAI zero-shot. It does not
rewrite this freeze table. The HAI→BATADAL transfer cell stays REFUSED. Native HAI
Mahalanobis 646.58 is not overwritten.

## What Wave 3 may do after this freeze

Plant-state *transitions* on a **declared** phase register. Sequence models versus 6B (a loss at 48
alerts is the result). Hypothesis-conditional forecasts attached as supporting or contradictory
evidence. If Mahalanobis still wins on HAI, Mahalanobis wins.
