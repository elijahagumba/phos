# ADR 0067 — Follow-up public corpora and partner ICD stay closed

- **Status:** Accepted
- **Date:** 2026-08-24
- **PART:** Engine week (days 31–90 honesty)
- **Supersedes:** nothing
- **Depends on:** [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0061](0061-clock-a-published-partner-unearned.md),
  [ADR 0063](0063-declared-physical-roles-unblock-cross-plant-measurement.md)

## Context

Days 31–90 of the engine map allowed CERT r4.2 compromised-vs-insider ranking, SWaT
in-plant/transfer names, ICSSim fault-vs-attack, and a partner ICD **only if the files
or a human answer existed**. They did not.

## Decision

1. **CERT r4.2 events** are not on disk. `scripts/probe_cert_release.py --release r4.2`
   still reads answers: 70 incidents, 3 scenarios, 10 account-holder-is-not-the-actor,
   **0** peer-relative positives. Headers of activity logs were **not** checked.
   Compromised-vs-insider ranking is **unrun**. r3.1 6B remains the ruler.
2. **SWaT / WADI** remain `operator-provided` / form-gated. No in-plant or transfer row.
   Engineering does not scrape the iTrust form. 646.58 and the 1078.99 zero-shot cell
   are not overwritten.
3. **ICSSim** licence is read-once and identity unestablished. Not acquired. Not a
   command corpus.
4. **Track C** peer corpora stay unfetched (peer-baselining-gap.md (lab record, not published)).
5. **Partner ICD** is not started. Outreach has not returned a yes. P1 stays
   `blocked_human_conversation`. No TAP, API, UI, or Intelligence.
6. **Command-lead 0/16** is not reopened. `discover_labelled_command_corpora` is still
   empty.
7. Cite this quarter's **new names** in Benchmark v2
   (`eval_runs/benchmark/phos-benchmark-v2.md`). Do not rewrite Benchmark v1.

## Consequences

The engine map's later months are closed by absence, not by a quiet number. The next
honest move on those corpora is a human returning a form, an events archive, or a
partner conversation — not a fetch script and not a product surface.

## Alternatives considered

- **Download r4.2 events (~4.8 GB) in this pass.** Rejected unless a human asked for
  that disk. The probe already shows peer positives are still zero.
- **Start Intelligence/API/UI because ninety days elapsed.** Rejected. P1 is not a
  calendar skip (ADR 0061).
