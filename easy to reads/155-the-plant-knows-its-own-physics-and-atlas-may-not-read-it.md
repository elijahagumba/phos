# 155. The plant knows its own physics, and Atlas may not read it

*Physics was meant to be the easy win. Two things got in the way. The plant never measures what
flows into the tank, so the textbook check is refused. And the one place this repository does write
down the plant's physics is a file the engine is forbidden to read — which turns out to be the right
answer, not a problem. Three laws are declared by hand instead. ADR 0423 opens the rung, ADR 0372 is
the declaration.*

The idea is simple to say. Atlas already checks a plant against what its controller program says.
Add a second, independent check: does the plant also obey physics? Water does not appear in a tank.
If the level rises while the only way in is shut, something is wrong — with the plant or with a
sensor — and either way it is worth saying out loud.

The plan named its own worked example: compare the change in level against the flow in and the flow
out. That is mass balance, the oldest sanity check in process engineering, and on a water plant it is
the whole game.

## The first problem: nothing measures what goes in

The simulator we use publishes thirteen signals, and each one was read out of the simulator's own
source code and written down with the line it came from. Of those thirteen, exactly one measures a
flow. It is the **outlet**.

The inlet exists in the data only as a valve that is open or shut. It never says how much.

The simulator does know — internally, the tank fills through that valve at a fixed rate. It simply
never publishes the number as a signal, so nothing checking the plant from outside can see it. Mass
balance needs both sides, and one side is invisible.

The rule for this rung was written before we knew that, and it says what to do: if the quantity is
not there, the law needing it is **refused rather than approximated**. We could have guessed the
inflow from the valve being open — pick a fill rate, call it good, and the law would run. It would
also be a number nobody measured, quietly holding up a conclusion. So it is refused, and written into
the register of things PHOS cannot do, as entry **R29**.

The useful part of that entry is its last column, which names what would lift it: **one flow meter on
the tank feed.** Not a research programme. One instrument, on one pipe. That is a sentence worth
being able to say to a plant.

## The second problem, which is actually the answer

Here is where the session changed shape.

This repository *does* write down the plant's real physics. There is a file listing twenty-one
cause-and-effect links read out of the simulator's physics code, including the one a mass-balance law
would need: the bottle fills from the outflow, but only while it is under the filler. The constants
are written down too, in an older decision record — the outlet pushes 0.0001 litres per millisecond
while its valve is open and the tank has water in it.

So the physics is right there. Except that file carries a warning in its own first paragraph: **this
is ground truth, and nothing that learns may read it.** It exists to *judge* the engine's claims, not
to feed them. There is a test that fails if any part of Atlas ever imports it.

That rule is correct and it should stay. An engine that reads the answer key cannot be said to have
worked anything out. But it has a consequence nobody had noticed: every physics law worth writing
relates two signals to each other, and in this repository *every* statement connecting two signals
lives in that forbidden file. The one file Atlas is allowed to read lists each signal's job and the
control rules, and deliberately states no physical connections at all — it even says roles were never
guessed from a signal's name, so Atlas may not assume "output flow" is the flow through "output
valve" just because the words match.

Which means the method that worked for the previous rung — derive the law from the source, then check
it against the version a human typed in — **cannot work here.** There is no permitted source to
derive from. That is register entry **R30**.

And the lift column for that one is the interesting part, because it is the product: **the plant
declares its own physics.** That was always the design. The law register's own description says it
holds "a law the plant or the operator already declared." A plant tells Atlas what must be true, and
Atlas checks the plant against it. Atlas does not reverse-engineer physics from network traffic — and
R30 says explicitly that lifting the entry must never let it start.

## What is declared, and why the numbers are safe

Three laws, all written by hand, each citing a document rather than importing one.

**A shut valve passes no water.** If the outlet valve is closed and the outlet flow meter reads
anything other than zero, one of those two readings is false. Nothing to argue about: zero is zero.

**With the only way in shut, the level does not rise.** Not "rises slowly", not "rises less than some
tolerance". Does not rise.

**While the tank is draining and nothing is coming in, it drains at exactly the quoted rate.** This is
the real mass balance, on the half of it that exists. It is the only law here with numbers in it, and
they are the simulator's own, quoted with the file and commit they came from — the same arrangement
the existing controller law already uses.

Two honest loose ends are written into the declaration rather than left for the build to discover.
Real sensors wobble; if the level reading jitters upward by a hair while the inlet is shut, the second
law breaks on noise rather than on anything real. The obvious fix is a tolerance — ignore changes
smaller than *x*. But where would *x* come from? If we pick it so the law stops complaining, we have
not measured anything, we have turned a knob until the answer felt comfortable. So the declaration
says: if noise breaks that law, the law is **refused**, not given a tolerance. Same for the third law
and the timing of the samples.

## What this is not

No data was opened, nothing was scored, and no code was written. The laws are declared and the
refusals are recorded; building and checking them is a later job, deliberately held back because
there is a funding deadline in January that needs the time more.

And a broken balance is still not an attack. The record already said so: a leak breaks a mass balance
exactly the way interference does, and it is read as equipment failing. Physics gives Atlas a second,
independent opinion about whether something is wrong. It gives it no opinion about who did it.

The rung set out to add physics and came back with three laws, two refusals, and a sharper idea of
what the product actually asks a plant for. That is a smaller result than the plan imagined, and it is
the true one.
