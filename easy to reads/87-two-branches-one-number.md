# 87. Two branches, one number

*The same decision number got used twice, because each session looked only at its own branch.
ADR 0292.*

## What went wrong

On 20 October two sessions were working at the same time, on two branches. Each needed a fresh
decision number. Each listed the numbers on its own branch, took the next one, and wrote. They
took the same two numbers, three minutes apart, for different decisions. The plain-English notes
did the same thing. That second clash was quieter: the files had different names, so the merge
did not call it a conflict.

The earlier pair kept the numbers. The later pair was renumbered. That is written down. What was
not fixed was the habit. The next pair of sessions would have done it again.

## The check

When a change adds a decision record or a note, a check looks at every branch this copy of the
repository can see. If that number is already the name of a different file on any of them, the
change is refused. The same file on two branches is one record, not two. The check does not go
back and reopen the clash that was already settled.

It runs when the lab's tests run, after fetching every branch, so a session on another machine is
visible too. A third clash is a reason to fix the check, not a reason to renumber again.

Nothing was measured.
