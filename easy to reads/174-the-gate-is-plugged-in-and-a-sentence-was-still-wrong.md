# 174. The gate is plugged in, and a sentence was still wrong

*The one check that refuses is now wired where the editor actually looks. Settling that turned up a
fourth sentence in the permanent record that the code did not match.*

Note 172 ended on an awkward fact. This repository has one safety check that **stops** work rather
than warning about it: before a measurement command runs, it asks whether any committed declaration
covers that run. In one of the two editors, that check had never been loaded. The file telling the
editor to run it sat on a branch, inside a working copy the editor was not looking at. The editor
reads its instructions from the folder you opened, and the folder that had been opened was the one
above.

The branch has since merged, so the file is now in the main copy and in every working copy made from
it. That fixes the half of the problem that a file can fix.

## The half a file cannot fix

The remaining half is where you point the window. The instruction file sits at the top of the
repository, so a window opened on the repository — or on any working copy of it — finds it. A window
opened on the folder *above* a working copy finds nothing, and the check is silently absent. Nothing
inside the repository can notice this, because the thing that would report it is the thing that was
never started.

So the fix is a sentence in the rules rather than a line of code: **open the editor on the copy you
are working in.** It is now in the file both editors load at the start of every session, which is the
only place a rule has a chance of being read.

## And then the fourth wrong sentence

While wiring it, the obvious thing to check was how the stopping check finds the record it consults.
A record from last month says, twice, and the long-form reference says it a third time, that this
check had stopped using an undocumented environment variable and now reads the folder from the
message the editor sends it.

That was true of the five *warning* checks. It was not true of the stopping check, which was still
reading the variable. The test that was supposed to cover this did not catch it, because the test
**set the variable** in order to point the check at a temporary folder. The harness depended on the
exact thing the record said had been removed.

With the variable unset — which is every real session, because the editor does not define it — the
check fell back to looking in its own folder. For a window opened on the copy being worked in, that
is the right answer. For a window opened on the folder above, it would consult the *other* copy's
record: a declaration properly committed on a branch would look undeclared, and the check would stop
and ask about a run that was entirely in order. Safe in direction, wrong in fact.

It now reads the folder from the message, the same way the warnings do, through one shared function
instead of two copies. Three tests hold it: no script contains the variable's name; setting the
variable to a decoy folder changes nothing; and with no folder named at all it falls back without
breaking. The first of those is a plain text search rather than a behaviour test, because that is the
shape the mistake had — a sentence and a line of code drifting apart, which no behaviour test was ever
going to notice.

## Four in one sitting

That is the fourth claim in the permanent record found false in a single stretch of work. The editor
has no skills or hooks — it had both. Five warnings run in only one editor — they had been moved to
both three commits earlier. The plain-English folder holds 126 notes — it held 161. And now: the
variable is no longer relied on — one of the two scripts still relied on it.

None of the four was invented. Each was written when it was either true or about to be, and then the
work moved and the sentence stayed. That is worth naming as a pattern rather than four separate
slips, because the lesson is not "be more careful when writing records". It is that a sentence
claiming something about code is worth a test, and the test can be as crude as searching for a word.

## What is still not shown

The stopping check has still never been watched refusing anything inside a live session of that
editor. Everything here is verified by running the real script as a program and feeding it the
message shape the editor documents — the same standard as before, and the same gap. The next session
opened on a working copy is what would close it.

Nothing was measured. No data was opened. The research record still holds one question and one judged
experiment, and the partner conversation is still the thing everything else waits on.
