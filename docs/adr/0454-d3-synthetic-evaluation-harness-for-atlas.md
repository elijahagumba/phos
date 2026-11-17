# ADR 0454 — D3: synthetic evaluation harness for Atlas, SYNTHETIC-DERIVED only

- **Status:** Accepted
- **Date:** 2026-11-17
- **PART:** D3 — Synthetic evaluation harness for Atlas (diagnostic, outside P1)
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md)
- **Amends:** nothing. `P1` remains blocked on the human partner conversation; this ADR records why
  D3 work proceeds outside it.

## Context

D1 builds the plants, D2 builds the graded attack library. Neither evaluates anything. D3 is the
missing third PART: it runs Atlas against the synthetic corpora D1+D2 produce and scores detection
performance — recall, false-positive rate, precision, latency — against perfectly known ground
truth.

D2 generates corpora in the prepared-corpus shape `phos.eval.LabelledCsvAdapter` already reads
(telemetry.csv with a label column, topology.toml in the format `phos.atlas.topology.load_topology`
reads, capture.pcap that `phos.atlas.packet.dissect_capture` already parses). Nothing in Atlas was
changed to accept this data; D3 only composes existing doors.

The harness exists because real-world labelled data is scarce: HAI has one coarse topology and no
command-action ground truth, and the public corpora PHOS inspected are all refused as detection
rulers (ADR 0040, ADR 0046, ADR 0047). Synthetic data lets Atlas be thrown at attacks across a full
difficulty range — obvious to near-invisible — and find where it goes blind, without waiting on a
design partner.

## Why this proceeds outside P1

`.phos_roadmap_state.json` names `current_session` as P1, blocked on a human partner conversation for
historian schema, clocks, and declared subsystems. P1's out-of-scope list explicitly forbids sockets
in `src/phos`, Intelligence/API/UI work, and claiming 2–3/day, 10×, or ≥70%. D3 does none of those:
it is a diagnostic harness against synthetic data, produces no public detection claim, and advances
nothing on P1's agenda. It is authorized here because it is not P1 work — it is D3 work, the third
PART of the synthetic data engine whose scope was declared in ADR 0015 ("D3 will run Atlas against
the result and map where it goes blind").

## Decisions

### Decision 1 — D3 is a script, not an engine change

`scripts/evaluate_atlas_synthetic.py` loads synthetic corpora through `LabelledCsvAdapter`, runs
`AtlasEngine.run` (or `ModelDetector` against a fitted joint model) on them, scores with
`phos.eval.harness.evaluate`, and writes reports to `eval_runs/synth/` — never to
`eval_runs/log.jsonl`. No module under `src/phos/atlas/` or `src/phos/eval/` is modified. The only
new code is the script and its tests.

### Decision 2 — Every result carries SYNTHETIC-DERIVED

Every report prints `SYNTHETIC-DERIVED` and attaches the four standing caveats:
`MODEL_NOT_REALITY_CAVEAT`, `ATTACKS_ARE_OURS_CAVEAT`, `SYNTHETIC_TOPOLOGY_CAVEAT`,
`INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT`. A result read without those caveats is misread.

### Decision 3 — No comparison against frozen public rows

D3 results are never compared against, never replace, and never share a log with the frozen public
rows: HAI Mahalanobis 646.58, grouped 53.26, distillation 18.72, CERT 6B 0.104. A table that places
a synthetic number beside one of those is a defect, not a measurement.

### Decision 4 — No rate claims from synthetic data

No recall figure, FP/normal-hour, precision, or detection rate from D3 may be quoted as a field
detection rate, a public-ZIP pass/fail, or evidence about any real plant. In particular:
- not ≥70%, not 10×, not 2–3 alerts/day
- not a lead rate (command-lead stays 0/16 and 1/4, unpooled)
- not a replacement for any frozen row
- not a row in `eval_runs/log.jsonl`

### Decision 5 — Hypothesis confidence is never printed

Constitution §3.3: uncalibrated confidence must not be surfaced. D3 reports detection metrics
(recall, FP/normal-hour, precision, latency, ECE, Brier) only. Hypothesis confidence from Atlas's
reasoning layer is structural — it may be present in a narrative, but never printed as a number.

### Decision 6 — The anti-bias construction still applies

D3 does not weaken ADR 0073's five mechanisms: the generator may not reference the detector, attacks
are specified by intent never signature, every scenario carries real-world provenance, a mandatory
band of misses exists, and the method is published including its failures. D3 is a consumer of
synthetic corpora, not a producer — but it must not be designed to pass.

## Success is

- `scripts/evaluate_atlas_synthetic.py` exists, runs without error, and scores Atlas against at
  least one D2-generated synthetic corpus.
- Every report is marked `SYNTHETIC-DERIVED` with the four caveats attached.
- Nothing is written to `eval_runs/log.jsonl`.
- Nothing is compared against a frozen public row.
- `mypy --strict` and `ruff` are clean on the new script and its tests.
- Tests pin determinism (same seed, same corpus, same report) and the SYNTHETIC-DERIVED marking.

## Success is not

- A detection rate for any real environment.
- A claim that Atlas detects attacks better than it did before.
- A number beside HAI 646.58, grouped 53.26, distillation 18.72, or CERT 6B 0.104.
- A claim of ≥70%, 10×, or 2–3/day.
- Printed hypothesis confidence.
- Any change to `src/phos/atlas/` or `src/phos/eval/`.

## Alternatives considered

- **Register synthetic corpora in `data/registry.json` as labelled command corpora.** Rejected.
  That would turn `discover_labelled_command_corpora` green on synthetic data — the precise lie
  ADR 0040's tripwire exists to prevent (ADR 0073, Decision 8).
- **Score D3 on `eval_runs/log.jsonl`.** Rejected. The public log holds frozen rows; synthetic
  results must never share it (ADR 0029, ADR 0073).
- **Compare synthetic recall against HAI recall.** Rejected. Different corpora, different
  topologies, different ground truth; the comparison means nothing.
