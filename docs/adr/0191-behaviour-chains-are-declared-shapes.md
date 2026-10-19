# ADR 0191 — Behaviour chains are declared shapes, not host names

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel capability 2
- **Depends on:** [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md)

## Context

The 34 count features are invariant to order. `phos.sentiel.sequence_scoring`
already scores n-gram surprise on the declared token alphabet. Target 1 also
asks for risky *chains*: a USB device, then a file, then a message that leaves
the organisation. Those are shapes in the same alphabet (`D`, `F`, `X`), not
named websites and not a labelled insider's destinations.

## Decision

`phos.sentiel.behaviour_chains` declares three ordered shapes, chosen before
any labelled score:

1. `D → F → X` — removable device, then a file, then external mail.
2. `D → F → H` — removable device, then a file, then the web.
3. `H → X → D` — the web, then external mail, then a removable device.

A shape is present when its tokens appear in that order in one day's collapsed
sequence, not necessarily consecutive. The training-prefix frequency of each
shape is counted with no label in sight. A scored day sums
`-log((count + 1) / (n_days + n_shapes))` for every shape it contains. A day
that contains none scores 0.

No host, recipient, or file name enters the score. `sequence_scoring` is not
edited. The stream name is `lane-a-dev:chains`.

## Consequences

A chain that is common in ordinary work scores near 0 even when present. A
chain that is rare in the attack-free prefix can speak. The shapes are
behavioural, not a copy of either labelled scenario's destinations. If both
insiders' days lack these shapes, the stream stays silent.
