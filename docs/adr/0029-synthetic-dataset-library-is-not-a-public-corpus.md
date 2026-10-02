# ADR 0029 — A synthetic dataset library is not a public corpus

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Atlas + Sentiel)
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md)

## Context

The cycle contract asks for cross-plant detection, command ranking, and a usable SOC budget.
Public ICS and CERT corpora remain licence-gated or too thin to host hundreds of distinct
adversarial windows. D1–D2 already generate plants and graded attacks; packing those into a
root-level **dataset library** makes the combinatorial expansion inspectable (committed
catalogues) without committing payloads.

The failure mode this record exists to prevent: a library recall being read as HAI attack
recall, distillation perturbation recall, or CERT insider recall.

## Decisions

### Decision 1 — The library lives at `dataset library/`, payloads are regenerated

OT and IT catalogues are committed JSON. Generated CSV/JSONL sits in `generated/` and is
git-ignored, matching ADR 0006's "never commit data" rule. Regeneration is
`scripts/generate_dataset_library.py`.

Rejected: downloading Track A corpora whose licence is only `read once` (data4cyber, s7,
3W). The data gate is unchanged.

### Decision 2 — OT windows are D2 attacks; IT rows are Observations

OT packs are `AttackDatasetConfig` values consumed by the existing injector. Ground truth is
still measured (inject refuses inert attacks). IT personas emit starter counts plus a few
peer companions, with `EntityLabelledInterval` labels. No malware, no exploit, no live
directory.

### Decision 3 — Every number carries `SYNTHETIC_LIBRARY_CAVEATS`

`source_note` on library evaluation reports concatenates the four standing caveats. A
library row must not be summarised as a cycle-contract win on public data.

## Consequences

**Gained.** Hundreds of labelled OT windows and person-days that Atlas and Sentiel can be
run against without waiting on licence confirmation.

**Cost.** Results describe our imagination of a plant and an organisation. Fingerprint risk
(ADR 0016) still applies. Command ranking on these packs is still "attacks we designed."
