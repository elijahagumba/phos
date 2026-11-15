# ADR 0414 — The five remaining guards become functions, and both editors run them

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. The rest of the guard surface, ported
- **Supersedes:** nothing. [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md) stands; this finishes what it names as unported
- **Depends on:** [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md),
  [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md), [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0413 wired the GENESIS gate into both editors and said plainly what it had not done: five
guards — `red_tier`, `frozen_log`, `file_scope`, `public_record`, `declared_before_harness` — were
Claude Code hooks with no Cursor counterpart. They are advisory, so what Cursor lacked was warnings
rather than refusals, but `red_tier` is the one that speaks before a protected corpus is read, and
GENESIS's own tier field is self-asserted.

Cursor's hook payloads were read from its published reference rather than guessed, which is the
discipline ADR 0413 exists to enforce:

| Event | Input | Output |
|---|---|---|
| `preToolUse` | `tool_name`, `tool_input`, `tool_use_id`, `cwd` | `permission`, `user_message`, `agent_message`, `updated_input` |
| `beforeShellExecution` | `command`, `cwd`, `sandbox` | `permission` (`allow`/`deny`/`ask`), `user_message`, `agent_message` |
| `beforeReadFile` | `file_path`, `content`, `attachments[]` | `permission` (`allow`/`deny`), `user_message` |
| every event | `workspace_roots`, `hook_event_name`, `conversation_id`, … | — |

Two facts from that reference changed the design. `beforeReadFile` accepts **only** `permission`
and `user_message`, and Cursor documents that a response which does not match the event's schema
**blocks the action** — so an `agent_message` on a file read would have turned an advisory guard
into a refusal of every read. And `workspace_roots` is sent on every event, which is a better root
than the `CURSOR_PROJECT_DIR` environment variable ADR 0413's hook reached for; that variable is
not in Cursor's reference and this record stops relying on it.

## Decision

**1. The five decisions move into `src/phos/guards/`, where they are typed and tested.**
`subject.py` holds `Subject` — a tool call normalised away from the editor that reported it — with
one builder per payload shape (`from_claude_code`, `from_cursor_tool`, `from_cursor_shell`,
`from_cursor_read`). `tiers.py` holds the tier parser and the red-tier check. `checks.py` holds
`frozen_log`, `file_scope`, `public_record` and `declared_before_harness`. Behaviour is lifted
unchanged; where a guard reached for git or the environment, the reach became an argument, which is
what made it testable.

**2. Both editors keep shims only.** The five `.claude/hooks/*.py` are ~50 lines each: read the
payload, call the function, map the verdict onto `warn()`. `.cursor/hooks/phos_guards.py` serves
all three Cursor events, choosing its normaliser from `hook_event_name`.

**3. `.cursor/hooks.json` registers them on three events** — `beforeShellExecution`, `preToolUse`
and `beforeReadFile` — so a red-tier corpus is caught whether it is read, written or named in a
command, and an attached file is scanned as well as the file being read.

**4. Two asymmetries, chosen and recorded.**

- *Only the gate fails closed.* `genesis_gate.py` keeps `failClosed: true`; `phos_guards.py` does
  not. Failing closed on an advisory guard would block work whenever the guard itself breaks, which
  is a worse failure than the warning going missing. The guard that refuses is the guard that must
  not fail open.
- *The five stay advisory in Cursor too.* Cursor's `ask` would be stronger, and using it would turn
  five warnings into five questions — a change to how the project is worked, not a port. It belongs
  in its own record.

**5. The hooks are tested, where before ADR 0413 none was.** `tests/guards/` adds **68** tests.
`test_parity.py` drives each editor's real script as a subprocess with that editor's own payload and
compares: a validation corpus reported by both; `hai-20.07` passing both silently; a Cursor
*attachment* scanned where Claude Code sees a path; a held-out seed in a shell command; a frozen-log
append; an out-of-scope edit; an advancing commit; an undeclared harness run. Running them as
subprocesses is deliberate — it exercises the `sys.path` handling, the package import and the
response encoding, none of which an in-process call would touch. Three tests assert the Cursor
response *schema*, including that `beforeReadFile` gets no `agent_message`.

## Consequences

**Gained.** Six guards in both editors from one tested implementation. The longest-match tier rule
— which is what makes `hai-20.07` read as development and `hai-23.05` as validation — is now
covered by a test rather than by a comment. Cursor sees red-tier *attachments*, which Claude Code
has no equivalent of. The root comes from `workspace_roots` rather than an undocumented variable.

**Cost.** `src/phos/guards/` is a second package outside the Constitution §5 list, on this record's
authority, holding method rather than detection. `.cursor/hooks/` and `.claude/hooks/` are linted by
ruff but are outside `mypy`'s configured `files`, so the shims are not type-checked; that is why the
logic sits in `src/`, and widening `mypy` is left alone here.

**A pre-existing false positive, disclosed rather than fixed.** The tier rule's red bullet quotes
`--compare` in prose, and the parser reads every backticked token in a bullet as a name of that
tier. So any command containing `--compare` reads as red tier. That behaviour is in the original
`red_tier.py` and is preserved here, because this record ports the guards without changing what
they decide. Fixing it means deciding what counts as a *name* in that rule, which is a change to a
guard's behaviour and needs its own record.

**Not claimed.** That any of this ran inside a live Cursor session. The shims were driven with the
payload shapes Cursor publishes and agree with Claude Code on every case tested, so the contract is
verified and the integration is not. The five remain advisory in both editors; nothing here refuses
that did not refuse before. No corpus was opened, no number produced, no finding at any level,
`eval_runs/log.jsonl` not appended, v1 unmoved, P1 still a blocked human conversation.
