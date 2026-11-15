# ADR 0441 — A drawn float is rounded, because a draw is not bit-reproducible across architectures

- **Status:** Accepted
- **Date:** 2026-11-15
- **PART:** R1–R5 debt
- **Supersedes:** nothing
- **Depends on:** [0438](0438-the-generator-reproduces-itself-and-the-batch-describes-itself.md), [0435](0435-a-family-draws-a-plant-and-one-family-is-sealed.md), [0434](0434-a-plant-is-a-document-and-its-physics-is-a-named-template.md), [0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md)

## Context

**CI has been red on the `claude/phos-master-build-spec-e76e78` branch since 12 November, on every
one of ten pushes, and it was not looked at.** `main` was green at `ffd2718` throughout. One test
failed, the same one each time:
`tests/synth/test_golden_corpora.py::test_every_standard_corpus_matches_the_golden_record`, added by
PART R1 as the safeguard behind the declarative refactor. Everything else was green — 6,179 passing
on the first failing run, 6,525 on the last.

That is the plain fact and it is recorded first, because R1 through R5 were each reported as verified
on the strength of the local suite alone. Constitution §8.1 asks that the tests pass; the standing
instruction in this repository is that *done* means verified, and verified includes a fully-run
green CI. It was not met, and five records' "Verified" paragraphs are true about the lab and silent
about CI.

## Decision 1 — The diagnosis, which is not what the first hypothesis said

The failure named six differences, one per corpus, every one of them the `manifest_sha256` field.
**No per-file digest differed**, which already said the telemetry, topology and capture were
byte-identical and only the manifest *document* had moved.

The first hypothesis was that the manifest carried a platform-sensitive derived float introduced by
R1's `PlantSpec` rendering. It was wrong, and checking it rather than acting on it is why this
record is short. Three measurements, in order:

1. A temporary worktree at `origin/main` on this machine produced digests **exactly equal to the
   golden record**, and so did `HEAD`. So R1–R5 had not moved the manifest at all; the difference
   was the machine, not the branch.
2. The twelve full-precision floats in a manifest all sit in `events[].parameters` — the benign
   event schedule, which predates this branch entirely and comes from `float(rng.uniform(lo, hi))`.
   A uniform draw *should* be pure IEEE arithmetic on a platform-independent bit stream, so the
   hypothesis predicted no difference at all.
3. So the manifest was generated inside a `linux/amd64` container with the locked dependencies. It
   reproduced CI's digest exactly, and a field-by-field comparison of the two documents found
   **one differing leaf out of 404**:

   | | `.events[0].parameters.clearwell_level_setpoint_m` |
   |---|---|
   | macOS, arm64 | `3.55187675975025` |
   | Linux, x86-64 | `3.5518767597502494` |

   One unit in the last place.

**So a drawn float is not bit-reproducible across processor architectures.** `numpy`'s `uniform`
computes `low + (high - low) * x`; on arm64 that multiply-add can be *fused*, rounding once where
x86-64 rounds twice. `log_uniform`, added in R2, is worse: it passes through `math.log` and
`math.exp`, whose last bits are a property of the platform's libm rather than of the standard.

## Decision 2 — Round at the draw, not in the document and not in the check

Three fixes were possible and the narrowest two were declined.

**Canonicalising the golden check** — hashing a float-normalised manifest — would have turned CI
green while changing nothing. The manifests on disk would still differ by architecture, so the
reproducibility claim would stay false and merely stop being checked. This repository's rule for
that situation is to write the record saying so, not to adjust the instrument.

**Rounding only when the manifest is written** would make that one document architecture-independent
and leave every other artefact carrying a raw drawn float, including the `plant.json` and
`manifest.json` of a generated plant, which PART R5's audit compares byte-for-byte.

**So the rounding happens at the draw**, in `phos.synth.randomise.settled`, applied inside
`StreamDraw.uniform` and `StreamDraw.log_uniform` and at the benign-event parameter draw in
`phos.synth.plant`. Every consequence of a draw — the description, the manifest, the physics the
value drives — then follows from the same number on every machine, rather than from a number that
agrees only as far as the next thing to round it.

**Twelve significant digits**, not decimal places: a gain of 1e-4 and a capacity of 1e6 keep the
same relative precision, and twelve sits about four orders of magnitude clear of where a 1-ULP
difference lives while remaining far finer than any physical quantity this package models.

**It is a mitigation, not a proof, and the record says so.** A 1-ULP difference landing exactly on
the twelfth-digit rounding boundary would still diverge, and no rounding scheme can rule that out.
What would catch it is the arrangement that caught this: development on arm64, and CI running the
golden corpus check on x86-64.

## Decision 3 — What moved, and the recapture is justified rather than assumed

`scripts/synth_golden.py` says, in its own words, that a mismatch is a result and not a thing to fix
by recapturing. The golden record **is** recaptured here, so the justification has to be explicit.

The change moved **six values: the six `manifest_sha256` fields, and nothing else.** Every per-file
digest, record count and byte size in the committed record is unchanged — six insertions and six
deletions in `tests/synth/golden/corpus_digests.json`. The corpora's *data* did not move; one field
of their *documents* did, from a setpoint now written to twelve significant digits. The digests that
would have caught a changed corpus are the ones that did not change.

## Consequences

**The claim is now demonstrated rather than assumed.** The full golden capture — all six corpora,
every per-file digest and every manifest digest — is **byte-for-byte identical on macOS/arm64 and
Linux/x86-64**, compared by generating it on both. That is the first cross-architecture
reproduction in this repository, and it is what PART R5's "the same seed writes byte-identical
files on another machine" needed in order to be true as stated. Before this change it was true
only on one architecture, and the public front page's testing section now carries that.

**Six tests hold the property.** `TestDrawsAreSettledForCrossArchitectureReproducibility` pins the
rounding, pins that the two values actually measured settle to the same number, and pins that
rounding never pushes a draw outside its declared bounds.

**What this does not fix.** Any float this package computes and writes at full precision from
somewhere other than a draw remains architecture-sensitive in principle; only the draw sites are
settled. Nothing in R1–R5 writes such a value today, and the golden check on CI is what would
notice if something began to.

**No measurement.** No score, no detector, no corpus opened, no harness run. No frozen number is
requoted or moved; v1 stays **8 of 12** and `current_session` stays **P1**. The six corpora's data
files are byte-identical to what they were before this branch, which is the property ADR 0434 set
the golden record up to protect.
