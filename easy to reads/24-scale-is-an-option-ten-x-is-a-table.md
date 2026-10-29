# Scale is a named option; 10× is a table

**What this is:** Sessions C3 and C4. Atlas can standardise *within a declared
mode* before it estimates covariance, and the joint-vs-univariate comparison is
now a table of already-measured corpora — not a stamp that every plant is 10×
quieter.

**Why it exists:** Mixed engineering units can floor every band. Pretending one
shrinkage is universal would paper over the dummy-batch failure. Pretending
every public ZIP is 10× quieter would paper over distillation (8.6×, not 10×),
Data4Cyber (6.6×, ruler refused), and BATADAL (a loss on the false-positive
axis).

## What changed

`ShrinkageTarget.AVERAGE_VARIANCE` stays the public default. `CORRELATION` is a
named option for bake-offs. Public ungated distillation **18.72** was not
overwritten.

The table lives in code (`PUBLIC_JOINT_VS_UNIVARIATE`). Ratios may miss 10×.
Recall kind is named: attack, perturbation, or process-phase. 3W is not a
measured row here — that is faults, later.

## What this is not

Not 10× on every dataset. Not 2–3 pages a day. Not a retune of command
templates.

The decisions are [ADR 0052](../docs/adr/0052-scale-invariant-shrinkage-is-a-named-option.md)
and [ADR 0053](../docs/adr/0053-joint-vs-univariate-is-a-table.md).
