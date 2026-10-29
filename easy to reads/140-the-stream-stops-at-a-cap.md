# The stream stops at a cap

The next piece of the protocol work is not a new language. It is a limit on
how much of a conversation the reader is willing to hold while it waits for
the rest of a message.

The numbers were written down before the code: 131072 bytes in one direction,
256 conversations at once, 16 pieces that arrive out of order, and a pairing
table of 256 that forgets a match only by writing down that it forgot, after
60 seconds of the capture's own clock. A conversation that asks for more than
that is refused. It is not cut short and treated as if it had fitted.

The code is now written. It sits in two new files beside the old reader, and
the old reader does not call them: Modbus still gets one frame at a time, and a
bad Modbus frame is still a bad Modbus frame. The reader also writes down three
things from the front of each frame it had been throwing away — the two hardware
addresses and the number that says what kind of frame it is — and leaves that
number alone even when it is the one a tagged network uses. Naming it would be a
guess about a layer this work does not read.

What refusing looks like in practice: a conversation that sends the same bytes
twice is refused rather than having one copy chosen for it, because choosing
would be inventing a conversation that nobody had. A gap is waited for, not
filled with zeros. A message that says it is longer than the cap allows is
refused before a single byte is removed, so the next reader finds the header
exactly where it was. A pair that times out is written down as a miss first and
dropped second, so the count of what was missed is real.

Every test the project has passes, the type checker and the linter are clean,
and the Modbus file has not been touched. None of that is a verdict. The record
that judges this work against the bar is not written, and the agent who wrote
the code is not allowed to write it. Nothing was scored, no capture was opened,
and version 1 still stands at eight of twelve.
