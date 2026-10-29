# 40 — The alarms were never about the plant

Note 39 said the first job of this phase was to find out *what kind of uncertainty* makes Atlas cry
wolf 53 times an hour on HAI — because "our model is wrong" and "the data could not have told us"
point in opposite directions, and we could not tell which one we were in.

We can now. It is the first one, and it is not close.

## The one measurement that settles it

HAI ships two files: a labelled one with the attacks in it, and a separate sixty-hour file its
authors declare contains no attack at all. Atlas has never used that second file for this
measurement. So we did something very simple.

We took the model **exactly as it was already fitted** — no retuning, no new threshold, nothing
touched — and pointed it at those sixty hours of ordinary running it had never seen.

It cried wolf on **55.74%** of them.

On the real test slice, the one that produces the famous 53-an-hour figure, it cries wolf on
**55.81%**.

Those are the same number. The model alarms on more than half of all moments of *perfectly ordinary
operation*. The 424 things it handed an operator were not a response to anything happening in the
plant. They are just what this model does.

## Why it does it

Three reasons, all measurable, all ours.

**It learned the plant from twenty-nine minutes.** The fit window is 0.48 hours. The boiler's flow
transmitter — the signal behind over half the queue — swings on a cycle lasting **3.15 hours**. So
the model watched 15% of one cycle and concluded that was the whole plant. Other signals cycle even
slower, out to seventeen hours.

**Its sense of "how much is too much" is borrowed from the wrong tag.** To make the maths work,
Atlas nudges its covariance towards a simpler shape, and it does that in raw units. HAI has one tag
reading in the hundreds of thousands and others reading in single digits. The result: **44 of 52
signals end up with the identical tolerance**, ±834, borrowed from the biggest number in the plant.
We can show it to nine decimal places — it is exactly `sqrt(0.05 × 1,545,200)`.

**So five signals are judged against a tolerance narrower than their own normal wobble.** A flow
transmitter that routinely swings ±878 is being asked to stay inside ±834. It cannot. It must alarm
during normal operation, not because anything is wrong but because the band is narrower than the
signal. Those five signals are behind **360 of the 424 alerts**.

## What it would cost to fix, and what it would cost in missed attacks

We ran the same model, same threshold, same seed, same eight hours being judged, same fifty-two
signals — and varied **only** how much ordinary running it was allowed to learn from first.

| Learned from | Alarms | Share of moments | Attacks caught |
| --- | ---: | ---: | ---: |
| 0.48 h (what we ship) | 5,123 | 55.96% | 2 of 2 |
| 3.89 h | 4,111 | 48.70% | 2 of 2 |
| **4.86 h** | **186** | **4.52%** | **2 of 2** |
| 60.00 h | 97 | 2.49% | 2 of 2 |

It is a cliff, not a slope. It falls between 3.89 and 4.86 hours — **just past one cycle of that
boiler signal**. And the last column never moves. It catches both attacks at every single setting we
tried.

## The discipline, which matters more than the finding

That table is the reason this note needs a warning attached to it, so here it is plainly.

**We did not make Atlas quieter, and we are not claiming we can.** The published number is still
53.26. Nothing was retuned. Nothing new went into the experiment log. Knowing that a longer fit
*would* read 97 instead of 5,123 is not the same as being entitled to publish 97, and this phase
explicitly forbids that, because a number that drops 53× in the same breath as its own explanation is
precisely how a research record turns into a brochure.

There is also a real obstacle, and it is the interesting part. The reason the fit is twenty-nine
minutes long is not carelessness. Atlas needs *examples of attacks* to calibrate its confidence, and
the clean sixty-hour file has none — by definition. So it has to carve its training data out of the
labelled file instead, and HAI's attacks sit early enough in that file that the carve has to be tiny
to leave any attack left to find. The short fit is a consequence of where the labels live. Fixing it
means solving a different problem first: how to calibrate without labelled examples. That is not
this session's work and we have not started it.

## Two other things fell out

**The queue was never 424 things.** It is **fifteen** distinct combinations of unit and instrument,
in 132 unbroken runs. One of them — three boiler signals moving together — is **221 alerts, over
half the entire queue, in just two runs** lasting from 22:11 to 02:47. An operator was being handed
the same single condition, once a minute, for four and a half hours. Only 9 of HAI's 79 signals ever
alarm at all.

**Note 33's mystery is solved.** That note found the queue sorted worst-first puts the real attacks
in the *back half*, and could not say why. Now we can: four of the six real alerts sit on signals
this model alarms on 14%, 11% and 4% of all normal moments — and their readings are *smaller* than
ones it produced on attack-free data. There is nothing to sort by. You cannot rank a list worst-first
when the real items look exactly like the noise.

## And the things we still cannot do

We wrote six new entries into the refusal register. Two are worth repeating here.

**We cannot tell maintenance from an attacker on HAI — and now we have checked rather than assumed.**
Zero of its seventy-nine columns is a work order, an operator name, or a mode register. Nothing in
this finding changes that, and no amount of better modelling will conjure one.

**One signal separates the attack perfectly, and we are refusing to use it.** `P2_CO_rpm` never once
leaves its band across seventy-one hours of ordinary running, and it leaves it during an attack. It
is tempting. It is also one signal, two alerts, one of two attack windows, one dataset. Turning that
into a detector would be fitting a rule to two events on the only corpus we have — the exact move
note 33 already refused. So it is written down as a refusal with a note saying what would lift it: a
second plant.

---

**The short version.** Our false alarms were not telling us something about the plant. They were
telling us that we taught the model about an eight-hour industrial process by showing it twenty-nine
minutes. That is a good answer to have, because it is about us, and the evidence that fixes it is
already sitting in the dataset we already have. What is *still* blocked on the outside world is
narrower and clearer than we thought: we need work orders, and we need a second plant.

*Record: ADR 0075. Numbers: `eval_runs/atlas/hai-error-taxonomy.md`, seed 11. Refusals: R7–R13 in
`docs/refusal-register.md`. Previous notes: 33 (the queue cannot be sorted), 34 (the work order
nobody ships), 39 (the phase that is allowed to fail).*
