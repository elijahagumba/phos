# ADR 0140 — The plant map survives the fourth held-back set, losing nothing

- **Status:** Accepted (a report)
- **Date:** 2026-10-15
- **PART:** ADR 0139's confirmation; next, ADR 0117's gate
- **Depends on:** [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0138](0138-three-confirmations-the-same-answer.md),
  [ADR 0139](0139-a-forward-rule-for-losses-within-the-champions-own-churn.md)

## The result

Attempt 6 (`{"detector": "atlas-plant-map-v1", "map": {"naming_rules": "adr-0135",
"calibrator": "platt"}}`), unchanged since ADR 0137, was scored once on `CONFIRM_SEEDS_3`
(95401–95410, 180 runs) beside the champion. Record: `eval_runs/arena/plant-map/red-team-confirm-3.json`.

| | Champion | Attempt 6 |
| --- | ---: | ---: |
| Liar passes | 46 | **111** |
| Water | 0 | **49** |
| Power | 22 | 28 |
| Batch | 24 | 34 |
| Champion passes lost | — | **0** (allowance under ADR 0139: 2) |

**Verdict: survives**, under ADR 0139's forward rule, and it would also have survived ADR 0123
§9.3's original rule, since it lost none. No corpus was unmeasurable.

## Across all four held-back sets

| Set | Champion | Challenger | Lost |
| --- | ---: | ---: | ---: |
| `RED_TEAM_SEEDS` (attempt 1) | 53 | 116 | 2 |
| `CONFIRM_SEEDS` (attempt 5) | 50 | 113 | 2 |
| `CONFIRM_SEEDS_2` (attempt 6) | 43 | 103 | 2 |
| `CONFIRM_SEEDS_3` (attempt 6) | 46 | 111 | 0 |
| **Together, 714 runs** | **192** | **443** | **6** |

The three earlier verdicts stay "fails". This one is the first held-back set the challenger
survives, and it does so on a rule declared before the set existed.

## What it does and does not change

- `atlas-plant-map-v1` (attempt 6) is now a candidate for **ADR 0117's gate, as a detector.** It
  is not yet the champion and not yet the engine's detector.
- Naming and reconstruction stay off everywhere (ADR 0129).
- **The gate needs work first.** The map models only signals with declared roles. Role files
  exist for HAI 20.07, the synthetic plants and ICSSim; HAI 21.03, 22.04, 23.05 and BATADAL have
  none, so on them the challenger would be the champion exactly (ADR 0127's test: with no map
  the challenger is the frozen detector) and could not catch more. Their role files, read from
  their documentation under ADR 0123 §3's rules, come before the gate, and those corpora's data is
  not in this build container. Then the gate is declared by commit (sha256, command, result
  name), run once, and recorded in an ADR for Elijah to accept.
