# ADR 0070 — The evidence facet replaces summary-string parsing

- **Status:** Accepted
- **Date:** 2026-08-31
- **PART:** Refactor (ontology / Atlas matchers)
- **Supersedes:** nothing. The stamps stay; what changed is which channel a matcher reads.
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0027](0027-unknown-master-writes-are-not-maintenance.md),
  [ADR 0059](0059-explanation-geometry-and-work-order-inlet.md),
  [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md)

## Context

`Evidence` records a `kind` — how a fact was produced — and never *which* fact. That was
deliberate: [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)
recorded it as a limit, with a test named
`test_a_command_behaviour_departure_bears_on_no_ot_explanation` pinning what the missing field
cost, and observed that "no pattern in 4B's language can ask whether it was a write share, a
polling rhythm or a register span."

Three later sessions needed exactly that question answered anyway, and each worked around the
missing field the same way — by writing a declared prefix into the human-readable `summary` and
parsing it back out:

| Marker | Written at | Parsed by | Introduced |
|---|---|---|---|
| `graph-finding:` | `_describe_change` | `graph_finding_feature_of` | P3 |
| `command-behaviour:` | `_describe_departure` | `command_behaviour_feature_of` | D1 |
| `work-order:` | `promote_work_orders` | `work_order_feature_of` | E3 |

Four `EvidencePattern` subclasses in `src/phos/atlas/templates.py` depend on that parsing —
`GraphFindingPattern`, `UntypedStructurePattern`, `WorkOrderPattern` and `CommandStructurePattern`.
Between them they decide whether an unknown master **contradicts** `engineering_maintenance`
(ADR 0027) and whether a work order **contradicts** `unauthorised_control_activity` (ADR 0059).

So a reasoning outcome — the one asymmetry Atlas has for separating an engineer from an attacker —
depended on the exact wording of a sentence written for an operator to read. Rewording
`_describe_change` for clarity would silently unmatch the templates. Nothing in the type system,
and no test outside the marker tests themselves, would have caught it.

This is also a Constitution §3.1 problem rather than a tidiness one. The ontology is meant to be
the one typed model every engine reads and writes; encoding a machine-readable field inside a
display string is an engine keeping a private format in a place the ontology cannot see.

## Decision

1. **`FacetKind`** joins `phos.ontology.enums` as a closed vocabulary: `GRAPH_FINDING`,
   `COMMAND_BEHAVIOUR`, `WORK_ORDER`. It names the sub-kind *within* an `EvidenceKind`, which is
   the dimension the four matchers actually switch on.

2. **`Evidence` gains `facet_kind: FacetKind | None` and `facet: str | None`.** The pair is the
   typed statement of what the marker said in prose. `None` means "declares no sub-kind" and never
   "unknown" — most evidence has no facet and that is a fact about it, not a gap.

3. **Half a facet is refused at construction.** A kind with no feature names nothing; a feature
   with no kind cannot be checked against a closed vocabulary. Either half alone is a fact that
   says less than it appears to, so `_check_facet_pairing` raises.

4. **The two boundary doors take an optional `facet`.** `evidence_from_deviation` and
   `evidence_from_relationship_change` each accept `facet: tuple[FacetKind, str] | None = None`.
   Omitted, they build exactly the `Evidence` they built before. The boundary stays the only
   sanctioned route into reasoning.

5. **The three promoters set it.** `promote_graph_findings`, `promote_command_behaviour` and
   `promote_work_orders` pass their feature through as a facet.

6. **The summary markers are still written, byte-identical.** Nothing an operator reads changes,
   and no test that asserts on summary text moves. The prose keeps saying what the facet says.

7. **Resolution is typed-first with the parse as a documented fallback.** The three
   `*_feature_of` functions read `facet_kind`/`facet` when a facet is present and fall back to the
   private `_*_from_summary` parsers only when it is absent. Call sites are unchanged, so the
   migration is one edit per resolver rather than four edits per marker across the matchers.

8. **The facet is authoritative.** Where the two channels disagree — which no promoter produces —
   the facet decides and the summary is ignored. That is the property the refactor buys, and it is
   the only thing a test can observe about which channel was read.

9. **An empty feature declares nothing rather than raising.** `Observation.feature` has no length
   constraint, so an unnamed feature was always constructible and always promoted — producing a
   marker like `work-order::` that the parser read back as `None`. `Evidence.facet` carries
   `min_length=1`, so passing such a feature straight through would have been a **new refusal on
   an input that previously worked**. `_facet_fields` in the boundary normalises it to no facet at
   all, reproducing the historical semantics exactly. The field constraint stays, because a facet
   naming nothing is not a weaker claim but an unreadable one.

10. **The 6B ontology freeze is narrowed, not lifted.** `TestReuseNotFork` in
   `tests/sentiel/test_engine.py` asserts `src/phos/ontology` is unmodified since the PART 6B
   commit — the guard that stops Sentiel forking the shared spine. It failed on this change, and
   it was **the only pre-existing test that did**. Following the convention its own docstring
   sets — `store.py` was opened by ADR 0038 and `narratives.py` by ADR 0045, each named with its
   record — `evidence.py`, `enums.py` and `__init__.py` join `_ONTOLOGY_OPENED_AFTER_6B` with
   this ADR against them. The freeze still holds for every other file in the package.

   This is admissible because the change is **additive and Sentiel-neutral**: two optional fields
   defaulting to `None`, one enum, one export. Sentiel sets no facet and reads none. The sibling
   assertions in the same test class — Atlas's five template priors to twelve decimal places, and
   the shared belief arithmetic — pass untouched, which is the evidence that opening these files
   moved nothing downstream.

## What this does not change

- **No reasoning outcome, score, or logged row moves.** Every fact the promoters build resolves to
  the same feature through both channels, and every `(template, role)` verdict is identical. That
  is asserted, not argued: `tests/atlas/test_evidence_facet.py` runs each promoted fact through the
  library twice, once as promoted and once with the facet stripped to force the old path, and
  compares.
- **`command-behaviour:` still matches no OT template.** ADR 0014's limit stands. D1 stamped the
  fact; this record types the stamp. Wiring a `CommandBehaviourPattern` is a separate decision with
  its own evidence, and it is not taken here.
- **The known-station wall stands.** Nothing about maintenance vs unauthorised control on a known
  link is weakened or strengthened. Command lead stays 0/16 and 1/4, unpooled.
- **`SUBSYSTEM_EVENT_MARKER` is untouched.** It marks `source_id`, not `summary`, and carries
  member ids rather than a facet. Different field, different purpose, out of scope.

## Consequences

**Better.** A reasoning outcome no longer depends on prose. `mypy --strict` now checks the
dimension the matchers switch on, and a reworded operator sentence cannot unmatch a template. The
next facet — a `CommandBehaviourPattern`, a Sentiel sanction fact — extends an enum instead of
inventing a fourth prefix convention.

**Worse.** Two representations of one fact now exist, and they can drift. The equivalence tests are
what keep them honest, and a promoter that sets one and not the other is a defect those tests are
placed to catch.

**Deferred.** Deleting the markers and the fallback parsers. Doing it now would silently unmatch
every hand-built fixture that stamps a summary and sets no facet, which is a behaviour change on
test fixtures and outside a refactor's licence. It becomes cheap once fixtures carry facets.
