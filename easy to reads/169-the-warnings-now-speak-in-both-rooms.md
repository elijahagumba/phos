# 169. The warnings now speak in both rooms

*Five safety warnings existed in one of the two programs this project is built in. They are in both
now, from one copy, and the move found a trap that would have broken file reading. ADR 0414.*

Last week's note was about discovering that the other editor could do things I had claimed it
could not. This is the follow-through.

PHOS has six small guards. They watch what the AI is about to do and speak up before the expensive
mistakes: reading a dataset that must stay sealed, writing to the frozen results log, editing a
file outside your lane, committing an advance without updating the public pages, and running a
measurement that nothing has declared. Five of the six only ever ran in Claude Code. The sixth —
the research gate — was wired into both last week.

So: port the other five.

## The important part is that there is only one copy

The obvious way to do this is to write five more scripts for the second editor. That is the wrong
way, and the project has a rule against it: a thing written down twice is a thing that will
eventually disagree with itself.

So the *deciding* moved out of the editor scripts entirely. There is now one function per guard,
in the main codebase where the type checker and the tests can see it. What is left in each editor
is a fifty-line translator: read what this editor sends, ask the function, say the answer in the
way this editor expects.

The two editors describe the same event differently. One says "the tool is called Write and here is
its input"; the other, for a file read, says "here is the file path, and here are the extra files
attached to it". So there is one small translator per message shape, and every guard reads the
tidied-up version. The guards do not know which editor they are serving, which is the point.

## The trap

Reading the other editor's published reference, rather than assuming, turned up something that
would have been bad.

For the event that fires before a file is read, that editor accepts exactly two fields back:
whether to allow it, and a message for the human. And — this is the trap — **if your reply does not
match the expected shape, the action is blocked.**

My first version sent three fields. It included a message aimed at the AI as well as the human,
because the other two events accept that and it is useful. On the file-read event that third field
would have been unexpected, so every single file read would have been blocked, by a guard whose
entire job is to warn and then get out of the way. The project would have appeared to seize up, and
the cause would have been a helpful extra line in a reply.

It is now a short allow-list: the two events that accept that field get it, the one that does not,
does not. There is a test whose only job is to fail if that third field ever comes back.

## Two things that stayed deliberately uneven

**Only the gate blocks when it breaks.** The other editor can be told "if this guard crashes, stop
the command". That is exactly right for the research gate — a gate that waves work through on the
day it breaks is not a gate. It is exactly wrong for the five warnings: they are advisory, so a
crash in a guard that is only meant to say "careful" would halt work for no reason. So the gate
fails closed and the warnings fail open, and that asymmetry is written down rather than left to be
discovered.

**The five stay warnings in both editors.** The second editor could stop and *ask* instead, and
that is tempting — a question is harder to ignore than a warning that scrolls past. But turning
five warnings into five questions changes how it feels to work here, every day. That is a decision
about the project, not a porting job, so it was not smuggled in with one.

## Something I found and left alone

The sealed-data guard reads the rule file rather than having the dataset names typed into it, which
is why adding a dataset to the rule protects it immediately. It does that by taking every
code-formatted word inside a bullet as a name belonging to that bullet's tier.

The sealed-data bullet happens to mention a command-line flag, `--compare`, in passing. So the
guard reads `--compare` as the name of a sealed dataset, and any command containing that flag gets
warned about.

That is a false alarm, and it was there before this work; I copied the logic across unchanged.
I did **not** fix it, and that was a choice. This job was to move five guards without changing what
any of them decides, so that if something breaks afterwards there is exactly one explanation. Fixing
it means deciding what counts as a *name* in that rule — a real question, with a real chance of
accidentally un-protecting something — and it gets its own decision record. It is written down in
the meantime, which is the difference between a known limitation and a bug.

## What is now true

Six guards, both editors, one implementation each. Sixty-eight tests, where a fortnight ago there
were none at all — including tests that run each editor's real script, with each editor's real
message format, and check the two reach the same answer. Agreement between two things is a property
of the pair, so testing one of them proves nothing.

And the honest limit, same as last week: none of this has been run inside a live session of the
second editor. It was driven with the message shapes that editor publishes and it agrees with the
first on everything tested. The contract is verified. The integration is not.
