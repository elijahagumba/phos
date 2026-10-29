# 30 — Yesterday's plant is not today's snapshot

Atlas already had a linear dynamical residual sitting in the tree: a VAR that predicts
this moment from the last one, then scores the error. It had only ever been run on
hand-built fixtures. This week asked it of HAI, the same three-way split that produced
Mahalanobis **646.58** false positives per normal hour (seed 11, threshold 3.0).

The logged name is new on purpose: `model:atlas-var1` on `hai-test-test`. It does not
overwrite the snapshot row.

What the harness wrote: window recall **1.00**, **14071.07** false positives per normal
hour. That is **louder** than snapshot Mahalanobis, and louder than the per-signal
Gaussian. The dynamical residual is refused as the HAI detector.

A plant that is mostly a correlated snapshot is allowed to stay a snapshot. Fitting
one more lag, or searching a prettier threshold, would be chasing a win the files
already refused.

The decision is [ADR 0064](../docs/adr/0064-var1-on-hai-is-louder-than-snapshot-mahalanobis.md).
