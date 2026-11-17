# ADR 0458 — The simulation engine was never closed, and the licence is what protects it

- **Status:** Accepted
- **Date:** 2026-11-17
- **PART:** Simulation engine release strategy
- **Supersedes:** nothing
- **Amends:** [ADR 0457](0457-proprietary-simulation-public-methodology-independent-validation.md), Decision 1 only.
  Decisions 2, 3, 4 and 5 of that record stand unchanged and are not restated here.
- **Depends on:** [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0342](0342-commercial-records-are-not-published.md),
  [ADR 0455](0455-simulation-engine-is-a-releasable-open-source-component.md),
  [ADR 0456](0456-independent-validation-programme-for-the-simulation-engine.md),
  [ADR 0457](0457-proprietary-simulation-public-methodology-independent-validation.md)
- **Amends nothing else.** `P1` remains blocked. No corpus is opened, nothing is scored, no frozen number
  moves, and v1 stays 8 of 12.

## Context

ADR 0455 proposed releasing `src/phos/synth/` under PolyForm Noncommercial. ADR 0456 built an independent
validation programme on top of it. ADR 0457, written the same day, reversed both and recorded a stricter
position in its Decision 1: *"It is not released under MIT or any open-source licence … the code is not
public at all."*

**That sentence was not true when it was written, and the public front page repeated it.** The export
manifest `public/manifest.toml` has included `src/*` wholesale since the public repository was created.
At the time ADR 0457 was committed, fifty-two files of `src/phos/synth/` were published in
`github.com/elijahagumba/phos` and had been for some time. The front page carried the sentence *"The
simulator is proprietary. Its source code is not released"* directly above a tree a reader could click
into and find the generator.

A record that misdescribes the disk is worse than no record, because the next session reasons from it. The
record is not edited — ADR 0457 keeps its wording, as ADR 0334 and ADR 0369 keep theirs — and this ADR
states what is actually in force.

## Decisions

### Decision 1 — The engine is source-available under the licence it already had

`src/phos/synth/` stays inside this repository and stays published, under the same terms as every other
part of PHOS: the **PolyForm Noncommercial License 1.0.0**. Research, education and personal
experimentation are permitted. Commercial use requires a separate licence.

This replaces ADR 0457's Decision 1. It is neither of the two positions that record considered: not an
MIT release, and not withdrawal from the public tree.

**Why the licence is the right instrument and withdrawal is not.** The thing to be protected is a
competitor shipping a product built on this engine, and PolyForm Noncommercial already forbids exactly
that. Withdrawal would buy nothing further — the engine's value to a competitor is the methodology, and
ADR 0457's own Decision 2 publishes the methodology deliberately — while costing the two things ADR 0457
names as requirements in its own context section: a researcher cannot critique a generator they cannot
read, and an operator deciding whether to hand over plant data is not reassured by a black box.

**What this does not do.** It does not reopen ADR 0455. That record proposed extracting the engine to a
separate repository under a different licence, and ADR 0457's extraction argument against it holds and is
not disturbed: `src/phos/synth/` imports from `phos.eval`, `phos.ontology` and `phos.atlas.topology`, and
splitting it would either duplicate the ontology (Constitution §3.1) or create a cross-licence runtime
dependency. The engine stays one tree with the rest, as it already is.

### Decision 2 — The public front page states the licence, not a closure

The sentence *"The simulator is proprietary. Its source code is not released"* is removed from
`public/overlay/README.md` and from the published `README.md`. What replaces it says what is true: the
licence does the commercial work, the record does the scientific work, the methodology is published in
full including where the simulator is known to be inaccurate, and example corpora ship with SHA-256
digests so a researcher can disagree with our numbers using their own detector on the same files.

## Consequences

- No file in `src/phos/synth/` is moved, removed or relicensed. Nothing is withdrawn from the public
  repository, and no published commit is rewritten.
- `public/manifest.toml` is unchanged. `src/*` continues to export.
- ADR 0457's Decisions 2 through 5 — public methodology, published example corpora, the Independent
  Research Programme, real-world validation as the objective — are unaffected and remain the position.
  The programme in Decision 4 gives a reviewer controlled access under confidentiality; with the engine
  source-available that access is to the project's attention rather than to otherwise-secret code, and
  ADR 0457's own qualification that a confidential audit is not public verification stands.
- A future record may still close the engine. It would have to say so against this one, and remove the
  files from the export in the same change rather than describing a closure that has not happened.

## What this record does not do

It does not open a corpus, run a harness, or produce a number. It does not fill reserved ADR numbers
0277–0284. It does not lift a data tier. It does not move v1 off 8 of 12. It does not start Intelligence,
the API or the UI. **P1 stays the blocked human conversation.**
