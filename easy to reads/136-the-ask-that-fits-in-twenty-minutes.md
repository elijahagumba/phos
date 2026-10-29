# The ask that fits in twenty minutes

Twenty-one letters went out to people who might hold industrial data. Every one of them asked for
the same thing: please export weeks of your plant's history and send it to me.

That is a bigger request than it sounds. Someone has to find the right weeks, agree that a stranger
may have them, and usually ask a lawyer whether that is allowed. Lawyers take months. So the letters
were asking for something that could not be given quickly even by someone who wanted to give it.

The odd part is that PHOS never needed the files. Atlas runs on one machine with no connection to
anything — that has been a rule since the first week, because a security system that phones home is
a security problem. So the request could always have been the other way round:

> Run it yourself, on your own computer, on your own export. Send me nothing. Then tell me where it
> is wrong.

Nobody has to approve that. Nothing leaves the building.

## What they would be running

A plant's history is a very wide table. One column per measurement, thousands of rows a day, and
column names like `P1_FCV01D` that mean something precise to the people who work there and nothing
at all to anyone else.

Atlas needs to know what those names are. Not statistically — actually. Which ones are readings
taken from the plant, which ones are things that get commanded, which ones are targets somebody set.
Until it knows that, it cannot check a single law, because "two valves moved together" requires
knowing which columns are valves.

The old way to find that out was to ask an engineer to write the whole list down. For a plant with
three hundred tags that is an afternoon of dull work for a stranger's benefit.

So instead the command reads the export and writes the list as a first draft:

```
tag          role      kind    why
FIT101_PV    sensor    flow    FIT means flow indicating transmitter; and the numbers
                               never sit still, which is how a reading behaves
P101_CMD     setpoint          nothing in the name told us anything; but the value only
                               ever takes two values and holds each one, which is how a
                               target behaves, not a reading
```

Every line says where the guess came from. Where it has nothing to go on, it leaves the box empty
rather than inventing something. And the heading at the top says, in so many words, that this is a
draft to be corrected and not a decision.

Correcting it is about fifteen minutes. An engineer reads down the list, fixes what is wrong, fills
in the blanks, and almost certainly says "you have missed three and two of these are the same
instrument". **That corrected list is the thing PHOS actually needed.** Not the data. The names.

## What was wrong with it, and is now fixed

Three things, all of them about reach rather than about what the tool does.

It insisted on two files: the history export *and* a recording of the plant's network traffic. The
first is a report somebody runs. The second needs a switch reconfigured, a change request, and a
conversation with whoever owns the network. Requiring both meant the easy half had to wait for the
hard half. It no longer does.

It could only be started by typing `python -m phos.atlas.onboarding`, which is not a thing anyone
remembers. It is now `phos onboard`.

And the public front page mentioned it exactly once, in a list of things PHOS has *not* finished.
A reader learned there was an outstanding trial and never learned they could run the thing today.

## What this is not

It is not a detector and it does not look for an attack. It proposes names for columns.

It is also **not** the trial that this part of version 1 is waiting on. That trial is a real
measurement: somebody who has never seen PHOS takes an unfamiliar plant's export and reaches a
usable list inside an hour, timed. Making the command easy to reach does not make that trial done,
and the scorecard still reads eight of twelve.

And a correction an engineer types is still not a declaration. A role that Atlas trusts has to come
from the plant's own documentation. A guess from a name, however good, stays a guess with its
reasoning attached — which is the whole point of printing the reasoning.

*Records: ADR 0220, ADR 0341. See also [the front door shows the path](124-the-front-door-shows-the-path.md)
and [a named law stays on the list](123-a-named-law-stays-on-the-list.md).*
