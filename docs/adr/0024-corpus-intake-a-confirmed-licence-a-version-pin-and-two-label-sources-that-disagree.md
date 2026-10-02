# ADR 0024 — Corpus intake: a confirmed licence, a version pin, and two label sources that disagree

- **Status:** Accepted
- **Date:** 2026-08-21
- **PART:** C1 (corpus intake)
- **Supersedes:** nothing
- **Depends on:** [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0019](0019-the-settling-allowance-and-the-blind-window-it-is-bounded-by.md)

## Context

Atlas can read exactly two real industrial corpora, HAI and BATADAL, and both are water. Every
cross-plant claim the programme wants to make — generalisation across process types, a false-alarm
rate that survives more than one plant, command reasoning measured on real data — is blocked on the
same missing thing, and none of it is a modelling problem yet.

A data campaign vetted four candidates and left all four at "accepted, pending licence confirmation".
This record covers taking the first of them — a laboratory batch distillation column published on
Zenodo — from a manifest to a registry entry, and the decisions that acquisition forced.

The corpus was chosen over the other three because Atlas's batch weakness is currently probeable only
on a simulator PHOS wrote itself. ADR 0018 records that Atlas was wholly blind on the synthetic batch
reactor before phase-conditional modelling; ADR 0019 records the settling allowance and the blind
window it buys. Both fixes were commissioned by, and measured against, our own idea of what a phase
change looks like. A real batch process is the only thing that can say whether they generalise.

## Decision 1 — A licence is confirmed by two *surfaces*, not two fetches

The manifest set its own gate: "licence read once, from the paper's own text rather than from the
Zenodo record page. The Zenodo record's own licence field has not been read. This one needs both
reads before acquisition." That gate has been passed. The Zenodo REST API for the record returns
`"license": {"id": "cc-by-4.0"}` with `"access_right": "open"`, and the descriptor paper states the
same in prose.

**Two fetches of the same page are one read performed twice.** They catch a transient network fault,
not a wrong claim. This distinction is now written into `docs/data-campaign/README.md` as the
definition of the `Verification status` field, and it immediately reclassifies two other manifests:
`s7-data-modification` and `3w-petrobras` each record "two independent automated fetches" of a single
surface, so both remain **read once** and both remain behind the acquisition gate.

The vocabulary deliberately includes **unchecked** as distinct from any word implying a check was
performed and passed. That word is borrowed from `scripts/probe_cert_release.py`, which reports
"unchecked" rather than "compatible" when a release's events are absent
([ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md)
D4). An instrument that cannot tell those two apart is not worth having, and the rule generalises
beyond that probe.

## Decision 2 — The registry pins a version record, never a concept DOI

The manifest cited `10.5281/zenodo.17395543`. That is Zenodo's **concept** DOI: it resolves to
whichever version is newest, which today is record `21535243` at version `1.1.2`. A corpus identified
that way changes underneath a published number without anything in the repository changing, which
Constitution §3.7 forbids.

The registry therefore pins the version record id, the version string, the version DOI, and the
published MD5 of every file. All seven files were verified against those checksums on download. The
concept DOI is kept in `homepage` — it is the right thing to cite and the wrong thing to fetch — with
a `note` on the `version` block saying exactly that.

## Decision 3 — Acquire the 47.5 MB that is needed, not the 95.21 GB that exists

The deposit is 95.21 GB. Audio is 47.40 GB and images 38.18 GB — together 90% of it, and PHOS reads
neither. Zenodo serves files individually, which answers the question the manifest raised and could
not settle without trying.

What is fetched is labels, sensors, actuators, the plant information register, the operation logs,
the plant metadata and the modality matrix: **47.5 MB**. Recording the seven filenames with their
sizes and checksums rather than "the dataset" is what makes that subset reproducible; a future reader
who fetches the whole deposit and gets different numbers needs to be able to see why.

## Decision 4 — Where the paper and the files disagree, the files win, and the manifest is corrected in place

Reading all 119 shipped experiments contradicted the manifest twice. Both corrections are written
into the manifest and labelled as corrections, rather than the earlier claim being deleted — a
manifest whose errors vanish is not evidence of anything.

**The labels are not only in YAML.** The manifest stated they were, and budgeted an interval-to-row
join for them. The archive ships a per-row `Time,Label (anomaly)` CSV *and* the YAML ontology. The
join is not needed for detection, which also means no new dependency is needed: `pyyaml` is not a
PHOS dependency and the detection path does not make it one.

**`hasCategory` is temporal persistence, not cause.** The manifest attributed a "sensor data
compromise" category to it; the field actually holds `transient` (249), `recurrent` (51), `permanent`
(25) and null (200). The security-relevant register is real and lives in `Perturbation` and
`PerturbationMode`, and it is stronger than the manifest claimed: 49 records are
`Compromised sensor output (noise)`, and their `Perturbation` string names the seven sensors whose
output was falsified.

**What is left unresolved is left unresolved.** The per-row label takes values 0, 1, 2 and 3. The
integers do not correspond to the YAML `class` field — files labelled `{0,2}` occur with
`ConfirmedAnomaly` and files labelled `{0,1,2,3}` occur with `Anomaly` — so they are not a
confirmed/unconfirmed severity, and nothing in the shipped files says what they are. The registry
therefore treats non-zero as anomalous and carries
`"unverified_multiclass_meaning": true`. A guess recorded as a fact is worse than a gap recorded as
a gap.

## Decision 5 — Atlas fits only on experiments that *both* label sources call clean

All 38 `train_normal` experiments carry the label set exactly `{0}`. But **19 of those 38 carry YAML
anomaly records anyway**, classes `ConfirmedAnomaly` and `Anomaly`, one of them 20 records. The
corpus disagrees with itself about which of its own experiments are normal.

The baseline is fitted on the intersection — the experiments both sources call clean. This is the
conservative reading and it costs real data: 34.81 of 62.54 normal hours survive it.

**Why the stricter source wins.** A behavioural engine's entire claim rests on its model of normal.
Fitting that model on periods the corpus's own expert annotators marked as confirmed anomalies
teaches Atlas that an anomaly is normal, and the resulting false-negative is invisible — it looks
like a clean baseline and a quiet detector. The failure mode of the conservative choice is a smaller
training set and a noisier fit, which is visible in the numbers. Prefer the error you can see.

**The contaminated 19 are not discarded.** They are prepared as a separate held-out corpus, because
"experiments the label column calls normal and the annotators call anomalous" is a directly useful
probe: it asks whether Atlas sees what the annotators saw, using disagreement that already exists in
the published data rather than anything PHOS injected.

**Rejected: trust the label column, use all 38.** It is what the file naming intends and it keeps
62.5 hours. It also silently accepts the exact contamination that a behavioural baseline is least
able to survive and least able to report.

## Decision 6 — The first measurement uses one recipe family, and says so

The corpus spans three mixtures. Under Decision 5 the conservative fit set distributes very unevenly:

| Mixture | Operating points | Clean train | Contaminated train | Test |
| --- | --- | --- | --- | --- |
| `binary_ethanol+propan-2-ol` | 2 | 2 (2.67 h) | 0 | 2 (0.94 h) |
| `ternary_acetone+butan-1-ol+methanol` | 13 | 2 (1.87 h) | 6 (6.52 h) | 16 (19.32 h) |
| **`ternary_butan-1-ol+propan-2-ol+water`** | **35** | **15 (30.27 h)** | **13 (21.21 h)** | **63 (109.92 h)** |

Only the third has a usable conservative training set, and it happens to hold 30.27 of the 34.81
clean hours available anywhere in the corpus — so restricting to one recipe family costs 13% of the
fit set rather than two thirds of it. The scope reduction is nearly free, which is why it is taken.

**30.27 hours of declared-normal operation is the point.** ADR 0003 defines the ruler as false
positives per hour of *normal* operation, and a denominator that thin makes the rate meaningless.
This is the property that ranks this corpus above `data4cyber`, whose 1.6 normal hours cannot support
a false-positive claim at all however good its attack labels are.

Experiments carry a time-of-day clock with no date, so each is given its own synthetic date. That is
safe for the model being run and the docstring says why rather than asserting it generally:
`MahalanobisModel` fits a covariance over rows and scores each row independently, so order and
inter-experiment gaps change neither the fit nor the score. What per-experiment dating protects is
**grouping**, which collapses evidence by time window — distinct dates guarantee a window never spans
two experiments.

## Decision 7 — Two claims this corpus does *not* license

**It is not attack data.** The manipulations are engineered process perturbations performed by the
plant's own operators. Some of them — the 49 `Compromised sensor output (noise)` records — are a
genuine false-data-injection analogue, and that is worth a great deal, but a recall figure computed
here is **perturbation recall and may never be quoted as attack recall.** This is the same discipline
`ATTACKS_ARE_OURS_CAVEAT` applies to the synthetic library, for the same reason: the denominator is a
property of what somebody chose to do, not of what an adversary would do.

**The equipment register is a topology candidate, not a topology.** `plant_description_bd+v1_mapping.yaml`
declares 40 actuators, 14 equipment items and 29 sensors with owner-written descriptions, and the
anomaly records independently name physical locations. ADR 0010 ranks a finer topology as the highest
-leverage change available to Atlas, and this is the first corpus since HAI that could supply one from
documentation rather than from co-movement.

It is not one yet, and the reason is the failure mode ADR 0010 already documented. "HV001: Side-draw
valve between V001 and C001" and "TCU1: Circulating thermostat for HE001, HE002, HE003" place a
component on two or three units at once. That is a covering, not a partition, and `Subsystem`
membership is validated as a **total partition** at construction. Whether a partition can be honestly
authored from this register is an open question to be answered by reading it and rendering it for a
domain expert to falsify — not by taking the reduction number it would produce as evidence that it
was right.

## Consequences

**What is now true.** The corpus's licence is confirmed against two surfaces, its version is pinned
with per-file checksums, and its label semantics are recorded in `data/registry.json` from reading
all 119 shipped files. `docs/data-campaign/README.md` exists and defines the verification vocabulary
the four manifests already cite. `scripts/fetch_datasets.py --list` reads the new entry and correctly
declines to fetch it while its `prepare` step is absent. `uv run pytest tests/eval` passes 177 tests.

**What is deferred, and named rather than left to be discovered.** Three traps are recorded in the
registry `quirks` and are the preparation path's problem: the ragged label file whose 1,216 null tail
rows would become fabricated attack rows inside a *training* split under `default_attack_when`; the
`hasBeginning`/`hasEnd` fields that hold paired arrays rather than scalars for recurrent anomalies;
and the fact that 119 experiments are 119 timelines. The meaning of label classes 1, 2 and 3 needs
the descriptor paper. Whether phase-conditional modelling (ADR 0018) applies here at all depends on a
phase register this corpus has not yet been shown to declare — the operation logs are the place to
look.

**What this record does not claim.** No detection number. Nothing has been measured on this corpus;
it has been acquired, verified and described. The three remaining campaign manifests stay behind the
Decision 1 gate.
