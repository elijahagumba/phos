# 39 — The phase that is allowed to fail

The last four things PHOS measured all came out as no.

A different statistical model of the plant's dynamics: **louder**, not quieter. An autopsy of
Sentiel's alert queue looking for a common cause: **there isn't one**. A mathematical trick to make
the correlation model behave: **it cannot be fitted on this data**. A search for any way to sort the
operator's alert list so the important ones float up: **no such ordering exists** in anything the
engine currently measures.

Four honest negatives in a row. The instinct is to try a fifth idea.

Read together, though, they say something else, and it took a while to hear it: **inventing more
algorithms is not what is stopping us.** Each of those four experiments made the machinery
different. None of them told us *why* the machinery fails, and none of them told us whether a
person holding PHOS's output makes better decisions than a person without it.

That second question has never been asked. This note is about the phase that asks it.

## The number nobody has ever looked at properly

Atlas produces about 53 false alerts per normal hour on the one real industrial dataset we have.
Concretely: 424 alerts over roughly eight hours — one shift — of which 6 land on an actual attack.

That number has always been treated as a quantity to *reduce*. Make it smaller. It has never once
been treated as a thing to *understand*.

Which is strange, because it is not one number. It is 424 separate events, each of which happened
for a reason, and those reasons are almost certainly very different from one another. Some are
probably the plant doing something ordinary that our model was too crude to expect. Some are
probably a sensor being noisy. Some are probably a shift change, or a filter slowly clogging, or a
gap in the data where the network dropped out.

And two of the possible reasons matter enormously more than the rest:

- **Our model is wrong.** The plant did something perfectly explicable and our maths could not
  represent it. If this dominates, the answer is a better model, and building one is worth doing.
- **The data could not have told us.** Nothing in the recording could have distinguished the
  innocent explanation from the guilty one. If this dominates, then **no amount of cleverness
  helps.** We would need a different kind of evidence — a maintenance record, a note of what the
  plant was making that day — and every hour spent on better mathematics is an hour wasted.

Those two conclusions point in exactly opposite directions. And right now, nobody working on this
project can tell you which one we are in. We have been walking without knowing which way is
forward.

So the first and most valuable job of the new phase is to take those 424 alerts apart and find out.

## Two places where the work has to stop and wait for a person

The first two jobs — taking apart Atlas's false alerts, and working out why Sentiel misses what it
misses — end in a **hard stop**.

An agent can do the investigation. An agent can write up what it found. An agent **cannot decide
what it means for the plan**. It has to hand the answer to Elijah and wait.

This is deliberate, and it is protecting against a specific and quite likely failure. Picture an
agent that has done genuinely good diagnostic work, understands the result, feels confident about
what follows, and simply carries on into building the next thing. That is how you end up having
answered "the problem is missing evidence" and then spending three weeks improving the maths
anyway. The answer would have been sitting right there in the report, and nobody would have acted
on it.

So the gate is not a formality to note in passing. It is a full stop.

## "This does not work" is written into the plan as a success

Here is the unusual part.

The plan says, explicitly and in advance, that any part of this phase is allowed to conclude that
the thing it was examining **does not work**, cannot be measured with the data available, or is not
worth continuing. And when that happens, it counts as a **success**.

That is not a nice sentiment. It is a structural defence against a specific and very common way for
projects like this to go bad, which the plan also names outright:

> "Atlas V47. 97.3% accuracy. Revolutionary."

— with no real-world evidence behind it, no honest account of what it cannot do, and not a single
experiment that ever changed anybody's mind.

The pressure to produce that sentence is highest exactly when a phase is ending and there is
nothing impressive to show. Writing the permission to fail *in advance*, before anyone knows how it
will go, is much easier than finding the courage at the end.

PHOS has form here. One earlier work session was completed **by refusing** — it went looking for a
public dataset containing the evidence we needed, established that no such dataset exists, wrote
that down carefully, and stopped. That record is one of the most useful documents in the whole
repository, because it tells anyone who comes along exactly which door is locked and why.

The excellent outcome for this phase is not a big number. It is five sentences:

1. Here is exactly what PHOS can demonstrate.
2. Here is what it cannot.
3. Here are the experiments that changed our minds.
4. Here are the bottlenecks that remain.
5. Here is the smallest real-world test that would tell us whether we are onto something.

## A list of what we cannot do, that gets longer

One of the deliverables is a **refusal register**: a permanent, growing record of what PHOS cannot
do and why.

It starts with six entries we have already earned. We cannot tell an attacker from a maintenance
engineer without the maintenance paperwork. We cannot check whether comparing a person to their
colleagues catches insiders, because no dataset contains a suitable case. We cannot claim what
works on one plant works on another. We cannot claim anything about real usefulness from a
simulation. We cannot usefully sort the operator's alert queue. There is no public dataset that
labels which commands an attacker sent.

Every entry has to say three things: what we cannot do, the evidence that we cannot, and — the
important one — **what would lift it**. Which means the register is not a list of excuses. It is a
shopping list. It is the precise specification of what PHOS needs from the world, which is exactly
what you want to be able to hand to someone who asks how they could help.

And note which direction it runs. As the phase proceeds, this list gets **longer**, not shorter.
A project honestly mapping its own boundary should accumulate known limits, not quietly shed them.

## The bit only a human can do

The last job is to write down the smallest real-world experiment that would actually tell us
something: what data, over what period, with what context, answering **one** question — bounded and
low-risk enough that a real plant could reasonably say yes.

This replaces "please share your data" with "here is a two-week question we could answer together",
which is a very different conversation.

But the roadmap is blunt about what happens next: **asking is something only Elijah can do.** No
agent can send that message, and no amount of computation substitutes for a person saying yes. It
is the dominant bottleneck for the whole phase, and pretending otherwise would be lying about where
the work actually is.

## What this phase will not produce

No new detection capability. By design.

If it goes well, PHOS will be able to describe its own limits far better than it can today, will
have a crude interface a human can actually read, will know why its false alerts happen, and will
have one precise question to ask a plant. It will not detect a single thing it does not detect
today.

That is the trade, made deliberately and written down.

## Related

[33](33-the-queue-is-sorted-the-wrong-way.md) is one of the four negatives that prompted this.
[34](34-a-work-order-is-the-alibi-nobody-ships.md) and
[38](38-the-writes-that-were-not-doing-anything.md) are the machinery the diagnostic environment
builds on. The plan is `docs/usefulness-phase-roadmap.md`, its live state is
`.phos_usefulness_state.json`, and the reasoning is ADR 0074.
