# ADR 0275 — Lane 1 is frozen, and its one held-out score is declared

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas, stronger-engine programme, lane 1
- **Supersedes:** nothing
- **Depends on:** [ADR 0034](0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md)

## Context

`atlas-v1-consistency` predicts each signal from the other signals and never sees a command, so
"the reading did not follow the order it was given" is a comparison it cannot make. The baseline
on the ICSSim development corpus costs 24 of 60 attacks, with `recon` and `mimic_maintenance` at
0 of 10 (`eval_runs/build/lane-e/baseline-icssim-dev.md`).

Development is complete and recorded in `eval_runs/build/lane-e/lane1-development.md`: 42 of 60
against 24, benign false alarms unchanged at 4 of 20, and `recon` 0 to 10.

**What this lane turned out to be, stated before the shot.** Both surviving components are
attribution: a poll from a role that never polled, and a write from a role that never wrote, both
learned from training rather than listed. That is PHOS's unknown master (ADR 0035). It is a real
capability — `recon` never moves the plant, so no telemetry-only detector can see it however it is
tuned — and it is **shallow**: an attacker who impersonated the operator station would defeat both
components completely. This record does not call that network-against-physics.

**The claim this lane was meant to test is not in this corpus.** A third component compared the
plant's response after a write with the response training saw after the same instruction, as a
summary and then as a trajectory. Neither separated `mimic_maintenance` from genuine
`maintenance`, because the two events are physically indistinguishable: over 39 summary features
of the plant's own behaviour they differ by a median of 0.17 training spreads and a maximum of
1.29, with none above two. It is a provenance attack — what makes it an attack is that no work
order authorised it — which is ADR 0069's CMMS inlet and criterion A5, not this lane. The
component was removed rather than frozen.

## Decision

**One shot, after this record is committed, and not before.**

| Item | Value |
| --- | --- |
| Detector | `atlas-command-consistency` |
| Code | `phos.atlas.command_consistency`, sha256 `87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`, raw file bytes, path not mixed in |
| Reader | `phos.atlas.icssim_adapter`, sha256 `06de74b3c6dd52b613a0a53fd7318cabcf5818496cc33030c18605e0e9f6669c` |
| Components | `unknown_writer`, `unknown_reader`. Scored apart, never pooled (ADR 0034, `command-ranking.md`) |
| Train | The three `normal` runs of `phos-icssim-dev`, seeds 96001–96003. Attack-free, and the only place the familiar roles and the calibration come from |
| Test | Every `mixed` run of `phos-icssim-heldout`, seeds 96101–96120, each 2 hours with eight events of which six are attacks |
| Budget | The frozen 8 alerts per 8-hour shift, `phos.atlas.consistency.budget_alerts`, unchanged |
| Caught | An attack is caught when a budgeted alert's row falls inside that attack's own labelled window |
| Comparison | `atlas-v1-consistency` scored on the identical runs, identical budget, not retuned |
| Result names | `atlas-command-consistency:icssim-heldout` and `atlas-v1-consistency:icssim-heldout` |

**Pass rule, not reworded from ADR 0273.** Strictly more attacks caught within the same budget
than the frozen engine, **and** at least one attack class the frozen engine misses entirely on
these runs. Equality is not a pass. Benign events drawing an alert are reported beside both
counts; a catch gain bought with more false alarms than the frozen engine is reported as that and
is not a pass.

**Reading fixed now, before the run.** `recon` is expected to carry the gain, because the
development runs show the attacker polling thousands of times from a station that never polls. If
that is what happens, the result is reported as **attribution on a simulated plant**: a station
behaving in a way training never saw. It is not reported as the command-against-physics claim,
which this corpus cannot pose, and it is not reported as a result about real plants — ICSSim is
generated, so R4 and ADR 0143 make it diagnosis and not proof. If instead the gain comes from
somewhere unexpected, that is the finding and it is reported as it stands.

**Not in scope.** No v1 number moves; v1 stays 8 of 12 and `atlas-v1-consistency` is never
edited. `eval_runs/log.jsonl` is not appended. No validation corpus is opened. The held-out runs
are not read before this record is committed, and the script refuses to start if its output
already exists or if either hash above does not match.

## Consequences

The programme's first held-out result. Whatever it says, the corpus's inability to pose the
`mimic_maintenance` test stands as the more important finding, and ADR 0122's generator needs a
declared change before any lane can claim network-against-physics on it.

## What would reverse this

A second run of the command, editing either file after this record, pooling the two components,
reporting attribution as the physics claim, or calling a simulated result a result about a real
plant.
