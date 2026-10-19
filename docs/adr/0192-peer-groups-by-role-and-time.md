# ADR 0192 — Peer groups are role and time of day, not a new 6B peer feature

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel capability 3
- **Depends on:** [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md),
  [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md)

## Context

6B already compares a user to people who share the LDAP `role` attribute.
Peer-group *advantage* stays retired (ADR 0023). This capability asks a
narrower question the 34 features do not: is this user unusual against people
in the same role, *at the same hours*?

The entity-day trace has no event clock. It has the calendar day and
`off_hours_logons`, the same working-hours policy the count features already
use. Finer clocks would require re-reading `http.csv` (gigabytes). They are
not used.

## Decision

`phos.sentiel.role_hours` buckets a day as weekday/weekend crossed with
on-hours/off-hours (`off_hours_logons > 0`). Inside each `(role, bucket)` it
fits the attack-free prefix of four counts: removable connects, external
emails, file accesses, and distinct hosts.

A scored day is judged only against its own `(role, bucket)`. Each count's
magnitude is the positive excess over the peer median, divided by the peer
median absolute deviation (or 1 if that is 0). The day score is the sum of
those four magnitudes. A role with fewer than eight peer-days in that bucket,
or a user absent from the directory, scores 0.

`peers.py` is not edited. No `_peer` feature is added to the 34. The stream
name is `lane-a-dev:role-hours`.

## Consequences

This is a second look at the same role groups, sliced by time, not a revival
of the retired peer-advantage claim. It does not enter the frozen 6B row.
Unknown hours stay unknown: the trace cannot say *which* hour a web request
happened.
