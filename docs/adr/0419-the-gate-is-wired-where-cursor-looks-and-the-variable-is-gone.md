# ADR 0419 — The gate is wired where Cursor looks, and the variable ADR 0414 said was gone is gone

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. The wiring ADR 0417 Decision 1 left open
- **Supersedes:** nothing. [ADR 0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md) stands; this record answers the question it deferred
- **Depends on:** [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md),
  [ADR 0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md),
  [ADR 0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md)

## Context

ADR 0417 observed that Cursor loaded none of this repository's Cursor hooks and said why: Cursor
reads project hooks from the **workspace root**, `.cursor/hooks.json` was on an unmerged branch
inside a worktree, and the workspace root was the `main` checkout. It recorded the finding and
wired nothing, on the grounds that wiring is a change to how the project is worked.

The branch has since merged (`9c0de71`), so `.cursor/hooks.json` is on `main` and present at the
root of every checkout and every worktree. That removes the *file* half of the problem and leaves
the half no file can fix.

## What was found while settling it

**1. The remaining half is the window, not the repository.** `.cursor/hooks.json` is tracked at the
repository root, so a Cursor window opened on a checkout — including a worktree — finds it. A window
opened on a *parent* directory, with the work happening in a worktree beneath it, finds nothing and
the gate is absent. Nothing inside the repository can detect that: the hook that would report it is
the hook that was never loaded. The remedy is therefore a rule about where the window is pointed,
not code, and it is written into `docs/rules/genesis.md` where every session loads it.

**2. ADR 0414 made a claim about this hook that was not true of it.** That record states, twice and
in the encyclopedia as well, that `workspace_roots` "replaces the undocumented `CURSOR_PROJECT_DIR`
ADR 0413 used" and that the variable "is no longer relied on". That was true of
`.cursor/hooks/phos_guards.py`, which ADR 0414 rewrote. It was **not** true of
`.cursor/hooks/genesis_gate.py`, which went on reading `os.environ["CURSOR_PROJECT_DIR"]` at line 70
until this record. The parity test did not catch it because the test *set* the variable in order to
point the hook at a temporary repository — the harness depended on the thing the record said had
been removed.

This is the fourth claim in the permanent record found false this session, after "Cursor has neither
skills nor hooks" (ADR 0413), "five guards are still Claude Code only" (corrected on this branch),
and a note index reading 126 against a directory holding 161. The pattern is consistent: the prose
describes the intended state and the code keeps the previous one, and only an attempt to use the
thing finds the difference.

**3. Where the hook looked mattered more than it appeared to.** With the variable unset — which is
every real Cursor session, since Cursor does not define it — the hook fell back to its own location,
`_HERE.parents[2]`. For a window opened on the checkout being worked in, that is the right
repository. For a window opened on a parent, the hook would consult the *other* checkout's GENESIS
store: a declaration committed on a worktree branch would read as undeclared, and the gate would
stop and ask about a run that was properly declared. Fail-safe in direction, wrong in fact.

## Decision

**1. `genesis_gate.py` resolves its root the way the guards do.** It reads `workspace_roots` from
the payload, falling back to its own checkout, through `phos.guards.subject.workspace_root` — which
is renamed from `_root` and exported, because two shims now need it and duplicating it across
`.claude/` and `.cursor/` is what ADR 0414 moved the decisions into `src/` to prevent. The
environment variable is read nowhere in this repository.

**2. The parity harness no longer depends on it either.** `run_cursor_hook` passes
`workspace_roots` in the payload, which is also what Cursor sends, so the test now exercises the
path a real session takes rather than a path only the test could reach.

**3. Three tests pin it, in a class that says why it exists.** No script under `.cursor/hooks/`
contains `CURSOR_PROJECT_DIR`; the hook ignores the variable when something sets it to a decoy and
answers from `workspace_roots` instead; and with no workspace root at all it falls back to its own
checkout without crashing. The first is the one that would have caught ADR 0414's claim parting from
the code, and it is a grep rather than a behaviour because that is the shape the defect had.

**4. The window rule is a rule, not a README line.** `docs/rules/genesis.md` loads into every
session in both editors. A session that reads it knows the gate is only live when Cursor is opened
on the checkout being worked in.

**5. The five guards stay advisory in Cursor.** Unchanged from ADR 0414 §4 and ADR 0417. `ask`
remains available and unused for them, because turning five warnings into five questions is still a
change to how the project is worked rather than a repair.

## What is not claimed

That the gate has now been observed refusing inside a live Cursor session. The change is verified by
the test suite driving the real hook script as a subprocess with Cursor's documented payload, which
is the same standard ADR 0414 met and the same gap ADR 0417 named. The next Cursor session opened on
a worktree is what would close it, and this record does not assert that it has happened.

No corpus was opened. No frozen number moved. No measurement was run. `genesis state` still reads one
question and one judged experiment. P1 remains the blocked human conversation.
