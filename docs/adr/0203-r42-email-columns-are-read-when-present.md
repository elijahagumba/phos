# ADR 0203 — r4.2 email columns are read when present

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Sentiel v1, before the r4.2 trace cache
- **Depends on:** [ADR 0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md),
  [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md)

## Context

The registered r4.2 archive matches its sha256. Its activity headers were read so the
existing reader could be taught them. `logon.csv`, `device.csv`, `http.csv` and
`file.csv` match the columns the reader already knows. `email.csv` does not. r3.1's
header is `id, date, to, from, size, attachments, content`. r4.2's header adds `user`,
`pc`, `cc` and `bcc`. The reader refuses an unlisted column rather than dropping it.

## Decision

Those four columns are optional on `EMAIL_SPEC`. A header without them is still r3.1,
and the actor is still the directory user for the `from` address. A header with them
is read:

- A non-empty `user` cell is the actor, the same cell the other logs use. The
  from-address lookup is the fallback when the cell is absent or blank.
- `pc` is the machine, the same detail the other logs already carry.
- `cc` and `bcc` are recipients, split on `;` like `to`. They are not dropped.

`AggregationPolicy`, the 34 features, exclusive-host-return, the rank key and the
per-day budget are unchanged. This record does not score r4.2.

## Consequences

The fast reader and `CertReader` both apply this rule, and a hand fixture checks they
agree. A later column that is still unlisted is still a refusal.
