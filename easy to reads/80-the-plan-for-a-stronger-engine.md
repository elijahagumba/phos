# 80 — The plan for a stronger engine

Version 1 is nearly finished and it meets 8 of its 12 goals. The detector it ships
is good: on the hardest dataset it catches 53 of 58 attacks inside the eight alerts
one person can read in a shift, where the published method we compare against
catches 10.

But "well evidenced" is not the same as "strong", and the goal for the public
release is an engine that is genuinely better than this one. So this note is the
plan, written before any of it is attempted.

## What we are changing, and why

The engine works by prediction. For each sensor it asks: given what every *other*
sensor is doing now and a minute ago, what should this reading be? When the real
reading drifts far from that prediction, something is wrong. That is a good idea and
it is most of why the engine works.

Three things about it leave room.

**It leans on one idea in one device.** Grouping alerts together accounts for about
a third of the catches. The prediction score supplies the rest — and a single
instrument supplies 11 of the 53 catches on one dataset. On a plant built
differently, that is where it would fall over.

**It never sees a command.** It compares sensors to other sensors. It never looks at
what the control system actually *told* the valve to do. So the one thing PHOS is
supposed to be for — the reading that doesn't match the order given, the sensor that
lies while the plant is wrecked — is a comparison this engine cannot make. That
information reaches the part that explains alerts, but never the part that raises
them.

**It judges each sensor alone, and only at its loudest.** Nudge ten sensors slightly
and nothing trips. Creep slowly and it only notices once you are already far off.

So: let it see commands. Judge all the sensors together. Add up small changes over
time instead of waiting for a spike. And let the prediction bend, because real
plants have valves that stick and batches that change stage, and a straight-line
model cannot represent either.

## The awkward part

We cannot practise on real data. The five datasets that judge version 1 have all
been looked at, and our own rules stop us tuning on something we have seen — that
rule is what makes the numbers worth anything. The one real dataset we may still
experiment with already gives 37 catches out of 38, so there is no room to show an
improvement on it. Every other public dataset we could find is either licensed in a
way we cannot use commercially, behind a paywall, missing its attack labels, or its
"attacks" never actually touch the plant.

So we build our own plant. There is an open industrial simulator we can run, which
writes out both the physical readings and the control traffic for the same plant —
the two halves no public dataset gives us together. Generating it is a few hours of
computer time. Half of it gets sealed and not looked at until we declare, in
writing, exactly what we are about to measure.

That is why making the data is step one and not a footnote: without it there is
nowhere to practise, and the most important change is one we could not even build.

## How anyone picks this up

Each step has an identification number reserved in advance. Whichever numbers exist
in the record are the steps that are done; the lowest missing one is where the next
person starts. There is no progress bar to forget to update, because the record *is*
the progress bar.

Two sessions on the same day both grabbed "the next free number" and collided,
twice. Reserving the numbers is the fix.

## What is not changing

The version-1 engine is frozen and never edited. Every attempt here gets its own
name and sits beside it. Version 1 stays at 8 of 12. And nothing from this plan may
be described as better on a real plant until the finished candidate is run, once,
against the datasets where the old numbers live — which is Elijah's decision to
authorise, not a session's.
