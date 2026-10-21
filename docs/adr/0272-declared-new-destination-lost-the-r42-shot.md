# ADR 0272 — Declared-new-destination lost its r4.2 shot; S3 stays not met

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Sentiel v1, S3, the one shot
- **Supersedes:** nothing
- **Depends on:** [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md),
  [ADR 0270](0270-declared-new-destination-is-frozen.md),
  [ADR 0271](0271-declared-new-destination-r42-is-declared.md)

## Context

ADR 0271 was committed as `58f77e0` before this run, with the scorer frozen at
sha256 `ee061bc7d86c8e24df55469a5867a8358a617f1fc1b99013bd54de0a52d5a6a3` and the
r4.2 directory register at `6b0597ae973edb27f2ff995ab1727e7bf12ae6af6aae57ba17c54169d294aac0`.
The output path did not exist. The command, run once:

```
uv run python scripts/score_s3_destinations.py --out eval_runs/build/v1/sentiel/s3-declared-new-destination-r42.json
```

It exited 0 in 676 seconds over 217393 person-days across 341 calendar days, with
70 labelled insiders. Both hashes were checked before a trace was opened. Neither
the scorer nor the budget nor the register was touched after r4.2 was seen.

## Decision

**S3 is not met.** The challenger surfaced fewer distinct labelled insiders than
frozen 6B, under the per-day rule ADR 0202 locked.

| Arm | Distinct labelled insiders | Alerts raised | Labelled days among alerts |
| --- | ---: | ---: | ---: |
| `declared-new-destination:cert-r4.2@48-per-day` | **21** | 13633 | 66 |
| `6b:cert-r4.2@48-per-day` | **59** | 15927 | 428 |
| Label-free chance null | 35.2855319099821 | — | — |

Three readings of that, each worth stating plainly:

1. **It lost the pass sentence.** 21 against 59. Equality would not have been a
   pass; this is not equality.
2. **It is below its own chance null.** A uniform draw of 48 person-days a day
   from the people present expects 35.29 distinct insiders. Ranking by this count
   finds 21. The signal is worse than not ranking at all.
3. **It finds nobody 6B misses.** The 21 surfaced ids are a strict subset of 6B's
   59. The challenger contributes no person, so there is no case for pooling it
   with 6B or reporting it as complementary.

**Realism, read as ADR 0271 fixed it before the run.** 930 of 930 innocent users
have at least one day with a positive new-declared-destination count, a share of
1.0. That is the first of the two declared readings: new directory mail is
ordinary, and the daily budget is the right tail of an ordinary count. r3.1 was
the same shape at 998 of 998, so r4.2 did not change the diagnosis — it confirmed
it at scale. The exclusivity count, reported beside the score and not the score,
is again 0 of 930 innocent users with a directory address nobody else mailed, the
same emptiness that defeated the host challenger.

**What is spent.** This shot. It is not rerun to improve it, and the sentence is
not reworded. `eval_runs/build/v1/sentiel/s3-r42.json` is untouched, so the host
challenger's 1 of 59 stays the record of that attempt. The frozen r3.1 row stays
precision 0.104 at 48 alerts, recall 0.5 — `frozen_r31_row_written` is false in
the result. `eval_runs/log.jsonl` was not appended. The 34 were not weighted and
S2 was not rescored.

**v1 stands at 8 of 12.** Met: A1, A2, A4, A5, A6, C1, S1, S2. Not met: A3, A7,
S3, C2. S3 now carries two spent shots on r4.2, under two different scorers,
both declared before their look and both lost.

## Consequences

Two identity readings of CERT r4.2 have now failed to beat a 34-feature Gaussian
on peer sets: exclusivity, which the generator leaves empty, and novelty, which
is ordinary for everyone. A third attempt should not be another reading of the
same column. The honest reading is that the directory register names destinations
but that counting them, new or exclusive, does not separate these insiders — and
that the thing S2 still cannot name, which host and machine a person touched, is
where the remaining identity signal would have to come from.

## What would reverse this

A second run of this command, calling 21 against 59 a pass, pooling the
challenger's subset with 6B, or reporting the 930 of 930 realism share as
evidence about real organisations.
