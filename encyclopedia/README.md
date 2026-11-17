# PHOS encyclopedia

**What this is.** A complete reference to the PHOS repository as it exists on disk: every package, every measurement that is allowed to be quoted, every architecture decision, every gap the files refuse to paper over.

**Why it exists.** A senior engineer who has never seen this tree should be able to reconstruct what PHOS is, what it has measured, what it forbids, and which file is the source of truth, without reading 3,600 lines of `PROGRESS.md` first.

**How to use it.** Read [00-how-to-read](00-how-to-read.md) once. After that, jump by volume. Volumes are reference-plus-explanation, not tutorials. Running the code is still [../README.md](../README.md).

**Keeping it current (ADR 0044).** This encyclopedia is required to expand when `main` advances. So are `easy to reads/` and `README.md`. An agent that lands a PART, measurement, or refusal on `main` without touching all three has not finished.

**What does not belong here.** Live-plant claims, pooled command-lead rates, uncalibrated hypothesis confidence treated as a probability, or any number that is not already in `eval_runs/`, an ADR, `PROGRESS.md`, or `.phos_roadmap_state.json`.

If a figure here disagrees with those files, **those files win**. This encyclopedia is a map, not a second experiment log.

---

## Volumes

| # | Volume | What it covers |
|---|---|---|
| [00](00-how-to-read.md) | How to read this encyclopedia | Authority order, frozen numbers, forbidden sentences, related docs |
| [01](01-mission-and-speech-contract.md) | Mission and speech contract | Thesis, engines, what operators would buy, monopoly claim |
| [02](02-constitution-programme-lock.md) | Constitution and programme lock | Invariants, stack, PART protocol, five sessions, forbidden list |
| [03](03-repository-layout-stack-ci.md) | Layout, stack, and CI | Canonical tree, pinned deps, pytest/mypy/ruff, GitHub Actions |
| [04](04-history-parts-sessions.md) | History, PARTs, and sessions | 28 Jul–22 Aug 2026, numbered PARTs, command-lead sessions 1–5 |
| [05](05-ontology.md) | Ontology | Entity through Narrative, ids, store integrity |
| [06](06-eval-and-models.md) | Eval harness and baselines | Metrics, adapters, Gaussian/EWMA/IQR/empirical, experiment log |
| [07](07-reasoning.md) | Reasoning | Evidence boundary, calibration, templates, belief, engine |
| [08](08-atlas.md) | Atlas | Joint plant, topology, grouping, packets, commands, templates |
| [09](09-sentiel.md) | Sentiel | CERT intake, features, peers, scoring, competing set |
| [10](10-synth-breaking-library.md) | Synth, breaking harness, library | Three plants, graded attacks, issuer split, crash-test library |
| [11](11-data-licences-measurements.md) | Data, licences, frozen measurements | Registry, HAI/BATADAL/distillation/Data4Cyber Track A/CERT, refused command corpora |
| [12](12-adr-catalogue.md) | ADR catalogue | ADRs 0001–0041, 0044–0081, one paragraph each |
| [13](13-scripts-tests-experimental.md) | Scripts, tests, experimental sandbox | CLI entry points, test map, mutation, `experimental/` |
| [14](14-glossary-file-index-absences.md) | Glossary, file index, what is absent | Vocabulary, every important path, Intelligence/API/UI |

## Companion documents (not replaced)

| Document | Role vs this encyclopedia |
|---|---|
| [../README.md](../README.md) | Public front door and how to run |
| [../easy to reads/](../easy%20to%20reads/README.md) | Plain-English narrative walkthrough (read in order) |
| [../docs/adr/](../docs/adr/README.md) | Why a decision was made |
| [../PROGRESS.md](../PROGRESS.md) | Chronological build log |
| [../docs/atlas-report.md](../docs/atlas-report.md) | Atlas through PARTs 5A–5C (point-in-time; packet work overtook two sentences) |
| [../docs/PHOS-encyclopedia.md](../docs/PHOS-encyclopedia.md) | Short Wikipedia-style article (snapshot; this folder is the living reference) |
| [../docs/category-defining-roadmap.md](../docs/category-defining-roadmap.md) | Category-form programme (Clock A C0–Ω2 complete; live session P1 blocked) |
| [../.phos_roadmap_state.json](../.phos_roadmap_state.json) | Live measurement freeze and command-lead tracker |

## One sentence

PHOS learns what *normal* looks like, flags statistically meaningful departures, holds competing explanations, and **refuses to speak** when the evidence or the data cannot support a claim. Nothing in this repository is a live plant or a live SOC.
