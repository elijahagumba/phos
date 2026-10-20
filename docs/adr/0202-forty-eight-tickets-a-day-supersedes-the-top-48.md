# ADR 0202 — Forty-eight tickets a day supersedes the top 48 overall

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Sentiel v1, S3 re-declaration, before the holdout lift
- **Depends on:** [ADR 0146](0146-identity-features-keep-the-thirty-four-symmetric.md),
  [ADR 0147](0147-cert-r42-held-out-and-not-fetched.md),
  [ADR 0194](0194-kept-scorer-is-still-6b-r42-unscored.md),
  [ADR 0195](0195-a-return-to-a-host-nobody-else-has-used.md),
  [ADR 0196](0196-exclusive-host-return-is-the-r42-one-shot.md)
- **Supersedes:** ADR 0196's budget of "top 48 overall", its result name
  `exclusive-host-return:cert-r4.2@48`, and the command that would have written
  `eval_runs/build/sentiel/exclusive-host-return-r42.json`. That command never ran, so that file
  <!-- evidence-ack: eval_runs/build/sentiel/exclusive-host-return-r42.json — the superseded command never ran, so that file was never written -->
  was never written. The scorer in ADR 0195 does not
  change. The amendment below stays in force word for word.

## Context

S3's pass sentence, from `docs/v1-roadmap.md` §2.2, is: "More distinct labelled insiders
surfaced than the frozen 6B scorer, beside a label-free chance null." The budget in that
sentence is 48 tickets a day (`docs/v1-roadmap.md` §1, and build brief C). ADR 0196 declared
a single cut of the top 48 person-days in the whole release.

The r4.2 archive is registered and not opened. `r42_may_be_scored()` is still false. The
October allow-list does not yet include `kilthub.cmu.edu` or `ndownloader.figshare.com`.
Brief C orders the fetch, so this record is the ADR that changes that list. The code change
is the next commit. This commit does not lift the holdout and does not score.

## Amendment kept verbatim

ADR 0196's amendment stays in force. This record does not edit its words. "At most 48" in
that amendment is applied inside each calendar day, by `alerting(ranked, 48)`, which is the
budget change below. The positive-score rule and the realism reading are unchanged.

> Written before any r4.2 file is fetched or scored. The scorer, its definition and the budget are unchanged; two things are added to what the run reports and how it is read.
>
> 1. **Only real alerts count.** The run raises alerts with `phos.sentiel.exclusive_return.alerting`: positive scores only, at most 48. A day that scores 0 is not an alert, whatever the tie order. It reports the alerts raised, the labelled days among them, and precision over the alerts raised. On r3.1 this rule gives 23 alerts, all 23 labelled, where the 48-slot figure of 0.479 counted 25 zero-score days of one innocent user that entered only by tie order.
> 2. **A realism check, declared now.** The run also reports, from `single_user_host_owners` over the whole release, how many innocent users have at least one web host that no other user requested, and what share of all innocent users that is. It is read this way, fixed before the run:
>    - **Near zero innocent users with such a host:** the signal most likely reads how the CERT generator plants scenario activity (benign browsing drawn from a shared pool, scenario hosts added on top). A pass is then reported as "finds the insiders in CERT r4.2 through hosts only they use", not as evidence about real organisations.
>    - **Many innocent users with such hosts, and the insiders still in the alerts:** the signal separates the insiders from ordinary single-user browsing, which is the stronger result.
>
> **The caveat, stated now.** On r3.1, no innocent user ever returned to a host that no one else had used; the only days that did were the two insiders' (`cch0959.md`, ADR 0195). In real browsing, many people use sites no colleague uses. Success on CERT therefore may reflect the dataset, and real enterprise logs are the test of real-world value. S3 is judged on r4.2 as declared; any public claim carries this scope.

## Decision

**The budget is 48 tickets a day.** A ticket is one person-day. This definition is locked
here. A later commit does not soften it after seeing r4.2.

1. **Queue.** Both arms rank the same person-days: every cached person-day whose window
   timestamp is on or after the first labelled attack in r4.2 (`min` of `label.start` from
   `read_insiders` for release `r4.2`). Days before that instant are the attack-free prefix.
   They are not tickets. Exclusive-host state is still built from every cached day, including
   the prefix, so a return can see earlier requests. Those prefix days are not ranked.

2. **Rank and alerts.** Each calendar day (the UTC date of the window timestamp), rank that
   day's person-days by `(-score, user_id, timestamp)`. `timestamp` is the window timestamp,
   the `day` field `phos.sentiel.bet001.rank_days` already sorts on. The rank key is not
   inverted and the malicious flag is not in it. `phos.sentiel.exclusive_return.alerting(ranked, 48)`
   keeps positive scores only, at most 48. A zero score is not an alert.

3. **Who counts.** A labelled insider is surfaced when at least one of their malicious
   person-days is among the alerts raised. A benign day of that user does not count. The
   headline is the count of distinct surfaced insiders.

4. **Frozen 6B, same per-day rule, not retuned.** Detector name
   `aggregate:gaussian:peer set (34 features) (6B)`. Policy `AggregationPolicy()` with empty
   weights, so each of the 34 has weight 1. The 34 stay `FeatureSet.PEER`. Fit
   `GaussianBaseline(min_samples=8)` on observations strictly before the first labelled
   attack, then `WindowScorer(fitted, AggregationPolicy(), None)` on the queue. That is the
   PART 6B procedure. No threshold is chosen from r4.2. The r3.1 alert threshold is not
   copied onto r4.2 and is not rewritten. New result name `6b:cert-r4.2@48-per-day`. This
   run does not write the r3.1 frozen row. That row stays the published ruler: precision
   **0.104** at 48 alerts overall, recall 0.5, in
   `phos.sentiel.cert_curve.CERT_R31_BUDGET_CURVE`. `eval_runs/log.jsonl` is not appended.
   Hypothesis confidence is not written into the result.

5. **Challenger, unchanged code path.** Result name
   `exclusive-host-return:cert-r4.2@48-per-day`. Scores come from
   `phos.sentiel.exclusive_return.exclusive_return_scores`. The count, the host rule, and
   the rank key are ADR 0195's. They are not retuned after r4.2 is seen.

6. **Chance null, label-free and score-free as a draw.** Each calendar day in the queue,
   draw `n_draw = min(48, n_person_days)` person-days uniformly from the people present that
   day. `n_person_days` is the number of person-day rows that day. `n_people` is the number
   of distinct user ids among those rows. The draw does not read a score and does not prefer
   a label. Expected distinct labelled insiders is the sum over insiders of
   `(1 - product over that insider's malicious days of (1 - n_draw/n_people))`. An insider's
   malicious days are the queue person-days the r4.2 label covers for that user. An insider
   with none contributes 0. The labels name whose days enter the product; they do not change
   the draw. The expectation is reported beside the two counts. It is not a pass bar by
   itself. If `n_draw > n_people` on any queue day, the run stops. It does not clamp the
   ratio. The trace cache is one row per user per day, so the two counts are expected to
   match.

7. **S3 is met only if** the challenger surfaces more distinct labelled insiders than frozen
   6B under this rule. Equality is not a pass. A loss is not met. The sentence is not reworded.

8. **Realism check, same JSON.** From `single_user_host_owners` over the whole release
   (every cached person-day, prefix included): how many innocent users have at least one
   web host that no other user requested, and what share of all innocent users that is.
   Innocent users are distinct user ids in the trace cache who are not labelled insiders of
   r4.2. The share is that count over the count of innocent users. The reading is the
   amendment's reading, applied to these two numbers. It does not move the pass bar.

9. **Command and output.** One shot, and the script refuses to run again if the output
   already exists:

   ```
   uv run python scripts/score_s3_r42.py --out eval_runs/build/v1/sentiel/s3-r42.json
   ```

   The JSON carries both result names, both distinct-insider counts, the surfaced user ids,
   the chance-null expectation, `s3_met`, and the realism counts. It does not carry a
   confidence.

10. **Allow-list.** The next commit adds `kilthub.cmu.edu` and `ndownloader.figshare.com`
    to `ALLOWED_FETCH_HOSTS` and changes `r42_may_be_scored()` to true, citing this ADR.
    That commit does not add an r4.2 scoring path and does not open an r4.2 event file.
    `CERT_R42.scored` stays false until the one shot has been written. The fetch, after that
    commit, checks sha256 `586446b00e83ce5cdabf9dc889b0b6e7a9f44556cee3c03d39445d790122556c`
    and size `4824287500` against the registry entry. A download that would leave less than
    10 GB free does not start.

The pure functions that implement the per-day budget and the chance null are tested on a
hand fixture before the shot. They do not read r4.2. Their names are
`phos.sentiel.daily_tickets.alerts_per_day` and
`phos.sentiel.daily_tickets.expected_distinct_insiders`. `alerts_per_day` groups by UTC
date, ranks with `rank_days`, and calls `alerting`. `expected_distinct_insiders` is the
sum-product in item 6 and nothing else.

## Consequences

Until the one shot, S3 is not measured. ADR 0196's r3.1 description stands. A pass or a
loss on r4.2 is the measurement this record named, and it is not rerun to improve it.

## What this record does not decide

It does not fill the identity register of ADR 0146. It does not put a weight on the 34.
It does not score S2. It does not start Intelligence, the API, or the UI.
