# 60 — Grouping raises the count, and Atlas still loses

The shared grouping rule has now been applied to the detectors that were already in
the first table. Each one keeps its own alarms. The rule only decides which of those
alarms spend one of the eight slots in a shift.

On the two HAI editions the rule was already allowed to see, the range check still
catches more attacks than Atlas. Atlas goes from 9 of 38 to 23 of 38 on the first
edition, and the range check goes from 15 to 32. On the second edition Atlas goes
from 7 of 50 to 15, and the range check goes from 14 to 36. The gap that remains
after both have been grouped is 9 attacks on the first edition and 21 on the second,
in the range check's favour. Those two rows are marked seen.

On the water network the counts do not move: Atlas still catches all 5, the range
check still catches 3, and the two attacks only Atlas catches after grouping are one
window. On the distillation file, which is a perturbation label and does not judge,
the range check still leads, 33 to 26. On the grid file, which is a process phase and
does not judge, both catch 1 of 2.

The two later HAI editions are still waiting. They get one look, and that look is
the next step, written down before it is run.
