# 166. We added two datasets, and the work was writing down what neither one can prove

*Finding data is the easy half. Deciding what it is allowed to support is the half that takes the
record. ADRs 0409, 0410 and 0411.*

PHOS needs data it has never looked at. Not more data in general — data that has been kept sealed
from the start, so that when a detector is finally run against it, the number means something. A
detector tuned on the same file it is tested on will always look brilliant and will always be lying.

A weekly search goes looking for new public datasets from industrial plants. This week it found
four worth examining. Two were added. One was behind a paid subscription and was not bought. One
turned out not to be a dataset at all.

## The first one records faults, not attacks

The first is from the University of Burgos in Spain. It is a real production machine — a station
that marks parts — driven by a real industrial controller, and the researchers deliberately broke
it in recorded ways: a sensor made to lie, a valve made to stick. Every break is labelled with what
it was and when it started.

That is genuinely valuable, and it is **not an attack dataset**. Nobody hacked this machine. The
distinction matters more than it sounds, because telling a broken instrument apart from an attacker
is one of the hardest things this project is trying to do — and a dataset of faults can help you
learn what a fault looks like, while proving nothing whatsoever about catching an attacker. So the
record puts it in the same bracket as the oil-well dataset we already hold, which is also faults
wearing the word "anomaly".

Two more limits went into the record rather than being discovered later by somebody hopeful:

**You cannot compute a false-alarm rate from it.** The data are stored as *events* rather than as a
steady stream of readings, so there is no "per hour" to divide by. Anyone wanting alerts-per-hour
from this file is going to invent the denominator, and inventing denominators is exactly how a
measurement flatters itself. It is refused instead.

**Part of it is unreadable to us, and that is written down.** The dataset includes raw network
recordings in a protocol called PROFINET. PHOS can read Modbus and nothing else. Those files are
listed in the record and left alone. Not parsed badly — not parsed.

## The second one is entirely simulated

The second is two million rows of electricity-grid measurements under attacks that inject false
readings. It covers four standard grid layouts and is a useful shape of problem.

It is also **100% simulation**. No wires, no substations, no instruments — a power-flow calculation
run in a modelling package. That makes it a diagnostic tool and never evidence. It cannot be mixed
in with a real plant's results, and no detection claim may rest on it alone. The record says so in
the sentence that defines it, not in a footnote.

One smaller honesty: the publisher says roughly half a million rows per grid layout. That is a claim
printed on the page, not something anybody here counted, and the record labels it as such. The time
between samples is not stated anywhere, which is the second reason a per-hour rate is refused.

## The splits were decided before anyone looked inside

For each dataset, part is kept for working with and part is sealed. The sealing rule had to be fixed
in advance, because a split chosen after seeing which half gives the nicer answer is not a split.

- **Burgos:** every third batch is sealed. Batches 3, 6 and 9 — three of eleven.
- **Grid:** the two smaller layouts are for working with, the two larger ones are sealed. A different
  number of buses is a different system, not another sample of the same one.

Neither rule is clever. Both are arbitrary. That is the point: an arbitrary rule written down first
cannot be bent to taste afterwards.

And one wrinkle got recorded instead of tidied away. **The sealed Burgos half contains no normal
run** — all three of its batches have something injected. So any future score on it has to bring a
model of "normal" learned somewhere else. The tempting fix is to reshuffle the batches until both
halves look balanced, which would mean choosing the split by looking at it. The honest move was to
write the awkwardness down and keep the rule.

## The check that failed in the right direction

One small thing is worth telling because of which way it broke.

The record included a command to verify the split had been built correctly: count the data files in
each half, expect two. The command looked one folder too shallow. The files sit one level deeper,
so it counted **zero**.

Zero is a failed check, and it was treated as one — the run stopped rather than carrying on. Then
the command was corrected and it printed two, as expected.

That is a bug, and it was logged as a bug. But notice which way it failed. A check that looks in the
wrong place and finds nothing **stops honest work**. A check that accidentally finds the right number
for the wrong reason would have **waved a wrong split through**. The first kind is annoying. The
second kind is the sort of thing this project exists to prevent. The wrong line stays in its original
record — accepted records are not edited — and a later record says plainly that it is wrong and gives
the corrected one.

## What was not added

A physical microgrid dataset looked like the single best match for what PHOS actually wants:
attack labels, real instruments, and the network traffic alongside. Downloading it requires a paid
subscription to the site that hosts it. It was not bought and not downloaded. It stays on the list.

A solar-plant record also looked promising and turned out to be a package of *results* from someone
else's analysis rather than a corpus of plant measurements. It was not registered, and the reason is
written down so next week's search does not re-propose it.

## Nothing was measured

No detector was run. No score was produced. Not one file in either sealed half has been opened — not
even to read a column heading. The data themselves are not in the repository and never will be; only
the record of where they came from, what licence they carry, and what they are not allowed to prove.

Version 1 still stands at eight of twelve. The design-partner conversation is still the thing that is
blocked, and no amount of public data unblocks it.
