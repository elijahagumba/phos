# Data hygiene and label disagreements

**What this is:** the rules for bringing data into PHOS — licence, version, labels, and what happens
when two “official” sources disagree.

**Why it exists:** a beautiful detection number on a corpus you were not allowed to use, or on
labels that do not mean what the paper said, is not a result. It is a liability.

## Two keys before you copy the filing cabinet

A dataset is not acquired until its licence is **confirmed on two independent surfaces** — for
example the repository’s structured licence field **and** the paper’s own sentence. Two downloads
of the **same web page** are one read performed twice. They catch a network glitch, not a wrong
claim.

Statuses used in the campaign:

| Status | Meaning |
| --- | --- |
| Unverified | Licence known only from a third party |
| Read once | One surface. Enough to keep evaluating. **Not** enough to acquire |
| Confirmed | Two surfaces agree. The acquisition gate |
| Unchecked | We have **not** examined this property. Distinct from “checked and fine” |

Analogy: you do not buy a house because two estate-agent printouts of the **same** listing agree.
You want the land registry *and* the survey.

## Pin the edition, not “whatever is newest”

Zenodo (and similar hosts) have a **concept** DOI that always points at the latest version. PHOS
pins the **version record**, version string, and file checksums. Otherwise last month’s published
number silently starts describing next month’s files.

Payloads are **never committed** to git. A registry and per-dataset `manifest.json` are. Anyone
can recreate the run; nobody copies 13 GB of CERT into GitHub.

## The files beat the paper

If the README says column `user` and the CSV has no such column, **the CSV is the fact**. Manifests
that were wrong are **corrected in place**, with the old claim still readable. A document whose
errors vanish is not evidence.

BATADAL’s `-999` means “not labelled,” not “attack.” PHOS’s naive default would have treated almost
the whole test set as under attack. That trap is why real-corpus tests exist.

Integer classes with **unverified meaning** stay unverified. Guessing that `2` is “worse than `1`”
and writing it down as fact is worse than recording a gap. The distillation classes stayed
unverified until the corpus's own paper named them (ADR 0082), and the files were checked
against it before the reading changed.

## When two label sources disagree: both doctors must clear the patient

On the distillation corpus, every “train normal” file has a numeric label column of all zeros —
*and* **19 of 38** still have YAML notes calling the run an anomaly. The corpus disagrees with
itself about which experiments are healthy.

Atlas **fits only on the intersection**: experiments **both** sources call clean. Why the stricter
reading wins:

Teaching “normal” from hours an expert marked as a confirmed anomaly **poisons the baseline**.
The detector then treats that pattern as healthy. The miss is **invisible** — a quiet, confident
wrong model. The conservative choice costs training hours and may look noisier. Prefer the error
you can **see**.

The 19 “contaminated” runs are not thrown away. They become a **held-out probe**: *does Atlas see
what the annotators saw?* That question is reserved; it is not today’s baseline.

## Perturbation is not cyber-attack

On the distillation column, labelled “anomalies” are often **engineered process knobs** turned by
the plant’s own operators so researchers can study detection methods. Catching those is
**perturbation recall**. Quoting it as **attack recall** would be like scoring a fire drill as a
real fire. The source note on every logged run says so.

## Packing our own plants is not a licence shortcut

When a public corpus cannot be acquired, PHOS may **expand the simulator it already ships**. That
is the [dataset library](14-the-dataset-library-is-not-a-public-corpus.md): catalogues committed,
payloads regenerated, caveats on every log row. It does **not** reopen the licence gate, and it
does **not** turn library recall into HAI or CERT recall.

## What this is not

- Not a decision to use every "accepted" campaign candidate. Licence is now **confirmed** on
  `data4cyber`, `s7-data-modification`, and `3w-petrobras`; none is acquired; none is a 2–3/day
  budget claim ([ADR 0033](../docs/adr/0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)).
- Not permission to fetch 95 GB of audio and images because they sat next to 47 MB of telemetry.

## Where to read more

- Campaign: `docs/data-campaign/README.md`
- Decisions: [ADR 0006](../docs/adr/0006-dataset-registry-and-never-committing-data.md),
  [ADR 0024](../docs/adr/0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md),
  [ADR 0029](../docs/adr/0029-synthetic-dataset-library-is-not-a-public-corpus.md)
