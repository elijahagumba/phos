# 173 — We caught every walk, and the record called it a refusal

Decision record: ADR 0418. Experiment: E-0001, answering Q-0001. Date: 3 November 2026.

Two months ago the slow walk was the thing both engines missed. One walk in nine. A decision record
said so, a second decision record tried a fix, the fix missed the same walk, and the fix was retired.

The open question was *why*. Either the miss was an accident of arithmetic — a score landing exactly
on the line that decides whether to raise an alarm — or the walk was genuinely invisible to anything
that looks at one reading at a time. Nobody had separated those two.

## How you tell them apart

Look at order instead of size. A normal operator changes a setpoint once and it stays changed. The
walk changes it 720 times, one small step per second. Every individual step is small and perfectly
ordinary. What is not ordinary is that the value never rests.

So the new detector counts, for each sample, how many samples in a row the value has been moving.
On normal running that number never got above 1 — one person, one write. On a walk it climbs into
the hundreds.

## What happened

It caught all nine walks. It raised no false alarms at all.

That is the first time anything in this programme has caught every walk. And the record calls the
experiment **refused**.

## Why the record says refused

Because the question had two answers and they exclude each other, and the form only has one word for
a result. One bar said "misses exactly one, same as before". The other said "misses none". Only one
of those can be true. The run hit the second one — the good one — and the first one therefore failed,
and *any* failed bar means refused.

There is no number that could have made this experiment "kept". Zero misses fails the first bar.
One miss fails the second. Two or more fails both. The verdict was decided by the shape of the
paperwork, not by what the plant did.

## Two reasons to be careful anyway

**Zero false alarms is not a medal here.** In this simulated plant an ordinary setpoint change is one
write, so its count is 1, and the threshold was learned as 1 and excludes it. The walks are the only
thing in this plant that moves a setpoint continuously. On a real plant, where a control loop and a
slow operator both exist, that will not be true. This is a property of the toy, not a result about a
plant.

**The second number was predictable before the run, and it was guessed.** We also counted how many
samples in each walk fell outside the range normal running had produced. That came to 2331. But the
walk is written to sweep the whole 6.5-to-7.5 band on purpose, and three normal runs only happened to
touch 6.6 to 7.24. So a walk was always going to leave that range, whether or not any detector could
see it. It is a weak number and it is labelled weak in the record.

## What could not be recovered

The old records say "one walk in nine was missed" and never say **which** one. That gap is still open.
The nine walks themselves could be rebuilt from the plant's own generator code, which is deterministic
and unchanged, and they came to nine walks across eight runs — one run held two. But the identity of
the missed walk is gone, and the old score may not be re-run to find it.

That is the thing worth carrying forward: a record that keeps a count and throws away the identities
has kept less than it looks like it kept.

## What this is not

A simulated plant, not a real one. Not a detection claim, not a daily record, not a field rate. The
sealed runs stay sealed. Version 1 still stands at eight of twelve.
