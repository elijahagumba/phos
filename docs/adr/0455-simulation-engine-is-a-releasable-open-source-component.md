# ADR 0455 — The simulation engine is a releasable open-source component

- **Status:** Accepted
- **Date:** 2026-11-17
- **PART:** Simulation engine release (D1 + D2 + D3)
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md),
  [ADR 0454](0454-d3-synthetic-evaluation-harness-for-atlas.md)
- **Amends:** nothing. `P1` remains blocked; this ADR records a release decision, not a P1 advancement.

## Context

D1 builds three simulated industrial plants (water treatment, power generation, batch reactor) with true-state
records, Modbus captures, and declared topologies. D2 builds a graded attack library (28 attacks per plant at four
difficulty levels, from obvious to near-invisible, plus input-hostile cases). D3 — built in ADR 0454 — runs Atlas
against the result and maps where it goes blind.

Together these form the **PHOS simulation engine**: `src/phos/synth/`, a component that generates clean, richly
labelled, attack-dense industrial data with perfect ground truth. Real-world labelled OT data barely exists in
public, and the public corpora PHOS inspected are all refused as detection rulers (ADR 0040, ADR 0046, ADR 0047).
The simulation engine is PHOS's answer to that gap.

The engine already carries the standing caveats in every corpus it writes:
`MODEL_NOT_REALITY_CAVEAT`, `ATTACKS_ARE_OURS_CAVEAT`, `SYNTHETIC_TOPOLOGY_CAVEAT`,
`INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`. It is built on the five enforced anti-bias mechanisms from ADR 0073:
the generator may not reference the detector, attacks are specified by intent never signature, every scenario
carries real-world provenance, a mandatory band of misses exists, and the method is published including its
failures.

## Decision

**1. The simulation engine is released as open-source software.**

`src/phos/synth/` — the plants, the injection hook, the true-state record, the graded attack library, and the
D3 evaluation harness — is released under the PolyForm Noncommercial License 1.0.0, the same licence as the rest
of PHOS (`public/overlay/LICENSE`). Noncommercial use, research, education, and personal experimentation are
permitted purposes; commercial use requires a separate licence.

This is **source-available**, not OSI "open source" in the strict sense: the PolyForm Noncommercial licence
restricts commercial use. That is deliberate and matches the rest of PHOS (ADR 0299: "The licence stays"). A
licence change would reverse the release decision (ADR 0299, "What would reverse this").

**2. The engine is documented with its caveats up front.**

Every file the engine writes carries the four standing caveats. A standalone README for the simulation engine
(`docs/simulation-engine.md`) states what it is, what it is not, the anti-bias construction, and the limitations
that any downstream user must read before drawing conclusions. The README is exported to the public tree
(`public/overlay/docs/simulation-engine.md`) alongside the release note.

**3. The engine produces data, not detection claims.**

ADR 0029 stands: the synthetic library is not a public corpus. ADR 0073 stands: the synthetic harness measures
nothing that may be believed as a real-world detection rate. Releasing the engine does not change any of that.
Downstream users may generate corpora and run detectors against them, but every number they publish must carry
the standing caveats and may not be quoted as a field detection rate, a replacement for any frozen public row,
or evidence about any real plant.

**4. The engine stays inside the `phos` package.**

`phos.synth` remains a subpackage of `phos`, importing from `phos.eval`, `phos.ontology`, and `phos.atlas.topology`
as it does today. It is not extracted to a separate repository. The release is the component, documented so it
can be understood and used independently of Atlas and Sentiel, but it ships as part of the `phos` package.

## Success is

- `docs/simulation-engine.md` exists and states what the engine is, what it is not, the four caveats, the
  anti-bias mechanisms, and the limitations.
- `public/overlay/docs/simulation-engine.md` mirrors it for the public tree.
- `mypy --strict` and `ruff` are clean on `src/phos/synth/` and `scripts/evaluate_atlas_synthetic.py`.
- All synth tests pass (`tests/synth/`).
- No claim in the README or public docs states or implies a real-world detection rate.

## Success is not

- A claim that the simulation engine produces real plant data.
- A detection rate, recall figure, or FP rate for any real environment.
- A replacement for any frozen public row (HAI 646.58, grouped 53.26, distillation 18.72, CERT 6B 0.104).
- A claim of ≥70%, 10×, or 2–3/day.
- An OSI-approved open-source licence (PolyForm Noncommercial restricts commercial use).

## Alternatives considered

- **Extract `phos.synth` to a standalone package.** Rejected. The engine imports from `phos.eval`,
  `phos.ontology`, and `phos.atlas.topology`; extracting it would either duplicate code or create a fragile
  cross-repo dependency. Keeping it as a documented component of `phos` is simpler and keeps the caveats
  attached to the same code that produces the data.
- **Release under an OSI-approved licence (MIT, Apache-2.0).** Rejected. ADR 0299 states the licence stays
  PolyForm Noncommercial, and a licence change is listed as something that would reverse the release decision.
  Commercial use needs a separate licence regardless.
- **Release the generated corpora as open data.** Rejected. ADR 0029: the synthetic library is not a public
  corpus. The engine is released; the corpora it generates are produced on demand by the user.
