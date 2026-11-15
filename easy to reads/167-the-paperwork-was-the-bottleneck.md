# 167. The paperwork was the bottleneck, so we taught the paperwork to check itself

*The research was not slow. Writing down the research was slow, and the reason was fixable.
ADR 0412.*

The founder said the way this project does engineering and research is slow and mundane. That is a
claim, so the first thing to do was measure it rather than agree with it.

In its first 98 days the project produced 320 decision records and 575 commits. Of the last 120 of
those commits, 64 were tagged as documentation and **59 changed no code at all** — no program, no
test, no measurement. The `docs/` folder holds more words than the `src/` folder holds code. And
one yes-or-no question — does the plant controller and its screen disagree when a sensor is
attacked? — cost about 2,200 words of hand-written record across two separate commits, to establish
one fact.

That is a lot of writing for one fact. The interesting part is *why*.

## The guards could only warn, so the rules had to be read

This project has a hard rule that keeps its results honest: **you write down what you are going to
measure, and what counts as success, and you commit that to history, before you run anything.**
Otherwise the bar can quietly move to wherever the answer landed, and the result means nothing.

There is a small program that is supposed to enforce that. It watches for a measurement about to
run and checks whether a declaration was committed first. Here is what it says about itself, in its
own comments:

> These records carry no machine-readable kind, so the guard cannot do better than their own words.

The declarations were English prose. To find out whether one existed, the guard had to pattern-match
the *title* of a document and guess. A guess has no business blocking anybody's work, so the guard
only warns and then gets out of the way.

Follow that through and the whole cost appears. Because the guard cannot say no, the rules have to
be carried in writing that a person is trusted to have read — about 5,700 words of them, loaded at
the start of every session. Because the writing is doing the enforcing, every record has to be long
and careful and hedged against every possible misreading. The ceremony was not anybody's
preference. It was the price of guards that could only clear their throat.

## So the record became something a machine can read

The change, called GENESIS, is one idea: **write the declaration as data first, and generate the
prose from it.**

A declaration is now a small structured file. It holds the question it serves, the claim being
tested, the reason the claim might be wrong, the observation that would disprove it, what it is
being compared against, which dataset and whether that dataset is allowed to be touched, the exact
command, and the bars — each bar a number the result either clears or does not.

None of those are optional. You cannot leave "why this might be wrong" blank; the record refuses
the file. You cannot declare a measurement on one of the sealed datasets; the record refuses that
too, by name.

And now the gate can actually refuse, because it is no longer guessing. It says no to three things:

- a measurement that nothing committed has declared;
- a declaration that was **edited after it was committed** — which is exactly how a bar sneaks
  across to meet a disappointing answer;
- a dataset whose one look has already been spent.

The verdict stopped being something anyone writes down. You supply the measured numbers, and the
system compares them with the bars you declared and tells you kept or refused. You cannot type in
the answer you wanted, and there is a check that reports any old record whose stated verdict
disagrees with its own numbers.

## The ladder, and why a claim cannot climb it by looking convincing

The founder's charter sets out six rungs, from "idea" up to "scientific contribution". Those used
to be adjectives. They are now a function that refuses.

To call something *reproduced* you need a measurement that was kept, named prior work it sits
against, and stated limitations. To call it *improved* you must put both numbers on the record —
the old one and the new one. To call it a *novel methodology* one citation is not a survey; you need
at least two. To call it a *novel finding* it has to hold on more than one dataset. And to call it a
*scientific contribution*, somebody must have genuinely tried to break it and failed, and there must
be instructions another person could follow to get the same result.

Ask to promote a claim and the system lists every one of those you have not got. It is a flat
refusal with a reading list, not an argument.

## What has not changed

Nothing was unlocked. The sealed datasets are still sealed. The frozen numbers are still frozen.
The project still does not build the parts of itself it has decided it is not ready to build, and
the one step that is waiting on a human conversation is still waiting on that human conversation.
The charter calls GENESIS "autonomous", and that word describes the *method* — it grants no
permission to touch a real plant, and the record says so in the charter's own text.

The same commands work in both tools the project is built with, which matters more than it sounds:
one of those tools cannot run the clever helpers, so anything important had to be a plain command
or half the work would go unguarded.

## What this does not claim

It does not claim the project is now fast. The numbers at the top of this note — 320 records in 98
days, 59 commits in 120 that moved no code, 2,200 words per yes-or-no answer — are written into the
charter as the **baseline**, not as a victory. Whether the new way is better is itself a question
with a bar, and it has not been measured yet.

Which is, more or less, the point.
