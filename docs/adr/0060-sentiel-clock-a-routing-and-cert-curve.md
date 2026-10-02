# ADR 0060 — Sentiel Clock A: routing rule, declared interaction, CERT curve, HR fixture

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Sessions S1–S5
- **Supersedes:** nothing
- **Depends on:** [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0032](0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0045](0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md)

## Context

Peer-group advantage is retired (0 labelled peer-relative positives). CERT 6B at
48 alerts is the public ruler. 30–50 tickets/day is an estate conversation.

## Decision

1. **S1.** `peer_features_allowed` / `cert_r31_role_is_not_a_peer_group`: a
   180-person r3.1 role is not a peer group. Default `PeerPolicy` is unchanged
   (`peers.py` stays the 6B spine). The advantage claim stays retired.
2. **S2.** `DeclaredCounterpartyDirectory`: expected counterparties are declared
   per role. Missing directory is insufficient, not a graph embedding. No
   clustering from who emails whom.
3. **S3.** A thin self-history departure leads with `insufficient_evidence`.
   Losers remain visible. No fake CERT contradictions. Hypothesis confidence
   stays unsurfaced.
4. **S4.** `CERT_R31_BUDGET_CURVE`: 48-alert 6B is 0.104 / 0.5 and is the
   headline. `:precision` at 48 is 0.083, a loss, not headlined. 30–50 is not
   earned on CERT.
5. **S5.** `promote_hr_tickets`: empty is a no-op. CERT has no such field.
   Fixture only.

## Consequences

- Completing S1–S5 does not revive peer advantage or earn a SOC budget on CERT.
