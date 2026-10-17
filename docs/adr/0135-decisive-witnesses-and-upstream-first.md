# ADR 0135 — Decisive downstream witnesses, and upstream first: two naming rules and a fresh test

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123 §5.2 and §5.3, ADR 0130 falsifier 4; before anything is scored
- **Amends:** [ADR 0123](0123-the-plant-map-proposed.md) §5.2–§5.3 when selected;
  [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md) §1 (one more override)
- **Depends on:** [ADR 0125](0125-a-drop-one-check-is-decisive-or-inconclusive.md),
  [ADR 0134](0134-red-team-and-the-trusted-map-first-results.md)

## Context

ADR 0134 diagnosed the trusted map's naming failure on development data. On the water plant a
downstream witness too weakly linked to tell a false level from a true one was counted as
agreeing with the reading, and turned every caught run into "reading true, plant changed". On the
batch reactor the map named the signals that changed because a controller followed the lie,
rather than the lying reading upstream. Both rules below come from principles the design already
states. They were found on the arena's development seeds, so they are judged on seeds no rule
has seen.

## Decision

**1. Decisive witnesses.** A downstream child testifies about a candidate only when it is
decisive: substituting the candidate's reconstruction for its reading moves the child's residual
by more than the child's band. A child that cannot tell the reading from the reconstruction is
inconclusive. It counts neither for the downstream check nor for "reading true, plant changed".
This is ADR 0125's rule for drop-one models, applied to the third check.

**2. Upstream first.** A candidate is named only when every ancestor outside its own loop (an
ancestor that is not also a descendant) is in band in its own model, judged without the
candidate. A disturbance that began upstream cannot be blamed on the reading it reached. ADR 0123
§5.2 checks a candidate's direct drivers; this extends the check to everything upstream of it.

**3. Both rules are selected together**, as `naming_rules = "adr-0135"` in the map's settings.
ADR 0125's rules stay the default, so attempts 1–4, the red team and ADR 0134 reproduce
unchanged. ADR 0127's overridable settings gain `naming_rules`.

**4. Attempt 5** is `{"detector": "atlas-plant-map-v1", "map": {"naming_rules": "adr-0135"}}`:
attempt 1 with these rules. The naming rules change which events are promoted (a "plant changed"
verdict promotes nothing), so they can change passes, and the attempt is scored as a
configuration. It is measured on the arena slices and every development measure, including the
trusted map (`graded`).

**5. Confirmation, once, on seeds nothing has seen.** `CONFIRM_SEEDS` are development seeds
95201–95210, disjoint from every other set (a test checks). After attempt 5's development
measures, and only then:

- `scripts/arena_red_team.py plant-map --confirm 5` scores the choice among attempts from 5 on
  beside the champion. **It survives** with more passes than the champion and no champion pass
  lost (ADR 0123 §9.3's rule).
- `scripts/plant_map_dev.py --candidate …/candidate-5.json --confirm liar` and `… graded`
  measure naming on the same seeds. **Naming is allowed** for the full map, or for the trusted
  map, only where it names the right instrument in at least 70% of caught runs and a wrong one in
  at most 10% (§9.7 and ADR 0130 falsifier 4, unmoved), and §9.9's band coverage still applies
  to any reconstruction shown.

## Consequences

- If both survive, the challenger becomes a candidate for ADR 0117's gate, as a detector and, if
  naming passes, as a namer. If either fails on the confirmation seeds, that is the result, and
  these seeds are spent like the red team's.
- These seeds also judge the trusted map's naming for the first time on data its rules never saw.

## What would reverse this

Scoring the confirmation seeds before attempt 5's development measures, or more than once;
changing either rule, or a bar, after a confirmation score; or making ADR 0135's rules the
default for earlier records.
