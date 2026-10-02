# ADR 0032 — Precision policy lost on CERT r3.1 at 48 alerts; 6B remains the headline

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Sentiel)
- **Supersedes:** nothing (does not replace [ADR 0028](0028-precision-policy-volume-peer-match-and-the-family-gate.md);
  it records the measurement that policy asked for)
- **Depends on:** [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0028](0028-precision-policy-volume-peer-match-and-the-family-gate.md)

## Context

ADR 0028 shipped an opt-in scoring policy so backups and peer-matching role changes would
fall down a SOC queue. Defaults left the PART 6B row comparable. A 48-person library fixture
then showed `:precision` helping (0.22 → 0.30 precision at a library-only threshold). That
fixture was designed to contain backups and thumb-drive onsets. ADR 0029 forbids reading it
as CERT.

The CERT r3.1 peer run with `--precision-policy` finished. At the 48-alert budget, seed 7:

| Detector | Precision @ 48 | Window recall |
| --- | ---: | ---: |
| `aggregate:gaussian:peer set (34 features)` (6B) | **0.104** | 0.5 |
| same, `:precision` | **0.083** | 0.5 |
| `enriched control (26 features):precision` | **0.042** | 0.5 |

Still one of two labelled insiders. The lever that helped on personas we wrote **hurt** the
public ruler.

## Decision

**The CERT 48-alert headline remains the 6B identity scorer.** `:precision` stays an opt-in
experiment name. It is not the path to the 30–50/day contract on this corpus. Factors are
not refit on CERT's test half.

Peer-group detection advantage stays retired (ADR 0022 / 0023): r4.2's labels still contain
no peer-relative positive. What r4.2 can unblock is compromised-account vs insider
(scenario 3), and only after its events are on disk.

## Consequences

**Gained.** A negative result on the corpus that matters, logged under a detector name that
cannot overwrite 6B.

**Cost.** Volume down-weighting is not a CERT precision strategy. Refusal when the only
unusual family is volume remains the honest SOC lever, and it is not yet the default page
rule.

**Unchanged.** Hypothesis confidence is uncalibrated. No contradictory CERT template.
