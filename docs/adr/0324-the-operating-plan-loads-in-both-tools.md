# ADR 0324 — The operating plan loads in both tools

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Process, session loading
- **Supersedes:** nothing
- **Depends on:** [ADR 0265](0265-the-always-apply-rules-load-themselves.md),
  [ADR 0287](0287-the-live-brief-is-discoverable-from-the-rules.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md)

## Context

`docs/zero-to-one-master-plan.md` is the sequence for building from the declared-law page, written 23 October 2026. It is not a measurement. A later session in Cursor loads `.cursor/rules/` and does not open that file unless a rule names it. A later session in Claude Code does not read `.cursor/rules/` at all. ADR 0265 and ADR 0287 exist because a programme that lives only in a document the session was not told to open is invisible, and an invisible programme gets replaced by whatever the older rules still call the next action.

The plan does not replace ADR 0316. The joint-command score remains the residual clock's outstanding declared run. The plan does not fill 0277–0284. It does not unblock P1.

## Decision

**The operating plan is loaded by both tools, as a short always-apply rule that points at the plan and states the locks. The plan stays the sequence. The rule lifts nothing.**

The body is `.cursor/rules/zero-to-one-plan.mdc`, with `alwaysApply: true`. `docs/rules/zero-to-one-plan.md` is a symlink to that file. `CLAUDE.md` imports it after `live-work.md`, by ADR 0265: one copy, Cursor and Claude Code.

`live-work.mdc` gains a pointer paragraph so a session computing its position from that file can find the plan. The paragraph does not authorise a harness run.

A session builds from the plan only when the human asks. The first engineering commit, when that ask comes, is the inlet declaration, and that declaration contains no code that reads a file.

## Consequences

**Gained.** A fresh Cursor session and a fresh Claude Code session both see the locks: residual files stay, the law page does not import them, no new protocol without a declaration, no station inferred from a function code, no score on the page, a break is not called an attack, an empty page is not called a safe plant, Intelligence, an API, a UI, and a TAP stay unstarted, and the later quarters wait on the month-12 gate.

**Cost.** Another always-apply rule in every session. It is short for that reason. The quarters live in the plan, which the rule orders the session to read before editing.

**Ten years.** The rule should be deleted or rewritten when the plan's month-12 gate has been recorded, whether the gate passed or stopped the vendor sequence. Leaving the pointer in place after the plan has ended would hide the next programme the way the pre-0273 rules hid the live one.

## What would reverse this

Building from the plan without the human having asked. Treating the plan as a measurement, a detection rate, or a ship authorisation. Importing a residual detector into `declared_law.py` because the plan was read as a purge. Starting a protocol, a socket, an API, a UI, or Intelligence from this rule. Running the plan's later quarters without the gate ADR. Retuning a frozen window, the walk length, or the ceiling because the plan mentioned them.
