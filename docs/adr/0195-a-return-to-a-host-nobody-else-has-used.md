# ADR 0195 — A return to a host nobody else has used

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Sentiel investigation, one challenger
- **Depends on:** [ADR 0148](0148-bet-001-is-scored-once.md),
  [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md),
  [ADR 0193](0193-rare-links-among-declared-peers.md)

## Context

`eval_runs/build/sentiel/cch0959.md` describes CCH0959 from the r3.1 answer file,
his own earlier days, his six role peers, and all 34 features. The frozen 6B
scorer is unchanged by that note. His labelled counts sit on top of his own
earlier medians, except the thumb drive and the file copies, which rise by
about one event a day. Those counts rank in the tens of thousands among the
340,171 cached person-days. The two features that touch the top 48 of the
210,814 scored days are ties at a shared value, not a value that stands clear
of the cut.

What the 34 features do not record is which host. From 1 July 2010, a person
returning to a web host that no other user has requested on any earlier day
happens on 23 person-days. Twenty are CCH0959, on `lockheedmartinjobs.com` and
`lockheedmartin.com`. Three are CSF0929, on `wikileaks.org`. No other user has
such a day. The first request does not count. `new_counterparties` and
`lane-a-dev:peer-links` score a name on the day it is new, and that first day
for `lockheedmartinjobs.com` is 2 August, whose midnight is outside the label.
The following month of repeats is invisible to both.

This record names the signal before it is scored. It does not contain a rank.

## Decision

**One signal, beside 6B, not inside it.** `AggregationPolicy()` stays the PART
6B sum. The 34 features stay symmetric. No weight is added. No host name from
the answer file is written into the code.

The score of a person-day is the number of web hosts in that day's set such
that both of these are true:

1. The same user requested the host on a strictly earlier day.
2. Every earlier request of that host, by anyone, was by that same user.

A day with no such host scores 0. The count is the score. There is no scale,
no threshold, and no second term. Same-day requests by other users neither
create a point nor remove one. The state that judges a day is the state at the
start of that day.

The queue is the same person-days 6B ranks: days on or after the first labelled
attack in r3.1. Rank by `(-score, user_id, timestamp)`. Cut at 48. The
malicious flag is not in the key. A user is found only by one of their labelled
days. The scorer name is `exclusive-host-return`. It is not the frozen 6B name.

**Why this should lift CCH0959.** Twenty of his labelled days are returns to a
host nobody else has used. Each of those days scores at least 1. CSF0929 has
three such days as well, so the same count keeps the first insider in the
queue without adding his 6B score back in.

**Why this should not flood the top 48.** In the measurement already written
down, those 23 days are the entire set. Twenty-three is less than 48, and
every one of them belongs to one of the two labelled insiders. Innocent
person-days score 0 and can enter the budget only as the tie that fills the
remaining slots.

**Success test, fixed before the run.** On CERT r3.1, at 48 alerts, at least
one labelled day of CCH0959 is in the top 48 and at least one labelled day of
CSF0929 is in the top 48. The run reports CCH0959's best rank, how many of
CSF0929's labelled days are in the 48, precision at 48, and how many innocent
people the score places in the 48. `eval_runs/log.jsonl` is not appended. The
frozen 6B row is not overwritten and not recomputed.

## Consequences

A pass on r3.1 is unconfirmed until a later session scores this named scorer
once on CERT r4.2. That session is not this one. r4.2 is not fetched here.

If the run fails, at most three refinements are written in
`eval_runs/build/sentiel/decisions.md` with a reason each, and then the work
stops.

## What this record does not decide

It does not score the mail to a single-sender external domain, the words in
those messages, or the September drive counts. Those are in the description.
They are not this signal.

## Note at merge (19 October)

The r3.1 result was already counted before this record was written: the investigation
(`cch0959.md`) had established that the days scoring above zero are exactly 23 labelled insider
days. The "one score" on r3.1 therefore confirms a count, and is a description of r3.1, not a
test. The 48-slot precision of 0.479 includes 25 zero-score days of one innocent user that
entered only by tie order; counting only real alerts, it is 23 alerts, all labelled
(ADR 0196's amendment). In r3.1 no innocent user ever returns to a host nobody else has used, which
may be how the CERT generator plants scenario activity rather than how people behave. The real test is r4.2,
with the realism check ADR 0196 now declares.
