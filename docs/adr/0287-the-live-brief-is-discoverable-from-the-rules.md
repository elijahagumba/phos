# ADR 0287 — The live brief is discoverable from the rules, in any tool

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Process, session loading
- **Supersedes:** nothing
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0265](0265-the-always-apply-rules-load-themselves.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md)

## Context

The build is moving to Cursor for a period, so the question "what does a session in another tool
know when it starts?" was checked against the files rather than assumed. Two facts came out of it.

**The good one.** Cursor loads six of the seven rule files unaided: `.cursor/rules/*.mdc` carries
`alwaysApply: true` on the constitution, the execution master, `category-programme`,
`cycle-eom-targets`, `data-tiers` and `docs-on-main`, and `docs/rules/<name>.md` is a symlink to the
same file, so ADR 0265's arrangement works in both tools from one copy. `command-ranking.mdc` is
the exception at `alwaysApply: false`, although `CLAUDE.md` imports it unconditionally.

**The bad one.** Nothing in any always-apply rule mentions `docs/build-brief-2026-10-e.md`. Every
one of their "Next action" and "live session" paragraphs names **P1**, and
`.phos_roadmap_state.json` still carries `current_session: P1`. All of that is true — P1 is blocked
on a human conversation — and all of it predates ADR 0273. So a session that reads the rules and the
tracker, which is exactly what the rules instruct it to do first, concludes that the project is
parked on a blocked conversation and that starting work is forbidden. The live programme, lanes 1
to 4 and ADRs 0273–0286, is invisible to it.

Claude Code papered over this with `/phos-today`, a skill that computes the position. Skills and
`.claude/hooks/` are Claude Code only, so in Cursor the gap is uncovered, and so are the five guards
the hooks provided.

## Decision

**A seventh always-apply rule, `live-work.mdc`, whose only job is to point at the live brief and say
how to compute the position.** Symlinked as `docs/rules/live-work.md` and imported first by
`CLAUDE.md`, by ADR 0265's convention: one copy, two tools.

It carries three things and nothing else:

1. That the other rules' "Next action" paragraphs predate build brief E, that P1 is genuinely
   blocked, and that neither fact means the project is parked.
2. The four commands that compute the position from the record — the brief, the reserved-ADR grep,
   `eval_runs/build/lane-e/`, and the tail of `PROGRESS.md` — with the reserved-number convention
   spelled out so a missing number is read correctly as "not run, or run and refused" rather than as
   a gap to fill.
3. What a non-Claude-Code tool is missing: the hooks, the role skills, and `command-ranking.mdc`,
   with the five hook-guarded mistakes listed so they can be checked by hand.

**It lifts nothing.** Every prohibition in every other rule file stands unchanged: P1 stays blocked,
Intelligence, API and UI stay unstarted, and every frozen number stays frozen. The file adds a
pointer and says so in its own text.

**`docs/cursor-handoff.md` is the companion, and is not a rule.** It holds the audit prompt to run
after another tool reports a task finished — trace every number to a command run now, run all six
gate commands and quote them, check the five hook-guarded mistakes, quote the bar verbatim and
report both halves, and report a missed bar in the same voice as a met one — plus how to tell a real
audit from a rubber stamp, and where the programme stands as a convenience with the record kept as
the authority.

## Consequences

An always-apply rule costs context in every session, so this one is short and will stay short. It
has a maintenance obligation that the ADR numbers alone do not: when build brief E finishes, the
pointer must move to whatever is live then, or it becomes the same kind of stale paragraph it exists
to correct. That is the risk this record accepts knowingly.

The deeper problem it does **not** fix: the execution master and `cycle-eom-targets` still describe
a cycle that ended, and `.phos_roadmap_state.json` still names P1 as `current_session` while the
real work is a programme beside it. Rewriting the lock is not a step to take in passing, and
`roadmap_state.py` is the only thing that writes the tracker. `live-work.mdc` makes the
contradiction legible instead of letting a session resolve it wrongly; reconciling it is Elijah's.

One stale clause is named here so it is not lost: `next_action_standing` in the tracker still says
"Follow-up corpora r4.2, SWaT, ICSSim and the partner ICD stay closed (ADR 0067)", and ICSSim is no
longer closed — it is generated and both lanes 1 and 2 were measured on it (ADR 0122, ADR 0274).
Standing prohibitions are carried by hand and never lifted by the script, so lifting that clause is
Elijah's call and is not done here.

## What would reverse this

Build brief E finishing without the pointer moving, which would make this file part of the problem.
Or a decision to reconcile the execution master and the tracker directly, after which a separate
pointer file is redundant and should be deleted rather than left to drift.
