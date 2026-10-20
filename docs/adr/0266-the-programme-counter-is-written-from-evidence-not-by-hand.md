# ADR 0266 — The programme counter is written from evidence, and the freeze stops pinning it

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** orchestration runtime
- **Numbered:** drafted as 0264 on `claude/elastic-perlman-79859c`; renumbered to 0266 when it
  reached `main`, which had meanwhile taken 0264 for the G1 regeneration. Nothing else changed.
- **Supersedes:** nothing
- **Depends on:** [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  [ADR 0061](0061-clock-a-published-partner-unearned.md),
  [ADR 0265](0265-the-always-apply-rules-load-themselves.md)

## Context

`.phos_roadmap_state.json` is the live tracker. `session_protocol` tells every session to open it
first and to update it after the tests pass; the lock in `docs/rules/phos-execution-master.md`
says the same. Nothing in the repository wrote it. It stood at `updated_at: 2026-08-24` with
`updated_by: director` while ADRs 0063–0260 landed, build briefs C and D ran, and the v1 count was
settled at 6 of 12 (ADR 0230). A program counter that nothing increments is not a tracker; it is a
note, and the only scheduler was Elijah reading the repository by hand each time.

The reason it could not be written is in the suite. `tests/eval/test_roadmap_freeze.py` asserted
`current_session == "P1"` and `sessions_completed == [1, 2, 3, 4, 5]` in one test named for both.
The second is a freeze the lock states. The first is the counter, and pinning it means any
legitimate advance turns the suite red — so the tracker could only ever go stale, never move.
Two other suites read this file (`tests/sentiel/test_public_row_freeze.py` reads only
`frozen_measurements`; `tests/eval/test_refusal_register_freeze.py` reads
`.phos_usefulness_state.json`), and neither pins the counter.

## Decision

1. **`scripts/roadmap_state.py` is the only writer.** It derives `current_session` from the one
   `category_programme` entry marked `current` (none, or several, is a refusal and a human decides),
   `sessions_completed` and `category_sessions_completed` from the records that already say
   `status: complete`, `evidence_as_of` from git HEAD plus the ADR index plus
   `eval_runs/log.jsonl`, and `updated_at` from HEAD's committer date rather than the wall clock.
   `--dry-run` prints the diff and writes nothing; `--check` exits 3 when the file is stale.
2. **It cannot move a frozen subtree.** Every write is compared against the document it read, and
   aborted if `frozen_measurements`, `frozen_knobs`, `command_lead`, `contract`, `scorecard`,
   `lock_verdict`, `charter` or `licence_gate` moved, or if a key named in
   `keys_that_must_not_exist` appeared anywhere. A frozen row is added only through `--freeze-row`,
   which demands a harness row carrying a seed, a commit and a report path, and refuses to
   overwrite a name that already exists — `session_protocol` item 6, enforced rather than recalled.
3. **The prohibitions in `next_action` are carried, not regenerated.** They move once into
   `next_action_standing`, verbatim, and the generated factual lead is prefixed to them. The lift
   deliberately does not split a sentence on the full stop inside a figure, so `646.58`, `18.72`
   and `0.104` arrive whole.
4. **The freeze narrows to what it is for.** The one test that pinned the counter is split: the
   contract half keeps `sessions_completed == [1, 2, 3, 4, 5]`, Clock A's completions, `Ω3` absent
   and the programme name; the counter half now asserts only that `current_session` names an entry
   `category_programme` itself marks `current`, and that it is not `Ω3`. P1 staying a blocked human
   conversation is still pinned by its own test, so the sequence cannot be skipped.

## Consequences

The tracker can now be true of HEAD, and `--check` gives the dispatcher a staleness test that does
not depend on anyone remembering to look. The freeze still turns red if a frozen figure, a frozen
knob, the contract, the scorecard or a forbidden key moves. It no longer turns red because the
programme advanced, which is what it was doing before.

Two `does_not_overwrite` arrays in `frozen_measurements` were written inline by hand and are
re-emitted one element per line by the writer's serialiser. The values are unchanged; only their
line breaks move, and the check in decision 2 compares the parsed subtree, not its formatting.

## What would reverse this

A programme state that cannot be derived — a `category_programme` with two live entries, or a
session whose completion is not recorded as a status. The script refuses rather than guessing in
that case, which is the behaviour to keep.
