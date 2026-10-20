# Bet 003 — The first shift

**Status: open.** These bars were fixed on 20 October 2026, before anything was measured against
them. This page's commit date in this repository is the public record of that. If a bar fails, it
is published as failed. A bar changed after a result it judges becomes a new bar with a new name,
shown beside this one.

## The question

An industrial plant's control room runs in eight-hour shifts, and the person on duty can read
about eight alerts in one. So: when an attack begins, does the shift it began in contain it, and
can the person on duty act on what they are handed?

## What we found when we looked at our own failure

Version 1 has a criterion, A3, asking that half of all attacks have a real alert in the top tenth
of their shift's queue. It failed: 57 of 203. Two attempts were made to fix it, and both were
reported as failures.

Reading the result file again showed why, and it was not the detector. Atlas's shift queues are
short. The median shift containing an attack carries **seven** alerts, and two thirds of them
carry eight or fewer, which is the whole of what an operator can read. The top tenth of a
seven-alert queue is one slot, so for 81% of the attacks the criterion was asking the attack to be
the single loudest alert of its shift, not to be inside the operator's reading.

Measured the other way, in alerts rather than percentages: of 203 attacks, **172 produce a real
alert in the shift they began in, and every one of those appears within the first nine alerts of
that shift.** The median is the third alert. The ordering was never the problem.

A fraction of a queue the detector itself sizes is also the wrong kind of bar, because a noisier
detector gets more top slots for free. So we are retiring it as an instrument and writing the bar
in the units an operator actually feels.

The old number stands. Version 1's A3 is not met, it is not rescored, and nothing here is compared
to it or counted as a pass for it.

## The bars

| | What is measured | Where it stands | The bar |
| --- | --- | ---: | --- |
| Coverage | Attacks with a real alert in the shift they began in | 172 of 203 | at least **187 of 203** |
| Position | Where that alert sits in the shift | median 3rd, worst 9th | **no attack beyond the 8th alert**, on any dataset |
| Story | What the operator is handed | not built | **one entry per attack**, carrying the explanations still standing and the one fact that would settle it, every sentence citing stored evidence |
| Load | How long the shift's list is | median 7 | the median **does not get longer**, on any dataset |

Coverage and load are judged together, and that is the whole point. Catching more attacks by
raising the alert count fails. A short list bought by missing attacks fails.

## What we are betting on

The thirty-one attacks that produce nothing in their first shift cannot be reached by reordering
anything. They need evidence Atlas already gathers but its queue has never been able to see:
whether an event persists across windows, whether it coincides with one in another part of the
plant, and whether a maintenance work order covers it. The third of those was built for a
different criterion this month and closes 158 of 180 maintenance alerts with a citation while
closing none of 80 attacks.

## What would make this bet meaningless

Tuning anything on the four datasets held back to judge it. Buying coverage with a longer list, or
a shorter list with misses. Counting one attack's story twice. Putting a confidence on a queue
entry that we have not shown to be calibrated. Quoting any number here as though A3 had passed, or
as a result on a real plant: every figure above comes from public datasets and simulated plants.

## The honest risk

Thirty of the thirty-one misses are in datasets we have barred ourselves from studying, because
looking at them is how a bar stops being a bar. One is in the dataset we develop on. So the
mechanism gets built on plants we simulate, where a first-shift miss can be constructed
deliberately, and then it is scored once. We are betting before we can see what we are aiming at.
That is the cost of a bar that means something.
