# ADR 0230 — v1 stands at six of twelve after the sprint; S2 is not met

- **Status:** Accepted (Elijah's decision on S2, 19 October 2026)
- **Date:** 2026-10-19
- **PART:** v1 scorecard, after build brief C (`docs/build-brief-2026-10-c.md`)
- **Depends on:** [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md),
  [ADR 0204](0204-the-identity-register-stays-empty.md),
  [ADR 0211](0211-a6-is-one-configuration.md),
  [ADR 0212](0212-a3-queue-rank-is-declared.md)

## Context

The sprint aimed at 10 of 12. Its reviewer pass counted 7. Its S2 row read the roadmap sentence
("implemented, tested and scored on CERT r3.1 and at least one larger release") as met by scoring
the six identity features with an empty register (ADR 0204). An empty register matches nothing, so
every feature is zero on every person-day by construction. S2's criterion is titled "Which, not
just how many". A score that cannot name a host, a destination or a machine has not measured which.
That is the softer reading the brief rules out.

## Decision

1. **S2 is not met.** The features are implemented and tested, and the zeros stay recorded as what
   an empty register produces. S2 is met only when a register declared without labelled insiders
   names something, and the features are scored with it on r3.1 and a larger release.
2. **The v1 count is 6 of 12**: A2, A4, A5, A6, C1 and S1. The rows are in
   `eval_runs/build/v1/REPORT.md`.
3. **A3 and S3 were each scored once and are not met.** A3: 57 of 203 attacks had a true alert in
   the top 10% of their shift's queue, against a bar of 102 (ADR 0212). S3: at 48 tickets a day,
   `exclusive-host-return` surfaced 1 distinct labelled insider on CERT r4.2 and frozen 6B surfaced
   59, against a label-free chance expectation of 35.3; 0 of 930 innocent users had a web host no
   other user requested, the reading ADR 0196 fixed as the generator artefact (ADR 0202). Neither is
   rescored.
4. **Still open and still reachable:** A1 (the four validation rows are reprinted, not regenerated
   from the files, ADR 0210), C2 (the timed trial in `eval_runs/build/v1/tools/c2-trial.md` needs a
   person) and A7. A7's bar is one command that regenerates every v1 number, run by someone outside
   the project. `scripts/reproduce_v1.py` (ADR 0221) checks the committed records' checksums and
   digits; it does not regenerate, so it does not meet A7 even when run from outside. Like A1, A7
   needs a regenerating command, which opens the validation corpora and so needs its own
   declaration, with nothing tuned.

## Consequences

Version 1 can reach at most 9 of 12 by 24 January 2027 without a new S2 register. The front page and
the record page say 6 of 12. The frozen r3.1 row (precision 0.104 at 48 alerts) is unchanged.

## What would reverse this

A register declared before any labelled look that names at least one host, destination or machine,
scored on r3.1 and r4.2 under its own declaration. It would move S2, not reword it.
