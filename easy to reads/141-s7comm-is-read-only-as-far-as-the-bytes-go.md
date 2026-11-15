# S7comm is read only as far as the bytes go

This is the first language Atlas learned after Modbus, and the honest headline is smaller than the
protocol's name suggests.

S7 is what Siemens controllers speak. It is also, by Siemens' own description in its communication
manual, **vendor-specific and not an open standard**. The manual explains how to configure the
connection and never once says what a message looks like. There is no published byte that says
"this is a download".

So the lane did what the bytes honestly allow, and stopped there. Atlas can now read the
**envelope** S7 travels in: the four-octet wrapper that says how long the packet is, and the small
header inside it that says what kind of message this is and whether it is the last piece of a
larger one. What it cannot read is the letter inside that envelope. When the reader reports a
message, it calls it `iso-tsap` — the name the internet registry gives the port — and never
`s7comm`, because calling it S7 would be claiming to have read something nobody has published.

That distinction is the whole point of this note. A dissector that says "I can see S7" and one that
says "I can see the envelope S7 arrives in" look identical in a demo and are not the same claim.
The second is true and the first is not.

## The part that matters more than the code

The lane was supposed to take an afternoon. It took five rounds of a red team trying to break it,
and four of those rounds found a real defect in a version a judge had already passed.

The first defect was the serious one. The one number this lane produces about the contents —
how many application bytes a frame carries — could be steered by the sender. A frame carrying a
22-octet program download could declare a slightly longer header and report that it carried
**nothing**. Nothing crashed. Every field stayed inside its declared range. The message validated,
the provenance was intact, and the single fact the module asserted about the application was a lie
the sender chose.

That is worth sitting with, because it is the shape of failure that a security product cannot
afford: not a crash, not a wrong answer, but a trustworthy-looking number an attacker writes.

The fix was not better arithmetic. It was to notice that the standard gives that kind of message a
header of exactly one length and no optional extras — so a frame claiming otherwise is not a frame
to be measured, it is a frame to be refused. The same reasoning then had to be applied to four more
message types, one at a time, each because someone asked "and what about this one?"

Two of the later findings came from the red team, and one came from the judge reading the finished
verdict and asking whether the same defect was hiding somewhere the checks did not look. It was.

## What four of those five rounds say about the method

The first verdict passed the checks the declaration listed. It did not sweep the space those checks
ranged over: it tested the data-bearing message thoroughly, because the bar named that one, and
never asked what every other message type did at every possible declared length. The third verdict
did sweep that space, and declared the family closed — which was true of minimum lengths and false
of exact ones, because a sweep built to find values that are *too small* cannot see a value that is
*too large*.

What caught it was the separation of roles. The person who built it never graded it; the person who
graded it never attacked it; the person who attacked it never fixed it. Every defect in this lane
was found by someone whose job was to break the work rather than to confirm the last fix. One agent
doing all three in one sitting would very likely have stopped at the first green suite.

This note is not a boast about the red team. It is a note about what a green suite is worth. Five
passing gates, a hundred and more tests, a clean type checker — and the module still told a lie an
attacker could author. The gates never had a chance of catching it, because nothing was out of
bounds. Only an independent reader asking "can I make this number wrong?" did.

## What this does not say

Atlas can read one more envelope than it could last week. It has not been measured against a single
real capture, because no licence-clean S7 capture has been registered. It says nothing about whether
Atlas is right when it looks — no recall, no precision, no false-alert rate, nothing that moves the
scoreboard, which still reads eight of twelve.

It also does not say Atlas can read S7. That is now written down as its own entry in the register of
things Atlas cannot do, with the one document that would lift it: a Siemens publication of the frame
format. Until someone publishes that, the letter inside the envelope stays closed, and this lane
says so in the register rather than in a footnote.
