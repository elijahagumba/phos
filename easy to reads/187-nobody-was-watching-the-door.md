# 187. Nobody was watching the door

*The public version of this project went thirteen days without an update, and nothing noticed. The
fix is not a reminder. It is a test that fails when too much is waiting.*

There are two copies of PHOS. The working one is private — it holds the experiments, the decision
records, the notes about who to talk to, the half-finished things. The public one holds a carefully
chosen subset: the records, the code, the plain-English notes like this one. A script copies one
into the other, and it only ever copies in that direction.

The script is careful. It refuses to run if it finds anything that should stay private, and it
refuses *before* writing a single file, so a mistake stops the whole thing rather than publishing
half of it. It never commits and never pushes, so a person always reads what is about to go out.

All of that is about **what** gets copied. None of it was about **when**.

## What happened

Between 2 and 15 November, nobody ran it. Not out of carelessness — there was simply nothing that
made it happen, and plenty of other work that did.

By the time somebody thought to ask, the public copy was missing twenty-four decision records and
fifteen notes. That included the research-record system, the roadmap that cut seven competing plans
down to one, the measurement that had been promised since October and finally taken, and an entire
new tool for generating test plants.

The part that stings most is smaller than any of those. There is a record that reserves a number
for a verdict before the verdict is written — a placeholder, so the gap is visible. The verdict was
written on 10 November. For ten days afterwards, anyone reading the public copy was told, in
writing, that the work was still unjudged. It wasn't. We just hadn't sent it.

## No rule was broken

This project has a rule that says a change is not finished until three public-facing files are
brought up to date with it. That rule has teeth: a test fails if the duty is ever deleted.

But the rule is about three files **inside** the repository. It says nothing about the copy that
strangers actually read. So nothing was violated. There was no rule to violate — which is a worse
problem than a rule being ignored, because an ignored rule at least leaves a trace.

## Three of these in one month

Written down because the pattern is the real finding.

A piece of plumbing was built, tested, and merged — and nobody wrote its verdict. It sat finished
and unjudged for a week. A measurement was promised in writing on 23 October, with the exact
command and the exact plant, and then not taken for seventeen days. And the export went thirteen.

Every one was found by a person happening to look. Not one had anything watching it. The project is
built around the idea that you shouldn't have to trust that somebody read something — and in all
three cases, the thing nobody checked was whether a step had happened at all.

## Why not just set a deadline

The obvious fix is "export at least weekly, and fail the build if it's been longer". That is worse
than it sounds.

A deadline fails on its own. One morning the build goes red and nothing changed — a clock moved.
Worse, it goes red on whoever happens to be working that day, about something they did not do. A
check that fires for a reason nobody caused is a check that gets loosened until it stops firing,
and then you have a dial set to "never complain" plus the comforting feeling of having a check.

So the bar counts **records waiting**, not days. That number only moves when somebody writes a
record. It goes red on the change that crossed the line, in front of the person who just wrote it,
who is the one person positioned to do something. And on a quiet week with nothing to publish, it
stays quiet, correctly.

The allowance is ten. Deliberately generous: the plant-generator programme was nine records, so a
whole programme can be finished before the guard says anything. The lapse it was built for was
forty-five by this count. A tight allowance would interrupt ordinary work, and the honest prediction
is that it would then get raised to make the noise stop — so the failure message says, in as many
words, that raising it requires writing a record arguing for the change.

## Two smaller things, both learned the hard way

The script now also **refuses to publish from a half-finished working tree**. If you have edits you
haven't committed, what gets published matches no saved version of anything, and the note recording
"the public copy holds version X" would be a lie. Editing private files is fine — it only objects
to unsaved changes in the files that would actually go out.

And there is deliberately **no check that the copying rules themselves haven't changed**. That
sounds like an obvious thing to check, and it is a trap: adding this very guard involved editing
those rules, in a way that changes nothing about what is published. A check like that would have
gone red immediately, with nothing actually owed — the same mistake as the deadline, in a different
costume.

## What this does not do

It cannot look at the public copy. This project's core is forbidden from reaching out over a
network, so the guard reads a note the script leaves behind saying what it last published, and
measures drift against that. Someone who hand-edits that note defeats the whole thing. It guards
against forgetting, not against lying — and forgetting is what happened.

Nothing was measured here. No data was opened, no detector built, no number moved. Four records are
waiting as this is written, which is the allowance working rather than a hole in it.
