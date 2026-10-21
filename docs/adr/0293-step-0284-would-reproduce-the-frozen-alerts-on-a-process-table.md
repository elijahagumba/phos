# ADR 0293 — Step 0284 would reproduce the frozen alerts on a process table

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Build brief E, step 0284, before it is authorised
- **Supersedes:** nothing
- **Depends on:** [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0058](0058-public-command-corpus-still-absent.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md)

## Context

Step 0284 is the one look at the seen corpora, and only Elijah may authorise it. The handoff
asked whether that look would be a null: lane 1 needs command traffic, and the corpora where
the v1 numbers live were said to have none, so the kept lane might score identically to the
frozen engine. That was an inference. This record is the check. It is not the look.

The files themselves were not opened. `hai`, `hai-21.03`, `hai-22.04`, `hai-23.05` and
`batadal` stay unread. 0284 stays unspent.

## Decision

**As lane 1 is built, a process table with no command messages produces the frozen engine's
alerts.** Three facts, each checked:

1. **The command inlet is ICSSim's `modbus.csv` and nothing else.** `Command` is constructed
   in `phos.atlas.icssim_adapter` only. The HAI editions and BATADAL are registered as CSV
   process tables: a timestamp, signal columns, and an attack flag (`data/registry.json`).
   No command-message file is registered for them.
2. **No messages means two zero columns.** Fitting `fit_commands` on an empty command tuple
   and scoring `augmented_scores` with another empty tuple leaves the signal columns equal to
   `feature_scores` and the two appended columns at zero. An empty set of writers does not
   itself mark every row an unknown master: a column moves only when a message arrives.
   `tests/atlas/test_command_consistency.py` tests
   `test_a_file_with_no_messages_adds_two_zero_columns`.
3. **A column that never exceeds the threshold adds no episode.** `events` opens an episode
   only where a column is greater than `THRESHOLD` (1.0). Two zero columns add none, so
   `events` and `budget_alerts` return the same alerts.
   `test_two_columns_that_never_cross_the_threshold_do_not_move_an_alert` shows that on a
   hand-built matrix, which is not a corpus.

ADR 0040 and ADR 0058 say there is no labelled public command corpus. That is a fact about
labels. This decision does not rest on labels. It rests on there being no messages for the
lane to read.

## Consequences

Spending 0284 on those process tables, with the candidate 0283 would assemble from the one
kept lane, would reproduce the frozen alerts. The score matrix would be wider. The alert rows
and scores would not move. That is the sense in which the look is a null.

It stops being a null if the assembler builds `Command` values out of setpoint columns in the
CSV, or if a command-message file is registered for one of those corpora. Neither is true of
the lane as it stands.

v1 stays 8 of 12. No seen corpus was scored. `eval_runs/log.jsonl` was not appended.

## What would reverse this

A command-message file on one of the seen corpora, an assembler that constructs `Command`
from the process columns, or a change to `events` that lets a column at or below the
threshold move an alert. Any of those makes this record the wrong reason to skip 0284.
