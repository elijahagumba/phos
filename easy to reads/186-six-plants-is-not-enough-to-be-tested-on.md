# 186. Six plants is not enough to be tested on

Imagine you are hiring someone to inspect water treatment works. You give them six to practise on.
They get very good at those six. They learn which pump in works number three always runs hot, and
the particular way the tank in works number five fills on a Monday.

Then you send them to the seventh.

That is the position our detector is in, and it is worth saying out loud before anybody else says
it for us.

## Where the six came from

Three of them we wrote by hand: a water treatment plant, a power generating set, a batch chemistry
plant. The other three are editions of a real industrial testbed that a research group published.

We have always varied these with a seed — a number you hand the simulator that decides all the
random parts. Change the seed and the sensor noise changes, the little drifts change, the schedule
of ordinary events changes.

**But the plant does not change.** Six tanks are six tanks on every seed. A controller's setting is
whatever somebody typed. The pipes connect the same way every time.

So when we say a result came from runs the detector had never seen, that is true and it is weaker
than it sounds. It had never seen *that noise*. It had seen that plant. Holding back a seed holds
back the weather, not the building.

## The obvious fix is the wrong one

You could just mangle the numbers. Scale a column, add noise, shuffle things.

Do that and you no longer have a plant. You have a tank whose level rises with nothing flowing into
it. There is no longer any physics for a detector to notice a departure from, so testing against it
measures nothing at all. It would look like more data and be less.

## What we built instead

We built something that draws plants.

Think of it as a **kind of plant** rather than a plant: pumped tanks feeding one another, with the
sizes left blank. How big the tanks are, how strong the pumps are, how twitchy the controllers are,
how many tanks there are in the chain, what the instruments can read, how badly they drift — all
left blank. Hand it a number and it fills every blank in and hands you one specific plant.

Two plants from the same kind are the same process built at different sizes and tuned differently,
which is exactly what two real water works of the same design are.

There are five kinds so far: pumped tank chains, heated vessel chains, islanded generating sets,
parallel batch reactors, and one that is both heated and pumped. **There is a sixth, and it is
sealed** — left out of the list, out of the catalogue, and out of the published table of ranges, so
that nothing we write while improving the detector can quietly point at it. Its code is still in the
repository. Sealing here is a discipline about what gets shown, not a secret.

## Four things we made it do, each of which cost us something

**It throws away plants that could not exist.** Draw the numbers independently and you get a pump
too weak to fill the tank it is bolted to, or a controller that oscillates forever, or a gauge that
cannot read the range the process lives in. So every drawn plant is **run first** and then checked
six ways, and one that fails is thrown away with the reason written down — never quietly nudged
into range, because a nudged plant is one the recipe said was impossible and we built anyway.

Writing that check found **five real mistakes in our own recipes** and **two places where the check
itself was doing nothing**. Fifty-two of a hundred and fifty drawn plants were refused.

**Things then happen to the plant, in four different places.** At the instruments, where a gauge can
lie. At the valves, where something can stick. **In the process itself** — a leak, which takes water
out by a route nothing measures, so the plant's own books stop balancing. And **on the wire between
the plant and the control room**, where a number can be changed in transit, so the control room's
record and the wire's record disagree. That disagreement is the single most useful piece of evidence
there is, and until now our simulator could not produce it.

**Two facts about every event are measured rather than claimed.** Did it actually move the process?
Did it stay inside the range that looks normal? We find out by running the same plant twice, once
with the event and once without, and comparing every signal. A simulator that *announced* an attack
was stealthy would be marking its own homework. An earlier version of ours did exactly that, by
looking only at the one gauge the attack touched — so it called a valve swung through its whole
travel "stealthy", because a valve's own reading is of course inside a valve's own range.

**It is reproducible, and we checked the harder half.** A kind of plant plus a number is the whole
recipe, so we do not store the data at all; you regenerate it. Hand the same number to two separate
runs of the program and every file comes out identical, byte for byte. But here is the half that is
easy to fake: a program that ignored the number entirely and returned the same plant every time
would pass that test perfectly. So the check also hands it a *different* number and insists the
plant that comes back is a genuinely different plant. Being repeatable without being varied makes it
a stored file wearing a generator's clothes.

A full day of a drawn plant takes under six seconds, so testing against hundreds is affordable.

## What this does not say, and it matters

**No detector has been scored on any of this.** Not one. The thing that would mark the detector's
answers against the known truth is not built yet. There is no catch rate, no false alarm rate and no
verdict for Atlas on a drawn plant, and nobody should read one into this note.

And more plants does not make them real. **A kind of plant generates models of a plant, and
unlimited draws are unlimited models.** Every file we write carries that sentence. A number measured
this way tells you how our detector handles our model of a plant. It never tells you how it would
handle yours.

## The other engine has it worse

Sentiel is the half of PHOS that watches corporate networks rather than pumps. There is one public
collection of insider-threat data worth the name, it contains two insiders, and Sentiel finds one of
them.

Every number Sentiel has comes from that one organisation. So the question lands harder: has it
learned what an insider looks like, or what *those two people* looked like?

The answer would be the same shape — draw a population of organisations rather than reuse one, and
vary the things that actually differ: how teams are shaped, how people's weeks run, who joins and
who leaves. **None of that exists and none of it has been written down as a plan.** Atlas is the
work right now. This paragraph is here so the problem is on the record before it surprises anybody.

## And one change to how we talk

The front page now opens with the thing that is true today rather than with a disclaimer. The plant
writes down its own laws; we check them and hand them back; nothing about the site leaves the site;
and where the plant's own records cannot settle what happened, we stop. That last one is the whole
product.

The limits sit in the same breath as the claim, not further down the page. **Atlas has never run on
a live plant.** We keep that sentence on the first screen on purpose, because a confident, grave,
beautifully set page is exactly what a company says right before it turns out not to have the
measurements. The only thing that tells the two kinds of page apart is whether the limit is printed
next to the claim.

The scoreboard still reads eight of twelve.
