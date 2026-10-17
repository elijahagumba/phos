# ADR 0110 — Whether the port reproduces ADR 0104's alert list on real HAI, declared before it runs

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1 rebuild, a check on ADR 0107
- **Depends on:** [ADR 0104](0104-the-frozen-candidate-on-clean-hai.md),
  [ADR 0107](0107-the-consistency-detector-enters-the-engine.md)

## Context

ADR 0107 proves the port identical to the frozen file with a lab test: one fixed synthetic plant,
compared against the frozen file's own `run`. Two things that test cannot see:

- **The scored path is not `run`.** ADR 0104's script (`scripts/measure_candidate_look.py`) cast
  the frozen file's float32 scores to float64 before `_events` and `_budget`. `run`, and the port,
  group the float32 scores directly. Under NumPy 2 a float32 array compared with a Python float
  compares in float32, so `scores >= level`, where `level` is `ONSET_FRACTION` times a peak, can
  differ between the two paths when a score falls between the float32 and float64 values of
  `level`. That moves an alert's onset, and so possibly a catch.
- **The synthetic plant is not HAI.** Identity on six signals does not show identity on 86.

A parallel session on 12 October, working from a stale checkout, wrote a duplicate port that
grouped as float64 and found it identical to ADR 0104's path on all six clean HAI test files.
That port was discarded unpushed. Its run is not evidence here. It is the reason this check is
worth one more look at editions this detector has already seen (ADR 0102 asks for a new command
and a written reason).

## Decision

One command, after this record is committed, and not before:

`uv run python scripts/measure_consistency_identity.py`

It refuses to start if `eval_runs/v1/consistency-identity-hai.json` exists. It checks the frozen
file's sha256. On HAI 22.04 and 23.05, loaded by `scripts/measure_clean_hai.py`'s `_load`, it fits
the frozen file and the port on the same training records, then for every test file computes:

- the **reference** list: ADR 0104's path, the frozen file's scores cast to float64, then
  `_events` and `_budget`;
- the port **as written**: `feature_scores`, `events`, `budget_alerts`;
- the port with **float64 grouping**: the same, with the scores cast to float64 before `events`.

It reports whether the float32 feature scores are identical, whether each port list equals the
reference `(row, column, score)` for `(row, column, score)` on every file, the alert totals, the
port alerts not in the reference, and each list's own-grouping catch from `_score_detector`. It
aborts without writing only if the reference itself does not catch 53/58 and 36/52. Otherwise it
writes the record whatever the comparison shows.

## Consequences

If the port as written is identical, ADR 0107's claim holds on the data the headline came from,
and nothing changes. If only float64 grouping is identical, the port reproduces `run`, not the
scored list, and a later record changes `events` to group as float64, with its own test. That is
a dtype correction to match what was scored, not a tuning. If neither is identical, the port has
a defect beyond the dtype, and nothing builds on it until it is found.

In every case, 53/58 and 36/52 stay ADR 0104's numbers. A port catch is a reproduction check,
not a new score, and no log row is written.

## What would reverse this

Running the command twice, or changing the port before the record of this run is committed.
