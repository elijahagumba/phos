# 111. The joint command is declared

*The next day's test, written down before anyone runs it. ADR 0316.*

The walk column missed the same slow walk the engines we already have missed, so
that column is retired. The next test moves two setpoints at once, from the
operator's own console, and rewrites nothing else.

One write is the tank's upper limit, inside the band from 6.5 to 7.5 that an
ordinary setpoint already uses. The other is the bottle's fill limit. The plant's
own default for that limit is 1.8, and a bottle cannot hold more than 2, so the
write stays between 1.3 and 2.0. The inlet valve is not held. No instrument is
rewritten. Each loop is left able to follow its own setpoint.

The two engines we already have are scored on that, and only after this note's
record is committed. If they already catch every one, no new column is written,
and the next class is packing incidents, which gets its own record. If they miss
some, a new column may be built from the fact that two setpoints stepped together
while both valves still did what the controller's own program says. That column
is described and not written.

The sealed runs are not generated. Version 1 still stands at eight of twelve.
