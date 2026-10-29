# Protocols are named before they are read

On 28 October 2026 the decision was to teach Atlas more industrial languages
than Modbus, before a partner had pointed at one and said "this is ours."

The plan on the wall still says the opposite for every other piece of work:
wait until a partner's capture is that protocol, then name the reader, then
parse a byte. That sentence was not deleted. This programme is the one place
it does not apply. Each language still gets its own written bar before any of
its bytes are parsed. A reserved number is not that bar.

Modbus remains the only language the code actually reads. It still checks the
length before it trusts it, and it still refuses a bad frame instead of
crashing. Nothing new was scored. The page of eight is unchanged. Version 1
still stands at eight of twelve.

The order, if the work continues, starts with the ability to put a split
message back together without letting a huge frame eat the machine. After that
comes Siemens S7, because a program download is already a kind of event the
page knows how to hold — and only if a Siemens document names the byte that
means download. A byte learned from someone else's program does not count. If
that document cannot be found, the honest result is to say so and not invent
the byte.

Quiet on a protocol we have not read is not a statement that the plant is fine.
