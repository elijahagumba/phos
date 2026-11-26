# ADR 0467 — A sealed batch's seeds never enter the repository, and its fingerprint does

- **Status:** Accepted
- **Date:** 2026-11-25
- **PART:** The referee, the sealed batch. No plant generated, no corpus scored in this record
- **Supersedes:** nothing. Adds a mechanism to what [ADR 0464](0464-the-sealed-corpora-live-only-in-an-encrypted-image.md)
  already decided about where sealed corpora live
- **Depends on:** [ADR 0464](0464-the-sealed-corpora-live-only-in-an-encrypted-image.md),
  [ADR 0117](0117-a-validation-corpus-may-not-be-tuned-against.md),
  [ADR 0143](0143-the-second-validation-look-is-spent.md)

## Context

The referee keeps four seed pools and enforces that a seed lives in exactly one of them
(`phos.referee.seeds`). It also enforces that no development or public seed draws from a sealed
generator family. Both rules are about keeping pools apart. Neither is about where the numbers in
the private pool came from.

That gap is not theoretical. A private pool is a JSON file. Its numbers are integers. Anyone who
opens it has the seeds, and a seed is all the generator needs to reproduce a plant exactly. So the
private pool has always been private in the sense that a drawer is private: shut, and easy to open.

The failure this ADR exists to prevent is specific. Suppose a batch is generated from seeds written
into a file that a person has read. That person can regenerate any plant in the batch, run a
detector against it, adjust, and run again. Nothing in the record would show it. The final score
would be presented as a first look at plants nobody had seen, and it would be a second look at
plants one person had seen many times. Every safeguard the project has about never reading the
sealed half is downstream of this, and this was upstream of all of them.

There is a second failure, less obvious and just as damaging. Even with seeds kept perfectly
secret, a batch can be *relabelled*. If nothing is committed that identifies which seeds an exam
used, then after a disappointing score somebody can generate a second batch, call it the sealed
batch, and there is no record to contradict them. A number nobody can tie to a fixed set is not a
measurement.

## Decision

**1. Seeds are read from the environment and never written.** `phos.referee.sealed_batch` builds a
`SealedBatch` only through `batch_from_environment`, which reads `PHOS_SEALED_SEEDS`. The type has
no field, no `repr`, no `str`, and no error message that carries a seed value. A test asserts the
`repr` and the parse-error message both name no seed, because "we remembered not to print it" is
not a guarantee.

**2. The repository commits a fingerprint, not the seeds.** The fingerprint is a SHA-256 digest
over a version tag (`phos-sealed-batch-1`) followed by each pair, sorted by `(family, seed)`, with
explicit separators. Sorting is part of the format, so re-listing the same set gives the same
digest. The version tag is part of the format, so a change to the encoding produces a different
digest rather than a silently different meaning under the same name.

**3. A batch cannot be relabelled.** `check_against_registered` refuses a batch whose recomputed
digest is not the registered one. This is the mechanism that turns "the sealed batch" from a
description into an identity.

**4. Two refusals stop a batch being built from already-seen plants.** A sealed seed that already
lives in the development, public or retired pool is refused, because a seed a detector was tuned
against cannot stand in for a secret. A sealed batch drawing from an open family is refused,
because an open family plus a guessed seed regenerates a plant, which would make the seal a label.

**5. The batch is registered, in a registry of its own, and registered before it exists.**
`data/sealed-registry.json` carries `phos-referee-sealed-1` with the family, the plant count, a
fingerprint and an explicit note that the batch has not been generated. It is deliberately not
`data/registry.json`: that file is the catalogue of public corpora, every entry there has a
homepage and a licence, and several tests assert its exact contents because the tier resolver
reads it. A sealed synthetic batch has no homepage, no licence and no URL, and putting one there
would have meant weakening tests about public corpora to make room for something that is not one.
The placeholder fingerprint is 64 zeros, which no real seed set produces by accident and which
`check_against_registered` refuses.

## What this does not do

**It does not produce the batch.** Generating it needs loopback network addresses, an encrypted
volume Spotlight does not index, roughly two hours with the machine awake, and an administrator
password. That is a human step, and it is handed over rather than run.

**It does not measure the seed space.** A digest over seeds is only as secret as the number of
candidate sets. If a family drew from a small integer range, anyone holding the digest could
enumerate sets until one matched. The seal rests on seeds being chosen large enough that this is
infeasible, which is a property of how seeds are chosen, not of this code. No bar in E-0016 claims
otherwise, and the registry entry says so in its own caveat.

**It does not make the batch a good exam.** A perfectly sealed batch of easy plants is still an
easy exam. Every bar in E-0016 would pass. Sealing protects a measurement from being tuned
against; it says nothing about whether the measurement is worth taking.

## Alternatives refused

**A private pool file, kept out of the repository.** This is what exists, and it is refused as
sufficient for the same reason a drawer is not a safe: the numbers are readable by anyone who
opens the file, and nothing records which numbers were used.

**Registering the batch in `data/registry.json`.** Tried first, and refused by the repository's own
tests: that schema requires a homepage string, and its role vocabulary is development, validation
and held-out, with no sealed among them. The honest reading was that the public catalogue is not
the place for this, rather than that the tests should be widened. The failure was caught before it
was committed, and the separate registry was built instead.

**A hash of the generated plants rather than of the seeds.** Refused because it requires generating
the batch to register it, which means the thing being kept shut has to be opened to write down that
it is shut. It also makes registration depend on the generator being unchanged: a generator fix
would invalidate the registration of a batch whose plants were already generated.

**Encrypting the seed file and committing the ciphertext.** Refused because the key becomes the new
secret with no better handling, and because a ciphertext in the repository is a durable thing an
attacker can work on at leisure. A digest discloses strictly less.

## Consequences

- The sealed batch's seeds exist in one place: an environment variable pointing at a file on the
  encrypted volume. Losing that file loses the batch, and the fingerprint will show a mismatch
  rather than letting a different batch take its place.
- Every sealed run must present the batch and have it checked against the registered digest. A
  batch that does not match is refused, not warned about.
- The `phos-referee-sealed-1` registry entry stays at `status: declared` and its fingerprint stays
  null until a human generates the batch. A later record fills both in.
- Nothing in this record was scored, and no plant was generated.
