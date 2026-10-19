# ADR 0146 — Identity features name declared hosts, destinations and machines

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane A, Sentiel S2
- **Depends on:** [ADR 0021](0021-sentiel-feature-enrichment-a-causal-trailing-history-and-the-budget-that-bounded-it.md),
  [ADR 0084](0084-non-saturating-aggregation-for-sentiel.md),
  [ADR 0093](0093-bet-001-three-candidates-declared.md),
  [ADR 0145](0145-bet-001-not-run.md)

## Context

The 34 features count how many machines, recipients and web hosts a person touched.
Register R16 records that they never say which. S2 asks for identity-aware features —
which counterparties, which hosts, which destinations — while those 34 stay symmetric.

Bet 001's three formulas are pre-registered on the 34 and were not run (ADR 0145).
Putting a weight on one of them, or folding a new feature into that set, would edit the
declaration. R16 also names the counterparties of one labelled insider. Copying those
names into a detector would be the answer key.

## Decision

**1. A separate stream, in `phos.sentiel.named_counterparties`.** The name is
deliberate: `phos.sentiel.identity` already scores the Clock B layers and leaves
the peer slot empty, and that file is unchanged. Six features, emitted only by
`IdentityFeaturiser`:

| Feature | What the count is |
| --- | --- |
| `declared_host_count` | Distinct declared web hosts touched |
| `declared_new_host_count` | How many of those were new for this user |
| `declared_destination_count` | Distinct declared email destinations |
| `declared_new_destination_count` | How many of those were new for this user |
| `declared_pc_count` | Distinct declared machines |
| `declared_new_pc_count` | How many of those were new for this user |

The matched names are on the observation, sorted, under `matched_identities`. The count
is the size of that list. `register_sha256` records which register produced it.

**2. The register is an input and it ships empty.** `DeclaredIdentities` holds hosts,
destinations and machine names. Matching is exact after case-folding. A destination may
be an address or a domain; a domain matches addresses at that domain and the observation
lists the address. A host does not match a suffix. Nothing in this module fills the
register from a labelled day.

**3. "New" uses `HistoryPolicy` unchanged.** The new-name features stay silent, value 0
and `new_status=insufficient_history`, until the user has `min_history_windows` prior
active windows. The default is eight, the same bar the 34 already use. The current
window is not part of the memory it is judged against. A name is forgotten when it ages
out of `trailing_windows`. One user's memory is not another's.

**4. The 34 stay as they are.** `PEER_FEATURES` is not extended. `AggregationPolicy()`
keeps empty weights, so each of the 34 has weight 1. The three Bet 001 candidates are
not edited. `family_of` does not know the six new names, so they are not smuggled into
a behaviour family. `Featuriser` is not modified. Tests check that renaming every host,
machine and recipient leaves the 34-vector unchanged, and that computing the identity
stream does not move that vector.

**5. This session does not score the stream.** CERT r3.1 is not on disk (ADR 0145). A
score against the two labelled insiders would also need a register declared before the
labels were consulted. No such register is declared here.

File names are not a seventh kind. S-W2 names files; this lane's sentence names
counterparties, hosts and destinations. Machines are the counterparties. Files stay an
open question for a later declaration, not a quiet addition.

## Consequences

S2's implementation and the symmetry tests exist. S2's pass bar also requires a score
on CERT r3.1 and on a larger release. That score does not exist. The 6B row is
untouched.

A later session that scores this stream declares the register in a commit that precedes
the labelled run, and scores the six features apart from the frozen 34. It does not
put a weight on `new_counterparties` or on any other of the 34.

## What would reopen the file question

A declaration, before any labelled score, that file names are a fourth kind with the
same empty-register rule.
