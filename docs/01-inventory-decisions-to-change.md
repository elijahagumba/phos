# Inventory: decisions affected by the proprietary-simulation / public-methodology position

This document lists every existing decision, document, or artefact that must change, be superseded, or be
reviewed as a consequence of ADR 0457. It is an inventory, not a decision itself. No changes are made here.

## ADRs to supersede

| ADR | Title | Disposition |
|---|---|---|
| 0455 | The simulation engine is a releasable open-source component | Superseded by ADR 0457. Engine stays proprietary; PolyForm release reversed. |
| 0456 | Independent validation programme for the simulation engine | Superseded by ADR 0457. Absorbed into Independent Validation Framework. |

## Documents to rewrite

| Document | Location | Change |
|---|---|---|
| Simulation engine documentation | `docs/simulation-engine.md` | Rewrite from "releasable component" to "public specification, proprietary implementation". |
| Independent validation programme | `docs/independent-validation-programme.md` | Rewrite as researcher challenge programme: criticise, don't validate; example corpora, not code access. |
| Public overlay copies | `public/overlay/docs/simulation-engine.md`, `public/overlay/docs/independent-validation-programme.md` | Mirror the rewritten documents. |
| README | `README.md` | Rewrite with lab tone: what Atlas is, what Sentiel is, why Atlas is current work, transparent vernacular. |
| Public release note | `public/overlay/docs/release.md` | Update to reflect proprietary engine / public methodology position. |
| Licence file | `public/overlay/LICENSE` | Professional legal review required (PolyForm vs. hybrid model). |

## Artefacts to publish (example corpora)

| Corpus | Location | Purpose |
|---|---|---|
| `synth-water-treatment-holdout` | `data/synth/synth-water-treatment-holdout/` | Quiet plant; false-positive baseline |
| `synth-attack-water-treatment-graded` | `data/synth/attacks/synth-attack-water-treatment-graded/` | Labelled attacks, four difficulty levels |
| `synth-attack-water-unknown-master` | `data/synth/attacks/synth-attack-water-unknown-master/` | Command/re-routing, unknown master |
| `synth-hostile-malformed-records` | `data/synth/attacks/synth-hostile-malformed-records/` | Software robustness |
| `synth-power-generation-train` | `data/synth/synth-power-generation-train/` | Second plant family, quiet |
| `synth-batch-reactor-holdout` | `data/synth/synth-batch-reactor-holdout/` | Batch process, quiet |

Each published corpus ships with: `telemetry.csv`, `topology.toml`, `manifest.json`, `capture.pcap` (where
applicable), and SHA-256 digests. Publication is selective, not exhaustive.

## Decisions that do NOT change

| Decision | Reason |
|---|---|
| Anti-fingerprinting (ADR 0016) | Remains in force; now lives in public specification. |
| Synthetic library is not a public corpus (ADR 0029) | Unchanged. |
| Synthetic harness measures nothing (ADR 0073) | Unchanged. |
| Frozen public rows (HAI 646.58, grouped 53.26, distillation 18.72, CERT 6B 0.104) | Unchanged; never overwritten. |
| P1 blocked | Unchanged; no Intelligence/API/UI work. |
| No ≥70%, 10×, or 2–3/day claims | Unchanged. |
| D3 harness (ADR 0454) | Unchanged; remains `SYNTHETIC-DERIVED` only. |

## Open questions requiring legal review

1. Whether PolyForm Noncommercial remains appropriate for a hybrid model where methodology is public but
   implementation is proprietary.
2. Whether example corpora published under PolyForm create any redistribution obligations for downstream
   researchers who build detectors on them.
3. Whether the Independent Research Programme confidentiality agreements are compatible with publishing audit
   findings.
