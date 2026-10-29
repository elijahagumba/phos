# 84. The model that understood too much

*Lane 4 of the stronger-engine programme: what happened when the engine's prediction was allowed to
bend. ADR 0288, with the numbers in `eval_runs/build/lane-e/lane4-development.md`. A plant PHOS
generated, so diagnosis and not proof.*

## What the engine does, and the suspected flaw

Atlas watches each instrument and asks, every second: *does this reading match what the rest of the
plant implies?* The implication comes from a straight-line model — add up the other readings, each
with a weight learned from quiet days, and that is what this one should be.

Real plants are not straight lines. A valve saturates: past a point, opening it further changes
nothing. A controller has a deadband: inside it, nothing responds at all. A plant changes phase, and
the relationships change with it. A straight line cannot follow any of that, so during perfectly
ordinary operation it is wrong in a patterned way — and being wrong looks, to this engine, like
something to raise an alert about.

So the plan for lane 4 was: let the line bend. Keep the question identical, answer it better. Two
benefits were expected. Fewer false alarms, because the model would stop being surprised by ordinary
non-linear behaviour. And more catches, because an attacker hiding in a region the straight line
could never represent would stop being invisible.

## What was built

The bend is deliberately the smallest one that works. Each input gets a few extra terms of the form
"how far above this level is the reading?" — zero below the level, rising above it. Add those up with
learned weights and you can build a curve that flattens (saturation), a stretch that is flat
(deadband), or a kink where the slope changes (phase change). It is still the same kind of model,
solved the same way; it just has more shapes available.

One detail matters for trusting the result. **With the extra terms switched off, this is exactly the
old engine** — not approximately, identically, and a test checks the scores match to the last digit.
So when the two are compared, the bend is genuinely the only thing that differs. Nothing else moved.

## What happened

The first expectation came true, clearly.

| | Old engine | With the bend |
|---|---|---|
| False alarms per day, on quiet days it had never seen | 28 | **20 to 24** |
| Ordinary maintenance wrongly alerting | 5 times in 20 | **1 time in 20** |

Fewer false alarms, measured honestly — holding back a quiet day, training on the rest, and checking
the day it had not seen. That is a real improvement to a real problem.

The second expectation came out backwards.

| | Old engine | With the bend |
|---|---|---|
| **Attacks caught** | **32 of 70** | **23 to 25 of 70** |
| The frozen sensor | 1 of 10 | **0 of 10** |
| A replayed trace | 5 of 10 | 1 of 10 |

It catches *less*. Not a little less at one setting — less at every amount of bend tried, from one
extra term to five. Bending at all costs about eight attacks.

## Why, and this is the part worth keeping

The engine's alarm is, at bottom, **surprise**. It predicts a reading and measures how wrong it was.

A crude model is surprised easily. That is its flaw during ordinary operation, and it is also, it
turns out, where some of its detection came from. A clever model explains more of what it sees — and
an attack is part of what it sees. A sensor held at a constant value, a replayed trace, a reading
drifting gently inside the range the plant normally covers: a model flexible enough to follow the
plant's real curves is also flexible enough to find these unremarkable. It fits them, so it is not
surprised, so it does not alarm.

So the straight line was not purely a defect to be removed. **Its crudeness was doing work.** Taking
that away bought quiet and paid for it in blindness, and on this plant, against this standard, the
price was higher than the gain.

## Why it was still turned down

Lane 4's standard had two halves: catch strictly more attacks, **and** raise no more false alarms. It
had to pass both. It passed the second comfortably and failed the first, so it is not adopted and no
result was taken on held-back data.

There is something slightly uncomfortable in that, and it should be said rather than hidden. Lane 4
is a genuine improvement on a dimension the programme only ever wrote down as a *limit* — "do not
make this worse" — never as something to win. A quarter fewer false alarms a day has nowhere to be
recorded as a success. Whether a real plant would take that trade, eight fewer catches for twenty-odd
fewer false alarms a day, is a question for an operator with a budget, not for whoever is writing the
code that week.

## Where that leaves the programme

Four lanes were planned to make the engine significantly stronger. One worked: letting the engine see
who sent which command, which catches an intruder that no amount of watching the physics could see —
though it is defeated by an attacker using the operator's own console. One cannot be tested at all
without inventing a far cleverer attacker. One caught twenty-one more attacks and was refused for
noticing a few seconds later. And this one is quieter and blinder.

That is an honest position and not a comfortable one, and it needs facing before the programme spends
its one remaining chance to measure itself against the old engine's published numbers. A gain in
sensitivity is still unproven; what has been established, twice over now, is the shape of the
trade-offs around it.
