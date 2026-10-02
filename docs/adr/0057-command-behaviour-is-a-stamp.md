# ADR 0057 — Command-behaviour is a stamp; narratives reconstruct to a frame or absence

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Sessions D1–D2
- **Supersedes:** nothing
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)

## Context

Command-behaviour deviations matched no OT template because `Evidence` has no
feature field. D1 asked for a declared marker so a template *could* read it later.
D2 asked for property tests from narrative to finding to frame.

## Decision

1. `COMMAND_BEHAVIOUR_MARKER` prefixes promoted command-behaviour summaries, same
   idiom as `graph-finding:`. Templates still do not match that stamp.
   `test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence`
   still passes. Known-link unexpected function was not put on maintenance-contradict.
2. `observations_under` walks a narrative to stored observations: subsystem events
   expand to members; deviations to readings; graph findings and stamps to their
   observation ids.

## Consequences

- Unique lead on known-station D2 stays 0/16. Unknown-master toml was not grown.
- Live session after D2 is D3 (public command corpus still refuse unless files change).
