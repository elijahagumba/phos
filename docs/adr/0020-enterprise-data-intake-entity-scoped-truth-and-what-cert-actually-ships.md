# ADR 0020 — Enterprise data intake: entity-scoped truth, a reused ruler, and what CERT actually ships

- **Status:** Accepted
- **Date:** 2026-08-19
- **PART:** 6·D
- **Supersedes:** nothing
- **Depends on:** [ADR 0001](0001-ontology-value-objects-and-store-enforced-integrity.md),
  [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0004](0004-first-real-dataset-and-the-operator-manifest.md),
  [ADR 0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md)

## Context

Sentiel is the enterprise/cloud engine, and this is its first PART. It deliberately builds **no
detection**: no behavioural models, no peer grouping, no templates, no engine. Those are 6A, 6B and
6C.

It exists because of how Atlas went. Atlas's reasoning layer was designed and built before
attack-dense real data arrived, and when the data came the layer was found to be starved — evidence
too thin to move a hypothesis, an evidence-weight ceiling nobody had measured. The remedy is
ordering: get the real, labelled corpus readable **first**, so every later Sentiel PART is measured
against it from its first commit.

The corpus is CERT Insider Threat (CMU/SEI). It was chosen over LANL because LANL's download links
are dead and access is request-gated, which the acquisition rules forbid working around.

---

## Decision 1 — One normalised `EnterpriseEvent`, and `Observation`s only after aggregation

An enterprise corpus is not a signal matrix. It is several logs of discrete, irregular events tied
to people. Two layers, not one:

- **`EnterpriseEvent`** — `timestamp`, `user_id`, `event_kind`, and a `str -> str` `details` map
  keyed by exported constants. One shape for all five logs, so adding a sixth changes the reader
  and nothing downstream. It is **not** an ontology object: it is raw input.
- **`Observation`** — produced by `phos.sentiel.featurise` by aggregating events into per-`(user,
  day, feature)` counts, with `entity_ids=[ent_<user>]` and `domain=SENTIEL`.

The ontology is therefore entered at exactly one point, and PART 3's models and PART 2's harness
work on Sentiel data with no changes at all (Constitution §3.1).

`details` is `str -> str` for the same reason `Entity.attributes` and `Observation.context` are:
it stays serialisable and no component can hide typed state in it. Multi-valued entries are joined
with `;`, which is what CERT's own recipient lists use.

**Entity ids are derived, not minted.** `user_entity_id("CSF0929") == "ent_CSF0929"`, reversible via
`user_id_of`. `phos.ontology.new_id` mints a random id, which is right for objects PHOS *creates*
and wrong for objects PHOS is merely *naming* — a random id would make two runs over one corpus
disagree and break reproducibility (Constitution §3.7). For the same reason `Entity.created_at` is
stamped from the LDAP snapshot's month rather than `utc_now()`.

---

## Decision 2 — Ground truth is entity-scoped, and flattening it would be a category error

**This is the load-bearing decision of the PART.**

PART 2's `LabelledInterval` says "the corpus was under attack between these two instants". For
Atlas that is the whole truth: an attacker manipulating a pump is attacking *the plant*, and every
alert inside the window concerns the same event.

For an organisation it is not the truth at all. When CERT says user `CSF0929` was malicious through
July 2010, an alert about user `ABC1234` on 14 July is **wrong** — it names an innocent person —
and a time-only matcher scores it as a hit.

The arithmetic settles it. **r3.1 labels 2 malicious users out of 1000.** A detector that alerted on
every user every day would score a *perfect* time-only window recall while being wrong 99.8% of the
time. Time-only labelling does not merely lose precision here; it removes the corpus's ability to
distinguish a working detector from a broken one.

So `EntityLabelledInterval` carries `user_id` alongside the window and `contains(user_id, timestamp)`
requires **both** halves to match. `as_labelled_interval()` exists to project to PART 2's type, and
its docstring states the one condition under which the projection is sound: the result must be
matched only against detections already restricted to that same user.

The same reasoning applies to the false-positive **denominator**, which is easy to get wrong
quietly. Entity-aware normal time is summed per user; a time-only reading subtracts the malicious
windows from the corpus's single span. On the PART's own fixture — two users, one labelled for all
but a minute of a day — that is 24 h 1 min against 1 min, a **1440×** difference, and every Sentiel
false-positive rate would have been inflated by that factor. `normal_hours` on a Sentiel report is
therefore per normal **user**-hour, stated in `source_note` on every run, and **not comparable to an
Atlas FP rate**.

### Rejected: teaching PART 2's `LabelledInterval` about entities

Rejected because PART 6·D is explicitly forbidden from modifying PART 2, and because it is the
wrong home anyway: an OT label genuinely has no entity, so the field would be optional-and-ignored
in the domain that uses the harness most.

---

## Decision 3 — Reuse the PART 2 harness by partition; do not fork it, do not modify it

The mechanism is one observation:

> Within one user's slice of the corpus, time-only matching and entity-scoped matching agree
> exactly.

So `evaluate_entity_aware` partitions the corpus by user, makes each slice an ordinary PART 2
`Dataset` carrying only that user's windows and only that user's alerts, and calls PART 2's own
`window_recall`, `false_positives`, `detection_latency`, `recall_sample`, `reliability_table`,
`expected_calibration_error`, `brier_score` and `sweep_thresholds` on the slices. Results pool by
count: recall is asked one window at a time so each answer is 1 or 0 and the pool is an exact
integer; reliability tables pool by bin population.

Consequences, both deliberate:

- **Every matching decision, including how `match_tolerance` widens a window, is made by PART 2.** A
  change to the ruler changes Sentiel's numbers too, which is what "one ruler" has to mean.
- **A user with no labels contributes every alert as a false positive** — the correct and expensive
  answer, and where a peer-blind detector loses its precision.

`evaluate_entity_aware` returns a **PART 2 `EvaluationReport`**, so Sentiel runs land in the shared
experiment log through the same `append_to_experiment_log`, with no second report type to reconcile.
It **refuses** a `Dataset` that still carries time-only `attack_intervals`, so the error this ADR
exists to prevent cannot be reintroduced by a caller.

Two things are assembled outside PART 2 and are named here rather than buried: the entity-aware
true-positive predicate (`entity_aware_detections`), which is the one primitive PART 2 cannot
supply; and pooled ratios (precision, FP rate), assembled from PART-2-computed numerators and
denominators.

**Candidate future harness extension.** If PART 7 or a later Sentiel PART wants this natively, the
smallest sound change is a `Detection`-to-`LabelledInterval` match *predicate* injected into PART 2's
metrics, defaulting to today's time-only behaviour. That is recorded as a candidate, not adopted.

### Rejected: laying the per-user timelines end to end

An elegant alternative makes time-only matching equal entity-scoped matching by offsetting each
user's timestamps into a disjoint segment, so a single unmodified PART 2 call computes everything
exactly. Rejected on a concrete defect: with any non-zero `match_tolerance`, an alert near a
segment boundary bleeds into the next user's segment and matches *their* window. Guarding it needs
inter-user gaps, which then corrupt the normal-time denominator. A subtly wrong ruler is worse than
a slightly inelegant one.

---

## Decision 4 — A per-entity **starter** feature set, and the code says so

Eight count features over a one-day window: `logon_count`, `distinct_pcs`,
`off_hours_logon_count`, `removable_device_connects`, `file_access_count`, `distinct_files`,
`external_email_count`, `distinct_http_hosts`. Each maps to a published CERT scenario; the mapping
is tabulated in `phos.sentiel.featurise`'s docstring.

Every one of them describes **one user in isolation**. There are no relationship features (6A) and
no peer-group context (6B), so a user is judged against their own history and never against their
team's. The baseline will therefore miss exactly the insider whose own history is unremarkable and
whose peers' is not — and that miss, measured, is the argument for 6B rather than an assertion that
6B is needed.

Two supporting choices:

- **A window a user was active in emits all eight features, zeros included.** An absent zero would
  narrow a quiet feature's learned band to only the days it happened to fire, which is a materially
  different and much tighter band. A window with *no* activity emits nothing: it was not observed.
- **"External" is read off the corpus, not typed in.** `EntityCatalogue.dominant_email_domain()`
  returns the organisation's own mail domain from LDAP (`dtaa.com` for CERT), and the baseline
  script passes it. `Featuriser.org_domains` remains configurable.

---

## Decision 5 — What CERT actually ships, which is not what its schema says

The reader declares, per log, the columns it **requires** and the ones it knowingly **ignores**; a
missing required column raises, and an *unrecognised* column also raises. Strictness paid for itself
immediately.

| Discovery | Verified against | Consequence |
| --- | --- | --- |
| **r3.1's `email.csv` has no `user` and no `pc` column.** Its header is `id,date,to,from,size,attachments,content` | the file itself, 2026-08-19 | The actor exists only as the `from` address and must be resolved against `LDAP/`. `CertReader.for_release` builds that index. A reader trusting the published schema would have produced **no email features at all** |
| The release's own `readme.txt` calls the attachment column `attachment_count`; the header says `attachments` | file vs readme | **The header is the authority.** Documentation about a corpus is a claim; the corpus is the fact |
| `file.csv` rows are file copies **to removable media**, not general file opens | `readme.txt` | `file_access_count` and `distinct_files` mean "copied out" in r3.1 |
| Removable-media wording is `Connect`/`Disconnect` in r3.1, `Insert`/`Remove` in r2 | both releases | Both vocabularies map to the same `EventKind`; the raw word is kept on `DETAIL_ACTIVITY` so the mapping stays checkable |
| `LDAP/` is 18 monthly snapshots; population falls 1000 → 897 | the directory | Snapshots merge last-wins, so a departed user is **kept**, not deleted. `directory_as_of` records the version read |

A user absent from the directory is **never dropped**. `entity_for` synthesises a real `Entity`
marked `ABSENT_FROM_DIRECTORY` with no invented role, and `absent_user_ids` reports the gap.
Silently discarding their events would shrink the corpus while every downstream number still looked
fine.

**Memory strategy.** The five logs are streamed row-by-row and merged with `heapq.merge` on the
timestamp, so peak memory is a handful of rows plus the heap rather than the corpus — r3.1 unpacks
to ~13 GB, of which `http.csv` is 11 GB. The merge is only correct if each file is itself sorted, so
that is *checked while streaming* and raises the moment a timestamp goes backwards. Rows are read
with `csv.reader` and indexed by position, so the ignored free-text `content` columns are never
materialised.

**Timestamps** are naive local wall-clock in the source and are read as **UTC**, matching
`LabelledCsvAdapter`'s documented choice. Every event and every label shifts by the same unknown
constant, so no interval, duration or ordering is affected — and "8pm is off-hours" stays a
statement about the corpus's own clock, which is what the featuriser wants.

---

## Decision 6 — Which release, and two registry defects found on the way

The PART suggested "r1 / r3.x". **r1 is not a candidate**: `answers/insiders.csv` has no r1 row, so
r1 contains *zero* labelled insiders and no recall number can come from it. Sizes were confirmed
against the figshare API for record 12841247 rather than copied from the article page:

| Release | Compressed | Labelled insiders |
| --- | --- | --- |
| r1 | 87.5 MB | **0** |
| **r3.1** | **4.25 GB** | **2** (scenarios 1, 2) |
| r3.2 | 4.29 GB | 2 |
| r4.2 | 4.82 GB | 70 |
| r2 | 8.66 GB | 1 |
| r6.2 | 23.81 GB | 5 |

r3.1 is the smallest release that carries labelled insiders, and was fetched with explicit operator
consent (it is 13× the registry's 300 MB size-confirm threshold).

Two defects in the committed registry were found and fixed:

1. **The deferred `r1.tar.bz2` entry pointed at figshare file `24844280`, which is `r6.2.tar.bz2` —
   23.8 GB — while declaring `size_bytes: 87541633`.** The size gate reads the *declared* size, so
   it would have waved a 23.8 GB download straight through. Corrected to `24857825`.
2. **The licence was recorded as CC BY 4.0 only.** See below.

`scripts/fetch_datasets.py` gained the minimum needed: SHA-256 verification against the publisher's
own `CHECKSUMS-sha256.txt` (a size match is a weak claim about a 4.25 GB transfer), archive
extraction with `filter="data"`, and `sentiel-manifest.json` for a multi-file event corpus.

That manifest is deliberately **not** named `manifest.json`: that name is claimed by the
labelled-CSV manifests which `tests/eval/test_real_dataset.py` discovers by glob and validates
against `LabelledCsvAdapter`'s field set. A CERT release has no single CSV path to give that
adapter, so writing one under the shared name would have broken a PART 2 test from the outside.

---

## Decision 7 — Record both licences, because the corpus ships two and they disagree

figshare's metadata for record 12841247 states **CC BY 4.0**. The payload ships its own
`license.txt` — in both `answers.tar.bz2` and `r3.1.tar.bz2` — which is an **ExactData, LLC End User
Agreement**, © 2011, under SEI agreement #12-00121-EXP-000. Its Grant of Rights (a) prohibits
redistribution or making the data available to any unauthorized party; (c) permits derivative works
such as reports and research papers that incorporate the data only to the minimal extent necessary
to describe measured performance.

These are not the same licence, and it is not this project's place to decide which one governs. Both
are recorded — `license` and the new `payload_license` field — and the fetch script logs a warning
naming the conflict on every run.

PHOS's existing practice satisfies **both** readings, which is why no behaviour changed: the payload
is git-ignored and never redistributed (ADR 0006), and only aggregate metrics are reported.

---

## Decision 8 — CERT is synthetic, and that travels with every number

`SENTIEL_CAVEATS` is exported **as data**, stamped into `Dataset.source_note` by
`sentiel_source_note`, and therefore copied onto every `EvaluationReport` written to the experiment
log. A test asserts all three are present. They cannot be read apart from the numbers:

1. **CERT is SYNTHETIC.** Simulated users, simulated attackers, generated by ExactData's DDG tool. A
   good number demonstrates the machinery works; it does not demonstrate real-world capability, and
   simulated insiders may be cleaner and more obvious than real ones.
2. **The featurisation is a per-entity STARTER set.** No relationship context, no peer baselining.
3. **Ground truth is ENTITY-SCOPED**, and the FP denominator is normal user-hours, not wall-clock
   hours.

The base rate is reported alongside, because at 2 labelled users in 1000 the evidence-weight ceiling
that starved Atlas ([ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md))
may well apply here too.

---

## Consequences

- Sentiel can read a real, labelled enterprise corpus, and every later Sentiel PART is measured
  against it from its first commit. The ordering failure that starved Atlas is not repeated.
- PART 2 is untouched — package *and* tests. A test asserts `git diff HEAD -- src/phos/eval` is
  empty, and that Sentiel's metric symbols are PART 2's own function objects rather than copies.
- Sentiel's false-positive rate is in **user-hours** and must never be compared with an Atlas rate.
- The reader is strict, so a different CERT release will **raise** rather than mis-read. That is the
  intent; the error names the columns and says to teach the reader.
- The blind spot is stated and is the next PART's job: a per-entity model cannot see the insider who
  is normal for themselves and abnormal for their peers.
