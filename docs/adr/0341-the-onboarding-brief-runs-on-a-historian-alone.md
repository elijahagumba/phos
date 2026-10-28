# ADR 0341 — The onboarding brief runs on a historian alone, and `phos` carries it

- **Status:** Accepted
- **Date:** 2026-10-28
- **PART:** v1 C2, tools lane (`docs/build-brief-2026-10-c.md`)
- **Supersedes:** [ADR 0220](0220-tag-suggestions-are-not-declarations.md) Decision 1's command
  surface only. Decisions 2, 3, 4 and 5 stand unchanged, and Decision 5 still gates C2.
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0220](0220-tag-suggestions-are-not-declarations.md)

## Context

*Written from the engineering constraint alone. `docs/adr/*` exports to the public repository
(`public/manifest.toml`), and the files that motivated this record do not, so the motivation is
stated here as the technical fact it rests on and nothing else. A record that exports must read as
if a stranger is its only reader.*

Asking a plant for a historian export is asking for operational data to leave its site. That
request needs a legal review wherever it is sent, and a legal review is measured in quarters, so
the size of the request — not its wording — is what decides how long an answer takes.

The request does not have to be that. The core is pure and offline by constitution §3.8, and
`phos.atlas.onboarding` already reads a historian export locally and proposes a role and a kind per
tag with its evidence printed beside each one. So the ask can be *run it on your own machine and
send nothing back*, and a corrected tag list is the first box of `docs/design-partner-icd.md`.

Three things stopped that tool being handed to a stranger. All three are surface, not behaviour.

1. **`main` required `--capture`.** A historian export is an afternoon for a plant engineer. A
   control-network capture needs a span port, a change request and a security conversation.
   Requiring both meant the easy half could not be done on its own. The library did not require it:
   `suggest(historian, capture=())` has defaulted the capture to empty since ADR 0220, and
   Decision 3's rules for an absent capture — reads alone are not a role, writes alone do not choose
   between an actuator and a setpoint — are already the behaviour when no capture is supplied.
2. **Nothing reached it from the `phos` command.** ADR 0220 Decision 1 set the command as
   `uv run python -m phos.atlas.onboarding`, which is not something a practitioner finds or
   remembers.
3. **The public record named it only as a gap.** The README listed "the onboarding trial" among the
   four v1 criteria *not* met, so a reader learned the trial was outstanding and never learned they
   could run the tool.

## Decision

1. **`--capture` is optional.** With no `--capture`, the brief is built from the historian alone and
   is identical to the brief for an empty capture table. A `--capture` that is given and cannot be
   read is still an error and still exits 2. A historian is still required.
2. **`phos onboard` is the command**, added to the `phos` parser in `phos.demo.cli` and delegating
   to `phos.atlas.onboarding.main`. `uv run python -m phos.atlas.onboarding` keeps working; ADR 0220
   Decision 1 named it and nothing here withdraws it. The parser lives in `phos.demo.cli` because
   that is where `[project.scripts]` already points; moving the `phos` command to a module of its
   own is a separate decision and is not taken here.
3. **The public README carries the invitation**, in the words that do the work: it runs on your own
   machine, it makes no network calls, and nothing leaves your site. ADR 0044's three surfaces move
   in the same change.

## What this does not change

- **C2 is still not met, and the v1 scorecard stays at 8 of 12.** ADR 0220 Decision 5 gates C2 on
  the human trial in `eval_runs/build/v1/tools/c2-trial.md`, and that trial has not been run. A
  reachable command is not a trial. No public surface may say or imply otherwise.
- **A suggestion is still not a declaration.** ADR 0123 stands: a role the plant map trusts is read
  from documentation, never from a name and never from the data. The brief header says so and the
  package still does not call `load_roles` and still writes no role file.
- **No kind from a statistic or a capture** (ADR 0220 Decision 2). Nothing in the role rules,
  the statistics or the evidence text moves.
- **The tool remains passive.** No network calls, no agents, no subprocesses; file reading stays in
  `main`.
- **P1 is still a human conversation.** A reachable command does not unblock it, and no message is
  sent by an agent.

## What would reverse this

Letting an absent capture change a role or a kind rather than only removing capture evidence;
treating a reachable command, or a brief produced from a stranger's export, as the C2 trial;
or any public surface implying the onboarding criterion is met.
