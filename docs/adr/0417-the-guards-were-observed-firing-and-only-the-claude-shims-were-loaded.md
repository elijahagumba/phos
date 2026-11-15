# ADR 0417 — The guards were observed firing in Cursor, and only the Claude shims were loaded

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. The Cursor half of GENESIS, observed rather than assumed
- **Supersedes:** nothing. [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md) and [ADR 0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md) stand; this record answers the question both left open
- **Depends on:** [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md),
  [ADR 0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md),
  [ADR 0415](0415-the-record-store-survives-two-writers-and-its-own-damage.md), [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md)

## Context

ADR 0413 and ADR 0414 both ended with the same sentence: **not claimed, that any of this ran
inside a live Cursor session.** Both drove each editor's real hook script with that editor's
published payload shape and compared the answers, so the *contract* was verified and the
*integration* was not. `tests/guards/test_parity.py` calls the functions directly.

This session ran inside Cursor 3.27.22 on the `phos` workspace. The branch
`claude/engineering-research-process-e97e69` is checked out in a **linked worktree** under
`.claude/worktrees/`, not in the workspace root. It was therefore possible to watch what the editor
actually did, and to read its own hook log rather than infer the wiring.

## What was observed

**1. Cursor loaded no Cursor hooks, and said so.** Its hook service names the file it wants and
reports the parse failure on every start, with the workspace root elided here as `<workspace>`:

```
[2026-11-03T02:07:12.812Z] Project config path (phos): <workspace>/.cursor/hooks.json
[2026-11-03T02:07:12.818Z] ERROR: Failed to parse project hooks configuration
[2026-11-03T02:07:12.818Z] No project hooks configuration found
[2026-11-03T02:07:12.820Z] Loaded Claude project hooks
```

That path does not exist: `.cursor/hooks.json` is on this branch and **not** on `main`
(`git ls-tree HEAD .cursor/` on `main` lists `agents`, `commands`, `rules`, `skills`). Cursor reads
project hooks from the **workspace root**, which is the `main` checkout, not from the worktree the
agent is editing in. So `genesis_gate.py`, `phos_guards.py` and every `beforeShellExecution` and
`beforeReadFile` registration in `.cursor/hooks.json` were never live in this session.

**2. What did load was the Claude Code shims, on `preToolUse`.** `.claude/settings.json` at the
workspace root is on `main`, and Cursor reads it as "claude-project" configuration. Anchored
parsing of every `cursor.hooks.*.log` under `~/Library/Application Support/Cursor/logs/` gives:

| Step | Times fired, all windows |
| --- | --- |
| `preToolUse` | 14034 |
| `workspaceOpen` | 38 |
| `beforeShellExecution` | **0** |
| `beforeReadFile` | **0** |

A first pass grepping for those names counted hits inside the *payload text* of the commands being
run, which is why the numbers above are anchored to log lines and not to the file. The distinction
matters: an unanchored grep "found" 15 shell events that never happened.

**3. The five guards fired and warned; nothing blocked.** Every probe below is a real tool call made
inside this session, and each was answered by the script Cursor had loaded:

| Probe | Event | Guard | Verdict |
| --- | --- | --- | --- |
| `echo scripts/measure_baseline_table.py` | `preToolUse` | `declared_before_harness` + `red_tier` | warned, allowed |
| `echo hai-23.05` | `preToolUse` | `red_tier` | warned, allowed |
| `Read` of `data/hai-23.05/this-file-does-not-exist.csv` | `preToolUse` | `red_tier` (`tool: Read`) | warned, allowed |
| `echo x >> eval_runs/log.jsonl` (echoed, not run) | `preToolUse` | `frozen_log` | warned, allowed |
| `git commit -m test` (echoed, not run) | `preToolUse` | `public_record` | silent — nothing staged |
| ordinary shell command | `preToolUse` | none | silent |

The verbatim `red_tier` message, as Cursor logged the hook's own stdout:

```json
{
  "systemMessage": "PHOS guard: a tool call naming red-tier data\n  rule: docs/rules/data-tiers.md — never read, score or iterate on the validation corpora\n  `hai-23.05` is red tier\n  `hai` is red tier\n  ADR 0117's gate look 1 is spent (ADR 0143); a new look needs Elijah to authorise it\n  tool: Read\n  advisory: this call was not blocked. Read the rule before going further."
}
```

**4. Step (c) is answered: the guard warned and the read proceeded.** Cursor returned
`Hook 3 executed successfully and returned valid response` and did **not** block. The
`beforeReadFile` concern ADR 0414 raised — that an off-schema reply blocks the action — did not
arise, because the event that actually carried the read was `preToolUse`, whose schema accepts
`systemMessage`. The read then failed on its own merits: the file does not exist. The corpus was
not opened, which was the point of choosing a path that cannot resolve.

**5. Step (a) was not exercised live, and the reason is a safety finding.** The task's example
command is `uv run python scripts/measure_baseline_table.py --help`. That script has **no argument
parser** — `grep -c "argparse\|sys.argv"` returns 0 and `main()` runs unconditionally — so
`--help` is silently ignored and the full recompute executes. Its own docstring says it
"recomputes every published corpus … including hai-21.03, hai-22.04, hai-23.05 and batadal", all
four of which `docs/rules/data-tiers.md` names `never read`. The payloads are present in `data/`.
Running it to watch a gate refuse would have opened four red-tier corpora, which the same task's
hard stop forbids. **The command was not run.** `genesis_gate.py` was instead driven with the exact
payload Cursor sends, which is a contract test and not an integration observation, and it answered
`{"permission": "ask", ...}`. Stated plainly: **the gate was never observed refusing inside the
session, because the only registered copy was not loaded and the declared probe was unsafe.**

## Decision

**1. The finding is recorded as the finding, not fixed quietly.** No hook was added to `main`, no
`hooks.json` was copied to the workspace root, and no guard was made stricter. Wiring the Cursor
hooks live is a change to how the project is worked and belongs in its own record, in the same way
ADR 0414 §4 deferred `ask` for the five advisory guards.

**2. The mechanism is now known and is not a code defect.** `src/phos/guards/` and
`src/phos/genesis/gatehost.py` behave as ADR 0414 describes. What was missing was the file, in the
place the editor looks. A worktree checkout cannot supply it.

**3. `audit_evidence.py` no longer resolves the store's run-time artifacts.** Writing Q-0001 with
`genesis ask` created `docs/genesis/.lock`, which made ADR 0415's acknowledgement of that path go
stale and **failed `audit_evidence.py --strict`, the CI gate**. The mechanism: a citation whose
target exists is "resolved", so the acknowledgement covering it matched no failing citation and was
reported stale. The path is git-ignored and exists only on a machine that has run the tooling, so
the gate's verdict depended on whether work had happened — passing in CI, failing locally. Both the
lock and the atomic-write temporaries are now classified as run-time artifacts and retired before
resolution, and an acknowledgement naming one is not reported stale. The audit is verified
hermetic: identical output and exit 0 with the lock present and absent. No accepted ADR was edited
to achieve this.

**4. Q-0001 is opened against a gap the record leaves open.** `genesis state` reported zeroes
because the store had never held a research object. It now holds one, drawn from ADR 0313–0316 and
`docs/atlas-daily-leaps.md`: whether the walk column's miss is an artefact of thresholding a
per-sample score under a saturated calibration, or a property of the class that any per-sample
comparison would share. ADR 0315 retired the column without separating those two. No declaration
was made; declaring is a commitment to run and that is the human's call.

## Consequences

**Gained.** The integration question ADR 0413 and ADR 0414 both deferred now has an answer with
evidence: what fires, what does not, and why. A latent CI defect that would have failed the build
on any machine that used GENESIS is closed and tested (5 new tests, `tests/scripts/test_audit_evidence.py`).

**Cost.** Cursor is running only the Claude Code guards. The GENESIS gate is advisory on this
workspace (`declared_before_harness`) rather than refusing (`ask`/`deny`), so the one check that is
supposed to stop a run does not stop it here. `beforeReadFile` and `beforeShellExecution` never
fire, so a red-tier corpus named in a command or attached to a read is seen by `preToolUse` only.

**Not claimed.** That the GENESIS gate refused anything in a live session. That `beforeShellExecution`
or `beforeReadFile` work in Cursor at all. That a returned warning changed what the agent did: all
46 `systemMessage` replies were logged as `executed successfully and returned valid response`, so
Cursor accepted and surfaced them, but this record does not measure whether they altered a
decision — the only evidence available is that the advisory guards allow by construction and the
work continued. No corpus opened or scored, `eval_runs/log.jsonl` not appended (verified
byte-identical, `md5 d5e8826813043c5a94a7e76c88f4bcb8` before and after), no number produced, no
finding at any level, v1 unmoved, P1 still a blocked human conversation.
