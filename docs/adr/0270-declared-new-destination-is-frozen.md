# ADR 0270 — Declared-new-destination is the second S3 challenger, and it is frozen

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Sentiel v1, S3, before the r4.2 look
- **Supersedes:** nothing
- **Depends on:** [ADR 0146](0146-identity-features-keep-the-thirty-four-symmetric.md),
  [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md),
  [ADR 0195](0195-a-return-to-a-host-nobody-else-has-used.md),
  [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md),
  [ADR 0261](0261-the-s2-register-is-the-directorys-email.md),
  [ADR 0262](0262-s2-is-met-on-directory-email.md)

## Context

S3's first challenger, `exclusive-host-return`, was scored once at 48 tickets a day
on CERT r4.2 and lost: 1 distinct labelled insider against frozen 6B's 59, beside
a chance expectation of 35.2855319099821. Its realism check was 0 of 930 innocent
users with a web host nobody else requested
(`eval_runs/build/v1/sentiel/s3-r42.json`). That shot is spent. It is not rerun.
The frozen r3.1 6B row stays precision 0.104 at 48 alerts, recall 0.5, in
`phos.sentiel.cert_curve.CERT_R31_BUDGET_CURVE`.

ADR 0262 made the destination features non-zero. With the directory register,
`declared_destination_count` sums to 1950179 on r3.1 (max 29) and
`declared_new_destination_count` sums to 455111 (max 13). Host and machine
features stay zero. Nothing had ranked a person-day by those counts.

r3.1 is the development release (ADR 0149). It has two labelled insiders, so it
describes the column. It is not the S3 bar. r4.2 was not opened for this record.

## Decision

**The score of a person-day is `declared_new_destination_count`.** The code is
`phos.sentiel.declared_destination.score_declared_new_destinations`. It calls
`IdentityFeaturiser` with `HistoryPolicy` at its defaults. The count is the
score. There is no scale, no threshold, and no second term. A day the history
cannot support is already 0. Another user's mail does not change this user's
count. The 34 features are not read and are not weighted. `AggregationPolicy()`
is not imported. The scorer name is `declared-new-destination`.

The register is ADR 0261's directory email, per release, unchanged. Hosts and
machines stay empty. The address list is not written into the repository.

**sha256** of `src/phos/sentiel/declared_destination.py`, raw file bytes, path
not mixed in: `ee061bc7d86c8e24df55469a5867a8358a617f1fc1b99013bd54de0a52d5a6a3`

Nothing in that file is retuned after r4.2 is seen.

**Why this count, after looking at r3.1.** Three readings of the same column
were counted on r3.1 only, with the directory register, before this hash. The
queue was every cached person-day on or after the first labelled attack,
210814 rows, ranked per calendar day by `(-score, user_id, timestamp)`, positive
scores only, 48 a day.

| Reading | What r3.1 did |
| --- | --- |
| Return to a directory address nobody else has mailed | 0 alerts. Every labelled day scored 0. 0 of 998 innocent users have such an address. |
| `declared_destination_count` | 0 distinct insiders surfaced. |
| `declared_new_destination_count` | CCH0959 surfaced, on 1 labelled day. CSF0929 not surfaced. 14793 alerts, 1 of them labelled. |

The labelled days' new-destination counts were 0 on 14 days, 1 on 14, 2 on 16,
3 on 6, and 4 on 3. On 205 of 317 queue days the 48th positive score was 4.
998 of 998 innocent users have at least one positive new-destination day, and
221840 person-days score above zero. New internal mail is ordinary, and the
budget is the right tail of that ordinary count.

Exclusivity is the host shot's failure mode, and on this column it is empty, so
it is not the challenger. The raw destination count is volume of colleagues,
which the 34 already approximate. The new-destination count is the identity
feature those 34 do not have. It was not rescaled to clear the cutoff of 4.
Finding one of the two development insiders is a description of r3.1, not a
pass, and not a reason to add a term.

## Consequences

The file above is the challenger. A later one-shot may rank it once, under the
budget ADR 0202 locked, against frozen 6B run the same way. This record does
not contain that shot.

## What this record does not decide

It does not rescore S2. It does not overwrite `eval_runs/build/v1/sentiel/s3-r42.json`.
It does not weight the 34. It does not surface a confidence. It does not start
Intelligence, the API, or the UI.
