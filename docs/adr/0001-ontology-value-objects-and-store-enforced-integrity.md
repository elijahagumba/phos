# ADR 0001 — Frozen value objects, reference by id, integrity enforced by the store

- **Status:** Accepted
- **Date:** 2026-07-28
- **PART:** 1 — Core Ontology & Evidence Store

## Context

Every PHOS engine, the reasoning subsystem, the API and the UI read and write one shared data
model (Constitution §3.1). Two invariants constrain its shape:

- **§3.2 Everything displayed is traceable.** Any confidence a user sees must be reconstructable
  from stored `Evidence`.
- **§3.7 Determinism and reproducibility.** Results must be re-creatable.

The model also has to serialise cleanly to JSON for the API, and it has to survive a hypothesis
changing its mind — evidence that first looked supporting can later read as contradictory.

## Decision

**1. Every ontology object is a frozen Pydantic value object.**
`model_config = ConfigDict(frozen=True)`. Updates return new instances (`with_evidence`,
`with_confidence`). Confidence histories and evidence links therefore cannot be silently
rewritten in place, and objects are safe to share across engines without defensive copying.

**2. Cross-references are by id, never by nesting.**
`Narrative` holds `hypothesis_ids`, `Hypothesis` holds `supporting` / `contradictory` evidence
ids, `Deviation` holds an `observation_id`. This keeps the object graph acyclic, keeps every
object independently serialisable, and leaves the store as the single source of truth. The one
deliberate exception is `Deviation.expected`, which embeds the `ExpectedRange` by value: a
deviation must stay explainable against the baseline it was actually judged against, even after
the model that produced that baseline is retrained.

**3. The store enforces referential integrity at write time.**
`add_deviation` rejects an unknown `observation_id`; `add_hypothesis` rejects unknown evidence
ids; `add_narrative` rejects unknown hypothesis and evidence ids. Reference-by-id only preserves
traceability if references actually resolve, so the check belongs at the write boundary rather
than at render time, where a broken reference would surface to an operator as a missing
explanation.

**4. The evidence role lives on the link, not on the evidence.**
`Evidence` does not know which hypothesis it bears on. The same evidence supports one explanation
and contradicts another, which is the entire point of maintaining competing hypotheses.

## Consequences

- Adding objects has an order: observation before deviation, evidence before hypothesis,
  hypothesis and evidence before narrative. Engines must construct bottom-up.
- Objects can be reordered, cached or sent over the wire freely; nothing holds a live reference.
- A revision means a new object, not a mutation. The store rejects a duplicate id rather than
  overwriting, so history cannot be lost by accident.

## Ambiguities resolved in this PART

The spec left several details open. Each was resolved toward the simplest reading consistent with
the Constitution, and each is covered by a test:

| Question | Decision | Why |
| --- | --- | --- |
| `with_confidence` — clamp or validate? | **Validate**; out-of-range raises `ValidationError`. | Silently clamping an out-of-range probability hides a caller bug, and §6 requires explicit error handling. |
| `with_evidence` when the id is already in the *other* list | **Move it**, so it appears once. | Upholds the stated invariant by construction and lets reasoning legitimately reassign a role. |
| `ExpectedRange.zscore` when `stddev == 0` | Return `0.0` at the mean, signed `inf` otherwise. | A perfectly constant feature is normal in OT; any departure genuinely is infinitely surprising. Returning a finite lie would corrupt downstream magnitudes. |
| `ForecastMiss` has no prefix of its own | Reuse the `fc_` family. | The spec fixes exactly seven prefixes; inventing an eighth would exceed the PART. |
| Referential integrity for `Narrative` | **Checked**, though the spec named only deviation and hypothesis. | `Narrative.timeline` cannot reconstruct a story from dangling ids — the same traceability rule that motivates the other two checks. |
| Timestamp handling | Timezone-aware, normalised to UTC on validation; naive datetimes rejected. | The spec says created_at is UTC. Normalising in one place (`UtcDatetime`) makes equality and JSON round-trips exact. |
| `Evidence.source_id` integrity | **Not** checked by the store. | `RELATIONSHIP_CHANGE` and `SEQUENCE_ANOMALY` derive from facts this PART does not model; a check would be enforceable for only one of four kinds. Revisit when those sources exist. |

## Alternatives considered

- **Mutable objects with an update log.** Rejected: reintroduces the "who changed this and when"
  problem the frozen model removes for free, and complicates sharing across engines.
- **Nested objects instead of ids.** Rejected: produces cycles (a narrative holds hypotheses which
  hold evidence which is also held by the narrative), duplicates state, and makes the store
  ambiguous as a source of truth.
- **Validating references lazily at read time.** Rejected: a dangling reference would then be
  discovered in front of an operator instead of at the point the bug was introduced.
