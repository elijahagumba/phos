# ADR 0143 — The plant map fails ADR 0117's gate: no gain on real HAI, three attacks lost

- **Status:** Accepted by Elijah, 16 October 2026 (ADR 0117 §3.4)
- **Date:** 2026-10-16
- **PART:** ADR 0117 §3 for `atlas-plant-map-v1`, the result
- **Depends on:** [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0141](0141-role-files-for-the-later-hai-editions.md),
  [ADR 0142](0142-the-plant-map-gate-is-declared.md)

## The run

`uv run python scripts/gate.py`, once, on commit `591f366` with the declared files hashing to
`b6d384ac…` as ADR 0142 pins. It ran in the build container after the four corpora were fetched
there: the HAI files from the corpus authors' repository at the registry's pinned commit, and
BATADAL's two files from batadal.net once Elijah allowed that host. Every file matched its
registered sha256. Pass 1 reproduced the champion and the chance maximum on all four corpora.
Record: `eval_runs/gates/plant-map-gate.json`. This is look 1 on these corpora as validation
corpora; the registry's seen ledger records it.

## The result

| Corpus | Attacks | Champion | Challenger | Chance max | Signals mapped |
| --- | ---: | ---: | ---: | ---: | ---: |
| HAI 21.03 | 50 | 42 | **40** | 8 | 33 of 79 |
| HAI 22.04 | 58 | 53 | 53 | 9 | 28 of 86 |
| HAI 23.05 | 52 | 36 | **35** | 8 | 31 of 86 |
| BATADAL | 5 | 5 | 5 | 5 | 0 of 43 |

**Verdict: fails ADR 0117 §3.3**, on two of its clauses:

1. It catches fewer than the champion on HAI 21.03 (40 against 42) and HAI 23.05 (35 against 36).
2. It catches strictly more on no HAI edition.

The second clause fails whatever is made of the first. Even if the three lost attacks were
forgiven, there is no edition where the map adds a catch. ADR 0139's churn allowance was declared
for `CONFIRM_SEEDS_3` only and is not applied here; applying it after this score would be the rule
change PHOS exists to refuse, and it would not change the verdict.

The challenger stayed above every chance draw wherever the champion is, and the map was not empty:
it modelled 28 to 33 signals with declared roles on each HAI edition. On BATADAL it had no roles
and equalled the champion, as declared.

## What it means

The plant map's gains were real on the development and held-back synthetic plants: 443 liar
passes against the champion's 192 over four sets, almost all on the water plant's falsified
sensors, where the champion caught nothing (ADR 0140). On the real HAI testbed it adds nothing at
8 alerts per shift and costs a few. The likely reading, which this record cannot test without a
second look: HAI's attacks are mostly ones the champion's per-signal and loop scores already
catch, so a map score that leads at some alert cells displaces a few correct alerts from the
budget and gains none. That is a hypothesis, not a finding.

## Decision

- `atlas-v1-consistency` stays the champion. Nothing enters the engine. Roadmap §2, the v1 verdict,
  priors and frozen rows are unchanged.
- Attempt 6 is not taken to these corpora again (ADR 0142 §7). No diagnosis runs on them: the
  record holds counts only, not which attacks were lost, and finding out would be a second look.
- The plant map stays in the lab as a research line, with its synthetic results reported as what
  they are. Any successor needs a new hypothesis, development data to build it on, and a held-out
  corpus no detector has seen; T1's held-out seeds (94001–94020) remain untouched, and the real
  plant data being sought (ORE Catapult, Cubico, MTC) would be the strongest test.
- Claims: the water plant's falsified-sensor result may be described as a synthetic finding. No
  claim may say the plant map improves detection on real industrial data.

## What would reverse this

Re-running the gate, scoring attempt 6 or a variant on these corpora outside a new declared gate,
or describing the plant map as an improvement on real plant data.
