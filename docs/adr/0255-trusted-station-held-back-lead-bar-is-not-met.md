# ADR 0255 — The trusted-station held-back lead bar is not met

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0254](0254-trusted-station-held-back-is-declared.md)

## Context

The one score declared in ADR 0254 was run after commit `592d051`:

`uv run python scripts/score_trusted_station.py --split held-back`

Result name `trusted-station:known-operator-effect`. Challenger sha256
`981270a8c60a0d4733e739ae182a01af2e040b90a9786406c6b77cbaa718f747`. Seeds 97901-97920.
Report: `eval_runs/build/d/trusted/held-back.md`. A second run was refused. This is a simulated
diagnosis (ADR 0073).

## Decision

**The lead bar is not met. Do not rerun it. Do not reword it.**

| Bar | Result |
| --- | --- |
| Hostile known-station writes led in more than 0 of them | 0 of 20. **Not met.** |
| False-alarm narratives per authorised run not above 0.20 | 0.00 (0 of 20). **Met.** |
| Known-link both-support tests green | 3 passed. **Met.** |

Every hostile seed gained `toward_limit_against_state` and `write_and_hide`. The narrative lead
was `insufficient_evidence` on all 20. Two facts at weight one half do not pass the residual
prior. The weight was not raised. `insufficient_evidence` listed first is not a unique
unauthorised lead (ADR 0036).

## Consequences

Lane T's challenger separates a hostile known-operator write from an authorised unusual write
on the evidence lists, and it does not make unauthorised control the unique narrative lead.
Known-station **0 of 16** and unknown-master **1 of 4** stay frozen and unpooled. Nothing here
is a field rate, and nothing here is ≥70%.
