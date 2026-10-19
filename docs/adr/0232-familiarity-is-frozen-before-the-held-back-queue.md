# ADR 0232 — Familiarity is frozen before the held-back queue

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane Q
- **Depends on:** [ADR 0231](0231-queue-rankers-and-mixed-shifts-are-declared.md)

## Context

The six reorderings declared in ADR 0231 have been scored on HAI 20.07 and on seeds
97651–97670. Nothing here is a score of seeds 97601–97620. Those seeds have not been
generated.

| Variant | HAI A3 | HAI recall within 8 | Seed A3 | Seed recall within 8 | Rejected |
| --- | ---: | ---: | ---: | ---: | --- |
| Champion order | 19/38 | 37/38 | 19/20 | 20/20 | |
| `familiarity` | 19/38 | 37/38 | 19/20 | 20/20 | no |
| `innocent` | 17/38 | 34/38 | 15/20 | 20/20 | yes |
| `cross-path` | 13/38 | 28/38 | 10/20 | 20/20 | yes |
| `familiarity-cross` | 16/38 | 32/38 | 10/20 | 20/20 | yes |
| `cross-innocent` | 13/38 | 28/38 | 10/20 | 20/20 | yes |
| `all-three` | 16/38 | 32/38 | 10/20 | 20/20 | yes |

`familiarity` changed no seed's pass and no HAI file's pass count. The margin over the
champion is zero, which is smaller than the one seed the champion already misses (97660,
water, 13 alerts, 6 of them inside the hold). The other five variants pass that seed and
lower recall within 8 on HAI, so they are rejected. Every development seed raised at least
one benign process event and at least one alert inside the hold.

## Decision

**Frozen ranker.** `familiarity` in `src/phos/eval/queue_reorder.py`. It demotes an alert
whose member-column set appeared on a training-normal event, and otherwise keeps the
champion order. It does not add or remove an alert.

**sha256.** `b5e0eed03bf0799f5f5db5d0898cda63a07ce2d27234e7c155ee45df97c0188b`

**Command.** `PYTHONPATH=src:. .venv/bin/python scripts/measure_d_queue.py held-back`

**Result name.** `atlas-queue-v2:familiarity`

**Output.** `eval_runs/build/d/queue/held-back.json`. The command refuses when that file
exists.

**Seeds.** 97601–97620, the generator in ADR 0231, not generated before this record.

**Bar.** On that batch, A3 strictly higher than the champion's own ordering of the same
alerts, and recall within 8 alerts a shift not lower. The bar is not reworded after the run.

## Consequences

The next step is to run the command once. Whatever it writes is the result.

## What would reverse this

Running the command before this record is pushed, running it twice, or freezing a variant
this table rejects.
