# ADR 0174 — The Kelmarsh held-back score is declared before it runs

- **Status:** Accepted (a declaration; this record has no alert count)
- **Date:** 2026-10-19
- **PART:** Round 3, Job 1
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0152](0152-kelmarsh-log-rule.md),
  [ADR 0165](0165-kelmarsh-round-2-trains-on-2018.md)

## Context

ADR 0144 holds back Kelmarsh SCADA 2023 and 2024, plus the PMU and grid-meter
archives. ADR 0165 trained `atlas-v1-consistency` on 2018 and scored 2019–2022.
That run was not repeated here. `which_half` still treats a timestamp on or
after 2023-01-01 as outside, so the development loader cannot score these years
without a different window. The detector and the status-log rule stay as ADR
0165 left them.

`df -h ~` before this declaration showed 4.5 GiB free. The five held-back files
in the registry sum to 1,564,921,875 bytes. They are not downloaded in this
commit. Their sha256 is empty until a later commit fills it. The score command
refuses to open a zip while that field is empty.

## Decision

1. **Scorer.** `atlas-v1-consistency`, unchanged. `src/phos/atlas/consistency.py`
   sha256 `71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`.
   The command exits if that file's hash differs. Modes are not run. Nothing
   is retuned on the result.

2. **Status-log rule.** The rule ADR 0165 kept from ADR 0152. Five signals,
   ten-minute windows from `windows_for_period(600)`, one fit per turbine on
   2018, attack flags all false. A status row explains an alert when the alert
   time is inside `[Timestamp start, Timestamp end]` and `Service contract
   category` is not `System OK (32)`.

3. **Window.** Train is `Kelmarsh_SCADA_2018_3084.zip`. Score is
   `Kelmarsh_SCADA_2023_5961.zip` and `Kelmarsh_SCADA_2024_5962.zip`, timestamps
   in `[2023-01-01, 2025-01-01)`. A row on 2025-01-01 is dropped. `which_half`
   is not edited. PMU and grid-meter members inside a SCADA zip are refused.

4. **Meters.** `Kelmarsh_PMU_4459.zip`, `Kelmarsh_PMU_2023_2024_5968.zip`, and
   `Kelmarsh_Grid_Meter_4458.zip` are checksummed. The command records member
   names and one header line. It does not call `detect` on them. They are not
   the five-signal input the status-log rule names.

5. **Command and result.** `uv run python scripts/round3_kelmarsh.py`. Result
   name `round-3:kelmarsh-heldback`. The declaration is
   `eval_runs/build/round-3/kelmarsh-declaration.json`. `authorized` stays
   false until every file's sha256 is committed. If the result file already
   exists, the command does not run again. Nothing is appended to
   `eval_runs/log.jsonl`.

## Consequences

The counts, when the one command writes them, are a false-alarm count on a
real plant. They are not a detection claim (ADR 0143).

## What would reverse this

Editing `consistency.py`, changing the OK category, or running the command
twice.
