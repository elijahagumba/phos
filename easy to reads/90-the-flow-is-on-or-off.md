# 90. The flow is on or off

*The attack that was going to move level and flow together, written down before anyone scored
it. ADR 0295.*

## What the plant actually does

The bottle plant does not make flow a share of the level. When the outlet valve is open and the
tank still holds water, the outflow is one fixed rate. When the valve is shut, or the tank is
empty, the outflow is zero. That is the plant's own code, read before any detector saw this
attack.

So an attacker who wants both readings to stay possible cannot turn the flow up by the same
fraction as the level. A flow in between those two values is a flow this plant never produces.

## The attack, fixed in advance

The level reading is nudged by between 3 and 8 percent, the same band already used for a
miscalibrated instrument, and not chosen by watching a detector. The flow reading is then set
to whichever of the two legal values matches that nudged level and the real valve. Nothing else
is touched.

Whether the engine catches that on one instrument, or only when it looks at the instruments
together, is not known yet. The band does not get tightened if the catch turns out to be easy.
A made-up plant is a diagnosis, not a proof. Version 1 still stands at eight of twelve.
