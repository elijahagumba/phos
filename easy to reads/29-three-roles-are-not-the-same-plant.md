# 29 — Three roles are not the same plant

Clock B froze a ruler before anyone tuned against it. One frozen cell said: you may not
teach HAI and test BATADAL and call that transfer until someone **declares** which
physical quantities are supposed to be the same thing. Different column names are not a
protocol.

Milestone 1 writes that declaration. It is small on purpose.

Atlas now maps three kinds of instrument — **flow**, **pressure**, **pump on/off** —
across plants that publish those quantities under different tag names. A BATADAL pump
flow and an HAI flow transmitter can share a column called `flow`. A SWaT tank level
cannot sneak in as extra cleverness. Neither can an HAI turbine RPM. Those tags are
plant-private. They are dropped.

The map is written from documentation, not from "these two signals move together."
If we had clustered our way to an alignment, we would have answered "are these the
same physical thing?" with the same statistic the detector uses. That is circular, and
ADR 0010 already forbade it for topology.

SWaT is behind a request form. The loader **refuses** when the files are not on disk.
Nobody here downloads around the form. So the first training set is BATADAL's
attack-free year, projected onto those three roles. HAI's labelled test file, projected
the same way, is the exam. The covariance is learned only on BATADAL. The threshold is
the public one (3.0, seed 11). Nobody hunts a prettier cutoff on HAI.

The logged names are new on purpose: `model:atlas-mahalanobis-physical-roles` on
`zero-shot:hai-physical-roles`. They do not overwrite HAI Mahalanobis **646.58** false
positives per normal hour, distillation **18.72**, or CERT 6B **0.104**.

What the harness wrote: **1078.99** false positives per normal hour, window recall
**1.00**. Transfer is **louder** than teaching HAI on HAI. Native Mahalanobis still
wins the in-plant HAI ruler. That is not a failure of honesty. Three averaged roles
are not one water network. Units differ. The plants are not the same machine.

If a later session wants a quieter number, the forbidden moves are still forbidden:
do not retune public knobs on this split, do not fetch SWaT around the form, do not
pool command-lead 0/16 with 1/4, do not skip the partner conversation by building an
API.

The frozen Benchmark cell that refused HAI→BATADAL without a schema stays refused.
This note is a **new** measurement under a declared three-role schema, not a rewrite
of that freeze.
