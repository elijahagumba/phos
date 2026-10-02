# ADR 0010 — Topology is declared, never inferred, and HAI supports it only this finely

- **Status:** Accepted
- **Date:** 2026-08-06
- **PART:** 5B

## Context

PART 5A brought Atlas to 646 false positives per normal hour on HAI, a 13× improvement over
PART 3's per-signal Gaussian at identical recall, and precision of roughly 0.005. Some of that
remaining number is detection error. A material fraction of it is **counting** error.

When one physical disturbance occurs — a pump falters, a valve sticks, a level transmitter drifts —
every instrument on that unit leaves its expected range at the same instant. Atlas emits one
`Deviation` per departing signal, so ten sensors on one pump produce ten deviations and an operator
with ten things to investigate. There was one thing.

Nothing downstream can correct this today, because nothing downstream knows which signals share a
physical unit. `vectorise` treats the signal set as a flat vector. `MahalanobisModel` and
`PcaResidualModel` attribute a joint anomaly back to the breaking *signal*, correctly, and have no
concept of a breaking *unit*. The information needed to collapse ten deviations into one is not
statistical. It is a fact about plumbing, and it was not in the system.

## Decision

### 1. Subsystem membership is declared from documentation, never derived from the data

There is an obvious shortcut: cluster signals by how they co-move over the training window and call
the clusters subsystems. It is rejected, and rejected as policy rather than as a preference for
this PART.

**The argument is circularity.** Grouping exists to answer the question "did these deviations share
a cause?". If membership is itself derived from co-movement, that question is being answered with
the same statistics that raised the deviations. Signals would be grouped together *because* they
move together, and their moving together would then be counted as one event *on the grounds that
they are grouped*. Every reduction PART 5C reports would be real in the log and meaningless in the
plant — and, worse, the failure would be invisible, because a tighter cluster produces a better
reduction number.

Topology therefore comes from outside the data: process documentation, P&ID diagrams, the corpus
authors' published description of the testbed. It is a claim about how the plant is physically
wired, and it must be falsifiable by someone who has seen the plant.

Two mechanisms make that enforceable rather than aspirational:

- **Every `Subsystem` carries a mandatory `source`** naming the document the assignment came from.
  A blank or whitespace source is refused at construction. A subsystem whose source reads
  "clustered by correlation" is visibly wrong to a reviewer, which is the point of the field.
- **`render_topology` prints the whole map** — every subsystem, label, source and member, in sorted
  order — so a domain expert can check the claim by eye. This is the audit path, and it is required
  rather than optional.

`tests/atlas/test_hai_topology.py` asserts that no authored source cites co-movement.

### 2. Membership is a partition, and all five failure modes raise at construction

A signal belongs to exactly one subsystem. Construction refuses, naming the offending signals:

| Failure | Why it is fatal rather than a warning |
| --- | --- |
| **Unassigned signal** (in corpus, not in file) | A partially mapped corpus silently reverts to per-signal counting for the unmapped remainder — worse than no map at all, because the failure is invisible in every number 5C produces |
| **Doubly assigned signal** (in two subsystems) | 5C's grouping key is `(subsystem_id, time_window)`, which is only well-defined if membership is a partition rather than a covering |
| **Phantom signal** (in file, not in corpus) | Catches topology drift when a corpus is revised, and catches typos, which in a hand-authored file of 79 entries are close to certain |
| **Empty subsystem** | A declared unit with no instrumentation is not a physical unit |
| **Duplicate subsystem identifier** | Not among the four the PART lists, but `signals_in(subsystem_id)` is ill-defined without it, so the specified API requires it |

None is recoverable at runtime. `SubsystemMap` validates and then freezes: no mutation API, no lazy
population.

### 3. HAI's topology is process-level for the three real processes and per-machine for the simulation

This was the judgement call, and it is a **mixed granularity** rather than a uniform level. Six
subsystems over 79 signals:

| Subsystem | Signals | Basis |
| --- | --- | --- |
| `p1-boiler` | 38 | Process level |
| `p2-turbine` | 22 | Process level |
| `p3-water-treatment` | 7 | Process level |
| `p4-steam-turbine` | 7 | Per simulated machine |
| `p4-hydro-turbine` | 4 | Per simulated machine |
| `p4-power-grid` | 1 | Per simulated machine |

The rule applied is the PART's: author at the finest granularity the documentation actually
supports, and **where the documentation does not distinguish, do not distinguish**. That rule is
per-unit, not per-level, so a mixed outcome is the honest one here.

**The sole documentary source** is *HAI Dataset Technical Details*, document version 4.0, May 31
2023, the only manual the HAI repository publishes. Its git history holds a single commit, so the
21.03-era v2.0 revision named in its own change log is not retrievable.

**Finer granularity for P4 was available and taken.** The manual's P4 section identifies three
distinct simulated units — the steam turbine model and its generator (P4.1/P4.2), the hydro turbine
model and its generator (P4.3/P4.4), and the power grid model carrying local load demand and the
infinite bus (P4.5). Critically, membership is not read off the `ST_`/`HT_` name prefixes, which
would be exactly the name-pattern inference the PART forbids: it is read off the manual's own
per-point descriptions, every one of which names its machine outright ("Frequency deviation of
STM", "Output power of HTM", and for `P4_LD` the *total* electrical load demand as distinct from
the per-machine `P4_ST_LD` and `P4_HT_LD`). The assignment is explicit, total and non-overlapping
with no tie-break invented.

`p4-power-grid` holds one signal and therefore contributes no reduction at all. It is declared
anyway, because the alternative is folding it into a machine the manual does not put it on.

**Finer granularity for P1 was available and declined.** The manual decomposes the boiler into five
feedback control loops with individual diagrams (P1-PC pressure, P1-LC level, P1-FC flow, P1-TC
temperature, P1-CC cooling). That decomposition is not usable here for two independent reasons:

- **It is a covering, not a partition.** `P1_FCV03D` appears in two loops at once — commanded by
  P1-FC, and a feed-forward input to P1-LC. Resolving that needs a tie-break rule the manual does
  not state.
- **It does not cover the corpus.** The loop diagrams name only 26 of these 38 points. The other
  twelve — both main water pumps, the heating water pump and its supply pressure, the heating water
  tank's temperature and outflow setpoint, the `FT01`/`FT01Z` transmitter pair, and the DCS
  start/stop — appear in no diagram, and would need a residual bucket that is not a documented unit.

The physical-unit route fails too: Figure 1 names six vessels and systems, but the manual assigns
no data point to any of them, and eighteen of the 38 P1 points name no vessel in their description
either. A further defect makes any fine P1 split unsafe — `P1_FT01` and `P1_FT03` carry **identical
descriptions** in the manual ("Measured flowrate of the return water tank"), so the documentation
cannot distinguish two of its own flow transmitters.

**Finer granularity for P2 was available and declined**, again for two independent reasons. Figure 1
distinguishes a motor system (P2a) from a rotor system (P2b) but assigns no data point to either.
The two documented control functions, P2-SC speed control and P2-TRIP over-speed/over-vibration
trip, are not a partition: both take `P2_SIT01` as input. And three of the 22 columns — `P2_CO_rpm`,
`P2_HILout`, `P2_SIT02` — have **no entry in the manual's data-point table under any name**, so for
those the documentation supports no assignment below the process prefix in the column name itself.

**Finer granularity for P3 was unavailable.** The manual documents exactly one feedback loop for the
process, and all seven columns are its instrumentation and setpoints.

This is a real cost, stated plainly: with P1 whole, two simultaneous but unrelated boiler faults
collapse into one group, and 5C's reduction will look excellent while hiding the second event.
HAI's own attack table contains many such combinations (A302 fires P1-PC and P1-FC together). The
PART's guidance settles which error to prefer — a coarse but honest map is a usable input to 5C; a
fabricated fine one is not, and its wrongness would not surface in any number 5C produces.

### 4. Two documentation defects found and recorded

Both are recorded in `data/hai/topology.toml` and pinned by tests.

- **The manual's data-point table uses HAI 22.04/23.05 tag names.** Several 21.03 columns are named
  differently (`P2_ASD` for `P2_AutoSD`, `P2_MSD` for `P2_ManualSD`, `P2_VXT02`/`VYT02`/`VXT03`/
  `VYT03` for `P2_VIBTR01..04`), and three 21.03 columns appear under no name at all. Any tooling
  that joined the corpus to the manual on tag name would silently drop those rows.
- **The manual states HAI 21.03 carries 78 data points. It carries 79.** The claim appears twice
  (release-history table, and the 21.03 section). The manual's own column arithmetic in the same
  paragraph — 84 columns, one timestamp and four label columns — corroborates 79. Had the topology
  been authored from the manual's count rather than from the corpus, one signal would have been
  left unassigned; construction would have caught it, which is the invariant earning its keep
  before 5C exists.

### 5. `topology.toml` lives beside `manifest.json` and is committed

ADR 0006 established that dataset payloads are never committed and a corpus directory contributes
exactly one tracked file, its manifest. Topology joins it as a second tracked file, with a
`.gitignore` exception. The reasoning is the distinction ADR 0006 already draws: `topology.toml` is
not corpus payload. It is hand-authored from published documentation, it is not downloadable, and
`scripts/fetch_datasets.py` cannot regenerate it. Leaving it untracked would make the one file in
the repository that cannot be re-derived the only one not under version control.

## Consequences

**Good.**

- PART 5C has a single, well-defined source of physical-unit membership, and a grouping key that is
  well-defined because membership is a partition.
- The declared-not-inferred policy is enforced by the type system and the test suite rather than by
  discipline: `source` is mandatory, co-movement citations are asserted against, and the full map
  renders for expert review.
- The authored map is validated against the corpus's actual signal set, read from the loaded corpus
  rather than hardcoded, on **both** HAI files. A corpus revision that adds, drops or renames a
  column fails a test instead of silently leaving a signal unmapped.

**Bad, and accepted.**

- **The reduction PART 5C can demonstrate on HAI is bounded by this map's coarseness.** With P1
  whole at 38 signals, the theoretical ceiling for a P1-wide disturbance is 38 deviations to one,
  which flatters the mechanism; and two independent P1 faults are indistinguishable from one. 5C
  should expect a large apparent reduction on HAI and should not read it as evidence that the
  grouping is correctly resolved — only that it is correctly *implemented*.
- **A one-signal subsystem exists** and contributes nothing to any reduction.
- **Nothing here is measured.** This PART produces no `eval_runs/log.jsonl` entry, deliberately.
  Whether the grouping helps is 5C's measurement to make.
- **Only HAI has a topology.** BATADAL has none, so any 5C behaviour that requires a `SubsystemMap`
  is HAI-only until one is authored. BATADAL's 43 signals never had a false-positive problem
  (0.06 FP/normal-hour), so the pressure to author one is low.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Cluster signals by training-window correlation | Circular; see decision 1. The reduction would be real in the log and meaningless in the plant, and the failure would be invisible |
| Infer subsystems from signal-name patterns (`P1_FCV*`, `P4_ST_*`) | Name-pattern inference is the same failure wearing a citation. Where a prefix happens to agree with the documentation (P4), the assignment is made from the documentation's per-point descriptions instead, so the map would be identical for a defensible reason rather than a coincidental one |
| Author P1 at control-loop level with a tie-break and a residual bucket | Both the tie-break and the bucket would be invented, and `P1_FT01`/`P1_FT03` are indistinguishable in the manual. A fabricated fine map is worse than a coarse honest one |
| Uniform process level, folding P4 into one subsystem | Would discard an explicit, total, per-point assignment the manual states outright. "Where the documentation does not distinguish, do not distinguish" cuts both ways |
| Allow partial maps, falling back to per-signal counting for unmapped signals | The failure mode is invisible: the reduction number still looks fine while an arbitrary subset of the plant is counted the old way |
| Make `SubsystemMap` a Pydantic model | It maintains lookup indices derived from its subsystems, and the type exists precisely so those cannot drift from the declaration. A plain class with a validating constructor and read-only properties expresses that better; `VectorisedSeries` set the precedent for a non-Pydantic type where there is a reason |
| Store topology in `registry.json` alongside the corpus catalogue | The registry is machine-written by `scripts/fetch_datasets.py`. Topology is hand-authored and must not be adjacent to generated content, or the next regeneration will invite overwriting it |
