# 105. The same value, after the window

*Two tags, one number, too far apart for the joint check. ADR 0310.*

One tag is written inside the ordinary band. Later, a different tag is written to that
same number. The gap is longer than the 300 seconds the joint check uses, and shorter
than a shift. The walk check wants 720 steps of one tag, so it sees nothing. The page
that holds both of those classes sees nothing either.

Twelve of these pairs. That page misses all twelve. Keeping eight of them misses four,
which is at most half. A pair that sits inside the 300 seconds stays with the joint
check.

This is a made example, not a plant. Version 1 still stands at eight of twelve.
