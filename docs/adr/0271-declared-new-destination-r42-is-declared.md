# ADR 0271 — The declared-new-destination shot on r4.2 is declared, and it is not run

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Sentiel v1, S3, one shot
- **Supersedes:** nothing
- **Depends on:** [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md),
  [ADR 0261](0261-the-s2-register-is-the-directorys-email.md),
  [ADR 0270](0270-declared-new-destination-is-frozen.md)

## Context

ADR 0270 froze `declared-new-destination` before any r4.2 file was opened for
this shot. S3's pass sentence, from `docs/v1-roadmap.md` §2.2, is unchanged:
more distinct labelled insiders than the frozen 6B scorer, beside a label-free
chance null, on the larger release, at 48 tickets a day. The first challenger
already lost that sentence. This is a different scorer. Equality is not a pass.

The output path does not exist. This record contains no r4.2 count.

## Decision

**One shot, after this record is committed, and not before.** The scorer, the
budget, the rank key, and the register do not change after r4.2 is seen.

| Item | Value |
| --- | --- |
| Scorer | `declared-new-destination` |
| Code | `phos.sentiel.declared_destination.score_declared_new_destinations` |
| sha256 | `ee061bc7d86c8e24df55469a5867a8358a617f1fc1b99013bd54de0a52d5a6a3` of `src/phos/sentiel/declared_destination.py`, raw file bytes, path not mixed in |
| Register | ADR 0261 directory email for r4.2, sha256 `6b0597ae973edb27f2ff995ab1727e7bf12ae6af6aae57ba17c54169d294aac0`, hosts and machines empty |
| Queue | Cached person-days on or after the first labelled attack in r4.2. Prefix days build history and are not tickets. |
| Budget | 48 tickets a calendar day. A ticket is one person-day. |
| Rank key | `(-score, user_id, timestamp)` |
| Alerts | `phos.sentiel.exclusive_return.alerting` via `phos.sentiel.daily_tickets.alerts_per_day`. Positive scores only. A zero is not an alert. |
| Who counts | A labelled insider is surfaced when at least one malicious person-day is among the alerts. A benign day does not count. |
| Frozen 6B | `6b:cert-r4.2@48-per-day`. `AggregationPolicy()` with empty weights, `FeatureSet.PEER`, `GaussianBaseline(min_samples=8)` fit on observations strictly before the first labelled attack, then `WindowScorer`. Not retuned. The r3.1 row is not written. |
| Chance null | `phos.sentiel.daily_tickets.expected_distinct_insiders`, ADR 0202 item 6. Reported beside the two counts. Not a pass bar by itself. |
| Result names | `declared-new-destination:cert-r4.2@48-per-day` and `6b:cert-r4.2@48-per-day` |

**Pass rule, not reworded.** The challenger surfaces strictly more distinct
labelled insiders than frozen 6B under the per-day rule. Equality is not a pass.

**Realism reading, fixed now.** The run reports, over the whole release, how
many innocent users have at least one day with a positive new-destination
count, and what share of innocent users that is. Innocent users are distinct
user ids in the trace cache who are not labelled insiders of r4.2. It is read
this way:

- **Nearly all innocent users have such a day.** New directory mail is ordinary.
  A pass means more labelled insiders had a malicious day inside the daily top
  48 of this count than frozen 6B did. It does not mean writing to a new
  colleague is itself an intrusion, and it does not describe a workplace where
  staff do not email new colleagues. r3.1 was this shape: 998 of 998.
- **Almost no innocent user has such a day.** The generator planted directory
  novelty on the people it labels. A pass is then reported as finding the
  insiders in CERT r4.2 through directory addresses ordinary staff do not add,
  not as evidence about real organisations.

The same JSON reports how many innocent users have a directory address nobody
else mailed. That count is not the score and does not move the pass bar. On
r3.1 it was 0 of 998.

**Command.** One shot. The script refuses to start if the output already exists,
or if the scorer file's sha256 is not the digest above. It checks both before
it opens a trace. On the default data directory it also refuses if the
directory register hash is not ADR 0261's r4.2 digest. The declared command
does not pass `--data-dir`.

```
uv run python scripts/score_s3_destinations.py --out eval_runs/build/v1/sentiel/s3-declared-new-destination-r42.json
```

The JSON carries both result names, both distinct-insider counts, the surfaced
user ids, the chance-null expectation, `s3_met`, the register hash, and the
realism counts. It does not carry a confidence. `eval_runs/log.jsonl` is not
appended. The address list is not written.

## Consequences

Until that command has been run, S3 is not met by this challenger. The host
shot's loss stands. A pass or a loss here is the measurement this record named,
and it is not rerun to improve it.

## What this record does not decide

It does not rescore S2. It does not rescore the r3.1 frozen row. It does not
weight the 34. It does not start Intelligence, the API, or the UI.
