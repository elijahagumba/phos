# 33 — The queue is sorted the wrong way round

We have said for a while that Atlas produces "53 false alarms an hour" on HAI. That is a true
sentence and it is the wrong sentence, because nobody works in false-alarms-per-hour. They work a
shift.

So we counted the shift. The same run that produces 53-an-hour hands an operator **424 things to
look at**, spread over about eight hours of normal running. **Six of them are the attack.** The
other 418 are not.

Reading 424 items to find 6 is not a job anyone will do. But there is an obvious way out, and it is
the one every security product takes: don't hand over all 424. Sort them worst-first and hand over
the top ten. Sentiel has worked this way since we built its CERT curve — recall at a ticket budget,
not alarms per hour. Atlas never had the equivalent. So we built it.

## What we found

Atlas carries three numbers that could plausibly say "this one is worse than that one":

- **how far the reading is from what the rest of the plant implied** (the magnitude),
- **how confident the calibrated model is** (the weight),
- **how much of the unit moved at once** (the breadth).

None of them works. Not "none of them works well" — none of them works.

**The distance is sorted backwards.** The six real alerts sit at positions 187, 204, 255, 320, 348
and 359 out of 424. They are in the *back half* of the queue. If you hand the operator the loudest
48, they get **zero** attacks. If you had picked 48 at random you'd expect to stumble into 0.68 of
them, so sorting by distance is not merely unhelpful — it is worse than shuffling. The loudest 96
items contain no attack at all.

That matters more than it sounds. If the ordering were just weak, a better cut-off would rescue it.
Because the ordering points the wrong way, **no cut-off can.**

**The confidence is not a number, it's a constant.** All 424 events carry the identical
confidence — 0.0338. Every one. We already knew the calibrator was starved (it only ever saw 140
attack-window examples out of 4,249), and we already wrote down that its output tops out around
0.034. What we hadn't checked is that on the queue an operator actually sees, it has flatlined at
that ceiling. It tells you nothing about which alert to read first because it says the same thing
about all of them.

**The breadth is nearly as flat**, taking only four values, and it also sorts the real alerts to
the back.

## The number we nearly reported

Here is the part worth dwelling on.

If you sort by confidence and take the top 48, you get **all six attacks, at 12.5% precision**.
That is better than Sentiel's CERT ruler. It looks like the best number in the repository.

It is not a number. All 424 confidences are identical, so "sorting" by it does nothing at all and
the list stays in **time order** — and HAI's attacks happen early in the test file. We measured the
clock, not the detector.

We didn't catch that by being careful in prose. The code catches it: when the cut-off falls in the
middle of a block of tied scores, the result is marked as *decided by the tiebreak* and struck from
the honest results. It fired on its first outing, on the single most flattering number available.
That is the machinery doing its job.

## What this changes

Atlas has no operator queue, and now we know why — and the why is not "we haven't tuned it enough."
There is simply no severity attached to a subsystem event. Distance from normal is not severity: on
this plant the biggest departures are a stretch of night-time behaviour between 22:54 and 02:05,
hours after the attacks ended, that the model never learned. We have not worked out what that
stretch is. We wrote that down rather than smoothing it over.

The tempting fix — the queue is backwards, so flip it — is one we are refusing. Flipping it would
be fitting a plus-or-minus sign to two attack windows on one corpus, and the top of the flipped
list would just be whatever sits nearest the threshold. That's the shape of the cut-off, not a
severity.

What a severity would have to come from instead: whether an event *persists* rather than flickers,
whether several units moved *together*, or whether there is a work order covering it. The last one
is the interesting one, and it is the piece a real plant already has and a public dataset never
does.

Detail: [ADR 0068](../docs/adr/0068-the-atlas-operator-queue-cannot-be-ranked.md). Numbers:
`eval_runs/atlas/hai-operator-queue.md`. Nothing here changes 646.58, 53.26, or CERT's 0.104.
