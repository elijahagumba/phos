# ADR 0221 — The v1 command checks the record

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** v1 A7, tools lane (`docs/build-brief-2026-10-c.md`)
- **Depends on:** [ADR 0116](0116-a2-status-four-of-five-beyond-chance.md)

## Context

A7 asks for one command that regenerates every v1 number, and for someone outside the project to
have run it. The recorded numbers sit in committed result files. Several of those files include
HAI 21.03, HAI 22.04, HAI 23.05, and BATADAL. Opening those corpora to recompute would be a new
look at validation data, and a full recompute would take hours.

## Decision

1. `scripts/reproduce_v1.py` does not rescore. It checks each pinned result file's path and
   sha256, and each pinned digit inside it, and prints a pass or fail table. A match says
   `record intact`. A mismatched digit exits non-zero.
2. The pin is `eval_runs/build/v1/tools/reproduce-pin.json`. It is a copy of digits already in
   the committed records, plus the sha256 of those files. It is not a new measurement.
3. The command refuses any path under `data/` before opening it. Validation payloads are not
   read. The command does not write an evaluation log.
4. How an outside person installs, which records the command checks, and how to read the table
   is `docs/reproduce.md`. A7 stays unmet until someone outside the project has run the command.

## What would reverse this

A recompute that opens a validation corpus, a pin edited so a changed digit still passes, or a
claim that writing this command meets A7.
