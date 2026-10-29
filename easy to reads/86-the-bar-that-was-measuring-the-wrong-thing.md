# 79 — The bar that was measuring the wrong thing

Version 1 has twelve things it must do. One of them, called A3, asks that half of
all attacks show up near the top of the operator's list for that shift. It failed,
57 out of 203, and we tried twice to fix it.

This week we read the result file again instead of the score. It carries, for each
attack, how long its shift's list was. The lists are short. The middle one holds
seven alerts, and two thirds of them hold eight or fewer, which is everything a
person on duty can read in eight hours.

"Near the top" was written as the top tenth. A tenth of seven is one. So for four
out of five attacks, the bar was asking the attack to be the single loudest thing
in its shift. That is a much harder question than the one we meant to ask, which
was whether the operator sees it at all.

Counted in alerts instead: of 203 attacks, 172 produce a real alert in the shift
they started in, and every one of those is within the first nine alerts of that
shift. Usually the third. The ordering was never broken.

There is a second problem with a bar written as a fraction. A noisier detector
gets a longer list, and a longer list has more room at the top, so the bar is
easier to pass by making things worse. A bar should not reward that.

So the fraction is retired as a measuring instrument, with the reason written down,
and the new bars are in the units an operator feels: how many attacks show up in
their first shift at all, how far down the list they sit, how long the list is, and
whether what the operator is handed is a story or a row. The old number stands
exactly as it was. A3 is still not met, and nothing new is counted as passing it.

The thirty-one attacks that produce nothing in their first shift are the real work.
No amount of reordering reaches them.

And an honest problem: thirty of those thirty-one are in datasets we have forbidden
ourselves to study, because looking is how a bar stops being a bar. So we build on
plants we simulate, where we can create the same kind of miss on purpose, and then
we score once. We are aiming at something we are not allowed to look at first.
