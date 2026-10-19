# ADR 0254 — The trusted-station held-back score is declared

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0252](0252-h2-is-rejected-for-false-alarms.md),
  [ADR 0253](0253-h3-is-kept-and-does-not-lead.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

Development is finished. H2 is rejected (false alarms 1.00). H1 and H3 each attach on the
hostile writes and on none of the authorised runs, and neither uniquely leads. Together they
are still 0 of 20 unique leads and 0.00 false alarms. The weight was not tuned.

Held-back seeds 97901-97920 have not been generated. This record declares the one score. The
scorer refuses if `eval_runs/build/d/trusted/held-back.md` already exists, and it refuses if
this file is not in HEAD or if the challenger bytes do not match the sha256 below.

## Decision

**Score once, after this commit, and do not score again.**

- **Challenger:** H1+H3. Features `toward_limit_against_state` and `write_and_hide`. H2 is off.
- **sha256:** `981270a8c60a0d4733e739ae182a01af2e040b90a9786406c6b77cbaa718f747`
- **Files in that hash, in order:** `src/phos/ontology/enums.py`,
  `src/phos/atlas/command_effect.py`, `src/phos/atlas/templates.py`,
  `src/phos/eval/trusted_station.py`. The path is mixed in before each file's bytes.
- **Command:** `uv run python scripts/score_trusted_station.py --split held-back`
- **Result name:** `trusted-station:known-operator-effect`
- **Seeds:** 97901-97920. Same generator as development: water-treatment, the declared operator,
  one hostile write and one authorised run per seed, plants in memory.
- **Bars, not reworded:**
  1. Hostile known-station writes led in more than 0 of them.
  2. False-alarm narratives per authorised run not above 0.20.
  3. The known-link both-support tests green:
     `test_a_function_change_on_a_known_link_still_supports_both`,
     `test_a_silent_known_link_still_supports_both`, and
     `test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence`.

A unique lead is `unauthorised_control_activity` at the front of the narrative, with
`tied_lead_ids` empty. `insufficient_evidence` listed first is not a lead. The result is a
simulated diagnosis. It is not a field rate (ADR 0073), not the frozen 0 of 16, and not ≥70%.

## Consequences

Whatever the one score finds is the result. A miss is not rerun. The weight is not changed
afterwards. Known-station **0 of 16** and unknown-master **1 of 4** stay frozen and unpooled.
