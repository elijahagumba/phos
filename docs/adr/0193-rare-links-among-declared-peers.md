# ADR 0193 — Rare user–machine–site links are scored, not drawn on the org graph

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel capability 4
- **Depends on:** [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md),
  [ADR 0146](0146-identity-features-keep-the-thirty-four-symmetric.md)

## Context

`phos.sentiel.graph` is the directory's declared org chart. It refuses any
edge inferred from activity. CERT r3.1 declares no user-to-device and no
user-to-host ownership. Target 1 still needs a way to flag a *new*
user–machine–site link that is rare among that user's peers, without turning
those links into graph edges and without copying a labelled insider's hosts
into a register (ADR 0146).

## Decision

`phos.sentiel.peer_links` does not add edges to `DeclaredGraph`. It scores
observed identity facts against the attack-free prefix:

- A host, recipient, or machine is *new* for a user when it is absent from
  that user's own training-prefix sets.
- Among users who share the LDAP role, it is *rare* when few of those peers
  touched it in the same prefix.
- Each new name contributes `-log((peer_count + 1) / (n_peers + 1))`.
- Names the user already had, and names that many peers already had, stay
  quiet. A user with no role peers scores 0.

No register of destinations is filled. File names are not a fourth kind
(ADR 0146). `named_counterparties` stays empty. The stream name is
`lane-a-dev:peer-links`.

## Consequences

A new site that half the role already visits is ordinary. A new site that
almost nobody in the role has visited can speak. The measurement is
symmetric and label-free. If CERT planted the same rare hosts as decoys
inside the same role, the stream will not separate the insider, and that
refusal is the honest result.
