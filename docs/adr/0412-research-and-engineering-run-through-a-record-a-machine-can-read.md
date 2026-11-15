# ADR 0412 — Research and engineering run through a record a machine can read, and GENESIS is that record

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. How the five-phase cycle is operated, in Cursor and in Claude Code
- **Supersedes:** nothing. Every rule file stands unchanged
- **Depends on:** [ADR 0265](0265-the-always-apply-rules-load-themselves.md),
  [ADR 0292](0292-a-number-another-branch-already-used-is-refused.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

The founder's judgement was that the way research and engineering are done here is "slow and
mundane". Before changing it, the claim was measured, because it is a claim.

Over the 98 days from the first commit to 3 November 2026 the repository accumulated 320 decision
records and 575 commits. Of the last 120 commits, 64 carry the `docs:` prefix and **59 touch
nothing but prose** — no code, no test, no harness. `docs/` holds 402,420 words against `src/`'s
365,997: the project has written more English than Python. One yes-or-no measurement — ADR 0407
declaring the GRFICS agreement tell and ADR 0408 reporting it — cost 2,201 words across two
records and two commits, for one bit of information.

The cause is not discipline and it is not verbosity. It is stated outright in
`.claude/hooks/declared_before_harness.py`:

> "What counts as a declaration here is a heuristic, and is stated as one: an ADR added on this
> branch but not on `main` whose title reads as a declaration. These records carry no
> machine-readable kind, so the guard cannot do better than their own words."

Every guard in `.claude/hooks/` is a regex over English, so every guard ships advisory — it warns
and exits 0. Because the guards cannot refuse, the prohibitions have to be carried in prose that a
session is trusted to have read: 5,748 words of always-apply rules, of which
`docs/rules/live-work.md` alone is a stack of ten dated "Successor" paragraphs that must each be
read to discover which one is current. Because the prose carries the enforcement, each record is
written long and by hand, hedged against every misreading. The ceremony is downstream of the
guards' inability to say no.

The founder also supplied a charter for what the research should be: ambition, originality,
mathematical rigour, a discovery ladder, integrity absolutes, and an instruction to improve the
research process itself and measure the improvement. A charter is prose. Installed as prose it
would have added roughly 2,500 words to the always-apply budget and enforced nothing, which is the
problem it was written to solve.

## Decision

**The record gets a machine-readable kind, and the prose is rendered from it.** GENESIS is that
record, its gates, and the charter that says what it is for.

1. **The charter** is `docs/genesis-charter.md`, the founder's text with one added section — §0,
   what it does not lift — and a short "Machinery" paragraph under each section that now has one.
   It is a document, read when choosing what to work on.

2. **The always-apply rule** is `.cursor/rules/genesis.mdc`, symlinked to `docs/rules/genesis.md`
   and imported by `CLAUDE.md` (ADR 0265 is the mechanism, so both tools load it). It is 606 words,
   not 2,500: the commands, what refuses, the precedence, and the ladder. The frontiers and the
   research directions live in the charter, where they are read by choice rather than at every
   session start.

3. **The record** is `docs/genesis/`, one JSON file per question, experiment and finding, beside
   the prose in `docs/adr/`. The models are in `src/phos/genesis/` and are frozen: a measurement is
   added by writing a new record, never by mutating the one committed before the run. Three fields
   that the charter asks for in prose are now refused when blank — `why_it_might_be_wrong`
   (§II.5), `falsifier` (§II.6), and `failures` (§IV).

4. **The gate refuses.** `scripts/genesis.py gate` exits 3 for a command no committed declaration
   covers, for a declaration edited since it was committed, and for a score already spent. It can
   refuse where the older guards cannot, because it reads a kind rather than a title.

5. **The ladder is a function.** `genesis promote` is the only way a level moves, it moves only
   up, and it refuses with every unmet requirement named. Level 1 wants a kept experiment, prior
   work and limitations; 2 adds the improvement with both numbers; 3 a survey rather than one
   citation; 4 a second corpus; 5 a survived falsification attempt and a reproduction recipe.

6. **One surface for both tools.** Everything above is a plain command. `scripts/genesis.py` is
   the contract; `.claude/skills/genesis/SKILL.md` and `.claude/hooks/genesis_gate.py` are the
   Claude Code conveniences on top of it. Nothing GENESIS needs exists only as a skill, because
   Cursor has neither skills nor hooks and half the work happens there.

7. **The verdict is computed.** `genesis result` derives kept or refused from the measured values
   against the declared bars. It is not typed in and cannot be overruled. `genesis audit` reports a
   verdict that disagrees with its own numbers, a citation that resolves to nothing, and a
   measurement naming an absent report.

Two layout notes. `src/phos/genesis/` is a package the Constitution §5 list does not name; this
record is the authority for it, and it holds method rather than detection. `docs/genesis/` is under
`docs/` rather than at the root because it is the machine-readable half of the same scientific
record `docs/adr/` holds in prose.

### What this does not lift

GENESIS is a method, not an authorisation, and §0 of the charter says so in the charter's own text.
`docs/rules/phos-execution-master.md`, `docs/rules/data-tiers.md`,
`docs/rules/phos-constitution.md` and `.phos_roadmap_state.json` win over it. No Intelligence, no
API, no UI. P1 stays a blocked human conversation. Frozen numbers stay frozen and unpooled. A
`never`-tier corpus stays unread — the record refuses to declare one. ADR 0044 still applies on
`main`. The reserved block 0277–0284 stays unwritten. The ADR 0316 score is untouched. "Autonomous"
in the charter describes the research method and confers no permission on a plant, a control system
or a protected corpus.

The five-phase cycle is unchanged. What changes is that phase 1 is a record before it is prose,
phase 3 is computed, and the ADR for both is rendered with its judgement left blank for a human.

### The migration stance, stated as one

`.claude/hooks/genesis_gate.py` refuses the two answers that have no legitimate reading — a spent
score and a declaration edited after its commit — and stays **advisory** on the third, "nothing
declares this command". Every harness in the repository predates GENESIS and was declared properly
in an ADR; refusing on silence today would block correct work. `ADVISORY_WHEN_SILENT` is the one
constant that closes the loop, and flipping it is a later decision with its own record.

## Consequences

**Gained.** A declaration that cannot be edited after it is committed without the gate noticing. A
verdict that cannot disagree with its numbers. A level that cannot be claimed without the evidence
it names. A research state that is one command rather than a reading of 400,000 words. A report
that is a projection of the record and therefore cannot claim an experiment the store does not
hold. One command surface in both tools.

**Cost.** A second place where a record lives, until the renderer is the only way ADRs for
measurements get written. The always-apply budget grows by 606 words. `src/phos/genesis/` is a
package outside the Constitution's list, on this record's authority. The gate is only as good as
the `command` string in the declaration: a run invoked a different way passes unexamined, and
nothing here detects that.

**Not claimed.** This record does not claim the process is now fast. §VI of the charter states the
baseline — 320 records in 98 days, 59 of the last 120 commits moving no code, 2,201 words per
yes-or-no answer — and the measurement against it is a later result with its own declaration. No
number in this record is a detection claim, and GENESIS has produced no finding at any level.
