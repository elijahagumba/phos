# The PHOS refusal register — what PHOS cannot do, and what would lift it

**This is a deliverable, not documentation of one.** It is the map of the boundary between what PHOS
knows and what it wishes it knew. Item **U6** of the Usefulness Phase (ADR 0074) establishes it;
every item of that phase that establishes a new limit appends to it.

Read it as a specification, not as a list of excuses. Every entry carries three things, and an entry
missing the third is incomplete:

1. **The refusal** — what PHOS will not claim.
2. **The evidence** — the measurement or the absence that establishes it.
3. **What would lift it** — the thing PHOS needs from the world, named concretely enough that
   somebody could supply it.

The third column is why the register is worth keeping. Collected, it *is* the list of what PHOS needs
from a design partner, a corpus author, or a plant — and U7's outreach ask is assembled from it.

---

## 0. The append procedure

The standing procedure in `docs/usefulness-phase-roadmap.md` §0 references this section.

1. **Append the moment a refusal is established**, not at the end of an item. A refusal discovered in
   passing and written down next session is a refusal that was briefly unrecorded.
2. **One entry per refusal.** If a measurement establishes two limits, it gets two entries.
3. **Cite the record.** An ADR, a report path under `eval_runs/`, or a test that pins it. An entry
   whose evidence is a memory is not evidence.
4. **Fill in what would lift it.** If nothing would — if the refusal is a statement about
   mathematics rather than about evidence — say that explicitly in the column rather than leaving it
   blank.
5. **Never delete an entry.** A refusal that is lifted is **struck through** with the date and the
   thing that lifted it, so the register records that the boundary moved rather than pretending it
   was always elsewhere.
6. **Register the item.** Add the U-item or session that established it, so the register can be read
   against the phase.

---

## 1. Established before the Usefulness Phase

These six are the seed set named in ADR 0074. Each was established by its own session and already
carries a record.

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R1 | Cannot distinguish an attacker from legitimate maintenance without work-order evidence | Both leave the same evidence on the wire and in the process; only priors separate them. ADR 0014, 0027, 0069 | A CMMS work-order export covering the capture window, reaching the inlet Session E3 built (ADR 0069): unit, window, authorised actor |
| R2 | Cannot validate peer-relative insider detection | No corpus contains a suitable labelled peer-relative case. The peer claim was retired rather than weakened. ADR 0060 | A labelled insider corpus with more than one business unit and declared peer groups — CERT r3.1 puts all 1,000 employees in one unit (ADR 0072) |
| R3 | Cannot claim cross-plant generalisation | No commercial-safe gas corpus exists (ADR 0067). Benchmark v1 HAI→BATADAL stays REFUSED: different column names are not a protocol. ADR 0063 declared three physical roles and measured BATADAL→HAI zero-shot at **1078.99** FP/normal-hour against native HAI **646.58** — transfer is **louder**, so the measurement exists and still cannot carry a generalisation claim | A transfer that is not louder than the in-plant ruler on a declared shared schema, or a third process (gas) that actually generalises. SWaT remains form-gated |
| R4 | Cannot claim operational usefulness from synthetic data | It is our model, our adversary and our maintenance practice. A system cannot be validated against its own assumptions. ADR 0029, 0073 | Real plant data, or plant-literate subjects sitting U5's Latin-square protocol. U5 ran a mechanical non-operator check and did not lift this (R25). Recruiting is U7, not started (R26) |
| R5 | Cannot rank the Atlas operator queue | No severity the engine carries orders it usefully. `magnitude` and `breadth` rank *towards the noise*; `weight` is a 424-way constant. ADR 0068, `eval_runs/atlas/hai-operator-queue.md` | A severity built from something other than distance from the fitted manifold — persistence across windows, coincidence across subsystems, or the absence of a covering work order. None is started |
| R6 | Cannot claim a labelled public command corpus exists | It does not. Searched and recorded rather than assumed. ADR 0040, 0058 | A published ICS capture with labelled command writes and a declared master/station map |

---

## 2. Established by U1 — the Atlas error taxonomy

Record: **ADR 0075**, `eval_runs/atlas/hai-error-taxonomy.md`,
`scripts/classify_atlas_alerts.py`, seed 11.

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R7 | Cannot treat the HAI false-positive load as evidence about the plant | The model exceeds its own reported band on **55.74%** of moments across 60 h of declared-normal data it never saw, against **55.81%** of the scored slice's normal moments. The two rates are indistinguishable, so the load is the model's out-of-sample behaviour on ordinary operation | Nothing from the world. This is a statement about the fit, and the evidence that settles it is already inside the corpus |
| R8 | Cannot separate maintenance from an attack on HAI, by inspection of the corpus rather than by assumption | HAI carries **no** work-order, operator-identity or mode-register column: 0 of its 79 data columns name one. Sharpens R1 from a reasoned position to a measured one | As R1. On HAI specifically, nothing — the channel does not exist in the corpus and cannot be added to it |
| R9 | Cannot separate equipment ageing from duty-cycle phase on HAI | The corpus spans 2.5 days. Three departing signals show a monotone trend across the scored slice (Spearman ρ to −0.54, against −0.14 over the 60 h reference), and every one of them does it inside an **unmoved envelope** — their 5th–95th-percentile band sits within 0.1% of the reference band's width of where the reference puts it. The only signal whose envelope did move materially (`P2_CO_rpm`, 26.8%) shows no trend at all. A monotone run inside an unmoved envelope is what the middle of a slow cycle looks like | Months of continuous declared-normal capture from one plant, enough that a trend in the envelope itself is separable from a trend within one cycle |
| R10 | Cannot attribute a grade, recipe or mode change on HAI | Every one of the 15 declared run-state, mode and pump-configuration signals is constant across the whole 7.92 h slice. There is no declared mode change anywhere in it for an alert to be reacting to, and no mode register to consult | A declared mode or recipe register covering the capture window, as a channel rather than as an inference from co-movement |
| R11 | Cannot detect communication artefacts in the prepared HAI corpus | All 2,851 inter-sample intervals in the scored slice are exactly 10.0 s, with no duplicate timestamps and no duplicate rows. **And the corpus could not show them if they existed:** the prepared CSV is a 1-in-10 downsample of the source, so any irregularity finer than 10 s is unobservable by construction | The undownsampled source capture, or a corpus carrying the transport's own gap and retransmit record |
| R12 | Cannot report a meaningful `not_separable` residual on HAI | Only 4 of the 10 categories reach a per-event discriminator; the other 6 are settled by the corpus screen. Of the two plant-side discriminators available, one requires a departure the model also makes on declared-normal data and the other requires the opposite, so no two can fire at once. The residual is **structurally** zero | More categories the corpus can actually decide, which means more declared context — the same dependency as R8 and R10 |
| R13 | Cannot promote `P2_CO_rpm`'s separation into a detector | It is the one signal whose departure is unprecedented against ~71 h of declared-normal data, and it departs only inside attack window 2 (magnitudes 3.648 and 3.772 against a declared-normal maximum of 0.308). **n = 1 signal, 2 events, 1 of 2 attack windows, 1 corpus.** Promoting it would be fitting a sign to two attack windows on the only corpus with a declared topology — exactly the move ADR 0068 rejected | An independent corpus with a declared topology in which the same signal class separates, measured without reference to HAI's labels |

---

## 3. Established by U2 — the Sentiel failure classification

Record: **ADR 0076**, `eval_runs/sentiel/cert-failure-classification.md`,
`scripts/classify_sentiel_failures.py`, seed 7, permutation seed 11.

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R14 | Cannot surface any behaviour that moves fewer than 14 of the 34 features at once | `AggregationPolicy` sums `1 - exp(-magnitude / 3)` per speaking feature, so a window in which *k* features spoke scores at most *k*. At the 48-alert operating point of **13.700640148454447** that requires **14** simultaneous departures — and **31 of `CCH0959`'s 42 malicious entity-days had fewer**, so no magnitude on them could have alerted. A property of the aggregation, not of the corpus | Nothing from the world. An aggregation whose per-feature contribution is not capped at 1.0. Not started, and **not** authorised by this item |
| R15 | Cannot separate `CCH0959`'s two-month theft from `CCH0959`'s ordinary fortnight | Their malicious days score **4.500** at the median against **4.586** on their own non-malicious days in the same scored half — *lower*. Best rank of any malicious day is **957** of 210,814, so the day was never a candidate and was never outranked. Measured against a fixed pre-attack baseline, the largest abs(z) across the 34 features is **1.27** (`distinct_pcs_peer`); the largest count-feature increase is **z = 1.07** (`removable_device_connects`, 2.213 → 3.262), against **z = 5.05** for `CSF0929` | An aggregation that can be reached by depth (R14), or a feature that expresses what the escalation was *for* (R16) |
| R16 | Cannot express *which* host or *which* recipient, only how many | 121 of `CCH0959`'s 310 labelled events are HTTP requests led by `lockheedmartinjobs.com` (**46**), with `linkedin.com`, `indeed.com`, `careerbuilder.com`, `monster.com` and `craigslist.org` behind it, and **7 of their 8 labelled emails are addressed to `Mario.Truman.Telsa@lockheed.com`**, a competitor. The corpus states the motive in plain text. `distinct_http_hosts` moves **62.394 → 63.667**, a ratio of **1.02**, because the 34 features count volume and novelty and never identity. **The evidence is in the corpus and is discarded by the feature space** | A feature that reads the identity of a counterparty against a declared list — a competitor register, a category for job boards, a declared sanctioned-destination set. None exists, and inferring one from behaviour is the circularity ADR 0010 and ADR 0022 refused |
| R17 | Cannot claim the episode unit groups anything a human would call one story | Reshuffling each entity's own scores across their own days — calendar and score distribution held, order destroyed — reproduces the whole episode set: 40 episodes observed against a permuted mean of 41.3 (95% [39, 44]), 506 entity-days against 471.7 ([360, 605]), longest 75 days against 65.5 ([35, 113]). Leading-feature agreement across the 39 multi-day episodes is **0.339** observed against **0.312** permuted ([0.274, 0.353], `P = 0.100`). The seven-day gap chains a per-entity base rate; the four long false episodes belong to entities above the floor on **36.9% to 52.8%** of **all** their days against a 10% population rate | A rule whose output leaves the reshuffle null — which means a grouping criterion that reads something other than "elevated and within seven days". Not attempted here |
| R18 | Cannot claim the episode coverage gain ADR 0072 reported as a ratio | The 9 malicious entity-days the episode queue shows at budget 48 are reproduced **as a gate** before the null is read, and against the same null the permuted mean is **6.63** with a 95% interval of **[5, 9]**, `P(permuted ≥ 9) = 0.055`. The observed value sits **at the edge of the interval, not outside it**. The count stands; "1.8× the malicious activity in front of an analyst" is a ratio the measurement cannot carry | A corpus with enough labelled insiders that the comparison is not two people wide. r3.1 has two |
| R19 | Cannot name a better unit of analysis on this corpus | U2 was required to say whether the person-day or the episode is the wrong object. Both are, **and for the same reason**: the episode ranks on `peak`, the maximum day score, so it inherits the per-feature cap entire. No unit over this feature space escapes a contribution bounded by 1.0, so changing the time unit could not have helped and did not | A different aggregation (R14) or a different feature space (R16). The unit is not the binding constraint and is not retired here |

---

## 4. Established by U3 — the synthetic diagnostic environment

Record: **ADR 0078**, `eval_runs/synth/u3-diagnostic.md`,
`scripts/diagnose_u3_environment.py`, seed 11. SYNTHETIC-DERIVED. Not a detection claim. Not a
row in `eval_runs/log.jsonl`.

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R20 | Cannot treat U3's four answers as evidence about a real plant, or as a detection claim | The environment is our model, our adversary and our maintenance practice. Runner banner and report (`eval_runs/synth/u3-diagnostic.md`) state this first. Sharpens R4 from a reasoned position to a constructed one: the questions are now *answerable*, and the answers still cannot travel | Real plant data covering the same four questions, or plant-literate subjects sitting the Latin-square protocol (R25/R26). U5 did not supply those subjects. Synthetic-derived remains unvalidated until then |
| R21 | Cannot uniquely lead `unauthorised_control_activity` from a known-station write even when command evidence genuinely exists | Question 4, seed 11, unauthorised scada write: 1 graph finding, 3 command evidence, competing set `{insufficient_evidence, engineering_maintenance, unauthorised_control_activity, process_disturbance}`, unique leader `insufficient_evidence`. Removing the capture shrinks the set to the residual and does not mint a contentful unique leader. ADR 0014 exercised on constructible evidence rather than lifted | A fact that carries intent, or an unknown-master write (ADR 0027). Not a template retune. Not authorised by U3 |
| R22 | Cannot host command, communication-failure, unauthorised-command or attacker scenarios on the batch reactor | `BatchReactorPlant` declares no control network. `construct(..., plant_id="batch-reactor")` raises `ValueError` naming that refusal (ADR 0015). Inventing a bus would be fiction | A plant that actually has a control network. The batch reactor is the telemetry-only control case and stays one |

### U4 — The first analyst interface (ADR 0079)

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R23 | Cannot settle Sentiel competing explanations from behaviour facts the templates declare | Sentiel templates declare no contradictory patterns (`src/phos/sentiel/templates.py`). U4's settling ask therefore names a declared sanction record (HR change, project assignment, change ticket) and states that no corpus PHOS reads carries one (`phos.reasoning.analyst_settling`) | A corpus or partner feed that carries sanction evidence, plus templates that declare the contradiction. Not invented behaviour |
| R24 | Cannot render a Sentiel ranking without documenting its depth-blind ceiling | Gate 2 binding condition; `depth_blind_ceiling_notice()` prints that at the 48-alert point at least 14 of 34 features must speak at once, and 31 of CCH0959's 42 malicious entity-days were structurally unalertable (ADR 0076 JSON, pinned) | A non-saturating aggregation measured under its own ADR. **ADR 0084 opened that session 2026-09-27. ADR 0093 declares three candidates; none is scored.** Until a candidate meets its criterion, the ceiling travels with every Sentiel render |

### U5 — Human decision usefulness (ADR 0080)

Record: **ADR 0080**, `eval_runs/usefulness/u5-decision-study.md`,
`scripts/run_u5_decision_study.py`, seed 11. **CRUDE_NON_OPERATOR_NOT_A_FIELD_STUDY.**
SYNTHETIC-DERIVED. Not a detection claim. Not a row in `eval_runs/log.jsonl`. `n_human` **0**.

| # | Refusal | Evidence | What would lift it |
|---|---|---|---|
| R25 | Cannot claim operational usefulness from the U5 crude run | The committed artefacts are a mechanical non-operator instrument check: subject kind `mechanical_non_operator`, `n_human` **0**, `n_with_time` **0** on every arm. The Atlas-explanation arm copies the U4 assessment, so any delta versus raw or threshold is the policy, not a person (`eval_runs/usefulness/u5-decision-study.json`). Sharpens R4 from a reasoned position to a run that existed and still cannot travel | Plant-literate subjects sitting the Latin-square protocol. Recruiting them is U7's partner conversation, which is not started |
| R26 | Cannot recruit plant-literate subjects from this repository | U5's named dependency: "Plant-literate subjects are not available." The real study is written down here rather than run. U7 produces the ask; outreach is a human action only Elijah can take | A partner who can name plant-literate readers and a window in which they will sit the protocol. U7 specifies the ask; this entry does not start U7 |

U5 is complete (ADR 0080). U7 is not started.

---

## 5. What the register is for

Read column three down the page and it resolves to a short list. PHOS's boundary is not mainly
algorithmic:

- **Work orders** — R1, R8. Named unit, named window, named authorised actor. The inlet exists
  (ADR 0069); nothing feeds it.
- **A mode or recipe register** — R10, and the `mixed_modes` half of U1's mechanism. Declared, not
  inferred from co-movement.
- **A second plant that actually generalises** — R3, R13. BATADAL→HAI three-role transfer is measured and louder (1078.99 vs 646.58); that did not lift R3.
- **A declared counterparty identity** — R16. A competitor register, a job-board category, a
  sanctioned-destination list. The only thing that could express scenario 2's motive, and the one
  dependency on this list that is **not** a design-partner ask: it is a declared reference set, and
  building one is ours to do.
- **More labelled insiders** — R18. Two is not enough to carry a ratio.
- **Long capture** — R9. Months, not days.
- **Plant-literate subjects** — R4, R25, R26. U5 built the instrument; the crude run cannot travel. Recruiting is U7.
- **A labelled command corpus** — R6.
- **U3's four questions answered on a real plant** — R20. Constructible here; not evidence about the world.
- **A fact that carries command intent, or an unknown-master write** — R21. A known-station write still cannot uniquely lead.
- **A declared sanction record for Sentiel** — R23. Behaviour alone cannot split the enterprise competing set.
- **A non-saturating aggregation (ours to build; ADR 0084 opened it, ADR 0093 declared three candidates, none scored)** — R24. Until then the 14-of-34 ceiling travels with every Sentiel render.

Most of those are things only a design partner can supply. That is the P1 wall the category
roadmap names, stated as a specification instead of as a complaint — and it is what U7 turns into a
two-week question a plant could say yes to. The exceptions that are ours to build are the declared
counterparty identity (R16) and the non-saturating aggregation (R24), whose session ADR 0084 has opened.

---

## 6. End-of-phase confirmation (U6, 2026-09-20)

Read against HEAD `5a7d8ae`. ADR **0081**. Every U1–U5 refusal is on disk as R1–R26. Four
entries had drifted and were corrected in this pass rather than left standing:

- **R3.** "What would lift it" still asked for a declared physical-role mapping. ADR 0063 already
  measured that mapping; transfer is louder (1078.99 vs 646.58). The claim stays refused.
- **R4.** Lift column still named U5 as if it had not run. U5 ran; `n_human` 0; recruiting is U7
  (R25/R26).
- **R15.** "Largest shift on any of the 34 features is z = 1.07" copied ADR 0076's curated
  count-feature pair. The committed U2 report ranks by abs(z) and leads with **1.27** on
  `distinct_pcs_peer`. 1.07 is the largest count-feature increase.
- **R20.** Lift column still named "U5 with plant-literate operators". U5 did not supply those
  subjects.

R1, R2, R5–R14, R16–R19, R21–R26 matched the code and the committed reports. The standing
procedure in `docs/usefulness-phase-roadmap.md` §0 now references this file's append
procedure; it did not, which was a U6 `success_is` gap, not a refusal.

U7 is not started.
