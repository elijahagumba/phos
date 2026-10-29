# Yesterday's covariance is not a correlation matrix we can invert

After VAR lost on HAI, the next Atlas question was the named correlation-target shrinkage
(ADR 0052): standardise, shrink toward the identity, rescale. Same HAI three-way split,
same seed, same threshold, a **new** detector name.

The fit never scored the test half. Fifty-two signals, shrinkage still 0.05, condition
number 10²⁵. The inverse has no digits. We did not raise shrinkage to make the matrix
pretty. 646.58 stays the public Mahalanobis number. There is no
`atlas-mahalanobis-correlation` row on the experiment log.

That is the result. Snapshot average-variance shrinkage is the model this plant can
actually be asked.
