# ADR 0413 — Cursor has skills and hooks, so ADR 0412's reason was wrong and the gate is now wired into both

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. The Cursor half of the GENESIS adapter, and a correction
- **Supersedes:** nothing. [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md) stands and is not edited; this record corrects one claim in it
- **Depends on:** [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0265](0265-the-always-apply-rules-load-themselves.md)

## Context

ADR 0412 justified GENESIS's shape with this sentence, which appears in that record, in the
charter, in the always-apply rule, in the Claude Code skill, in `README.md`, in
`encyclopedia/13-scripts-tests-experimental.md` and in `PROGRESS.md`:

> One surface for both tools: everything is a plain command, because Cursor has neither skills nor
> hooks.

**It is false.** Measured on the installed environment, Cursor **3.27.22**:

| Capability | Cursor's location | Evidence |
|---|---|---|
| Skills | `.cursor/skills/<name>/SKILL.md` | `~/.cursor/skills-cursor/` ships 26, including `create-skill` |
| Hooks | `.cursor/hooks.json` + `.cursor/hooks/*` | `~/.cursor/skills-cursor/create-hook/SKILL.md` documents the schema |
| Subagents | `.cursor/agents/*.md` | this repository already had 23 |
| Commands | `.cursor/commands/*.md` | this repository already had 2 |

This repository already carried `.cursor/skills/phos-category/SKILL.md` — a Cursor skill that
ADR 0412 asserts cannot exist.

The architectural conclusion ADR 0412 drew — one engine behind thin adapters — happens to be
correct, and the GENESIS mandate of 3 November independently requires it. The *reason given* was
not. That mandate's §2 says: "Do not assume Cursor supports every Claude Code feature. Inspect the
actual capabilities and configuration conventions of the installed Cursor environment." The claim
was asserted without inspection, which is the inverse of the instruction, and the consequence was
material: the gate was wired into one editor and the parity ADR 0412 claimed was never tested.

Two further facts the audit turned up. Cursor's hook contract is **stronger** than Claude Code's in
two respects: `failClosed: true` blocks the command when the hook crashes, times out or returns
invalid JSON, where a Claude Code hook fails open; and `permission: "ask"` exists, so an undeclared
run can stop and ask a human rather than printing a warning that scrolls past. And no hook in this
repository had **any** test, in either editor, with CI running nothing editor-specific.

## Decision

**1. The decision moves out of the hooks.** `src/phos/genesis/gatehost.py` holds `decide`, which
returns a `GateDecision` — `allow`, `silent`, `uncommitted`, `tampered` or `spent`, with the reason
as data. `scripts/genesis.py gate`, the Claude Code hook and the Cursor hook are three ways of
asking the same function. The first Cursor prototype worked by matching English out of
`genesis gate`'s stderr; that is recorded here because it should not have been kept — a reworded
message would have silently started allowing a spent score.

**2. The Cursor adapter exists.** `.cursor/hooks.json` registers
`.cursor/hooks/genesis_gate.py` on `beforeShellExecution` with `failClosed: true` and no matcher,
because Cursor's own guidance prefers script-side filtering to a regex matcher until the matcher is
"simple and clearly correct". `.cursor/skills/genesis/SKILL.md` points at the Claude Code skill
rather than restating it, the pattern `.cursor/skills/phos-category/SKILL.md` already used.

**3. Cursor uses `ask` where Claude Code warns.** A harness run that nothing declares is
`permission: "ask"` in Cursor and an advisory warning in Claude Code. This is the one state where
the two editors differ, and the difference is Cursor expressing something Claude Code cannot. It is
recorded rather than hidden: `GateDecision.softenable` is true only for `silent`, so a spent score
and an edited declaration are flat refusals in both, and no host may soften them.

**4. The hooks are tested, which none was before.** `tests/genesis/test_gatehost.py` drives each
editor's real hook script with that editor's own documented payload and asserts the pair agrees:

| Store state | Cursor | Claude Code |
|---|---|---|
| nothing declares the command | `ask` | exit 0, advisory |
| declared, not committed | `deny` | exit 2 |
| declared and committed | `allow` | exit 0 |
| a bar edited after the commit | `deny` | exit 2 |
| the score already spent | `deny` | exit 2 |
| an ordinary command | `allow` | exit 0 |

Parity is a property of the pair, so a test of one proves nothing. The config itself is asserted
too: `failClosed` true, and the registered script present and executable.

**5. What is still Claude Code only, stated plainly.** Five guards have no Cursor counterpart:
`red_tier`, `frozen_log`, `file_scope`, `public_record` and `declared_before_harness`. They are
advisory there, so what is missing in Cursor is warnings rather than refusals — but `red_tier` is
the one that speaks before a protected corpus is read, and ADR 0412's own tier check is
self-asserted (the audit declared a run on `hai-21.03` by labelling it `iterate`, and GENESIS
accepted it). `.cursor/skills/genesis/SKILL.md` lists the five as checks to make by hand until they
are ported. Porting them is not in this record.

## Consequences

**Gained.** The gate is enforced in both editors, from one tested function. Parity is measured
rather than claimed. The reason as data instead of as stderr prose. `failClosed` means the Cursor
gate blocks when it breaks. And the migration conflict ADR 0412 left — advisory versus refuse —
has a third answer in Cursor that neither warns nor blocks correct pre-GENESIS work.

**Cost.** One state behaves differently in the two editors, by design and recorded. Five guards
remain Claude Code only, so Cursor is the weaker environment for everything except the GENESIS
gate. `.cursor/hooks/` and `.claude/hooks/` are outside `mypy`'s configured `files`, so the shims
are not type-checked; that is why the logic was moved into `src/`, where it is.

**Not claimed.** That the Cursor integration has been exercised inside a live Cursor session. The
hook was driven with the payload shape documented in Cursor's own `create-hook` skill and agrees
with Claude Code on every state, but the contract is verified and the integration is not. No
corpus was opened, no number produced, no finding at any level, `eval_runs/log.jsonl` not appended,
v1 unmoved, P1 still a blocked human conversation.
