# ADR 0220 — Tag suggestions are not declarations

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** v1 C2, tools lane (`docs/build-brief-2026-10-c.md`)
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md)

## Context

C2 asks for an onboarding tool: from a historian export and a capture, suggest a role and a kind
for each tag, with the evidence, so an engineer can confirm or change it. The tool is passive.
It makes no network calls and starts no agents.

ADR 0123 already owns the words sensor, actuator, and setpoint. A role the plant map trusts is
declared from documentation, never inferred from a name and never from the data. ``P1_FCV01D``
suggests a valve command, and a suggestion is not a declaration. C2 needs that suggestion to be
printable. It must not become a second way to fill `roles.toml`.

The pass bar is unchanged: a corpus not used in development reaches its first brief in under an
hour of human time. Tests on hand fixtures and on HAI 20.07 column names do not meet it.

## Decision

1. The tool is `phos.atlas.onboarding`. It reuses `SignalRole`. It does not call `load_roles` and
   it does not write a role file. The command is `uv run python -m phos.atlas.onboarding`.
2. A kind is one of flow, pressure, level, pump, or valve, and it comes only from a name token.
   A temperature transmitter is reported as a sensor with no kind, because temperature is not one
   of the five. A statistic never assigns a kind. A capture never assigns a kind.
3. A name token wins the role. A sample statistic (how many distinct values, and what fraction of
   the sample sits still) is used only when no token named a role. A constant sample does not
   separate a setpoint from a stuck sensor, so it names no role. A capture write that contradicts
   a sensor token is printed and the token is kept. Reads alone are not a role. Writes alone do
   not choose between an actuator and a setpoint.
4. The first brief is the printed list: tag, role, kind, evidence. A blank role or kind is a cell
   the engineer fills in.
5. The human trial is `eval_runs/build/v1/tools/c2-trial.md`. Until that trial has been run, C2
   is not met.

## What would reverse this

Writing a suggestion into a role file without a documented source, assigning a kind from a
statistic or a capture, or treating a green unit test as the C2 pass bar.
