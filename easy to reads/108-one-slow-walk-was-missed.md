# 108. One slow walk was missed

*The fallback test, scored on a simulated plant. ADR 0313.*

The first day's engines caught every in-range command, so the slow walk was allowed.
The operator moves one setpoint from 6.5 toward 7.5 in 720 small steps. The valve is
not held. No instrument is rewritten.

Both engines we already have missed 1 of 9 of those walks. They caught the other 8.
What caught those is the ordinary signal check. They also raised 19 false alerts each,
1.187500 an hour, and the ones they caught arrived at a median of 0.950000 seconds.
Routine maintenance drew an alert on 3 of 14. Ordinary setpoint changes drew 3 of 9.

Because one walk was missed, the detector written down before this score may be built.
It is not built in this record. The score is not run again.

This is a simulated plant. It is not a result about a real one. The sealed runs stay
sealed. Version 1 still stands at eight of twelve.
