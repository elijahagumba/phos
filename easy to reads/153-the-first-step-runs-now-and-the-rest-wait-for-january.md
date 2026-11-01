# 153. The first step runs now, and the rest wait for January

*The four-step programme named last record is split. Step one starts today. Steps two to four wait until after 6 January 2027. Step one has since been built, run once and refused. ADRs 0369, 0370 and 0371.*

Note 152 described a programme in four steps: read the controller program and
write the rules automatically, add physics rules, predict what the rules will
miss, then search for the attacks that slip past all of them. That note ended
by saying none of it had started, and that it waited for the protocol work to
finish.

That wait has been shortened for the first step only, and lengthened for the
other three.

There is a water-industry funding competition, the Ofwat Catalyst stream, whose
entries close on the 5th or the 6th of January 2027 — the two official pages
disagree, so the record plans against the later date and Elijah works to the
earlier one. A bid has to be led by a licensed water company, which turns the
awkward request "please show me your plant" into "there is money here, you
lead, I bring the thing being funded." That is the single most time-sensitive
item in the whole repository, and it needs the one person who can also build
the engine.

So the engine work is cut to what is cheap and does not get in the way.

**Step one runs now.** It reads a Python control program from a fixed, frozen
copy of the simulator and writes the valve rule out of it automatically. It
touches no shared file. The protocol work is running in a different folder on a
different branch, and the two never meet. The test is whether the rule the
machine writes is the same rule a human copied out by hand last month: the same
four numbers, the same comparisons, the same answer on every case worth
checking. If it is not the same, the machine's rule is thrown away. The
hand-written one is not quietly adjusted to agree with it.

**Steps two, three and four wait** until after the 6th of January, or until a
later record opens them. Each of them needs a new set of data generated, a
prediction written down first, or a search run. That is exactly the time the
bid needs.

One thing in the new record is worth saying plainly, because it is the most
likely way step one fails. The simulator decides a valve is under manual
control when its mode is 1 or 2. The hand-copied rule says the valve is under
automatic control when its mode is exactly 3. Those two sentences agree on
every mode the simulator actually uses, and disagree at mode 4. A machine
reading the source honestly would write the first sentence. The hand copy wrote
the second. If that is what comes out, the step is refused and recorded as
refused — not patched over on either side.

Nothing was measured. No data was opened. No attack was generated. Version 1
still stands at eight of twelve, and the design-partner conversation is still
the thing that is blocked.

## One of these two records stays in the lab

Every decision record in this project is published, which is the point: the
argument is that the reasoning can be inspected. But the record that splits the
programme explains itself by naming a funding bid and saying it comes first.
That is commercial reasoning, and last month a record like it was published by
accident and then withdrawn.

So the same rule is applied here, before anything is served rather than after.
The splitting record is kept in the lab. It is not edited and it is not
deleted; its decisions still govern the work. The public list of records keeps
its number and says plainly that the record is held back and why, because a gap
in a numbered sequence is a question a reader is entitled to have answered.

The other record, the one that writes down the first step's test, has no
commercial reasoning in it at all. It is published as usual.

Worth noting honestly: the automatic check that is supposed to catch this kind
of record did not catch it. It looks for sums of money written in dollars, and
this one is in pounds. The record was caught by a person reading it.

## The check now speaks the local currency

That gap has since been closed, as its own decision. The check carries a
pounds pattern and a euros pattern beside the dollars one.

The way it was done matters more than the patterns. Each was run against the
whole of what the project currently publishes — every one of the 1213 files,
written out and read, not a sample — before it was added, and neither matched
anything there. Then the exporter's own checker was pointed at the record that
had slipped through, with the by-hand block taken away, to prove the new
pattern stops it on its own rather than sitting there looking reassuring.

What it still does not catch is written down rather than glossed: a sum
smaller than a million, a sum with no currency sign in front of it, and
commercial reasoning that mentions no money at all. Catching smaller sums was
considered and refused for now, because a measurement project is full of
ordinary six-figure numbers, and a check that stops the publication every week
is a check somebody eventually loosens.

The first line of defence is still a person deciding where a record belongs
before writing it. The check is there for the day that person is tired.

## The first step is built, and not yet marked

The machine that reads the controller program now exists. It opens three files
of a frozen copy of the simulator, checks each one against a fingerprint written
down beforehand, and refuses to go on if any of them has changed by a byte. Then
it reads them the way a person reads a page — it never runs them. A program that
is read cannot do anything to you.

Out of that reading it writes the valve rule: when the tank is too full, close;
when it is too empty, open; in between, say nothing. Every number in that rule
carries the file and the line it was read from, so a reader can go and look.

When the rule and the plant disagree, the break comes with its working. Not a
number, a working: the rule, the handful of readings the decision actually used,
the controller's own comparison that fired, and the equality that came out
false. Someone holding those readings can check it with a pencil and never touch
PHOS. There is nowhere in that certificate to put a score, and the shape of it
means it can never be mistaken for one of the eight things on an operator's
page.

**It has now been marked, by a different session, and the answer is no.**
That is the whole point of the arrangement: a builder who grades their own work
grades it kindly, so the person who wrote the machine was not the person who got
to say whether it passed. A different session checked the frozen copy had not
moved by a byte, confirmed the test had never been run, ran it once, and wrote
the verdict.

## Six questions out of seven

Seven questions were written down in advance, each a yes or a no with no middle.
Six came back yes.

The four numbers are the same four numbers, and each one now says where it came
from: close is a `0` on line 18 of the control program, open is a `1` on line
20, the belt distance is the `1.0` on line 26, and the mode is the `3` sitting in
the tag table on line 49 of a different file. Someone checked all four by opening
the files and looking. The tank rule is the same rule, in the same order, with
the same strictness: too full closes, too empty opens, anywhere in between
including exactly at either end says nothing at all. The bottle rule is the same
rule, and exactly at the limit it opens rather than closes. On all 1620 cases
worth checking, the machine's rule and the hand-copied rule gave the same answer
every single time. The break certificates hold up. The tests, the type checker
and the linter are all clean, and the hand-copied rule was not touched by a
single character.

## The one question that came back no

It is the one the last section of this note said was most likely, which is
some comfort and no excuse.

The machine says: this rule applies unless the valve's mode is 1 or 2. The hand
copy says: this rule applies when the valve's mode is exactly 3. Those are
different sentences. They happen to give the same answer at modes 1, 2 and 3,
and a different answer at mode 4 — the machine would check the valve, the hand
copy would shrug. The simulator's own code is where the machine got its sentence,
and it is on line 404 of a file called `Device.py`, and anyone can go and read
it.

Because one of the seven came back no, the whole step is **refused**. There is no
partial credit written into the test, deliberately, because partial credit is
how six honest answers and one awkward one become "mostly passed".

Nothing was adjusted to make it pass. The number 3 does not appear anywhere in
the part of the machine that reads the program — it is looked up in the tag
table, not typed in. The hand-copied rule was not widened to match the machine.
Both sentences are faithful to something: one to the mode the plant's own table
says is normal, the other to the function the controller actually calls. Neither
is a mistake. They are two readings of the same machine, and the gap between
them is a real gap.

## Three things worth saying plainly

**The 1620 cases are not as impressive as they sound.** In 1440 of them, both
rules say nothing — the mode is 1 or 2, so the machine calls it manual and the
hand copy calls it not-3, and silence agrees with silence. Only 180 cases have
both valves in normal mode, which is where either rule speaks at all, and 126 of
those produced a break where the two wrote the identical sentence. That is still
a real check. It is just not 1620 of anything, and mode 4 — the one place they
are known to differ — is not in the list at all. The test that caught the
difference was the one that read the shape of the rule rather than trying values,
which is why it was written that way.

**One line of the report is sloppier than the rest.** There is a column headed
"as the source writes it", and for two of the four numbers it is reconstructed
rather than quoted, so it prints `3.0` where the file actually says `3`. The
number, the file and the line are all correct, so it does not change the answer.
But in a step whose entire subject is whether a copy is faithful, a column that
claims to quote and does not is worth fixing.

**The machine reads half of one thing.** The simulator's manual check does two
jobs: it decides whether the automatic rule runs, and when the mode is 1 or 2 it
also pushes the valve shut or open itself. The machine reads the first job and
drops the second, so its rule is silent in a place where the real controller is
perfectly decisive. Nothing in the test asked for it, so nothing failed. It is
simply a piece of the controller that the derived rule does not yet carry, and a
later step that wants the machine's rule to stand on its own will have to.

## What this is not

It is agreement with one person's copy of one comparison in one Python program.
A machine that was wrong in exactly the same way the person was wrong would have
sailed through all seven questions — the record said so before anything ran, and
this result does not change it. Nothing was detected. No data was scored, no
held-back data opened, no attack generated, and there is no percentage, no rate
and no accuracy figure anywhere in this step, because there is nothing here that
could honestly produce one. Real plant controllers are mostly not Python; they
are ladder diagrams and vendor formats, and reading a Python file tells you
nothing about reading those. The derived rule is not on the operator's page and
does not go there without its own written-down test first.

Steps two, three and four are still shut until after the 6th of January. Version
one still stands at eight of twelve. The design-partner conversation is still the
thing that is blocked.

## One more question, asked afterwards

The disagreement above sounds like a quibble. The machine's rule says "run the
check unless somebody has put this valve in hand mode", and hand mode means the
number 1 or the number 2. The person's copy says "run the check when the number
is exactly 3". Those are the same thing as long as the number is only ever 1, 2
or 3. So somebody asked the obvious follow-up: in this simulator, can that
number ever be something else?

It can.

Only two things in the whole simulator ever write it. When the controller starts
up it writes the number from its own settings table, which says 3. And when a
person sits at the operator console and chooses from the menu, the console sends
what they picked. The console asks "Command (1 to 3):" and throws the input away
if it is outside that range. That check is real, and it is the **only** one. It
lives in a text prompt in front of a human. Nothing underneath it checks
anything.

Underneath it, the number travels as two sixteen-bit words with four decimal
places bolted on, which can carry anything from zero to about four hundred and
thirty thousand, in steps of a ten-thousandth. There is no list of allowed
values, no whole-number check, no per-signal rule. It always comes back out as a
decimal, never a whole number. And the function that reads it asks two questions
— "is it 1?", "is it 2?" — and if the answer to both is no it just carries on. It
has no case for a number it was not expecting, and it writes nothing to a log
when it sees one.

Then there is the part that makes this concrete rather than theoretical. The
simulator ships with its own attacker, and one of its attacks sits in the middle
of the network and quietly multiplies every number it sees in passing by 1.1.
It does not look at which signal it is changing — it reads the address only to
write it into its own log file, and never compares it to anything. The attack
runs fourteen times in the scenario the project ships. So an operator presses 3
for "back to automatic", and the controller receives 3.3.

3.3 is not 1 and it is not 2, so the machine's rule runs the check. 3.3 is not
3, so the person's copy stays silent. The two rules part company on a number
this plant can genuinely end up holding, delivered by a tool sitting in the same
folder.

PHOS's own corpus generator, for what it is worth, only ever writes 1, 2 or 3 —
in four places, all checked. So nothing we have generated contains one of these.
That is a fact about the generator, read from the generator. Nobody opened a
recording to see whether such a number ever actually turned up in one, because
that is a different question and it was not asked.

**What this does not do is pick a winner.** It is tempting to read it as "the
machine was right all along", and that is not what it says. The person's copy is
faithful to the number the plant's own settings table calls normal. The machine's
rule is faithful to the function the controller actually calls. A plant's
engineers might sign either one, and some would rather a rule go quiet when a
signal looks wrong than carry on checking against it. Which rule PHOS keeps is
Elijah's call, it gets written down before anything changes, and nothing was
edited here. Nothing was detected, nothing was scored, and there is no number in
any of this that is a rate or an accuracy. The first step is still refused.
