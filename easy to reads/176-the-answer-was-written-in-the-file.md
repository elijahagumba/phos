# 176. The answer was written in the file

*We were about to tell a scientist her dataset contradicted itself. Her own files had already
answered the question — in a sentence we had never read — and believing otherwise had cost us
twenty-one hours of perfectly good data.*

One of the few real plants PHOS can read is a laboratory distillation column in Kaiserslautern. The
people who built it published everything: the readings, the labels, and a written note on each
unusual event explaining what it was. It is a generous piece of work, and PHOS has used it for over
a year.

A co-author answered an email this week about the plant's layout. Writing back seemed like a chance
to give something useful in return, so the draft included a problem our own record said we had found
in her data: **the labels disagree with each other.** The experiments the dataset calls normal are
marked clean in one place and marked as containing anomalies in another.

Before sending a sentence like that to the people who published the data, it seemed worth checking.

## What was actually in the files

The dataset labels each experiment twice. One label is a column of numbers, one per second, and it
says every one of the 38 training experiments is clean. The other label is a written record beside
it, and in 19 of those 38 experiments it does list unusual events — 55 of them, under headings like
"Confirmed anomaly".

That is where our reading stopped, and it is where the answer begins. Every one of those 55 entries
carries a sentence from the person who wrote it:

> This event was assessed as negligible and treated as normal; optional for anomalous set inclusion.

Fifty-five out of fifty-five. No exceptions. The annotators had been asked this exact question by
somebody and had written the answer down beside each entry. *We looked at the heading and never read
the line underneath it.*

And the other 19 files? They contain a placeholder meaning **nothing happened here** — which anybody
counting "files with a record in them" counts as a file with an anomaly in it. It isn't one.

## The check that could have let us off, and didn't

There was an obvious way the misreading might still have been reasonable: if that "treated as
normal" sentence appears on *every* entry in the whole dataset, then it is boilerplate and means
nothing.

So we counted. In the 81 experiments the dataset calls abnormal there are 451 entries, and **40 of
them** carry the sentence — fewer than one in ten, against ten out of ten in the training half. The
annotators used it deliberately, and they used it where they meant it.

The two labels were never in conflict. They are the same statement written twice.

## What it cost

Believing in the conflict had a price, and it was paid in data. Because PHOS only trusted the
experiments both labels called clean, it taught Atlas what normal looks like using **30.25 hours** of
plant operation and set aside **21.19 hours** as suspect. The set-aside hours were normal operation
that the plant's own experts had called normal.

For an engine whose entire job is to learn what ordinary looks like, throwing away 41% of the
available ordinary is not a small thing.

There was also a measurement built on the mistake: a test asking whether Atlas could spot the events
the annotators flagged but the column did not. It was prepared and never run, which is lucky, because
there was nothing there to spot.

## What has and has not changed

The honest part is what we are *not* doing. No number has been remeasured. The published false-alarm
figure for this plant — 18.72 an hour — was measured properly on the data it was trained on, and it
stays exactly as it is. Retraining on all 51 hours might make Atlas better, worse, or identical, and
nobody here knows which. **That is a measurement, and a measurement has to be written down before it
is run**, which is the rule this project is built on. So it will be, separately, and whatever it says
will be recorded.

The old records keep their mistake visible. The decision from August is not edited and not retitled,
even though its title contains the error, because a record quietly changed afterwards is a record you
cannot trust. The correction sits beside it instead.

The email went out without that paragraph. It did carry a genuine finding — one label file out of
119 has 1,216 blank rows padding the end, which could make a careless reader see over a thousand
anomalies inside a training file — and a request to check our reading of her plant diagram.

## The thing worth keeping

The mistake was not carelessness about data. It was reading a structured field and ignoring the
plain-English note attached to it. The heading said `ConfirmedAnomaly`; the comment said *we looked
at this and it's fine*. One of those is easy for a program to count and the other is not, and the
easy one was wrong.

It survived a year because it was written in a dataset note, promoted into a decision record's
title, repeated in a second record, and then built into prepared data files. None of that made it
true. It was caught because it was about to be said out loud to the person who would have known.
