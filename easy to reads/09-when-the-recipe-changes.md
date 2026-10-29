# When the recipe changes

**What this is:** two Atlas fixes commissioned by measurement, both about **batch** (phased)
processes.

**Why it exists:** a continuous water plant and a batch reactor do not share one idea of normal.
Treating them as if they do made Atlas **blind**, then **noisy**, in ways a control-room operator
would recognise immediately.

## Baking is not mixing

A batch recipe has **phases**: idle, charge (fill), heat, react, empty. What “normal” looks like
during **charging** is illegal during **heating**. If you average them into one blob of “normal,”
the allowed band becomes enormous — wide enough that **nothing can ever look wrong**.

That is what happened. The joint model’s shrinkage floor was expressed in mixed units. Across
phases, one feed-rate signal had a huge variance; that huge number leaked onto every other signal’s
diagonal. On the synthetic batch reactor, **13 of 13 signals** had a “normal” band wider than their
own observed range. The largest attack departure was **1.99** against a threshold of 3. Atlas
could not fire. Blindness, complete and explained.

The fix: **one joint model per reported phase**, routing each moment to the phase it claims to be
in. Unlearned phases and missing phase registers get different fallbacks — they are different jobs.
Water treatment and power generation, which are not phased that way, were required to stay
**byte-identical** so a batch fix could not quietly retune another plant.

After the fix, every attack type on the batch reactor moved off the floor. Danger cases on that
plant fell from 9 to 1. The harness **still refused a detection claim** because false alarms were
above the saturation line. Seeing is not the same as being usable.

## Waiting for the oven to catch up

When you turn an oven from 180 °C to 220 °C, the display can say “220” a moment before the air
inside has arrived. The plant’s **phase register** can lead the physics by one sample. Atlas was
judging that instant against the *new* phase’s settled band — so **every** CHARGE→HEAT transition
looked like an attack, whether or not one was present.

The settling allowance forgives a short window **only if the phase being left still explains the
reading**. It is a duration in real time, not a count of rows, because different files sample at
30 s vs 60 s.

False positives on the batch reactor moved **3.59 → 2.45 per normal hour** (−32%). Still saturated.
Worse (and more useful): **three of twenty “caught” attacks** in the previous map were credited to
that **always-on transition blip**, not to the attack. The fix withdrew the false credit.

A probe showed the remaining exposure: D2’s attack library had **no** attack lying wholly inside a
settling window, so the battery could not test that blind spot. The gap is written down rather than
papered over.

## What this is not

- Not proof the same trick will work on a **real** batch plant. Both fixes were measured on a
  simulator PHOS wrote. That is exactly why a public distillation corpus was acquired
  ([first number](12-batch-distillation-todays-work.md)). That corpus still has **no declared
  phase** Atlas may route on; the quieter distillation row is a **gated pooled model**, not
  per-phase envelopes ([quieter queues](13-quieter-queues-and-honest-ranking.md)).
- Not a general “ignore the first N minutes of every change.” Forgiveness is only for readings the
  outgoing phase can explain.

## Where to read more

- Decisions: [ADR 0018](../docs/adr/0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0019](../docs/adr/0019-the-settling-allowance-and-the-blind-window-it-is-bounded-by.md)
