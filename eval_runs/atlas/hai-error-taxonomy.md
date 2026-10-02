# Atlas error taxonomy on hai — what kind of uncertainty generates the false alerts

**Not a detection claim and not a new operating point.** This decomposes an alert set the
Atlas vertical already logged. No model was refitted for a public row, no threshold was
searched, and no frozen number was re-derived.

- Frozen-row gate, reproduced before any number below: **reproduced** — 646.58 FP/normal-hour ungated, 53.26 grouped, 424 subsystem events, window recall 1.00
- Alerts classified: **424** (418 false, 6 overlapping an attack)
- Seed: `11`
- Commit: `4b27a54f93d8558f17ce1e12f09f2f235a803e25`

## The answer

**Modelling error, in 418 of 418 false alerts.** Not insufficient context — and the two point in opposite directions, so which it is decides what the rest of this phase should do.

The evidence is one measurement. The model exactly as the vertical fitted it, applied to the corpus's own 60.00-hour attack-free training file which it never saw, exceeds its own reported band on **55.74%** of moments — against **55.81%** on the normal moments of the scored slice. Its loudest signal, `P1_FT02`, exceeds on 44.86% of declared-normal moments on its own. The same signals exceed, at the same rates, to the same maxima. Every one of the 418 false alerts has a departure no larger than one the model produces on data the corpus declares attack-free. None exceeds it.

**The mechanism, in three measured parts.** (1) A shrinkage floor: 4 of the 9 signals that depart carry a band set not by their own variation but by the plant's largest-scale tag, because Ledoit-Wolf shrinkage is applied in raw units and HAI is a mixed-scale plant (`shrinkage_floor_mixed_scale`, ADR 0018). (2) For 5 signals — `P1_FT02`, `P1_FT02Z`, `P1_B400B`, `P3_LCV01D`, `P3_LCP01D` — the resulting band is **narrower than the signal's own declared-normal standard deviation**, so those signals must alert in normal operation as arithmetic. (3) A fit set shorter than one duty cycle: the fastest-cycling departing signal, `P1_B400B`, has a period of 3.15 h, and the fit window is 0.48 h — 15% of it (`mixed_modes`). The other departing signals cycle more slowly still, out to 17.04 h on `P3_LIT01`.

**The contribution, quantified, and what it costs.** Holding the model class, the threshold, the seed, the scored slice and the signal space fixed, and varying only the length of the fit set:

| Fit set | Per-signal alerts | Moments alerting | Attack windows caught |
| --- | ---: | ---: | ---: |
| 0.48 h (173 timestamps, the frozen row's own fit) | 5,123 | 55.96% | 2 of 2 |
| 0.97 h (350 timestamps) | 4,458 | 50.88% | 2 of 2 |
| 1.94 h (700 timestamps) | 4,243 | 49.09% | 2 of 2 |
| 3.89 h (1,400 timestamps) | 4,111 | 48.70% | 2 of 2 |
| 4.86 h (1,750 timestamps) | 186 | 4.52% | 2 of 2 |
| 5.83 h (2,100 timestamps) | 241 | 6.38% | 2 of 2 |
| 7.78 h (2,800 timestamps) | 116 | 3.19% | 2 of 2 |
| 15.56 h (5,600 timestamps) | 140 | 3.61% | 2 of 2 |
| 31.11 h (11,200 timestamps) | 94 | 2.38% | 2 of 2 |
| 60.00 h (21,601 timestamps) | 97 | 2.49% | 2 of 2 |

The transition is a step, not a slope: it falls between 3.89 h and 4.86 h of fit data — the first fit length past `P1_B400B`'s 3.15 h period — and the alert count drops from 4,111 to 186 across it. It does not then fall to nothing: the curve flattens near 2.38% of moments and stays there, which is what a fit still shorter than the slowest signal's 17.04 h cycle should look like. Window recall is 2 of 2 at every fit length tested, so none of this is bought with detection.

**What this is not.** It is not a proposal, an operating point or a detection claim. The reason the public fit is 0.48 h is not an oversight: the vertical needs labelled positives to fit its isotonic calibrator, the declared-normal file carries none, so it splits the labelled file three ways, and HAI's attacks fall early enough in that file that `train_fraction` must be 0.04 to leave any attack in the scored slice. The fit length is a consequence of where the only labels live.

**What remains genuinely blocked on evidence.** Maintenance and mode attribution. HAI carries no work order, no operator identity and no mode register, and no amount of modelling will conjure one. Those are the categories the synthetic diagnostic environment was built to exercise, and they are untouched by this finding.

## Before anything else: the queue is not as long as it looks

The 424 events carry **15 distinct signatures** — (subsystem, departing-signal-set) pairs — in **132 contiguous runs**. A signature with many
events and few runs is one condition re-counted once per grouping window.

| Events | Runs | Subsystem | Signals that departed |
| ---: | ---: | --- | --- |
| 221 | 2 | `p1-boiler` | `P1_B400B`, `P1_FT02`, `P1_FT02Z` |
| 54 | 22 | `p3-water-treatment` | `P3_LCP01D`, `P3_LCV01D`, `P3_LIT01` |
| 42 | 24 | `p4-steam-turbine` | `P4_ST_GOV` |
| 41 | 27 | `p3-water-treatment` | `P3_LCP01D`, `P3_LCV01D` |
| 24 | 22 | `p3-water-treatment` | `P3_LCV01D` |
| 14 | 13 | `p3-water-treatment` | `P3_LIT01` |
| 9 | 4 | `p1-boiler` | `P1_FT02` |
| 7 | 7 | `p3-water-treatment` | `P3_LCV01D`, `P3_LIT01` |
| 4 | 4 | `p3-water-treatment` | `P3_FIT01` |
| 2 | 1 | `p2-turbine` | `P2_CO_rpm` |
| 2 | 2 | `p3-water-treatment` | `P3_FIT01`, `P3_LIT01` |
| 1 | 1 | `p3-water-treatment` | `P3_FIT01`, `P3_LCP01D`, `P3_LCV01D` |
| 1 | 1 | `p3-water-treatment` | `P3_FIT01`, `P3_LCP01D`, `P3_LCV01D`, `P3_LIT01` |
| 1 | 1 | `p3-water-treatment` | `P3_FIT01`, `P3_LCV01D` |
| 1 | 1 | `p3-water-treatment` | `P3_FIT01`, `P3_LCV01D`, `P3_LIT01` |

## Stage 1 — what the corpus can say about each category, before any event was looked at

| Category | Verdict | Basis | What would lift it |
| --- | --- | --- | --- |
| `modelling_error` | **assigned** | the model's own band and its behaviour on declared-normal data are both available, so the counterfactual in MODEL_FAULT_PRECEDENCE is decidable | — |
| `normal_process_variation` | **assigned** | the corpus declares an operating envelope elsewhere — its 60 h attack-free training file — so 'inside the envelope declared elsewhere' is decidable | — |
| `genuinely_unusual_benign` | **assigned** | decidable as the residual of the declared-normal reference being exceeded | — |
| `communication_artefacts` | **refuted** | every one of the 2,851 inter-sample intervals in the scored slice is exactly 10.0 s, with 0 duplicate timestamp(s) and no duplicate rows. The corpus carries no gap, repeat or timestamp irregularity for an alert to be reacting to | — |
| `startup_shutdown_transition` | **refuted** | all 15 declared run-state signals are constant across the whole 7.92 h slice (0 moved). The plant did not start, stop, trip or go to manual during it | — |
| `grade_or_recipe_change` | **refuted** | no declared mode or setpoint change occurs anywhere in the slice — the same constant run-state and pump-configuration signals are the only mode evidence HAI carries, and none of them moves | — |
| `sensor_noise` | **refuted** | the lag-1 absolute-difference scale of all 9 departing signals in the scored slice is within 1.5x of its scale over the declared-normal reference (median ratios 0.76-1.05, 99th-percentile ratios 0.86-1.02). No instrument became materially noisier | — |
| `maintenance` | **not_separable** | HAI carries no work-order, operator-identity or mode-register channel: 0 of its 79 data columns name one. Maintenance and an attacker leave the same evidence and only priors separate them | a CMMS work-order export covering the capture window, reaching the inlet Session E3 built (ADR 0069), naming the unit, the window and the authorised actor |
| `equipment_ageing` | **not_separable** | the corpus spans 2.5 days. 3 departing signal(s) show a monotone trend across the slice (Spearman rho to -0.54 against -0.14 over the much longer declared-normal reference), and every one does it inside an unmoved envelope — their 5th-95th-percentile band sits within 0.1% of the reference band's width of where the reference puts it. The only signal whose envelope did move materially, `P2_CO_rpm`, shows no trend at all. Over 2.5 days a monotone run inside an unmoved envelope and a degradation are one measurement | months of continuous declared-normal capture from one plant, enough that a trend in the envelope itself is separable from a trend within one cycle |
| `insufficient_context` | **assigned** | available as the residual when no other discriminator fires | — |

## Stage 2 — what the same fitted model does to declared-normal data it never saw

The instrument that separates modelling error from a plant phenomenon. A signal whose
band is narrower than its own declared-normal variation must alert in normal operation.

| Signal | Band ± | Declared-normal sd | Band covers it | Exceeds band on normal | Max departure there | Floored |
| --- | ---: | ---: | :---: | ---: | ---: | :---: |
| `P1_FT02` | 834.19 | 877.69 | **no** | 44.86% | 7.110 | **yes** |
| `P1_FT02Z` | 834.03 | 1,165.97 | **no** | 43.47% | 10.109 | **yes** |
| `P1_B400B` | 834.03 | 1,165.92 | **no** | 43.46% | 10.104 | **yes** |
| `P3_LCV01D` | 6,267.90 | 6,822.71 | **no** | 14.21% | 9.460 | no |
| `P3_LIT01` | 8,730.30 | 4,264.66 | yes | 11.99% | 4.930 | no |
| `P3_LCP01D` | 3,531.89 | 5,118.43 | **no** | 10.56% | 6.140 | no |
| `P4_ST_GOV` | 3,218.67 | 1,820.11 | yes | 4.43% | 10.129 | no |
| `P3_FIT01` | 2,634.81 | 1,782.13 | yes | 0.39% | 3.631 | no |
| `P2_CO_rpm` | 835.14 | 21.20 | yes | 0.00% | 0.308 | **yes** |

Reference length: **60.00 h** of
declared-normal data. Every verdict below is relative to it; a shorter reference holds
fewer tails and makes more alerts look unprecedented.

## Stage 3 — contribution per category

| Category | Axis | Events | Share of the queue |
| --- | --- | ---: | ---: |
| `modelling_error` | model | 418 | 98.6% |
| `overlaps_labelled_attack` | — | 6 | 1.4% |
| `normal_process_variation` | plant | 0 | 0.0% |
| `sensor_noise` | plant | 0 | 0.0% |
| `maintenance` | plant | 0 | 0.0% |
| `grade_or_recipe_change` | plant | 0 | 0.0% |
| `startup_shutdown_transition` | plant | 0 | 0.0% |
| `communication_artefacts` | plant | 0 | 0.0% |
| `equipment_ageing` | plant | 0 | 0.0% |
| `genuinely_unusual_benign` | plant | 0 | 0.0% |
| `insufficient_context` | model | 0 | 0.0% |
| `not_separable` | — | 0 | 0.0% |

Residual in `not_separable`: **0**, stated rather than
distributed across the categories that claimed those events.

**Read that residual with the screen.** 4 of the 10 categories screened reached a per-event test at all (`genuinely_unusual_benign`, `insufficient_context`, `modelling_error`, `normal_process_variation`); the rest were settled by the screen, which is where the categories this corpus could not decide are recorded. Where only two plant-side discriminators are available and they are complements — a departure the model also makes on declared-normal data, or one it does not — no two can fire at once, so a zero here means "no two claimants" and not "nothing was ambiguous".

### Precedence, stated so it can be disagreed with

When a model-side and a plant-side category are both true of one alert, the model-side one takes the primary slot. The test is a counterfactual settled by measurement rather than by preference: replace the plant's behaviour with declared-normal behaviour and the alert still occurs, because every one of its departures is one the same model produces on data the corpus declares attack-free. The plant's behaviour is therefore not the condition without which the alert would not exist, and the condition that is gets the slot. Where no model-side category fires — where some departure is larger than anything the model produced on declared-normal data — the plant-side reading is the only reading, and it takes the slot instead. The rule therefore does not presuppose its own answer: on a corpus where the model is adequate, every primary category here is a plant-side one.

### Where a second category also fired

| Primary | Also fired | Events |
| --- | --- | ---: |
| `modelling_error` | `normal_process_variation` | 418 |
| `overlaps_labelled_attack` | `modelling_error`, `normal_process_variation` | 4 |
| `overlaps_labelled_attack` | `genuinely_unusual_benign` | 2 |

## The alerts that overlap a labelled attack window

Not false alerts, so not the taxonomy's subject — but what the references say about them
is the mechanical reason a queue of this kind cannot be ranked.

| Timestamp | Subsystem | Strongest | Magnitude | Verdict against declared normal |
| --- | --- | --- | ---: | --- |
| 20:21:00 | `p3-water-treatment` | `P3_LCV01D` | 7.885 | inside the model's declared-normal noise |
| 20:21:00 | `p4-steam-turbine` | `P4_ST_GOV` | 6.082 | inside the model's declared-normal noise |
| 20:22:00 | `p3-water-treatment` | `P3_LCV01D` | 7.223 | inside the model's declared-normal noise |
| 20:22:00 | `p4-steam-turbine` | `P4_ST_GOV` | 4.439 | inside the model's declared-normal noise |
| 21:03:40 | `p2-turbine` | `P2_CO_rpm` | 3.648 | **unprecedented** |
| 21:04:00 | `p2-turbine` | `P2_CO_rpm` | 3.772 | **unprecedented** |

## Read every number above with these

- A category assignment is a diagnosis of an alert, not a detection claim. Nothing here is a new operating point and nothing here replaces or re-derives a frozen row.
- 'No larger than the model produces on declared-normal data' is relative to a reference of a stated length. A shorter reference contains fewer tails and makes more alerts look unprecedented. Read every verdict with its reference_hours.
- A declared-normal reference is declared normal by the corpus author, not verified by PHOS. An unlabelled attack inside it would be learned as normal.
- A refuted screen is refuted for this corpus and this slice only. It says the evidence was present and said no, never that the category cannot occur on a plant.
- A not_separable screen means the corpus does not carry the evidence the category needs. It is not a statement that the category is absent, and it must not be read as one.
- Categories are not a partition. primary_category is one reading under a declared precedence; co_firing carries the rest, and both must be read together.
- A not_separable count of zero is not a claim that nothing was ambiguous. Only the categories in DISCRIMINATED reach a per-event test at all, and where a corpus supports only two of them the residual can be structurally zero because no two can fire at once. Read it with the screen, which is where the categories nothing could decide are recorded.
