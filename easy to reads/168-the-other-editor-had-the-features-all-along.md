# 168. I said the other editor could not do this. It could, all along

*A sentence that justified a design turned out to be false, and the thing it was hiding was that
half the guard was missing. ADR 0413.*

PHOS gets built in two programs: Claude Code and Cursor. Both are editors with an AI in them, both
work on the same repository, and the project's rules are deliberately written so that each one
loads them.

When the research gate went in last week, the record explained its shape like this:

> One surface for both tools: everything is a plain command, because Cursor has neither skills nor
> hooks.

That sentence went into the decision record, the charter, the always-apply rule, the front page and
the encyclopedia. It is false.

## What was actually there

Cursor has skills. It ships twenty-six of its own, in a folder on this machine, including one whose
whole job is helping you write more of them. It has hooks. It has subagents and commands. And the
most embarrassing part: **this repository already contained a Cursor skill**, written months ago,
sitting in a folder called `.cursor/skills/`. The claim that Cursor cannot have skills was
contradicted by a file already in the project.

The instruction that came with the research mandate had said, in plain words, not to assume what
the other editor can do — go and look. I did not go and look. I asserted a limitation and built
around it.

## Why it mattered beyond being wrong

The design conclusion happened to survive. Putting all the real work in one plain command-line
program, with a thin wrapper for each editor, is the right shape — it is what the mandate asks for
anyway, for its own reasons. So nothing had to be torn up.

But the false sentence was covering something real. **The gate was only ever installed in one of
the two editors.** The record claimed both tools were covered. In fact, if you did your work in
Cursor, nothing stopped you re-running a measurement whose one look had already been spent, or
running one whose declaration you had quietly edited afterwards. The guarantee existed in one place
and was described as existing in two.

## The fix, and a better idea that came out of it

The deciding is now done by one function that both editors call. Ask it about a command and it
hands back *what* it decided and *why*, as data — allowed, nothing-declared, not-committed,
edited-after-the-fact, already-spent.

That matters because of how the first version worked. The first Cursor wrapper I wrote read the
other program's **error message** and looked for the words "already judged" to work out why it had
refused. It worked. It was also one reworded sentence away from silently letting a spent
measurement through. That is written into the record rather than quietly replaced, because it is the
exact species of mistake this whole system exists to catch.

Then Cursor turned out to be *better* at this than Claude Code, in two ways:

**It can fail closed.** If the gate itself crashes, Cursor blocks the command. Claude Code's hooks
do the opposite — if the guard breaks, the work sails through. A guard that fails open is not a
guard on the day it breaks.

**It can ask.** There was an awkward compromise in the original design: every measurement in this
project predates the new gate and was declared properly the old way, so refusing anything
undeclared would block correct work — but merely printing a warning means it scrolls past and
nobody sees it. Cursor has a third option: stop, and put the question to the human. That is neither
blocking good work nor waving it through, and it is now what happens there.

## Two honest limits

**The other five guards still only exist in one editor.** They warn before reading a protected
dataset, before writing to the frozen results log, before editing outside your lane, and before
advancing the project without updating the public pages. In Cursor, none of them speaks. They are
only warnings, so what is missing is advice rather than a lock — but one of them is the warning
that comes before touching a dataset that must never be read, and the gate does not yet check that
for itself. The Cursor skill now lists all five as things to check by hand.

**And the new wrapper has not been run inside Cursor.** It was tested against the message format
Cursor's own documentation describes, and it agrees with the other editor on all six situations.
That makes the contract verified and the integration unverified, and the record says so in those
words.

## The thing worth keeping

Before this, not one of the six guards in this project had a single test. Programs that only ever
run inside an editor, that nothing in the automated checks touches, that nobody would notice had
stopped working. There are tests now — for the two gate wrappers, driving each editor's real script
with each editor's real message format, and checking they reach the same answer. Parity between two
things is a property of the pair, so testing one of them proves nothing at all.
