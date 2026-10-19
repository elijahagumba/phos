# ADR 0196 — exclusive-host-return is the r4.2 one-shot, and it is not run

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Sentiel investigation, S3 declaration
- **Depends on:** [ADR 0147](0147-cert-r42-held-out-and-not-fetched.md),
  [ADR 0195](0195-a-return-to-a-host-nobody-else-has-used.md)

## Context

ADR 0195 named `exclusive-host-return` before it was scored. On CERT r3.1,
at 48 alerts, it places 20 labelled days of CCH0959 and 3 of CSF0929 in the
top 48 (`eval_runs/build/sentiel/exclusive-host-return.json`). That is a
development result. r4.2 is the one-shot check, and it has not been fetched.

## Decision

A later session may score this scorer once, and only once, on CERT r4.2.
The definition in ADR 0195 does not change between this record and that run.
`AggregationPolicy()` stays the frozen 6B sum. The 34 features stay symmetric.

| Item | Value |
| --- | --- |
| Scorer | `exclusive-host-return` |
| Code | `phos.sentiel.exclusive_return.exclusive_return_scores` |
| Budget | 48 alerts |
| Rank key | `(-score, user_id, timestamp)` |
| Result name | `exclusive-host-return:cert-r4.2@48` |
| Command | `uv run python scripts/score_exclusive_host_return.py --release r4.2 --out eval_runs/build/sentiel/exclusive-host-return-r42.json` |

The command exists. It returns without reading a file, because
`r42_may_be_scored()` is still false and this script has no r4.2 path.
The archive was not fetched. No sha256 was invented. Nothing was appended
to `eval_runs/log.jsonl`.

The later session lifts the holdout in its own commit, builds the r4.2
trace cache the same way r3.1 was cached, and then runs that command once.
It does not retune the count, the rank key, or the budget after seeing r4.2.

## Consequences

Until that run, r3.1 is the only score of this signal. A pass there does
not say what the signal does on a larger release.

## Amendment before the one-shot (19 October, at merge)

Written before any r4.2 file is fetched or scored. The scorer, its definition and the budget are
unchanged; two things are added to what the run reports and how it is read.

1. **Only real alerts count.** The run raises alerts with `phos.sentiel.exclusive_return.alerting`:
   positive scores only, at most 48. A day that scores 0 is not an alert, whatever the tie order.
   It reports the alerts raised, the labelled days among them, and precision over the alerts
   raised. On r3.1 this rule gives 23 alerts, all 23 labelled, where the 48-slot figure of 0.479
   counted 25 zero-score days of one innocent user that entered only by tie order.
2. **A realism check, declared now.** The run also reports, from
   `single_user_host_owners` over the whole release, how many innocent users have at least one
   web host that no other user requested, and what share of all innocent users that is. It is
   read this way, fixed before the run:
   - **Near zero innocent users with such a host:** the signal most likely reads how the CERT
     generator plants scenario activity (benign browsing drawn from a shared pool, scenario hosts
     added on top). A pass is then reported as "finds the insiders in CERT r4.2 through hosts only
     they use", not as evidence about real organisations.
   - **Many innocent users with such hosts, and the insiders still in the alerts:** the signal
     separates the insiders from ordinary single-user browsing, which is the stronger result.

**The caveat, stated now.** On r3.1, no innocent user ever returned to a host that no one else had
used; the only days that did were the two insiders' (`cch0959.md`, ADR 0195). In real browsing, many people
use sites no colleague uses. Success on CERT therefore may reflect the dataset, and real
enterprise logs are the test of real-world value. S3 is judged on r4.2 as declared; any public
claim carries this scope.
