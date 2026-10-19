# ADR 0165 — This Kelmarsh run trains on 2018 and scores 2019–2022

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane B, false alerts on a real plant
- **Depends on:** [ADR 0152](0152-kelmarsh-log-rule.md),
  [ADR 0154](0154-the-kelmarsh-score-did-not-run.md)

## Context

ADR 0152 trains on 2016–2018 and scores 2019–2022, and it refuses a partial
year set. Round 2's development years are 2018–2022. On this machine
`Kelmarsh_SCADA_2017_3083.zip` is absent, and `Kelmarsh_SCADA_2016_3082.zip`
is smaller than the registry size, so it is not the file ADR 0154 checked.
Opening those two years, or scoring without them under the old split, would
be a different configuration from both records.

2018 through 2022 are the files this run may open. 2023 and 2024 stay held
back. The five signals, the ten-minute windows, and the status-log rule stay
as ADR 0152 wrote them. `atlas-v1-consistency` is not edited.

## Decision

1. `SCORED_SCADA_FILES` is the five year zips 2018–2022. The round-2 loader
   refuses 2016, 2017, and every held-back name before the path is read.
2. Because only the 2018 zip is loaded as training, train is 2018 and score
   is 2019–2022. `which_half` in `kelmarsh_log` is unchanged, so a later run
   that loads 2016–2017 still follows ADR 0152.
3. Each zip's size and md5 are checked against `data/registry.json` before
   use. A mismatch stops the run. No partial farm is scored.
4. A 2022 turbine or status member may be named through 2023-01-01. That end
   label is not the held-back zip. The member is read; any timestamp on or
   after 2023-01-01 is outside the score and is dropped. PMU and grid-meter
   members stay closed. The default loader, without this flag, still refuses
   any member whose name contains 2023 (ADR 0152).
5. The result name is `lane-b-dev:kelmarsh-2018-2022`. It is not appended to
   `eval_runs/log.jsonl`.

## Consequences

This is not the ADR 0152 configuration, and it is not a detection claim.
A later held-back score of 2023–2024 is a separate declaration.
