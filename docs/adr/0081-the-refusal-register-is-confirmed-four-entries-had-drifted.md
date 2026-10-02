# ADR 0081 — The refusal register is confirmed; four entries had drifted

- **Status:** Accepted
- **Date:** 2026-09-20
- **PART:** Usefulness Phase item U6 (end-of-phase confirmation)
- **Supersedes:** nothing
- **Depends on:** [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md),
  [ADR 0076](0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md),
  [ADR 0078](0078-the-synthetic-diagnostic-environment-is-constructible-and-answers-its-four-questions.md),
  [ADR 0079](0079-u4-renders-an-existing-narrative-in-plain-english.md),
  [ADR 0080](0080-u5-three-arm-instrument-is-not-operational-usefulness.md)

## Context

U6 runs throughout the phase. By U5 it held R1–R26 on disk. The remaining work is the
end-of-phase confirmation: every entry still true of the code at HEAD `5a7d8ae`, and every
contract the phase made either earned, honestly refused, or tracked as a future session.
U7 is not started.

## Decision

**1. Confirm against the artefacts that computed the numbers, not against memory.**

R1–R26 were re-read against the cited ADRs, the committed reports under `eval_runs/`, and
the code at HEAD. Pins live in `tests/eval/test_refusal_register_freeze.py` so a later edit
that drops an entry, empties a lift column, or re-claims a withdrawn number turns red.

**2. Four entries had drifted. They are corrected, not left standing.**

- **R3.** "What would lift it" still asked for a declared physical-role mapping. ADR 0063
  already measured BATADAL→HAI at **1078.99** FP/normal-hour against native HAI **646.58**.
  Transfer is louder. The generalisation claim stays refused; the lift is now a transfer
  that is not louder, or a third process that actually generalises.
- **R4.** The lift column still named U5 as if it had not run. U5 ran; `n_human` is 0
  (R25). Recruiting is U7, not started (R26).
- **R15.** "Largest shift on any of the 34 features is z = 1.07" copied ADR 0076's curated
  count-feature pair. The committed U2 report ranks by abs(z) and leads with **1.27** on
  `distinct_pcs_peer`. 1.07 remains the largest count-feature increase. ADR 0076 is not
  rewritten; the register is.
- **R20.** The lift column still named "U5 with plant-literate operators". U5 did not
  supply those subjects.

R1, R2, R5–R14, R16–R19, R21–R26 matched HEAD.

**3. The standing procedure now references the append procedure.**

U6 `success_is` required that. `docs/usefulness-phase-roadmap.md` §0 named the register as
an item and did not point at `docs/refusal-register.md` §0. That is a procedure gap, not a
refusal. Fixed in the same change. Roadmap §7 no longer says "no item started".

**4. End-of-phase contracts, none assumed met.**

| Contract | Verdict |
|---|---|
| U1 taxonomy of 424 events; frozen 53.26 / 646.58 untouched | Earned (ADR 0075). Gate 1 passed by Elijah 2026-09-11 |
| U2 four questions; frozen 6B 0.104 at 48 untouched | Earned (ADR 0076). Gate 2 passed by Elijah 2026-09-12 |
| U3 twelve scenarios; four questions; realism identity proof | Earned as SYNTHETIC-DERIVED (ADR 0078). Not a detection claim |
| U4 four-property render; no probability required; not Ω3 | Earned (ADR 0079). Gate 2 ceiling travels with Sentiel output |
| U5 executable instrument; crude run with limitations first | Earned as machinery (ADR 0080). Operational usefulness **refused** (R25) |
| U6 register seeded, appended, confirmed | Earned by this record |
| U7 smallest real-world experiment | Tracked. Not started. Outreach remains Elijah's |
| Calibrator without labelled positives | `future_sessions.calibrator_without_labelled_positives`: tracked, not authorised |
| Non-saturating aggregation | `future_sessions.non_saturating_aggregation`: tracked, not authorised |
| Intelligence / API / UI | Forbidden. Not present under `src/phos/` |
| Frozen public rows 646.58 / 53.26 / 18.72 / 0.104 / 0/16 / 1/4 | Untouched. `.phos_roadmap_state.json` not edited. Nothing appended to `eval_runs/log.jsonl` |

**5. Residual public-surface copy that contradicted R18 is corrected here.**

Gate 2 required the withdrawn 1.8× ratio off the public surfaces. `easy to reads/37` still
closed with "nearly twice as much", and `easy to reads/README.md` still summarised it that
way. The counts stand; the ratio does not. Note 37's closer and the README line move with
this confirmation.

## Consequences

The register is the specification of what PHOS needs from the world, confirmed current.
U7 may assemble its ask from section 5. It is not authorised by this record.

## Alternatives considered

- **Leave R15 as ADR 0076 wrote it.** Rejected. The committed report the register cites
  ranks 1.27 first. An entry that overclaims "any of the 34 features" is the thing U6
  exists to catch.
- **Rewrite ADR 0076.** Rejected. Records are immutable; the register is the living
  boundary map. ADR 0076's curated table remains a valid illustration of count-feature
  onset-from-zero vs escalation-from-base.
- **Start U7 in the same session.** Rejected. The instruction is U6 only.
