# 81 — The machine that had never spoken

Atlas watches a plant's readings and notices when they stop making sense together. What it has
never done is look at the *instructions* — what the control system actually told the valves to
do. That information reached the part of PHOS that explains an alert, and stopped there.

This is the first time it reached the part that raises one.

## What was added

Two questions, both learned from ordinary days rather than written down as rules:

- Is this machine one that normally *asks* the plant for readings?
- Is this machine one that normally *tells* the plant to do something?

A machine that has never done either, suddenly doing it, is worth an alert. That is all. No list
of bad addresses, no signatures — just a memory of who spoke during the quiet days.

## The result

Tested on twenty simulated runs that had never been opened, with the rule for passing written
down and committed beforehand:

| | Before | After |
| --- | ---: | ---: |
| Attacks caught, in the eight alerts a shift allows | 49 of 120 | **87 of 120** |
| Ordinary events that wrongly drew an alert | 6 of 40 | 6 of 40 |

The clearest case is an attacker quietly mapping the plant — reading everything, touching
nothing. Before: **0 of 20**. After: **20 of 20**. That one is not a matter of tuning. An
attacker who only looks never moves the plant, so there is nothing in the readings to notice,
ever. The only way to see it is to notice who is doing the looking.

## Why this is smaller than it sounds

Both questions amount to "is this machine a stranger?" A capable attacker would not come as a
stranger. They would take over the operator's own workstation and give orders from there, and
both questions would answer "yes, that machine is familiar" and say nothing.

The attack that tests the real idea is in the corpus and is called a mimicked maintenance job:
someone issues a legitimate-looking instruction from the operator's own station. Catching that
needs the thing PHOS is actually for — comparing the instruction with how the plant physically
responded.

We could not test it. Measuring the plant during a real maintenance job and during the mimicked
one, they are **the same**: across thirty-nine ways of describing what the plant did, none
differs by more than noise. There is nothing to tell apart. The difference between the two is not
physical at all — it is that nobody authorised one of them. That is a question for the
maintenance records, not the sensors.

So the honest summary: a real improvement, on a real question, that is not the hard question. And
the simulated plant we built needs changing before it can ask the hard one.
