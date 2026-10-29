# 54 — Three formulas, before any score

Sentiel misses one of the two labelled insiders because a day needs fourteen signals at once
before it can alert, however far one signal has moved. The rules for trying a different way of
adding those signals up were fixed before any formula existed. This note is the formulas. None
of them has been run on the insiders.

There are three, and there will not be a fourth in this try.

- **Depth above the bar.** Each signal that moved past the existing emission bar adds how far
  it went past that bar. The bar is 1.0, the one the scorer already uses. A signal that the
  model could not measure adds nothing.
- **How rare, under a bell curve.** Each measured signal adds the negative log of the chance a
  standard bell curve would be at least that far out. A z-score already is that curve. Signals
  the model could not measure add nothing.
- **One voice per kind of behaviour.** Signals that are the same behaviour counted several ways
  keep only the largest. Those largest values are then added across the kinds of behaviour
  Sentiel already names. Mean was the other option in the record, and it was not chosen: the
  point of this formula is that counting the same behaviour four times should not be four votes.

The fourth shape in the earlier record, a dial between "add them" and "take the biggest", is
not here. That dial would be a number we picked, and picking it is the thing the rules forbid.

No signal is given extra weight. The published number, precision 0.104 at 48 alerts, is not
touched. The prediction in the earlier note still stands: this probably will not be enough,
and if it is not, that is a result.

---

**The short version.** Three ways of letting a deep day count are written down, with every
number they use, before any of them is tried on the two insiders.

*Record: ADR 0093. Not scored. No new measurement.*
