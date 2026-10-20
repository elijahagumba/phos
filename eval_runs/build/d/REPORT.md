# Build D

Merged to `main` from `7ff682c`, in the order `build/d-reasoning`, then
`build/d-trusted`, then `build/d-queue`. ADR 0260. Each held-back batch was
scored once. None was repeated. `data-tiers.mdc` is unchanged. The gate was
not run.

## Lane Q

No ranker beat the champion. Familiarity tied it: 19 of 38 on HAI 20.07, and
20 of 20 on seeds 97601–97620. The other reorderings lowered recall within 8
alerts a shift on HAI 20.07 and were rejected.

The HAI 20.07 oracle ceiling is 21 of 38. Most A3 misses are shifts with more
attacks than top-10% slots, so not every attack can take the front of the
queue. That ceiling is a finding for any future queue metric.

v1's A3 stays 57 of 203 and is not reworded. The five-corpus gate is ADR 0234,
result name `atlas-queue-v2:familiarity-gate`. It was declared and not run.

## Lane R

On held-back seeds 97701–97720, 60 of 60 contentful leads were right, against
33 of 54 before. The held-back seeds come from the same five scenarios the
separators were designed around, so this shows generalisation across runs, not
to new scenario types. Seeds 97501–97520 were not opened, and that 33 of 54
stands.

W5 is not met. Its high flag is a Wilson 95% lower bound on the leads that
share one separation count. The largest such group in development is 15, and
15 right out of 15 has a lower bound under 0.8, so the flag could not come on.
That is a design flaw to fix, not evidence about the reasoning.

## Lane T

0 of 20 hostile known-station writes led on seeds 97901–97920. The two kept
facts, a write toward a limit against the plant's call and a write hidden by a
reading that does not move, attached on every hostile write and on no
authorised run, in development and held-back. What stopped them leading was
the fixed half weight under the residual prior, not the evidence. Known-link
indistinguishability and the frozen weights were not changed.

This is a simulated diagnosis. It is not the frozen known-station 0 of 16, and
it is not pooled with the unknown-master 1 of 4.
