# ADR 0456 — Independent validation programme for the PHOS simulation engine

- **Status:** Accepted
- **Date:** 2026-11-17
- **PART:** Simulation engine release (D1 + D2 + D3)
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0455](0455-simulation-engine-is-a-releasable-open-source-component.md)
- **Amends:** nothing. `P1` remains blocked; this ADR records a programme decision, not a P1 advancement.

## Context

The PHOS simulation engine (`src/phos/synth/`, released under ADR 0455) generates clean, richly labelled,
attack-dense industrial data with perfect ground truth. It is a model of reality, not reality. Its realism
is a claim to be defended — `PlantDescription.model_source` is where each plant defends it — and not a
property to be assumed.

The engine carries standing caveats in every corpus it writes:
`MODEL_NOT_REALITY_CAVEAT`, `ATTACKS_ARE_OURS_CAVEAT`, `SYNTHETIC_TOPOLOGY_CAVEAT`,
`INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`. It is built on five enforced anti-bias mechanisms from ADR 0073:
the generator may not reference the detector, attacks are specified by intent never signature, every
scenario carries real-world provenance, a mandatory band of misses exists, and the method is published
including its failures.

These mechanisms reduce circularity; they do not eliminate it. The same person chose which processes to
model, which failure modes to consider interesting, and which real-world citations to draw on. A scenario
catalogue assembled by someone who had never seen Atlas would be different, and the difference is
unmeasurable from inside.

PHOS therefore will not invite researchers to *validate* the simulator. Validation implies endorsement.
PHOS invites researchers to *criticise* it — to publish where it is wrong, where its assumptions are
simplified, which attack scenarios it represents and which it fails to represent, whether its
randomisation genuinely produces meaningful diversity, and whether Atlas performs differently across
independently generated environments.

Criticism is the product. Validation is not.

## Decision

**1. Researchers are invited to criticise, not to validate**

PHOS publishes the simulation engine source, the four standing caveats, the anti-bias construction, and the
D3 evaluation harness. Researchers may generate corpora, run detectors against them, and publish their
findings independently. PHOS will not endorse, quote, or incorporate those findings as PHOS claims.

A researcher's publication may state:
- Where the simulator accurately represents industrial behaviour
- Where its assumptions are simplified
- Which attack scenarios it represents
- Which scenarios it fails to represent
- Whether its randomisation genuinely produces meaningful diversity
- Whether Atlas performs differently across independently generated environments

PHOS makes no claim about any of these. Each is a research question for the researcher to answer.

**2. Every published result carries the standing caveats**

Any number published about Atlas's performance on synthetic corpora must carry `SYNTHETIC-DERIVED` and the
four standing caveats: `MODEL_NOT_REALITY_CAVEAT`, `ATTACKS_ARE_OURS_CAVEAT`,
`SYNTHETIC_TOPOLOGY_CAVEAT`, `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`. A result read without those caveats
is misread.

**3. No frozen public rows are touched**

Synthetic results are never compared against, never replace, and never share a log with the frozen public
rows: HAI Mahalanobis 646.58, grouped 53.26, distillation 18.72, CERT 6B 0.104. A table that places a
synthetic number beside one of those is a defect, not a measurement.

**4. No rate claims from synthetic data**

No recall figure, FP/normal-hour, precision, or detection rate from synthetic corpora may be quoted as a
field detection rate, a public-ZIP pass/fail, or evidence about any real plant. In particular:
- not ≥70%, not 10×, not 2–3 alerts/day
- not a lead rate (command-lead stays 0/16 and 1/4, unpooled)
- not a replacement for any frozen row
- not a row in `eval_runs/log.jsonl`

**5. Hypothesis confidence is never printed**

Constitution §3.3: uncalibrated confidence must not be surfaced. Reports carry detection metrics
(recall, FP/normal-hour, precision, latency, ECE, Brier) only. Hypothesis confidence from Atlas's
reasoning layer is structural — it may be present in a narrative, but never printed as a number.

**6. P1 remains blocked**

This programme is independent of P1. The design-partner conversation for historian schema, clocks, and
declared subsystems stays blocked. Nothing in this programme advances P1, starts Intelligence/API/UI, or
claims 2–3/day, 10×, or ≥70%.

## Success is

- `docs/independent-validation-programme.md` exists and states the programme's terms, the six publication
  targets, and the standing caveats researchers must attach.
- `public/overlay/docs/independent-validation-programme.md` mirrors it for the public tree.
- The simulator source, caveats, anti-bias construction, and D3 harness remain available for researchers
  to use and criticise.
- No PHOS document states or implies endorsement of any external validation result.

## Success is not

- PHOS endorsing any researcher's validation of the simulator.
- A detection rate, recall figure, or FP rate for any real environment.
- A replacement for any frozen public row.
- A claim of ≥70%, 10×, or 2–3/day.
- Printed hypothesis confidence.
- Any advancement of P1.

## Alternatives considered

- **Invite researchers to validate the simulator.** Rejected. Validation implies endorsement. PHOS has not
  earned the right to endorse, and researchers have not earned the right to have their validation treated
  as PHOS measurement. Criticism is the honest frame.
- **Pool synthetic results with frozen public rows.** Rejected. ADR 0029 and ADR 0073 stand: the synthetic
  library is not a public corpus, and synthetic results must never share `eval_runs/log.jsonl`.
- **Let researchers publish detection rates as field claims.** Rejected. Constitution §3.3 and the
  execution master forbid surfacing uncalibrated confidence and claiming rates from synthetic data.

## Related decisions

- [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md) — Simulated plants
- [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md) — Anti-fingerprint discipline
- [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md) — Not a public corpus
- [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md) — Anti-bias construction
- [ADR 0455](0455-simulation-engine-is-a-releasable-open-source-component.md) — Release decision
