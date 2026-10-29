# 100. Two setpoints together

*One ordinary write is quiet. Two tags moving together are not. ADR 0305.*

A setpoint written inside 6.5 to 7.5 is what an operator already does. One tag in
that band raises nothing. Two different tags in that band, close together, are one
move, and the time shown is the first write.

Four of those pairs are all caught. A lone extra write adds no alarm. Twelve pairs
cannot all fit on a page of eight, and the ones that miss are at most half of the
twelve the single-tag check misses. A register write is still not a setpoint.

This is a made example, not a plant. Version 1 still stands at eight of twelve.
