# ADR 0265 — The always-apply rules load themselves, from `docs/rules/` through a root `CLAUDE.md`

- **Status:** Accepted, amended the same day (see Amendment)
- **Date:** 2026-10-20
- **PART:** orchestration runtime
- **Numbered:** drafted as 0263 on `claude/elastic-perlman-79859c`; renumbered to 0265 when it
  reached `main`, which had meanwhile taken 0263 for the G1 regeneration. Nothing else changed.
- **Supersedes:** nothing
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md)

## Context

Six rule files carried `alwaysApply: true` and about 24 KB of constitution, lock, scorecard,
command-ranking and data-tier text. `phos-constitution.mdc` line 8 told the reader to paste the
document at the start of every session. Cursor applies those files itself; Claude Code does not read
`.cursor/rules/` at all, and `.gitignore` carried `/CLAUDE.md` with a comment recording that agent
guidance lives in `.cursor/rules` and `.claude/skills` with no root `CLAUDE.md`
(`encyclopedia/02-constitution-programme-lock.md` says the same).

The consequence was not a gap in the specification. It was that the specification never executed in
one of the two agents that does the work: every Claude Code session since the rules were written
began without the constitution, the frozen numbers, the data tiers or the forbidden list, and the
ten `.claude/skills/phos-*/SKILL.md` files restated parts of them from memory. Two of those restated
figures had already drifted (`phos-director` named a `current_session` that closed several sessions
earlier), which is the drift the lock exists to prevent.

A root `CLAUDE.md` whose body is `@` imports is the mechanism Claude Code has for this. Its import
reader accepts an allowlist of text extensions, and `.mdc` is not on it: an `@…mdc` import is
skipped, silently, as a non-text file. So importing `.cursor/rules/*.mdc` in place is not available.

## Decision

1. **The rule bodies stay at `.cursor/rules/<name>.mdc`, and `docs/rules/<name>.md` is a relative
   symlink to each.** There is exactly one copy of every rule, every `.cursor/rules/...` reference
   in the ADRs, briefs and encyclopedia still resolves to the real text, and the `.md` name exists
   only so Claude Code's import will accept the extension. The Cursor frontmatter (`description`,
   `alwaysApply`, `globs`) stays at the top of the body, where it is now also informative to a
   Claude Code session. The direction of the link is deliberate; see the Amendment.
2. **A committed `/CLAUDE.md` imports all seven** (the six always-apply files and
   `command-ranking.md`, which is glob-scoped in Cursor and cheap to carry). `/CLAUDE.md` is
   removed from `.gitignore`. It is configuration, not a runtime artefact.
3. **`CLAUDE.md` restates no rule, number or prohibition.** Its own body holds only what the rule
   files do not: the five-phase cycle by name and order (declare, run, judge, land, propagate), a
   pointer to the role skills, and a pointer to the guards. On conflict, the imported files and
   `.phos_roadmap_state.json` win over any summary anywhere.
4. **The constitution no longer asks to be pasted.** Its opening paragraph now says it loads itself.
5. **The ten role skills keep their role and method and defer for every figure.** Each one's
   frontmatter uses only the keys Claude Code dispatches on (`name`, `description`,
   `allowed-tools`); the non-spec `version`, `status` and `triggers` keys are gone and the dispatch
   intent moved into `description`, which is the only field dispatch reads. Restated frozen numbers
   are replaced by a pointer to the lock and the tracker. No frozen number was changed.

## Amendment — which file is the link (2026-10-20, same day)

This record first put the bodies under `docs/rules/` and made `.cursor/rules/*.mdc` the symlinks.
That is the wrong way round, and the reason is how each tool finds a rule.

- **Claude Code** resolves an `@` import as a literal path: it checks the extension of the path as
  written, then `stat`s and reads it. `stat` follows a symlink unconditionally, and no file walker
  or setting is involved. A symlink on this side cannot fail to load.
- **Cursor** finds its rules with a workspace file search over `**/.cursor/rules/**/*.mdc`. That
  search is governed by `search.followSymlinks`, which defaults to `true` but is a user setting. A
  symlink on that side loads today and would silently stop loading if that setting were ever turned
  off — and the failure mode is the one this whole record exists to remove: the rules not loading,
  with nothing saying so.

So the real files stay where Cursor expects them, and the link is on the side whose loader was
verified to follow links. Both were checked by reading the first lines through each path, and the
`.claude/hooks/` guards, which read their prohibition from `docs/rules/`, were re-run through the
link. Nothing about the single-copy decision changed; only which name is the file.

The same amendment adds the two Cursor entry points. Cursor does walk a workspace's
`.claude/commands/` directories, but only when its third-party-extensibility setting is on, and
that setting reads `?? false`. So `/phos-today` and `/phos-dispatch` would not appear in Cursor by
default. `.cursor/commands/phos-{today,dispatch}.md` are pointers, not copies: each names the
`.claude/commands/` file as the command, states the two differences that matter in Cursor (no
session-starting tool, so dispatch takes the branch that stops at the worktrees and the briefs),
and says plainly that the `.claude/hooks/` guards do not run there. The procedure, the roster and
the tier fence stay in one file. The guards remain Claude Code only; nothing warns a Cursor session,
and the pointers say so rather than implying cover that does not exist.

## Consequences

The rules now reach both agents from one copy. A skill can no longer carry a stale figure, because
it carries no figure. `docs/rules/*.md` are symlinks, so a Windows checkout or an archive extracted
without symlink support would see link stubs there — `.cursor/rules/` would still hold the real
text, so Cursor would be unaffected and only the Claude Code imports would need repointing. This
repository is worked on one macOS machine and in Linux CI, where both resolve.

`encyclopedia/02-constitution-programme-lock.md` still says there is no root `CLAUDE.md`, and the
public record (`encyclopedia/`, `easy to reads/`, `README.md`) has not moved for this change. Under
ADR 0044 that is owed before this lands on `main`, and it is not owed while the work is unmerged.
This record does not claim it is done.

## What would reverse this

Claude Code reading `.cursor/rules/` natively, or accepting `.mdc` as a text extension in `@`
imports. Either one makes the symlink and the `docs/rules/` location unnecessary, and the rule
bodies would move back with the imports pointed at them.
