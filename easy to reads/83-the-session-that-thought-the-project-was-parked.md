# 83. The session that thought the project was parked

*What happened when we checked, rather than assumed, what a session in a different tool knows when
it opens this repository. ADR 0287.*

## The check

The build is moving to Cursor for a while. Before that, one question: a fresh session there, with no
memory of any previous one, reads the project's own rules — what does it conclude?

The rules are seven short files. They cover the mission, the things that must never be claimed, which
data may be touched, and what has to be updated whenever work lands. They are set to load
automatically, and the good news is that most of that works: six of the seven reach Cursor on their
own, from one copy that both tools read. That part of the design holds.

Then the bad news. Every one of those files, and the project's live progress tracker, says the same
thing about what is currently being worked on: **session P1, blocked, waiting on a human
conversation.** None of them mentions the engine programme that has been running since 20 October —
four lanes of work, fourteen decision records, two of them written today.

Every one of those statements is true. P1 *is* blocked. The sentences were simply written before the
engine programme started, and nothing updated them.

So a fresh session reads its instructions, reads the tracker exactly as the instructions tell it to,
and concludes that the project is parked on a conversation it cannot have, and that starting
anything new is forbidden. The actual live work is invisible to it.

## Why Claude Code did not notice

Because it had a shortcut. A command called `/phos-today` computes where things stand by reading the
records directly, so the question never had to be answered from the rules alone. That command, the
role definitions, and six small guard scripts that warn before common mistakes are all specific to
one tool. In Cursor none of them exist. The shortcut was hiding the gap, and moving tools removed the
shortcut.

## The fix, and what it deliberately does not do

One more short rule file, loaded automatically like the others. It says three things: the other
rules' "what's next" paragraphs were written earlier and still name P1; here is the brief that
describes the live work; and here are four commands that work out how far it has got by reading the
record rather than trusting anyone's summary.

It **lifts nothing**. P1 is still blocked. Everything still forbidden is still forbidden. Every frozen
number is still frozen. It adds a signpost, and it says so in its own text.

It also lists what a non-Claude-Code tool is missing, so those things can be checked by hand: the six
guards, the role definitions, and one rule that — it turns out — Cursor was never loading anyway,
because it is marked differently from the other six while the Claude Code loader pulls it in
regardless. The two tools were not reading the same set of rules, and nobody knew.

## The part that is honest rather than fixed

The real problem is deeper and is not solved here. The project's "lock" file and its progress tracker
both describe a cycle that has ended, while the work actually happening is a programme running beside
it. Rewriting a lock is not something to do in passing, and the tracker is only ever written by one
script, on purpose.

So the new file makes the contradiction **legible** instead of letting a session resolve it wrongly.
It does not pretend the contradiction is gone. Reconciling the two is a decision for Elijah, taken
deliberately, not a tidy-up performed by whichever session noticed.

There is one cost worth naming. A file that loads in every session and points at "the current work"
has to be kept current, or in two months it becomes exactly the kind of stale paragraph it was
written to correct. That is a real maintenance debt, taken on knowingly, and the record says so.
