# 110. The walk column missed the same one

*Scored once, and not kept. ADR 0315.*

The new column watches the inlet valve the way the plant's own controller would.
On the simulated plant it missed the same one slow walk the engines we already
have missed, 1 of 9. False alerts stayed 19, 1.187500 an hour. Nothing it caught
arrived later.

The column's training scale is 2. A full disagreement, once scaled, sits exactly
on the line where an episode opens, and an episode opens only above that line. So
the column added no alert. The scale was not changed afterwards.

The column is not kept. The score is not run again. This is a simulated plant. It
is not a result about a real one. The sealed runs stay sealed. Version 1 still
stands at eight of twelve.
