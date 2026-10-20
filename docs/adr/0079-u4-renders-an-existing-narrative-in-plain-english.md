# ADR 0079 — U4 renders an existing narrative in plain English, with unresolved and the Sentiel ceiling visible

- **Status:** Accepted
- **Date:** 2026-09-16
- **PART:** Usefulness Phase item U4
- **Supersedes:** nothing
- **Depends on:** [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0045](0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0076](0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md),
  Gate 2 decision (2026-09-12)

## Context

U1–U3 diagnosed the engines and built a synthetic environment. An operator still had no way to
read a `Narrative` without opening the ontology objects and the hypothesis confidences. U4 is the
smallest thing that turns an existing narrative into something a person can act on. It is **not**
Ω3: not FastAPI, not React, not `src/phos/api/` or `ui/`. Neither tree is built.
<!-- evidence-ack: src/phos/api/ — not built; U4 is explicitly not the forbidden surface, so neither tree exists -->

Gate 2 required that Sentiel output **explicitly document** the depth-blind ceiling (at the
48-alert point at least 14 of 34 features must speak at once; 31 of CCH0959's 42 malicious
entity-days were structurally unalertable). An interface honest about ambiguity that hid that
blind spot would be honest in form and dishonest in substance.

## Decision

1. **`phos.reasoning.analyst`** derives a `NarrativeBrief` from a `Narrative`, an `EvidenceStore`,
   and the `TemplateLibrary` those hypotheses came from. It renders crude markdown: summary,
   assessment, what would settle this, evidence, why, and (for Sentiel) the known ranking limit.
2. **Assessment is `resolved` or `unresolved`.** Unresolved covers a ceiling/epsilon tie, a
   prior-only rival set (ADR 0036 / 0059), or a residual lead. No confidence or prior figure is
   printed. The operator does not have to read a probability to act.
3. **The next settling fact is derived from template asymmetries**
   (`phos.reasoning.analyst_settling`), not invented. A pattern that supports one rival and
   contradicts the other is named in plain English (e.g. a covering work order, a write from a
   device that has never commanded this target). When the templates declare no contradiction
   (Sentiel), the renderer says so and names a declared sanction record as the class of fact that
   would create one — and that no corpus PHOS reads carries.
4. **Sentiel renders call `depth_blind_ceiling_notice()`** from `phos.sentiel.failure`. The 14 and
   34 are computed (`features_required`, `len(PEER_FEATURES)`); the 31 and 42 are frozen
   measurements pinned against the ADR 0076 JSON. Atlas renders carry no Sentiel ceiling.
5. **`Narrative` gains no new fields.** Assessment and next-evidence are render-time views. The
   ontology remains the single typed model; the renderer does not bypass it.

## Consequences

- U5 can feed subjects the markdown this module produces as the "Atlas explanation" arm.
- Surfacing uncalibrated hypothesis confidence remains forbidden.
- Intelligence / API / UI remain blocked (Ω3 / P1).
- A future session that wants a richer "next evidence" vocabulary must extend the templates'
  declared patterns, not the renderer's prose.

## Ontology sufficiency (honest)

The existing narrative ontology is **sufficient to render what happened and the competing
explanations**. It is **not sufficient, by itself, to name the next settling fact**: that requires
the template library's support/contradict asymmetries, which are reasoning artefacts, not narrative
fields. Sentiel's templates still declare **no contradictory patterns**, so the settling ask for
enterprise narratives is necessarily the sanction-record statement above rather than a behaviour
fact — that limit is the templates', and U4 surfaces it instead of papering it.
