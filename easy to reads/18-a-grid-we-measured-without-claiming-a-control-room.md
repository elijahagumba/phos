# 18 — A grid we measured without claiming a control room

Data4Cyber is a real electrical distribution grid, published under CC BY 4.0, with process
telemetry at one sample per second. Session 5 already read the packet captures and refused them
as a *command* corpus: the labels say which process phase the plant was in, not which valve an
attacker turned.

This note is the next honest step. We fitted Atlas on the quiet baseline recording (S0, about
thirty minutes) and scored the Industroyer-on-PV recording (S1). The answer columns — attack
flags, attacker copies, phase names — were not fed in as plant signals. Reconnaissance seconds
stayed labelled, because that is how the file marks them.

Mahalanobis was quieter than a per-signal Gaussian by **6.6 times**, at the same recall. That is
not the 10× contract. PCA was louder than the Gaussian. Recall was 1.00 on **two** labelled
windows. The false-positive rate on the page is enormous because the quiet stretch in the test
file is about fifteen minutes. A number divided by a quarter-hour is not a control-room budget.
We refuse to quote it as one.

This is a third public process type on the board (water, batch chemistry, now a grid). It is not
three staffable plants. It is not command reasoning. It is not ≥70%. The packets are still not
a labelled command capture.

If a sentence here disagrees with ADR 0046 or `eval_runs/log.jsonl`, those files win.
