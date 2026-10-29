# The snapshot model says what it assumes

**What this is:** Session C1 of the category-defining programme. Today's joint
model is a photograph of the plant, not a movie. The tests now say so.

**Why it exists:** Atlas already talked about a manifold. The code scored one
timestamp at a time, dropped tags that never moved, and treated "normal" as a
linear blob. That is fine if we name it. It is a defect if we pretend the
photograph is dynamics.

## What the tests pin

A wild previous timestamp does not change how the current moment is rebuilt.
PCA's allowed set is a subspace. Mahalanobis' allowed set is an ellipsoid.
PCA's in-sample residual band is not the out-of-sample band (we already knew
that from ADR 0009; the test forbids "fixing" it by training on the drifted
set).

The code now lists the named breaks: capture drift, mixed recipe steps,
constants dropped in training, mixed-unit shrinkage flooring every band.

## What this is not

Not a new detector. Not a quieter distillation row. Not permission to rewrite
`_shrink` on the public comparison. Dynamics are a later session (C5).

The decision is [ADR 0050](../docs/adr/0050-snapshot-joint-assumptions-are-executable.md).
