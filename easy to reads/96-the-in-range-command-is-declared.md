# 96. The in-range command is declared

*The first day's test, written down before anyone runs it. ADR 0301.*

An ordinary setpoint already moves the tank's upper limit into the band from 6.5 to 7.5.
The new attack does that same write, from the operator's own console, and at the same
time holds the inlet valve off, using the same on and off values a maintenance job
already uses on the other valve. No instrument is rewritten. The tank reports whatever
the physics does while the valve is held.

The two engines we already have are scored on that, and only after this note's record
is committed. If they already catch every one of these attacks, the slow walk is next:
the same band, crossed in 720 tiny steps, one a second. That walk is not generated
unless the first score misses nothing. If they miss some, a new column may be built
from the check that already asks whether the valve answered the command. That column
is described and not written.

The sealed runs are not generated. Scored on 22 October 2026 (ADR 0309): both engines
caught 13 of 13, so no new column was written. The slow walk is still not generated.
Version 1 still stands at eight of twelve.
