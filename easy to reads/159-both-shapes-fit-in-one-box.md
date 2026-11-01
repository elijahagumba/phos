# 159. Both shapes fit in one box, and the two rules still disagree everywhere

*The guard type that step one's verdict asked for now exists, and the two rules were
compared on a wider set of mode numbers. All the questions that could be answered came
back yes. The answer is still a refusal, for a reason the questions could not see.
ADR 0382 declared the run, ADR 0383 judges it.*

Note 153 ended with one question answered no. The simulator says a valve is under
manual control when its mode is 1 or 2. The hand-copied rule says it is under automatic
control when the mode is exactly 3. Those two sentences part at mode 4, and at 3.3, the
number an operator's 3 becomes when the simulator's own middle-man attacker rewrites it.

So the next step was to build the one thing the verdict said was missing.

## The box that holds both shapes

The old guard could hold one shape: a list of mode numbers to exclude. That shape can
say "the check runs unless the mode is 1 or 2". It cannot say "the check runs when the
mode is exactly 3", because that is a different kind of sentence. So the first rule could
never be compared with the second through it, which is why the old verdict could not even
ask the question properly.

The new guard holds either an exclusion list or an equality, and it knows which one it
is holding. A guard that tries to hold both at once, or neither, is refused.

That matters because the comparison is now made by reading which shape each guard is,
not by running through a list of mode numbers and seeing which ones fire. The difference
is not pedantic. A test that tries values can only find disagreements on the values
somebody thought to try. A test that reads the shape gives the same answer whatever
values anyone offers. One of the tests walks every mode number in the set and confirms
that the exclusion never answers as though it were an equality.

## Seven questions, and the one about the wider set

The declaration wrote down seven questions before any code existed, then widened the set
of mode numbers to include the numbers that matter: 0, 1, 2, 3, 3.3, 4 and 100 on each
of the two mode tags. Seven numbers on one tag, seven on the other, five tank levels,
three bottle levels, three belt positions and both valves, which multiplies out to 8820
cases. All of them were checked. None were sampled.

The run happened once, by a different session from the one that built the guard, and the
three files it reads were confirmed unchanged by a single byte first.

Six of the seven questions came back yes, and the seventh was answered by the judging
session rather than the report, which is how the declaration set it up.

The four numbers are the same four numbers and each now quotes its source faithfully:
`0` and `1` from the control program, `3` from the tag table, `1.0` for the belt. One
line of the old report was reconstructed from the decimal rather than quoted from the
file, so it printed `3.0` where the file says `3`. That is now fixed.

The tank rule and the bottle rule are the same rules. The forced pushes are now a stated
fact: the simulator's manual check does not only decide whether the automatic rule runs,
it also shuts the valve at mode 1 and opens it at mode 2, and the derived rule now says
so instead of dropping that half. The certificates hold up. The tests, the type checker
and the linter are clean, and the hand-copied rule's file was not touched by a single
character.

## Refused, and why the yeses did not settle it

The answer is still a refusal, and the reason is worth stating carefully, because it is
not a missed question.

**4320 of the 8820 cases disagree.** Not on the valve value: wherever both rules speak,
they write the same sentence. They disagree on whether the rule applies at all. Every
one of those cases is listed, with its working, in a report of some four thousand lines.

One of the questions asked: list every disagreement, with a certificate. That question is
answered yes by an accurate list. An accurate list of a total disagreement is answered yes
by a complete disagreement. To their credit the builders did not take the easy road out:
the check fails if the list comes back empty, so quietly editing either rule until they
agreed would have failed the question rather than passed it.

The question about the guard's shape is similar. It asks whether the two shapes can be
told apart and compared. They can, now. It does not ask whether the two rules agree, and
it could not have come out any other way once the box existed.

So: all the questions that were asked came back yes, and the two rules still part on
every mode number outside 1, 2 and 3. The run measured the gap. It did not narrow it.

## The direction that matters

Worth saying in the plant's own words rather than as a count.

The derived rule follows the function the controller actually calls: check the valve
unless the mode is 1 or 2. So a mode of 3.3, which the middle-man attacker produces from
an operator's 3, gets checked.

The hand-copied rule follows the number the plant's own settings table calls normal:
check the valve only at exactly 3. So 3.3 gets silence.

On the one mode this plant can reach by accident, one rule looks and the other shrugs. A
valve left wrong at 3.3 is seen by one of them and not the other. That is the whole case
for replacing the hand copy with the machine's reading, and this run neither makes that
case nor settles it. It only writes down the difference precisely enough to argue about.

## One thing a reader of the record should know

The code that produced last month's report was rewritten in place to produce this one.
Seven of the eight modules changed. The old report is still the record of what that code
did, and it should not be re-run, because re-running it now would exercise different code
and could produce a different answer. A changed derivation gets a new declaration and a
new result name, which is exactly what this one had. That rule exists so nobody can move
the test after seeing the answer.

## What this does not show

Nothing was detected. No data was scored, no held-back data opened, no attack generated,
and there is no rate, no percentage and no coverage figure anywhere in this step. It is
agreement, or rather disagreement, between two readings of one Python control program.

It does not show that the machine's rule is better. It shows that it is different, and
names where. A machine wrong in exactly the way the program is wrong would pass every
question, which the declaration said before anything ran.

Real plant controllers are mostly not Python. Reading a Python file tells you nothing
about reading a ladder diagram or a vendor format, and a real controller may simply reject
a mode number it was not expecting, in which case this whole gap cannot arise on it.

Which rule PHOS keeps is still Elijah's call, still unwritten, and still needs its own
record before anything changes. The hand-copied rule is not on its way out yet. The machine
does not get to decide that because its questions came back yes.

Steps two, three and four are still shut until after the 6th of January. Version one
still stands at eight of twelve. The design-partner conversation is still the thing that
is blocked.

No decision record was written as 154 for this step, because that number was used by
another record on the main line between this programme being written and this step landing.
The record for this step is ADR 0383 and this note is 159.
