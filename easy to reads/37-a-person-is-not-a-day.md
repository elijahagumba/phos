# 37 — A person is not a day

Sentiel has always scored a **person on a day**. Alice on the 4th of July gets a number. Alice on
the 5th gets another number, computed as if the 4th never happened. Then the numbers are sorted and
an analyst reads the top forty-eight.

That works fine when somebody does one strange thing once. It works very badly when somebody does
strange things for two months, which is what the insiders in the CERT corpus actually do — one of
them across sixty calendar days.

Fifty-three days of one person's malicious behaviour arrive as fifty-three separate items, all
competing with each other for the same forty-eight slots, and all competing with two hundred and
ten thousand ordinary days from a thousand other people. It isn't one finding presented badly. It's
one finding **shattered into fifty-three**, and the shattering is what hides it.

This work built the missing thing: an **episode**.

## What an episode is

A run of one person's unusual days, held together by a stated rule, presented as one item with a
start, an end, and every day it contains.

The rule matters more than the idea, because a rule you can tune is a rule you can tune *until it
finds the two people you already know about* — at which point it tells you nothing about the third.
So:

**The gap between days was not chosen.** It's seven days, and it was taken from a number Sentiel
already had: the reasoning engine's correlation window, set to seven days a long time ago with a
reason given at the time (a shorter window splits somebody's working pattern across a weekend). If
we'd picked a different number here, PHOS would hold two answers to one question.

**The whole sweep is published.** Five gap settings by five threshold settings, all twenty-five
rows, in the report, with the default marked. Including the settings that make the result worse.
You can look at what we didn't choose.

**No label was consulted anywhere in the rule.** The thresholds are read off the distribution of
scores, the same way an operating point already was.

## What it bought

At a budget of forty-eight items — the same budget the frozen public result uses:

| | Items read | Malicious days shown |
|---|---:|---|
| Old: one alert per person-day | 48 | **5** of 53 |
| New: episodes | 40 | **9** of 53 |

At a budget of twenty items, it's **9 against 4**, because the insider's episode sits at rank one
rather than scattered through the queue.

**A correction, added 2026-09-12.** When this note was written, that difference — 9 against 5 —
was reported as a gain, and a later session checked whether it was one. The check is simple: take
each person's own daily scores and deal them out onto different days of their own calendar, keeping
everything else the same, and see how many malicious days the episodes catch by luck alone. Do that
two hundred times and the answer averages **6.63**, and lands anywhere from **5 to 9**. The real
number, 9, is at the very top of that range — but it is *inside* it. So the honest reading is that
the episode queue may well be showing more of the insider, and this corpus cannot prove it. **The
counts below are real and unchanged. The "1.8 times" that was read off them has been withdrawn**
(ADR 0076, refusal register R18). With only two labelled insiders in the whole corpus, a ratio was
always more than the evidence could carry.

That difference is a **coverage** comparison, not a detection gain, and the difference is the
whole point of saying it carefully. **Both queues still find one of the two insiders.** The
second one, `CCH0959`, is absent from the episode queue exactly as she was absent from the day
queue. Nothing here found a person the old system couldn't find. Whether the extra days of the
person it *did* find are more than chance is what the correction above refuses to claim.

## What it cost

An episode is a bigger thing to read than a day. On average an episode in this queue holds **12.7
entity-days**. And the queue contains episodes of 49, 41, 71 and 75 days that are **entirely
false** — one innocent person's whole quiet spring, gathered up and handed to an analyst as a
single item.

Whether forty episodes are less work than forty-eight days is not a question this measurement
answers. We report both numbers and let the trade be visible instead of hiding it inside a
compression ratio.

## Two things we built that turned out to say nothing

This is the part worth reading twice, because it's the part that was easiest to quietly not
mention.

**A relationship graph, built from the company directory.** Who reports to whom, who's in which
team and department, which email address belongs to which person. Then: did today's activity go
somewhere the org chart says this person has no business going?

It carries **nothing**. The findings fire on between 63% and 91% of all person-days and touch the
malicious ones at almost exactly the rate you'd get by drawing at random — 35 against 33.3 expected,
52 against 48.3. One of them lands *below* chance: 3 malicious days against 9.0 expected. That is
not a weak signal. It's not a signal.

**Order, not just volume.** Every existing feature counts things, and a count can't see sequence:
four hundred web requests and four web requests are the same *shape*, and "logged on, plugged in a
drive, copied files, mailed out" is a different story from the same four actions in a different
order. So we measured how surprising each person-day's *path* was against the organisation's own
attack-free history.

It carries **nothing** either. At the stated cut, 2,108 person-days alert and **one** of them is
malicious, against a chance expectation of 0.5. One event above an expectation of half an event is
noise. And it agrees with the plain order-blind count baseline at a rank correlation of 0.642, so
much of what it says was already being said more cheaply.

Both are built, wired, exercised end-to-end, and measured. Neither has a detection claim attached
to it, and neither ever will on this corpus.

## The thing that nearly fooled us

The graph work was originally going to ask a cleaner question: *did this person deal with somebody
the directory places nowhere near them?*

Then we looked at the actual directory. All one thousand employees at the fictional company are in
**one business unit**. So "nowhere near them" never happens — everybody is at least a colleague of
everybody. That question would have returned zero on every single day, forever, for a purely
structural reason.

And a zero looks exactly like a measured negative. It would have gone in a report as "we asked, and
the answer was no" when the truth was "the question could not be asked here." The cut moved one
level in — outside your *department* rather than outside your *company* — decided from the shape of
the directory and nothing else. That story is in the record because a null you can't distinguish
from an unasked question is worse than no result.

The same corpus, incidentally, declares **nothing at all** about which computer belongs to which
person. So we built no such link. Every "this person shouldn't be on that machine" claim you could
make from this data would really be a claim about what they've done before — which is a question
the system already asks a different way.

## What did not change

The public CERT number is untouched: **precision 0.104 at 48 alerts**, still the ruler. It isn't
re-derived or re-stated from memory — the new measurement *reproduces it from scratch* and refuses
to run if it comes out even slightly different. Peer-group baselining stays retired. The confidences
attached to explanations are still not calibrated and still must not be shown to anyone as
probabilities.

If anything, the episode makes that last point worse rather than better, and the code says so: the
belief arithmetic treats each day as independent evidence, and an episode is by construction a run
of days that are **not** independent. A long episode therefore accumulates more confidence than a
short one for the same behaviour — which measures duration, not certainty.

## The one sentence to keep

Grouping days into episodes shows 9 malicious entity-days at budget 48 against a per-day 5; that
difference sits inside a chance interval (permuted mean 6.63, 95% [5, 9]), so it is not a ratio
this corpus can carry. The relationship graph and the sequence signal were built properly,
measured honestly, and carry nothing on this corpus.
