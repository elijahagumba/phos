# 181. The same commit failed two different ways

*A checker gave opposite answers about the same file on two machines, and both answers were correct.
The thing it was checking had not changed in either place.*

PHOS has a gate that stops a record citing something that is not there. Write "see
`src/phos/atlas/thing.py`" in a decision record, delete the file, and the build goes red. It exists
because a record whose references have quietly rotted reads exactly like a record whose references
are sound, and the whole point of keeping records is that a stranger can check them.

It also has an escape hatch, which it needs. Sometimes a reference *should* dangle — a dataset that is
deliberately not committed, a file a measurement has not produced yet. So you can write a note beside
the citation saying why it does not resolve, and the gate accepts it. The note has to give a reason;
a one-word wave-through is refused.

## What went wrong

A record about reading an industrial protocol contains a careful little warning. While checking the
code, somebody searched the folder for a number and got a hit in a file that was not source code at
all — it was the compiled, machine-readable copy Python leaves behind after it runs. Harmless, but
worth flagging, so the record says: *watch out, searching this folder also matches a leftover build
file, and here is its name.*

Naming it was the right thing to do. Naming it is also what broke the gate.

On a clean machine that file does not exist, so the gate saw a citation pointing at nothing and
failed: **nobody has explained this**. The obvious fix is the escape hatch, so the note was added,
saying the file is compiled byte code and deliberately not kept.

Four minutes later the build failed again — for the **opposite** reason. On the build server the tests
run before the gate does, and running the tests creates exactly that compiled file. So by the time the
gate looked, the file was there, the citation resolved perfectly, and now the *note* was the problem:
it vouched for a reference that did not need vouching for. A note that explains a missing file is
itself wrong once the file is present, and the gate says so, because a note nobody maintains is worse
than no note.

Same commit. Same record. Two failures, pointing in opposite directions, neither of them a mistake by
the gate.

## The actual fault

The gate was asking a question whose answer depends on something irrelevant: **has anything run here
yet?**

That is not a property of the record. It is a property of the room you happen to be standing in. Any
check whose verdict moves with the weather is not checking what it thinks it is checking.

And this had happened before, in October, with a different file: a lock the research tooling creates
while it is writing. Absent on the build server, present on any machine that had done some work. The
fix then was to stop treating it as a citation at all — not to explain it, but to recognise that it is
not evidence and never was.

Compiled byte code is the same thing one folder over. So it gets the same answer: the gate no longer
reads those paths as citations. A record may name one, as this one does, and the gate is silent about
it whether it happens to be on disk or not.

## What was deliberately not done

The record was not edited. It would have been easy to reword the sentence until the checker stopped
complaining, and the sentence was *correct* — the warning is useful and the filename is right. A
record rewritten to suit a tool is a record you can no longer trust, and this project has had to say
that once already this month about a different mistake.

The escape hatch was not widened either, and there is a specific reason to be careful. There is
another file in the same situation by appearance only: a measurement report that a record says does
not exist yet, which has since been produced. It looks like the same shape of problem. It is not. That
one is **real evidence**, and a measurement that has not been taken is exactly the kind of gap this
gate exists to show. Sweeping it in with the byte code would have turned a useful alarm off to make a
nuisance one stop. It is left for its own decision.

## How we know it is fixed

By making the problem happen on purpose. The test that matters runs the gate with the file absent,
creates the file, runs the gate again, and insists both runs agree and that neither reports a stale
note. Without the change that test fails in both directions, which is how we know it is testing
something.

Nothing was measured here. No dataset was opened, no detector built, no number moved. The scoreboard
still reads eight of twelve.
