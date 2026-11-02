# 165. We asked whether the screen and the program agree, and the answer separated the two stories

*The question was written down before the computation ran, and the computation ran once. ADRs 0407
and 0408.*

[Note 164](164-the-cyber-half-turned-out-to-be-possible.md) ended with a pair of recordings and a
question still unanswered. The recordings are of a fake chemical plant — GRFICS, built by a company
called Fortiphyd — running twice. In one run a level sensor broke. In the other, somebody sat on the
wire between the control program and the operator's screen and fed the screen an old reading.

Both runs look the same to an operator. The number on the screen stops moving. That is the whole
difficulty: a broken instrument and an attacker holding the screen still are, from the chair in
front of the screen, the same event.

Fortiphyd's own design document says how to tell them apart, and it comes down to one question:

**Does the operator's screen agree with the control program?**

If the instrument broke, the lie entered the data at the source. The control program believes it,
the screen believes it, and they believe it *together*. They agree, and they are both wrong.

If somebody intercepted the wire to the screen, the control program never saw the lie. It is still
reading the real sensor. Only the screen is fooled. So they **disagree**.

## Writing the question down first

It would have been easy to compute something, look at it, and then decide what counted as success.
That is how a measurement flatters itself. So the bar went into the record first, and the record was
committed before the analysis existed.

Three things had to hold:

1. In the broken-instrument run, every tag the control program was actually moving had a screen that
   moved with it.
2. In the attack run, every tag the control program was actually moving had a screen that did not.
3. No tag managed both.

Writing that down forced two problems into the open, and both were found by reading the recordings
rather than by running anything.

**The screen polls slower than we sample.** The operator's screen asks the plant for its numbers
every 2.01 seconds; the recording takes a sample every second. So if the bar had been "the screen
changed as often as the register did", the answer would have been about half, every time, in every
run — and I would have been measuring the polling interval while believing I was measuring
agreement. The bar is therefore **"did the screen change at all"**, which for the runs in hand is
roughly six hundred changes against a flat zero. Nothing subtle is needed when the gap is that wide.

**The plant was not in the same state in the two runs.** Two of the thirteen tags were moving in one
run and pinned in the other, for reasons that have nothing to do with faults or attackers. Comparing
a tag across the two runs would have been comparing two different plants. So each run is judged
**against itself**: the screen's value against its own register, at the same instant, on the same
clock.

## What came back

All three held.

In the broken-instrument run, **eight** tags were genuinely moving on the control side, and all
eight had a screen that followed. In the attack run, **six** tags were genuinely moving, and all six
had a screen that changed **zero times** across 1174 samples. The two sets do not overlap.

The sharpest single case of agreement is pressure in the broken run: the register took 197 different
values, and the screen tracked them. The sharpest case of disagreement is any of the six in the
attack run, where the register moved through hundreds of values and the screen held exactly one for
twenty minutes.

Four of the thirteen tags never move in either run, even when nothing is wrong. They are pinned by
the simulation. They prove nothing in either direction and the tables mark them as such, because a
count that quietly included them would be inflated by four.

## The row I had to explain

The tank level — the tag this whole experiment was built around — behaves strangely, and it is worth
sitting with.

In the **broken-instrument** run, the level register is not moving at all. One value, the entire
time. By my own rule that makes it carry no evidence, and the analysis excludes it.

In the **attack** run, the level register moves through 181 different values while the screen holds
one.

At first glance that looks like the experiment failing on its own headline tag. It is the opposite.
The broken instrument froze the sensor *at the source*, so the register froze too — and everything
downstream was fooled identically, which is exactly what the design document predicts for a physical
fault. My analysis was fooled along with everyone else, and it can say nothing about that tag from
the register alone. Saying so is more honest than quietly leaving the row out.

That is why the clean example of agreement is pressure and not level. The record says so in those
words, rather than leaving a reader to spot the asymmetry and wonder whether anybody noticed.

## What this is not

It is **not a detection result**. Nothing was scored. There is no recall here, no false-alarm rate,
no accuracy, no confidence, no alert budget, and none of those may be quoted from the report by
anyone, including me later. Eight tags agreeing and six disagreeing is a description of two
recordings, not a claim about how often anything is caught.

It is **not a real plant**. It is a simulator, so this is a diagnosis and not proof. Version 1 still
stands at eight of twelve.

It is **not cross-zone evidence**. This corpus runs on one flat Docker network with no router, so
there is no firewall log, no intrusion detection and no ARP monitor to point at. Fortiphyd's design
leans on those; this pair poses the agreement question and nothing else.

And the corpus was **not widened** to make the answer bigger. Two runs were recorded and two were
analysed. Eight more runs sit undriven, because running them would not make this question better
answered — it would just make the paragraph longer.

## Why the small answer is the right size

The result is: on an emulated plant, under one fault and one attack, the question Fortiphyd's design
document poses can actually be asked of recorded files, and the answer comes out the way the document
says it should. That is all.

What it does not tell us is whether a real plant separates the same way — whether real instruments
fail this cleanly, whether real operator screens poll this predictably, whether a real attacker holds
a value this still. No amount of further simulation answers that. The next honest step is a plant
with an owner, not more seeds.

GRFICS is Fortiphyd's work. They permitted research use by email and asked for credit, and they have
it here, in the report, and in the record.
