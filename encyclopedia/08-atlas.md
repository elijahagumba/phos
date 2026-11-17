# 08 — Atlas (industrial / OT engine)

**What this is.** The complete OT vertical: telemetry and (optionally) Modbus commands in; competing-hypothesis narratives out. Package: `src/phos/atlas/`.

**Why it exists.** A plant is one machine, not 79 independent signals. PART 3's per-signal Gaussian posted 8,389.81 false positives per normal hour on HAI. That is a modelling failure, not a threshold failure (ADR 0009).

**What Atlas is not.** Deployable. A field command-detection rate. A live Modbus actuator (`tests/atlas/test_never_actuates.py`). A place to retune `templates.py` to chase 70%.

## Vertical (`engine.py`)

`AtlasEngine.run(dataset) -> list[Narrative]`:

1. Score with the fitted joint model.
2. Promote only out-of-band deviations through the 4A boundary (calibrated weights).
3. Group by `(subsystem, tumbling window)` (ADR 0011: group **before** reason).
4. Interleave optional `CommandEvidence` by time.
5. Reason with `atlas_library()`.
6. Narrate. `annotate_with_caveats` attaches standing honesty sentences.

`AtlasConfig` carries model, topology, calibrator, optional command inlet. Hypothesis confidence **must not be surfaced** (`ATLAS_VERTICAL_CAVEATS`, including `SATURATED_FP_LOAD_CAVEAT` from ADR 0051).

If no commands are supplied, the sensor path is byte-identical to the pre-command engine (tests pin interleave determinism).

## Joint models (`multivariate.py`, `vectorise.py`)

`vectorise` is the only `(time × signal)` reshape. Missing readings: forward-fill a bounded number of rows, else drop the timestamp. **Never invent zeros.** `NO_OBSERVATION = -1`. A carried cell informs reconstruction but **cannot raise a deviation** (no measurement to point back to).

Two joint models, chosen because they fail differently. Session C1 (ADR 0050) names what they actually assume (`SNAPSHOT_ASSUMPTIONS`: temporal independence of a moment, linear feasible set, constants dropped) and when that is invalid (`MANIFOLD_BREAK_CONDITIONS`: capture drift, mixed modes, constant-in-train, shrinkage floor on mixed-scale batch). Tests: `tests/atlas/test_joint_assumptions.py`. Public `_shrink` default remains average-variance. Session C3 (ADR 0052) adds named `ShrinkageTarget.CORRELATION` (standardise within a declared mode) as a bake-off option, not the public distillation row. Session C4 (ADR 0053) publishes `PUBLIC_JOINT_VS_UNIVARIATE` — ratios may miss 10×.

| Model | Mechanism | HAI three-way (seed 11, threshold 3.0) |
|---|---|---|
| `MahalanobisModel` | Shrunk covariance (`shrinkage` 0.05); conditional mean given the rest of the plant | 5,099 FPs, **646.58**/normal hour, recall 1.00 |
| `PcaResidualModel` | Standardise, PCA (`variance_retained` 0.95), reconstruction residual | 138,243 FPs, 17,529.93/normal hour, recall 1.00 |

PCA was nominated as primary and **lost**. In-sample it looks calibrated (~0.64% out of a 3σ band) and out-of-sample inflates 7.7×. Recorded (ADR 0009), not tuned away. Public comparison row is ungated Mahalanobis.

Both emit ordinary `Deviation`s with a **dynamic** `ExpectedRange` centred on the implied value, so downstream code has no special joint type. That is Constitution §3.2: a joint score that was only a scalar would be a black box.

`JointMomentDetector`: optional gate on joint distance (`joint_k`; default **0** = ungated) and dwell (`dwell_samples` default **1**, ADR 0026: dwell-1 is the detector unchanged). Public logs keep those names. Do not retune on library personas as a cycle win.

## Dynamics (`dynamics.py`, ADR 0054 / 0064)

`LinearDynamicsModel` (`atlas-var1`, default lag 1) is a named experiment beside snapshot Mahalanobis: OLS VAR on attack-free train, residual \(r_t = x_t - \hat{x}_t\) with per-signal `ExpectedRange`. Dummy-batch pooled snapshot stays blind. Mixed-mode VAR is not the public distillation row. Fixture bake-off: `tests/atlas/test_dynamics_bakeoff.py`.

HAI three-way (seed 11, threshold 3.0, commit `5b62230`, log rows **182-183**): `model:atlas-var1` window recall **1.00**, **14071.07** FP/normal hour. Snapshot Mahalanobis **646.58** is not overwritten. VAR is **louder** and **refused** as the HAI detector (ADR 0064). Do not retune lag or threshold to chase a win. CLI: `scripts/evaluate_atlas.py hai --protocol three-way --var`.

Correlation-target shrinkage (`atlas-mahalanobis-correlation`, ADR 0066) **cannot invert** on the same split at frozen shrinkage 0.05. No log row. Do not retune `_shrink`. CLI: `--correlation`.

## Topology and grouping (`topology.py`, `grouping.py`, ADR 0010/0011)

Membership is **declared** from documentation, never clustered from co-movement. Clustering would answer "did these deviations share a cause?" with the same statistic that raised them.

`SubsystemMap` is a total partition at construction (five failure modes, named signals, none recoverable). Every `Subsystem` has a mandatory `source`. `render_topology` is for a domain expert to falsify by eye. A test forbids authored sources that cite co-movement.

HAI's documentation could not be partitioned below **process** level. Grouping cut the operator queue from 5,123 alerts to 424 (53.26 FP/normal hour, precision 0.0094) at unchanged recall. That 12.1× is evidence grouping is *implemented*, not that it is *correctly resolved*. Only HAI has a declared topology, so anything requiring a subsystem map is HAI-only.

`group_evidence`: absolute tumbling windows from UTC epoch; key `(domain, subsystem_id, window_start)`; event weight = max member weight; `entity_ids` = departed **signals** (breadth for templates). Marker: `SUBSYSTEM_EVENT_MARKER`. Counting collapse only, not a detection retune.

## CMMS work-order inlet (`cmms.py`, ADR 0069)

E3 (`work_orders.py`) wired the templates — a work-order fact (`work-order:` stamp, and since ADR 0070 the typed `facet_kind=WORK_ORDER`) **supports** `engineering_maintenance` and **contradicts** `unauthorised_control_activity` — but `promote_work_orders` takes `Sequence[Observation]`, so nothing could feed it a real record. `cmms.py` is the adapter.

`CmmsSchema` declares column names and timestamp formats; `SAP_PM_SCHEMA` (`AUFNR`/`EQUNR`/`GSTRP`/`GLTRP`/`STTXT`/`AUART`, sanctioning `rel`/`teco`) and `MAXIMO_SCHEMA` (`WONUM`/`ASSETNUM`/`SCHEDSTART`/`SCHEDFINISH`/`STATUS`/`WORKTYPE`, sanctioning `appr`/`inprg`/`comp`) ship. `load_work_order_export` → `WorkOrderRecord` → `observations_from_work_orders` → `promote_work_orders`. `covering_order(records, timestamp, asset_ids)` is the coverage primitive.

Four refusals: `CmmsExportMissingError` (missing ≠ empty — empty is a finding, missing is silence); declared columns and formats, never sniffed; exact asset identity (`P-101` ≠ `P-1010`) with `UndeclaredAssetError` rather than a dropped row; sanctioning status only (`CAN`/`CRTD` authorise nothing). `WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE` states that cover makes maintenance live, not proven — an attacker with the calendar can act inside a window.

**Nothing measured.** `discover_work_order_exports` reads `registry.json`'s `datasets` list and returns **empty**, so coverage claims on public corpora are **REFUSED** (ADR 0040 idiom). Do not invent a maintenance calendar for HAI. Coverage is not wired as a queue severity: `covering_order` is the primitive a future `uncovered` key would call, but every HAI alert would read "unknown" today.

## Operator queue (`queue.py`, ADR 0068)

Grouping leaves the queue in **time order** with no severity on it. `queue.py` is the separate stage that ranks a finished subsystem-event queue and scores it at declared budgets, under `atlas-queue:<key>` — never a vertical name, never appended to `eval_runs/log.jsonl`. `grouping.py` is not modified, so its "re-scores nothing" promise and the frozen 53.26 row both stand.

`QueuedAlert` (magnitude / weight / breadth / `covers_windows`) → `rank_queue` (desc score, ties on timestamp then id) → `outcome_at_budget` → `QueueCurve`. Truth is **overlap-aware** (`windows_overlapped`): an event is stamped at its earliest member but tested against all of them. Precision divides by the **budget**, matching `precision_at_budget`.

Two honesty mechanisms. `cut_is_arbitrary` fires when the last alert taken and the first dropped share a score — the cut was the tiebreak's, so `honest_points` omits it (ADR 0051's idiom on a budget). `expected_true_positives` / `beats_random` make "worse than chance" computable rather than impressionistic; `sorts_truth_downwards` names an anti-ranking.

**Measured on HAI (seed 11, `eval_runs/atlas/hai-operator-queue.md`): the queue cannot be ranked.** 424 events / 7.89 normal hours / **6** true. `magnitude` — 424 distinct scores, true alerts at ranks 187, 204, 255, 320, 348, 359 (44th–85th percentile), **0** TPs in the top 48 against a random expectation of 0.68, loudest 96 contain no attack. `weight` — **1** distinct value (0.03375934410417169, the isotonic ceiling): zero ranking information. `breadth` — 4 values, truth at ranks 285–351. `atlas-queue:weight` at 48 (precision **0.1250**, recall 1.00) is **REFUSED**: a 424-way tie is timestamp order and HAI's attacks fall early. Do not quote it, do not compare it to CERT 6B's 0.104, and do not invert the magnitude ranking because truth sits at the back. Unexplained at the time: a quarter of the queue pinned near magnitude 10.10, all between 22:54 and 02:05, hours after the attacks. **Resolved by ADR 0075** — 10.10/10.11 is the ceiling of the `P1_B400B`/`P1_FT02Z` departure geometry under this model, reproduced identically on 60 h of declared-normal data with no attack in it, so it is not an operating-point shift peculiar to the slice.

A signal that is constant in training is dropped; Atlas says nothing about it.

## Error taxonomy (`phos.eval.taxonomy`, ADR 0075)

The decomposition of a false-positive rate into *what kind of uncertainty produced it*. Lives in `phos.eval`, not in Atlas: `taxonomy.py` classifies (pure, no model), `taxonomy_evidence.py` holds the measurements the verdicts rest on so no report figure is transcribed, `taxonomy_report.py` renders. Driven by `scripts/classify_atlas_alerts.py`, which **reproduces 646.58 / 53.26 / 424 / recall 1.00 as a gate and aborts on any drift past 1e-4** before producing a number. No log rows; report at `eval_runs/atlas/hai-error-taxonomy.md`.

**Two axes, declared as such.** Eight categories answer *what was the plant doing*; two answer *why did the model speak*. An alert carries a `primary_category` **and** its full `co_firing` set, because both are usually true at once. `MODEL_FAULT_PRECEDENCE` is the single precedence rule and it is a counterfactual settled by measurement, not by preference; it is deliberately **not** keyed on band-versus-spread, since a conditional band is legitimately narrower than a marginal spread. Where no model-side category fires the plant-side reading takes the slot, so the procedure cannot only ever answer "modelling error".

**`CorpusScreen` decides a category before any event is looked at.** `assigned` lets it compete, `refuted` means the evidence was present and said no, `not_separable` means the corpus does not carry the evidence — and that verdict must state `what_would_lift_it`. A screen marking a category `assigned` when no per-event discriminator exists is a **hard error**: its zero would otherwise read as a measurement. Only 4 of the 10 categories reach a per-event test; `DISCRIMINATED` names them.

**Measured on HAI (seed 11): modelling error, 418 of 418 false alerts, `not_separable` residual 0.** The same fitted model, applied to HAI's own 60 h attack-free file it never saw, exceeds its own band on **55.74%** of moments against **55.81%** of the scored slice's normal moments — indistinguishable, so the load is the model's out-of-sample behaviour on ordinary operation. Mechanism: 44 of 52 signals share a conditional spread of exactly **277.9568140855581** = `sqrt(0.05 × 1,545,199.81)` (`shrinkage_floor_mixed_scale`, ADR 0018, to nine significant figures); five signals have a band **narrower than their own declared-normal standard deviation** and are the strongest member of 360 of 424 events; the fit is **0.48 h against `P1_B400B`'s 3.15 h duty cycle** (`mixed_modes`). A fit-length sweep holding threshold, seed, slice and signal space fixed shows a **step** between 3.89 h (4,111 alerts) and 4.86 h (186), flattening near 2.4%, with **window recall 2 of 2 at every length**. The 0.48 h fit is a consequence of the isotonic calibrator needing labelled positives the declared-normal file does not have — not an oversight.

**Four categories refuted by measurement**: communication artefacts (all 2,851 intervals exactly 10.0 s), start-up/shutdown (all 15 declared run-state signals constant across 7.92 h), grade/recipe change (no declared mode change anywhere), sensor noise (lag-1 jitter within 1.5× of declared normal on all 9 departing signals). **Two not separable**: maintenance (0 of 79 columns is a work order, operator or mode register) and equipment ageing (3 signals drift inside envelopes unmoved to 0.1%; the one moved envelope shows no trend). Register R7–R13.

**Nothing here overwrote the public isotonic row.** 53.26 stands as the frozen grouped vertical.
ADR 0083's implementing session fitted a `normal-score-cdf` calibrator on held-out attack-free
magnitudes (no labelled positives) and ran the vertical on the same test slice under **new** names:
grouped **31** alerts at **3.55** FP/normal-hour, recall **1.00**
(`hai[designed-normal-score][after]`). That row is now **appended** to `eval_runs/log.jsonl` beside
53.26 — dual-corpus success failed because batch-distillation detection stayed at parity with
designed (0.548 recall / 20.19 FP/hr). Weights carry `NORMAL_SCORE_WEIGHT_CAVEAT` (extremity under
ordinary scores, not P(attack)). Diagnostic 97 and the new 99 per-signal count remain citations.

**The queue is 424 alerts and 15 phenomena.** `signature_of` / `signature_runs`: 15 (subsystem, departing-signal-set) signatures in 132 contiguous runs, one of them 221 events (52% of the queue) in **two** runs over 22:11–02:47. Only 9 of 79 signals ever depart.

## OT templates (`templates.py`) — LOCKED

Five explanations. No mechanism for a sixth. Priors from an executable base-rate ladder (`prior_at_rank`, `EVIDENCE_STRENGTH` steps). Conditional on "a unit that already departed," not on a plant-hour. Matchers see **breadth** (`ONE_DEVICE_MAX_SIGNALS = 2`, a HAI instrumentation fact) and **marked graph findings**.

| `template_id` | Prior rank | Supported by | Contradicted by |
|---|---|---|---|
| `sensor_or_device_fault` | 2 (most common) | localised (≤2 signals) | broad (≥3) |
| `engineering_maintenance` | 1 | untyped structure; known-link silence or unexpected function; work order; **declared command behaviour** | **unknown master only** |
| `process_disturbance` | 1 | broad | localised; any relationship change |
| `unauthorised_control_activity` | 0 (rarest) | broad; any structure change; **declared command behaviour** | localised; work order |
| `insufficient_evidence` | residual | (engine) | — |

**ADR 0014 remaining limit:** unexpected function or silence on a **known** link still supports both attack and maintenance. Do not put known-link unexpected function on maintenance-contradict to chase 70%.

**ADR 0027:** a **marked unknown master** supports attack and contradicts maintenance.

**ADR 0071 — command behaviour routes, and still does not discriminate.** Command-behaviour `DEVIATION`s carry a declared stamp (ADR 0057), typed as a facet by ADR 0070 and read by `CommandBehaviourPattern` since ADR 0071. A declared departure **supports both** `engineering_maintenance` and `unauthorised_control_activity` and bears on **neither** process explanation. The refusal is deliberate: a closed loop answers a real upset by commanding differently, so calling a command departure evidence against an upset would be false, and calling it evidence for one would be a claim about controller dynamics Atlas has never measured. ADR 0014's structural asymmetry is about *who commands whom*, which an upset cannot change — not *how much* an existing commander commands, which it changes routinely. The pattern carries **no `features` field**: sub-selecting a feature would be tuning toward a corpus ADR 0040 says does not exist. Known-station indistinguishability stands, untouched — both roles are SUPPORTING. This is **readiness, not a measured result**; no detection number follows from it.

Work-order stamps (ADR 0059) are a separate inlet: empty lists leave ranking unchanged; a present fact supports maintenance and contradicts unauthorised control. Do not retune known-link matchers to chase 70%.

`tests/atlas/test_templates.py::test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence` must keep passing, and so must `tests/atlas/test_command_behaviour_pattern.py::test_the_tie_between_an_engineer_and_an_attacker_is_not_resolved` — the same tie, reached from command behaviour instead of from the graph.

## Phase-conditional batch (`phased.py`, ADR 0018/0019)

Pooled joint models were blind on the batch reactor (normal *is* a sequence of recipes). `PhaseConditionalModel` routes by a **declared** `phase_feature`. After a phase change, `_settle` re-judges with the outgoing phase (`emit_k=0`) and swaps if the reading is in the outgoing band. Default settling window **10 minutes**. Unmeasured: an attacker falsifying the phase register.

On **batch-distillation** the operation logs declare `Executing step` (ADR 0048). Joining that register (and the path's `operating_point`) and scoring `PhaseConditionalModel` with settling disabled **raised** perturbation recall (0.60 → 0.75 / 0.74) and **exploded** false positives (18.72 → 235.64 / 140.40 per normal hour). The pooled ungated Mahalanobis row is unchanged. 2–3/day remains refused. Do not invent a phase from correlations. Do not quieter-pool `dwell` to paper over this.

Sessions C7–C8 (ADR 0055): phases seen in train but too rare to fit a tight inner model are listed on `starved_phases` and scored by the pooled fallback. That is not "the mode was learned." Forged valid phase with matching physics is **unhandled** — switching is not a security claim against a lying PLC.

A-FIX-2 also established that three of A-FIX-1's twenty "caught" batch attacks had been credited to a false positive at every CHARGE→HEAT transition.

## Stability (`stability.py`)

Plant-health helpers: `baseline_similarity`, `dominant_period`, `learn_process_cycle`. Communication-timing / protocol-state stubs were retired when the packet path landed.

## Packet path (`atlas/packet/`, ADR 0012–0013)

```
read_frames → dissect_capture → command_events
    → featurise_commands
    → learn_device_command_graph / compare_to_graph
```

**Capture.** Stream pcap/pcapng to `RawFrame`. Count undecodable / empty / truncated. Catch untrusted parse errors only around adversary bytes.

**Dissect.** First-claim `DissectorRegistry`, first true wins in registration order; `claims` may read the payload, and a decline falls through. No default registry stuffed with every ICS protocol. A dissector that raises is a PHOS bug (not swallowed). Modbus/TCP claims port 502. Check-before-read, cap-before-allocate, refuse → `MalformedFrame`. `dissect_capture` still hands one `RawFrame` to one dissector: no reassembly on that path.

**Foundation (ADR 0345 declared, built 29 October 2026, judged met by ADR 0346 on 5 November 2026).** `packet/reassembly.py` and `packet/pairing.py`, beside the old path and imported by neither `modbus.py` nor `dissect_capture`. Caps as declared: 131072 octets a flow, 256 flows, 16 out-of-order segments, 65535 octets a segment, 256 open pairs, 60 seconds of capture time. A breach is a returned `FlowRefusal` or `PairMiss`, never an exception, and the offending segment is not stored. An overlap refuses the flow rather than splicing one copy; a gap is waited on, never zero-filled; a declared PDU length outside [header, cap] refuses without consuming the header, and that refusal is returned to every later caller. `RawFrame` gains optional `dst_mac`, `src_mac`, `ethertype` (0x8100 stays that integer; 802.1Q is not read) and `tcp_seq`. Seeded fuzz: seed 20261029, 2000 segment lists, four claims. `modbus.py` has an empty diff. **The verdict is ADR 0346: met.** It was written by a session that did not build the lane, as ADR 0344's step 4 requires, and judged against the declaration as committed rather than a restatement of it. All six caps match the declared digits; `FlowRefusal` is returned and never raised; `OVERLAP` fires both for octets already delivered and for a stored segment, so there is no last-write-wins branch; the fuzz corpus is seed 20261029, 2000 lists, 30s budget as declared. At `2560b6b` the suite is 5416 passed, 24 skipped, 45 deselected in 237.41s, `mypy --strict` finds no issues in 294 files, `ruff` passes, and `modbus.py`'s diff across `bf37107` is empty. One `raise ValueError` exists, at `pairing.py:144`, on a timezone-naive capture timestamp; its own docstring calls it a caller bug rather than a capture, it sits on a path no packet reaches, and the verdict records it so a later reader meets it in the record and not in the source. The foundation was on `main` from 29 October to 5 November as working code with no result against it — a declared-and-unjudged step is the one state the record exists to make visible, and ADR 0420 parked the programme on 3 November without noticing this step of it was finished. Nothing was scored.

**Programme G (ADR 0344, 29 October 2026; parked by ADR 0420, unparked by ADR 0422 on 5 November 2026).** The human decided on 28 October to name further protocols ahead of a partner's capture. The brief is `docs/build-brief-2026-10-g.md`. Numbers 0346–0367 and notes 141–151 are reserved and are not results. ADR 0345 declares the foundation caps; they are built and judged met (see **Foundation** above). **ADR 0420 parked the programme on 3 November against A3 and A7; ADR 0422 unparks it on 5 November and names a different criterion.** A3 asks whether an Atlas queue ranks and A7 whether a stranger can re-derive the numbers; neither asks whether Atlas can read the plant at all, so reach measured against them returns *moves nothing* whatever the answer. The criterion is **R27** of `docs/refusal-register.md`, appended in the same change: Atlas cannot read a plant that does not speak Modbus/TCP. That limit has held since ADR 0012 and was unrecorded until now, in a register whose other twenty-six entries are the most sovereign-grade artefact in the repository — a vendor stating its own boundary in advance. Each protocol lane that reaches a verdict strikes through part of R27; **a refused lane sharpens the entry and counts as a result.** Reach is not performance: no lane may be quoted as recall, as a rate, or as evidence for A2, A3 or A7, and the honest sentence stops at *Atlas can now read this language*. The standing rank is unchanged — foundation, S7comm, DNP3, IEC 60870-5-104, EtherNet/IP with CIP, OPC UA, IEC 61850, S7comm-plus, then Profinet and BACnet as optional slots — with S7comm second because a software download is the act `program_transfer` already knows, not because Siemens is large. MQTT and Sparkplug B have no slot and ADR 0422 records that gap rather than filling it. `modbus.py` is not edited to make room. No corpus was scored. v1 stays 8 of 12.

**S7comm lane (ADR 0347 declared, ADR 0348 met, 5 November 2026).** `packet/s7comm.py` reads the ISO-on-TCP envelope an S7 controller speaks and **not** S7 itself. Two headers, and nothing behind them: the four-octet TPKT header — version (always 3), reserved octet, 16-bit packet length counting the header (RFC 1006 §6) — and the COTP TPDU header inside it — length indicator at octet 1, TPDU code at octet 2, and the fixed part of whichever TPDU that code names (RFC 905 §§13.1–13.12). It reports `iso-tsap`, the service IANA registers on TCP 102, and `IsoTsapMessage.protocol` is a `Literal["iso-tsap"]` so `"s7comm"` is **unrepresentable in the type** rather than merely unused. The application octets are carried as `user_data_length` only — not stored, not decoded, not named. **No `ProgramAct` is constructible**: the spec-audit found no published job byte and positive evidence none will be published, since the Siemens manual states S7 communication is "vendor-specific … (not an open standard)" (11/2025 A5E03735815-AN §9, p.161). That refusal is **R28**.

Claiming is **by port alone**, resolved against ADR 0345's rule that 102 is not a claim for S7comm or MMS: port 102 *is* a claim for `iso-tsap`, which IANA registers, and the module never names S7 or MMS from the port. An IEC 61850 MMS frame on 102 therefore decodes as a valid `iso-tsap` message with its application unread, which is correct — MMS *is* an ISO-on-TCP frame. Four things the module **refuses to refuse**, each because a refusal would manufacture malformations on real Siemens traffic: a non-zero reserved octet (RFC 2126 §6.10, "ignored on input"); a COTP class other than 0 (Siemens labels its own transport "(Class 4)"); a CR/CC carrying initial user data or a third parameter (RFC 1006 §5 permits both — and they lengthen a TPDU past its header, never shorten the header); and an unknown TPDU code, which is a decoded message rather than a failure. Structural refusals are the six fixed-part rules: **DT exactly LI 2**, **ED exactly LI 3**, **DR ≥ 6**, **ER ≥ 4**, **CR ≥ 6**, **CC ≥ 6** (the code octet is inside the header LI measures — RFC 905 §13.2.1), plus a **dangling one-octet variable part** refused generically for every TPDU whose fixed-part size is known (RFC 905 §13.2.3), and the **16-octet XSDU cap** on expedited data only (RFC 1006 §6). `65524` is deliberately **not** coded: RFC 1006 states it as a maximum TSDU and it contradicts the memo's own minus-3 rule and RFC 905 §13.7.5, so only 65535 (TPKT) and 65531 (TPDU) are bounds. Two limits travel with the lane: a TPKT split across TCP segments is refused rather than reassembled, and a class-4 data TPDU is refused because its fixed part is one octet longer than the class-0 reading applied. **The lane took five red-team rounds and five judgement takes.** Four of the five rounds found a real defect in a version already pronounced met: the worst was that `user_data_length` was steerable by the sender's length indicator, so a 22-octet S7 job could report as an empty frame with every field in bounds and the message validating. Each was fixed by refusing a shape the standard does not permit, not by better arithmetic. Seeded fuzz: **seed 20261105**, 2000 random + 2000 mutated + a truncation sweep at every byte + a length-lie sweep; the adversarial suite adds a 256-code × 254-LI sweep per named TPDU. At the lane head: 1120 passed, 3 skipped in the packet package; `mypy --strict` no issues in 295 files; `ruff` clean. Reports: `eval_runs/build/lane-g/s7comm/spec-audit.md`, `red-team.md`. Nothing scored; no capture registered, so the lane is specification without a corpus and says so.

**Identity.** Device entity id is the IP (`ent_<ip>`). `unit_id` is preserved but is not identity (ADR 0013).

**Commands.** Request-only `CommandEvent`s. Write function codes enumerated. Window helpers. `WRITE_FUNCTIONS` / `REGISTER_WRITE_FUNCTIONS`.

**Behaviour.** Per-device per-window observations: volume/mix, write addresses/values, `write_command_share`, interval mean/CV. Default window 1 minute; `min_commands=4`. Caveats for short captures.

**Graph.** Learn who commands whom. Compare live traffic. Three finding features:

| Feature | Meaning | Horizon rule (ADR 0037) |
|---|---|---|
| `unknown_command_relationship` | Link absent from learned graph | command count |
| `silent_command_relationship` | Learned link empty in live window | vs stretches of comparable duration; typical (median) occupancy ≥ `_TYPICAL_SILENCE_FLOOR` (1.0) |
| `unexpected_command_function` | New function on a known link | count per code |

`GraphComparePolicy.window` default 1 minute (`DEFAULT_GRAPH_HORIZON`). `min_edge_commands` default 4: **do not raise this to quiet D2.** Context records `learned_span_seconds` vs `live_span_seconds`. Unknown + unexpected on the same new link → report **only** unknown. Not topology. Promotion is P3.

Issuer classification is **not** in Atlas. `phos.breaking.commands.classify_command_issuer` looks up the learned graph: if any learned edge has that device as issuer → `known_station`, else `unknown_master`. Not `AttackType.ROGUE_COMMAND`.

## Command evidence and grounding (P3, sessions 2–3)

`command_evidence.py` promotes behaviour deviations and graph findings into ordinary `Evidence`. Graph summaries stamped `graph-finding:<feature>:` and, since ADR 0070, carrying the typed `facet_kind=GRAPH_FINDING` / `facet=<feature>` the matchers actually read; behaviour departures carry `COMMAND_BEHAVIOUR` and still match no OT template (ADR 0014). Caveats: `UNMEASURED_COMMAND_DETECTION_CAVEAT`, `POOLED_GRAPH_CALIBRATION_CAVEAT` (do not fit a per-feature calibrator on the D2 battery, ADR 0035), `UNGROUPED_COMMAND_EVIDENCE_CAVEAT`.

`command_grounding.py` is a co-occurrence **table**, not a fourth score:

| Grounding | When |
|---|---|
| `UNAUTHORISED` | Unknown master in the window (wins over known activity) |
| `COMMANDED` | Behaviour departure or unexpected function |
| `UNCOMMANDED` | Silence alone / no activity |

Attachable: unknown-master and unexpected-function findings in the act; silence only if it **shares an entity** with act entities (ADR 0038). Unmarked findings always attach (legacy untyped).

## Command eval seam (`command_eval.py`, ADR 0040)

`discover_labelled_command_corpora` looks under `data/*/manifest.json` for `format="pcap"` **and** non-empty `attack_intervals` plus captures on disk. **Empty on this repository.** `test_this_repository_holds_no_labelled_command_corpus` is the tripwire: it should fail only if a real labelled command capture arrives.

Clock B research objects (not a new lead rate): `command_reconstruction.py` records who/what/path/when/state with `lead_rate` always `None`. `reconstructions_from_attack_config` walks D2 TOMLs as a **completeness** diagnostic (path/state/aftermath usually empty). That completeness is not unique lead. Known-station 0/16 and unknown-master 1/4 stay unpooled. `transitions.py` learns declared-phase adjacency and **refuses** an inferred distillation phase (ADR 0018 / 0031).

Inspected and refused as command corpora: Data4Cyber (process phases; Track A S0/S1 is a separate process-telemetry row, ADR 0046), s7 parquet (ADR 0012; process table unlabelled, ADR 0047), 3W faults (ADR 0033). Hunt tickets (unverified, not acquired): TEP, Electra, HVAC/BACnet, further Modbus pcaps.


## Cross-plant physical roles (`data/`, ADR 0063)

`phos.atlas.data` is the intake for Milestone 1 transfer. Canonical path: `src/phos/atlas/data/` (not `src/atlas/data/`). BATADAL and HAI load prepared CSVs already on disk. SWaT raises `CorpusMissingError` (`form-gated`) and is never fetched.

The shared schema is three **declared** roles: `flow`, `pressure`, `pump_state`. Maps cite documentation (BATADAL prefixes, HAI technical details, SWaT published FIT/PIT/P tags). Unmapped tags are dropped. Averaging tags that share a role is a declared reduction, not a learned alignment (ADR 0010).

Zero-shot: ungated Mahalanobis fitted on projected BATADAL train (SWaT joins only if present); scored on projected HAI test; threshold 3.0; seed 11; no HAI threshold search. Log names `model:atlas-mahalanobis-physical-roles` / `zero-shot:hai-physical-roles`. Measured **1078.99** FP/normal hour, window recall **1.00**. Native in-plant HAI Mahalanobis **646.58** remains the public HAI ruler. Transfer is louder. Caveat `TRANSFER_IS_PHYSICAL_ROLES_NOT_IDENTICAL_PLANTS`. The Benchmark v1 HAI→BATADAL cell stays REFUSED.

Script: `scripts/evaluate_cross_plant.py`. Tests: `tests/atlas/test_cross_plant.py`.


## The stronger-engine lanes beside the frozen detector (ADR 0273)

`atlas-v1-consistency` is frozen and never edited. Every attempt at a stronger engine is a new
module appending **extra score columns** to the same matrix, sent through the unchanged `events` and
`budget_alerts` so the new columns compete with the per-signal columns for the same eight alerts a
shift rather than being added on top of them.

`phos.atlas.command_consistency` (lane 1, **kept**, ADR 0276) — `unknown_writer` and
`unknown_reader`, a write or a read from a role that never did so in training, scored apart and never
pooled (ADR 0034). 87 of 120 held-out attacks against the frozen 49, `recon` 0 to 20 of 20. The gain
is **attribution**, not command-against-physics: an attacker on the operator's own station defeats it.

`phos.atlas.breadth_consistency` (lane 2, **undeclared**) — one column, the sum over signals of each
signal's score capped at `THRESHOLD`, so breadth across instruments drives it and depth in one
cannot. Tied twice, 24 of 60 and 32 of 70, because every class in the corpus moves one thing and a
multi-signal attack a cross-signal detector can already see does not need breadth. Needs an attack
invisible **per signal** — level and flow biased together in the plant's own ratio — which is a
declaration of its own, not an adjustment to ADR 0285's magnitudes.

`phos.atlas.drift_consistency` (lane 3, **undeclared**, ADR 0286) — one leaky accumulator per
signal over that signal's own frozen score: `A[i] = max(0, r * A[i-1] + score[i] - slack)`, slack the
attack-free 0.99 quantile per signal, `r = 1 - 1/detrend_window` so the tally remembers exactly as
long as the detrender forgets, each column calibrated by the third-largest attack-free episode peak
and clipped at `CONTRIBUTION_CAP = ONSET_LEVEL / ONSET_FRACTION`. **53 of 70 against 32** on
`phos-icssim-dev2`, nothing lost, `liar_freeze` 1 of 10 to **10 of 10**, `creep_many` 22 s earlier —
and median delay worse at every setting, so it failed its bar.

`phos.atlas.bending_consistency` (lane 4, **undeclared**, ADR 0288) — the one lane that appends no
column: the same ridge over a hinge basis, `[x, max(0, x - t_1), ...]`, knots at attack-free
quantiles per signal, inputs clamped to the training range so the predictor saturates rather than
extrapolating. Still linear in its parameters, so still one solve per signal from one shared Gram,
still excluding the target's own history. **With zero knots it is the frozen detector, pinned
bit-for-bit by a test.** Out-of-sample false alarms fell **28.00 to 20.00–24.00 a day** and benign
alerts **5 of 20 to 1 of 20**; catches fell **32 to 23–25** at every setting, `liar_freeze` to 0 of
10. A crude predictor is surprised easily and a faithful one explains more of what it sees, the
attack included — so part of the frozen engine's detection is a side effect of its misfit. Note for
any future false-alarm claim: the frozen engine measures **18.00/day in sample against 28.00
leave-one-out** on the same runs.

**The constraint that sank lane 3, which binds every lane that appends a column (ADR 0286).** `events` places an
event's alert at the earliest member reaching `level = max(ONSET_LEVEL, ONSET_FRACTION * best_peak)`
and **skips any member whose own peak is below that level**; alone, an episode always qualifies
against itself because `level` is clamped by `min(best_peak, ...)`. So a weak per-signal episode —
peak between `THRESHOLD` and `ONSET_LEVEL`, which is what an instantly-caught `replay` looks like —
loses the right to place its own early alert the moment a stronger appended column joins its group.
On a saturated budget the two cannot be separated: a column must score high to win a slot, and that
is the same number that takes the placement. A delay-aware rule is a **new** grouping function beside
the frozen one, never an edit to it. It does **not** reach lane 4, which appends nothing; ADR 0286
carries a dated correction where it assumed otherwise.

### The placement question, tested and refused (ADRs 0398, 0399)

`phos.atlas.placement_consistency` (undeclared) is that new grouping function, built and measured
once. It places each event's alert at the **earliest sample any member of the group is at or above
`THRESHOLD`**, and derives no onset level from the group's strongest peak; the event's score stays
that peak, so the budget ranks the same events onto the same slots. It has no constant of its own.
Lane 3's matrix, unchanged, goes through it.

**Three of the four bars failed.** 49 of 70 attacks against the frozen 32 (bar 1 met, strictly more),
paired set **30** against 32 (bar 2 failed), paired median delay **0.80 s** against the frozen
0.85 s but own-set median **6.10 s** (bar 3 half met, both must hold), benign **8 of 20** (bar 4
failed).

**The answer to "statistic or placement?" is: both, and the rule's share is not enough.**
Replacing the placement recovers the paired delay outright — 5 s to 0.80 s, 8 alerts earlier and
none later on the same 30 attacks — so ADR 0286's diagnosis was right. It was incomplete:

- **Bar 4 belongs to the statistic.** 8 of 20 before and after. The rule re-timed benign alerts and
  the count did not move; placement cannot make a saturated column quieter.
- **Bar 3b belongs to the statistic.** The 17 attacks the frozen engine misses are the slow
  accumulated ones with an **11.0 s** median delay alone, so any engine catching more of them raises
  its own-set median. On this corpus no such engine can meet that reading.
- **Bar 2 is a fresh defect in the new rule, the mirror of the old one.** The frozen rule can place
  an alert too late by skipping a weak member; this one can place it too early, crediting a crossing
  far before the attack. `mixed2-96213`'s `rogue_command` lands **378.4 s before** its window and
  `mixed2-96217`'s `replay` **40.8 s before**, each spending one of eight shift slots. A rule that
  only moves earlier must eventually move earlier than the event. No look-back dial was added after
  seeing this; that is a different rule and needs its own declaration.

## Onboarding brief (`atlas/onboarding/`, ADR 0220 / 0341)

Reads a historian export — CSV or `.csv.gz`, wide or long — and proposes a role and a kind for each
tag, printing the token or statistic each proposal came from. `suggest` keeps historian order and
appends capture-only tags. A kind comes only from a name token; a statistic and a capture never
assign one (ADR 0220 Decision 2). A token wins the role, and a statistic is used only where no
token named one: a sample that sits and then steps suggests a setpoint, one that keeps moving
suggests a sensor, and a constant sample names no role because it cannot separate a setpoint from a
stuck sensor. A capture write against a sensor token is printed and the token is kept.

**A suggestion is not a declaration** (ADR 0123). The package does not call `load_roles`, writes no
role file, and its brief header says so. It is passive: no network calls, no agents, no
subprocesses, and file reading happens only in `main`.

**ADR 0341** made the capture optional, so a historian export alone produces a brief — the easy
half of the ask no longer waits on a span port — and added `phos onboard` beside
`uv run python -m phos.atlas.onboarding`, which still works. A `--capture` that is
named and cannot be read is still an error. **C2 is still not met:** ADR 0220 Decision 5 gates it
on the timed human trial at `eval_runs/build/v1/tools/c2-trial.md`, and a reachable command is not
a trial. v1 stays 8 of 12.

## Build brief H, rung H1 — judged and refused (ADRs 0368, 0369, 0370, 0371)

**The question.** Given a plant's controller program, the physics of its process, and the laws
its engineers sign, which departures break at least one of the three, and which break none?
ADR 0368 named four rungs in a fixed order: H1 derives laws from the controller program, H2 adds
physics balances, H3 writes a detectability prediction before an attack corpus is generated, and
H4 searches for departures that break nothing. The brief is
[`docs/build-brief-2026-10-h.md`](../docs/build-brief-2026-10-h.md).

**What is open.** ADR 0369 amended ADR 0368 Decision 5, and only Decision 5. H1 runs now beside
brief G, in its own worktree on `build/h-triangulation`, touching no file under
`src/phos/atlas/packet/`, no law predicate, `declared_law.py` or `law_inlet.py`, and no file a
brief G lane owns. H2, H3 and H4 are closed until after 6 January 2027, or until a later record
opens them, because the Ofwat Catalyst bid takes priority over further engine work. Reaching the
date is not a declaration; each rung still needs its own, committed before any code.

**H1's bar.** ADR 0370 is the declaration, written before the code exists. A valve law is derived
from three files of the pinned ICSSim checkout — `src/PLC1.py`, `src/Configs.py`,
`src/ics_sim/Device.py`, read as text, never imported or executed, and never `roles.toml`, which
would be circular — and must equal `controller_valve` literal for literal: close `0.0`, open
`1.0`, release mode `3.0`, belt `1.0`, with the same comparisons, the same band ends, the same
guard, and the same answer on an exhaustive enumeration of threshold and mode cases. A derived
law that disagrees is refused. `controller_valve` is not edited to match it and its literals do
not move.

**The refusal named in advance.** `Device.py` treats a valve as manual at mode `1` or `2`;
`controller_valve` treats it as released at exactly `3.0`. The two differ at mode `4.0`. A
derivation that emits "not 1 and not 2" has not produced the literal `3.0`, so it is refused —
not patched by hard-coding the literal, and not patched by widening the hand law.

**Certificates.** Every break the derived law produces carries the law, the rows it was evaluated
on, and the comparison that came out false, so a person holding the rows can recheck it without
PHOS. A certificate has no field for a confidence, probability, weight, magnitude or score, is
refused by the same score-word check as a placed sentence (ADR 0323), and is not a `LawBreak`
subclass, so page admission stays `type(item) is LawBreak` (ADR 0322).

**Built, 29 October 2026.** `src/phos/atlas/code_law/` is the derivation. Six
modules: `source.py` reads the three declared files and refuses any whose sha256 does not match
(an absent file and a file that is not UTF-8 are refusals too, and a refusal returns rather than
raises); `parse.py` holds the small readings of the syntax tree; `law.py` is the derived law as
values, each number carrying its file and line; `derive.py` assembles them and returns a refusal
naming anything the provenance table wants and the source does not hold; `certificate.py` builds
the break and its working; `agreement.py` computes the bars. `report.py` renders the result.
Nothing imports, executes or simulates the controller source: `ast.parse` builds a tree and no
statement in it is run. `roles.toml` is not read, because a derivation compared against a
hand-written quotation of the same source is compared against itself.

Three design points a later reader should not have to re-derive. The **release literal and the
guard are kept apart**: the literal is a tag default from `Configs.py`, the guard is what
`Device.py` states, and they are different facts, so `DerivedGuard.states_only` answers bar 4
from the guard's *form* rather than by trying modes — which means the answer does not depend on
which values anyone thought to test. The **enumeration compares sentences, not numbers**: the
derived law words its break exactly as the hand-written law words it, and the two are compared
through the public `assess_plant` over 1620 cases, which carries the side and the required value
in one comparison and is what would reach the page. **Bar 7 is reported as not computed**, because
the suite, `mypy --strict`, `ruff` and an empty diff on `declared_law.py` are commands a session
runs and reports, not something the module can honestly assert about itself; a report that
claimed seven met when six were checked would be the failure this programme exists to prevent.

**Judged, 29 October 2026 (ADR 0371): refused.** ADR 0370 was in `HEAD`,
`eval_runs/build/lane-h/` did not exist, the three declared digests matched on disk, and the
command `uv run python scripts/lane_h_code_laws.py --icssim data/icssim-source/repo` was run
once, by a session that did not build the derivation. Exit status 1. Report
[`eval_runs/build/lane-h/h1-code-law-agreement.md`](../eval_runs/build/lane-h/h1-code-law-agreement.md),
result name `code-law:valve-agreement`. It was not rerun, nothing was tuned,
`eval_runs/log.jsonl` was not appended, and `controller_valve` was not edited.

Six bars met, one not. **Bar 1** — `close 0.0` from `src/PLC1.py`:18, `open 1.0` from
`PLC1.py`:20, `release_mode 3.0` from `src/Configs.py`:49, `belt_past_filler 1.0` from
`PLC1.py`:26; every citation was checked against the pinned source by hand, and
`TAG_TANK_OUTPUT_VALVE_MODE` at `Configs.py`:57 also defaults to `3`, so the two defaults the
derivation requires to agree do agree. **Bar 2** — the input rule is the maximum first then the
minimum as an `elif`, both strict, with no `else`, so the band including either end is silence.
**Bar 3** — the output rule is the `or` with an `else` that writes `1`, so either equality opens.
**Bar 5** — 1620 cases, none parted. **Bar 6** — 126 certificates, each naming its rows and its
false comparison; independent arithmetic over the enumeration reaches the same 126 (36 input-side
and 90 output-side breaks). **Bar 7** — the report's row 7 says "not computed here", which is the
module declining to assert about itself; the judging session ran the commands and got 4879
passed, 11 skipped, 85 deselected, `mypy --strict src` clean over 276 files, `ruff` clean, and an
empty diff on `declared_law.py`.

**Bar 4, guard agreement, is not met**, and ADR 0370 says missing any one bar is a refusal of the
derivation. `src/ics_sim/Device.py`:404 is `_check_manual_input`, returning true at mode `1` and
mode `2` and false otherwise, so the derived law states its comparison at every other mode;
`controller_valve` states it only at `3.0`. The two agree at modes 1, 2 and 3 and part at 4. That
is the divergence ADR 0370 named before the code existed, and it was not closed in either
direction: no `3.0` appears in `derive.py` or `parse.py`, the release literal is read from
`Configs.TAG_LIST`, and the hand law's release test was not widened.

Three readings worth not re-deriving. **What bar 5 covers**: 1440 of the 1620 cases have mode 1
or 2 on at least one tag, where both laws are unstated — agreement in silence, not agreement on a
decision. The 180 cases with both modes at `3.0` are where either law speaks, and 126 of those
produced a break on which the two wrote identical sentences. Mode `4.0`, where the two are known
to part, is outside the declared enumeration by construction, so bar 5 could not have caught the
divergence and bar 4 is the bar that does. **One report column overstates**: the literal table's
"As the source writes it" is read from the source node for `close` and `open` (`0` and `1`) and
reconstructed from the derived float for `release_mode` and `belt_past_filler`, so it prints
`3.0` where `Configs.py`:49 writes `3`. Value, file and line are right in every row, which is
what bar 1 asks, so the bar is met; a successor should take `literal_text` from the node for
every literal. **The derivation reads half the guard**: `_check_manual_input` forces the actuator
to `0` at mode 1 and to `1` at mode 2 *and* returns false otherwise. The derivation reads the
second half only, so its law is silent where the source is deterministic. No bar asks for the
manual writes, so none fails, but a rung that wants the derived law to stand without the hand law
beside it must read them. Relatedly, `DerivedGuard` can only hold an exclusion list, so
`states_only` is a constant false for every law this module can build — the honest answer for
this source, and the reason a successor that meets bar 4 needs a guard type holding both shapes.

**What it establishes, and what it does not.** A valve law can be read out of a controller's own
program without running it, and on four of the five agreement bars a machine that never saw the
hand copy confirms the human's October transcription. It does not establish more than that: a
derivation wrong in exactly the way the hand copy is wrong would have met every bar, which
ADR 0370 said in advance and this result does not close. Nothing here is a detection claim — no
corpus scored, no held-out corpus opened, no attack generated, and no rate, recall, percentage or
coverage figure exists for this rung. ADR 0336's finding that the law page is empty on every
corpus run is untouched. Nothing transfers to ladder logic, structured text or a vendor binary:
ICSSim's controller is Python, and reading it with `ast` is not reading an IEC 61131-3 program. No
derived law is on the law page; wiring one into the register needs its own declaration. The six
laws stay six. H2, H3 and H4 stay closed until after 6 January 2027 or a later record (ADR 0369);
reaching the date is not a declaration. ADR 0378 and note 158 stay reserved for the programme
close, which this is not. v1 stays 8 of 12. P1 stays blocked.

**The mode has no enforced domain, 29 October 2026 (ADR 0380).** ADR 0371's refusal left one
factual question open: can `tank_input_valve_mode` or `tank_output_valve_mode` ever hold a value
other than 1, 2 or 3? The pinned checkout was read again as text — nine files digested, nothing
imported, executed or simulated, no corpus opened, `roles.toml` still unread — and the answer is
that such a value is **reachable**.

Under the simulator's intended operation the two tags hold only 1, 2 or 3. Exactly two things
write them: `PLC._before_start` pushes the tag table's `'default': 3`
(`Device.py:395-397`, `Configs.py:49` and `:57`), and `HMI2` sends what the operator typed
(`HMI2.py:47`, `:50`). The operator's value is bounded by a range test in a terminal prompt,
`int(input('Command (1 to 3): '))` with a `ValueError` outside 1–3 (`HMI2.py:77-79`) — and that
prompt is the only validation of a valve mode anywhere in the checkout. Nothing else writes
them: `CommandInjectionAgent` targets the three *status* tags, `DDosAgent` only reads, `PLC2`
owns the belt mode, and the replay attack resends what it sniffed.

Below that prompt nothing narrows the value. `ModbusBase.encode` multiplies by 10 000 and
refuses only above 2³², so the register pair carries any multiple of 0.0001 up to 429 496.7295;
`decode` divides and always returns a float; the server, the actuator connector and every
`Connector.set` pass it through untouched. `_check_manual_input` (`Device.py:404-414`) tests
`mode == 1` and `mode == 2` and returns false otherwise, with no branch for an unexpected mode
and no log line that notices one.

And the repository ships an attacker that produces such a value. `ScapyAttacker.inject_callback`
rewrites the data words of every Modbus write request and read response it sees with
`new_value = value + (value * error)` (`ScapyAttacker.py:147-150`); it reads the register address
only to fill a log record (`:160`) and never compares it, so the rewrite hits every tag alike.
The default error is 0.1 (`Attacks.py:32`, `AttackerBase.py:107`) and `AttackerMachine` schedules
fourteen MITM runs in its scenario (`:23`). An operator's "auto" command of `3` crossing one of
those windows lands in the register as `3.3` — not 1, not 2, so the comparison runs, which is
what the derived law says and is not what `controller_valve` says. PHOS's own generator writes
only 1, 2 or 3, in four places (`phos_icssim.py:572`, `575`, `593`, `597`, `635`, `637`, `648`,
`650`).

**What that settles and what it does not.** The difference ADR 0371 recorded is live rather than
an artefact of two wordings: at a value this plant can carry, the two guards give different
answers. It does not say which rule is right. The hand rule is faithful to the mode the tag table
calls normal; the derived rule is faithful to the function the controller calls; a plant's
engineers might sign either, and choosing needs its own declaration. Nothing here is a
measurement — no corpus scored, no held-out corpus opened, no attack generated, no rate, recall
or coverage figure, because reading source cannot produce one. Whether any recorded run actually
contains such a value is a question about a capture and was not asked. Nothing transfers off
ICSSim: a vendor PLC may well reject an out-of-range mode in firmware. H1 stays refused,
`controller_valve` and the derivation are untouched, the six laws stay six, v1 stays 8 of 12, and
P1 stays blocked.

## Build brief H, rung H1: the guard type built and the result refused (ADRs 0382, 0383)

**The decision to adopt, taken before the code.** ADR 0382 records Elijah's direction: the derived
valve rule becomes the **candidate** replacement for `controller_valve`, because it is the
controller's own logic and because reading laws out of a program is the method that could transfer
to a real plant. It keeps nothing. `controller_valve` is not edited, its four literals do not move,
and no derived law is placed on the page. The record also names the two limits ADR 0371 left as
bars so they cannot be dropped in silence.

**The extended enumeration.** ADR 0370's mode set was `{1.0, 2.0, 3.0}` on each tag. ADR 0382
extends it to `{0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0}` on each, keeping the process-value grid
unchanged: five tank levels, three bottle levels, three belt positions, both valves. The product is
8820 cases, exhaustive over the declared grid and not sampled. Its arithmetic splits them 180 where
both tags are `3.0` and both laws decide, 4320 where at least one tag is `1.0` or `2.0` and both
laws are silent, and 4320 where both tags sit outside `{1.0, 2.0}` and are not both `3.0`, which is
the live gap. Those counts are arithmetic on a declared set, not a measurement.

**The guard type.** `GuardForm` has two members, `EXCLUSION` and `EQUALITY`. `DerivedGuard` holds
one of the two and refuses a constructor that sets both or neither. `guard_from_device` reads the
two `if mode == N` branches out of `_check_manual_input` and builds an exclusion;
`hand_guard` builds an equality at the release literal. `differs_in_form_from` is a comparison of
the two enum members and `states_only` answers an exclusion with `False` without consulting a
value, so ADR 0382 bar 3 is answered from the form rather than by trying a mode list. That was
ADR 0371's named precondition for comparing the two guards at all.

**Judged, 30 October 2026 (ADR 0383): refused.** ADR 0382 was in `HEAD` at `ab4fba1`,
`eval_runs/build/lane-h/h1-guard-form.md` did not exist, ADR 0383 was free on every branch, and
the three pinned digests matched on disk. The command
`uv run python scripts/lane_h_guard_form.py --icssim data/icssim-source/repo` was run once by a
session that did not build the guard type. Exit status 1. Report
[`eval_runs/build/lane-h/h1-guard-form.md`](../eval_runs/build/lane-h/h1-guard-form.md), 4396
lines, result name `code-law:guard-form`. It was not rerun, nothing was tuned, and
`eval_runs/log.jsonl` was not appended.

Six bars are met and bar 7 was answered by the judging session: `pytest -q` gave `4899 passed, 11
skipped, 85 deselected`, `mypy --strict src` was clean over 276 files, `ruff` was clean, and
`declared_law.py` had an empty diff. Bar 1 now quotes `3` from `Configs.py`:49 rather than printing
`3.0`, closing the overstatement ADR 0371 recorded, because `literal_text` comes from the node for
every literal. Bar 4 is met by a new fact: `_check_manual_input` forces the actuator to `0` at mode
1 and `1` at mode 2, and `forced_writes_from_device` reads those `_set` calls into
`law.forced_writes`, kept apart from `law.rules` so the write is carried and not folded into the
comparison.

**Refused, and the reason is not a missed bar.** The report's own overall standing is `not met`
because its row 7 declines to assert about itself, which is honest; the judging session answered
it. Taken bar by bar, all seven are met. What the record says instead is that three of the bars
could not have failed here. Bar 3 is a statement about the code: any source with that guard shape
and any hand law written as an equality satisfies it. Bar 5 asks that every disagreement be listed,
and an accurate list of a total disagreement satisfies it, though `_enumeration_bar` fails an empty
list so editing either law to agree would have failed the bar rather than passed it. Bar 6's text
check tests a literal tuple for the `comparison` and `required_because` fields rather than calling
`_score_word`, and those strings are rendered by f-strings and never passed through
`cited_statement`; the derived law cannot currently emit a score word, so no certificate is wrong
today, and the gap is stated so a successor does not read the bar as enforced.

**4320 of 8820 cases disagree, all of them on standing.** Among the 180 cases where both laws
speak, the two write the same sentence, so there are no actuator disagreements and the report's
4320 entries are all guard partings. The direction matters more than the count: the derived rule
checks the valve at any mode that is not 1 or 2, and the hand rule checks it only at exactly 3, so
at `3.3` (what ADR 0380 showed a middle-man rewrite makes of an operator's `3`) the derived rule
looks and the hand rule shrugs. That is the case for the candidate. This run states it and does not
settle it.

**The old run cannot be reproduced from `HEAD`.** The builder rewrote `parse.py`, `law.py`,
`derive.py`, `certificate.py`, `agreement.py` and `report.py` in place; only `source.py` is
byte-identical to the ADR 0370 build, and `scripts/lane_h_code_laws.py` changed by one docstring
line. None of the digests ADR 0371 recorded for those six modules exists in `HEAD`. The report at
`h1-code-law-agreement.md` stands as the record of what that code did on 29 October 2026 and must
not be rerun; a changed derivation gets a new declaration and a new result name, which ADR 0382 is.

**What it does not show.** No corpus scored, no held-out corpus opened, no attack generated, no
rate, recall, percentage or coverage figure. A derivation wrong in exactly the way the controller
program is wrong would meet every bar, which ADR 0370 said in advance and this does not close.
Nothing transfers to ladder logic, structured text or a vendor binary. No derived law is on the law
page. H2, H3 and H4 stay closed until after 6 January 2027 or a later record (ADR 0369). The six
laws stay six, v1 stays 8 of 12, and P1 stays blocked.

## Tests worth naming

`test_templates.py` (indistinguishability), `test_command_eval.py` (empty discovery), `test_command_grounding.py`, `test_command_evidence.py`, `test_joint_gate.py` (dwell=1 no-op), `test_phased.py`, `test_never_actuates.py` (issuer from graph; 0/16 and 1/4 not pooled), `test_clock_b_schemas.py` (reconstruction completeness is not unique lead), `test_cross_plant.py` (declared roles; SWaT form-gated; no public log-name reuse), `test_drift_consistency.py` (the tally is bounded, re-arms, never goes negative, and the cap is where the onset level stops rising; the frozen scores come back bit-for-bit), `test_bending_consistency.py` (zero knots reproduces the frozen detector exactly — the pin that makes the bend the only difference; the target never predicts itself; attack rows reach neither the knots nor the calibration), `packet/test_hardening.py` (fuzz: nothing escapes), `packet/test_graph.py` (duration mismatch is not silence).

## Related

**One engineering roadmap (ADR 0420, 3 November 2026).** `docs/atlas-engineering-roadmap.md` is the
only Atlas engineering sequence. Seven programmes had been open at once — the daily-leaps contract,
roadmap F, briefs G and H, the zero-to-one plan, GENESIS and P1 — and none of them named a criterion
it moved; six were opened while P1 was blocked, which is the cause rather than a lapse of discipline,
since P1 is what orders the work. The roadmap is organised around **A1–A7**, frozen with their
definitions in `docs/v1-roadmap.md` before any result, which is what makes them usable as a
destination.

**Gathered in one place for the first time, Atlas stands at five of seven.** A1 met (ADR 0264,
grouped block not recomputed), A2 met (strictly higher than grouped MinMax on 5 of 5, beyond every
chance draw on 4, every corpus seen), A4, A5 and A6 met. **A3 is not met:** its top-tenth fraction was
retired as an instrument (ADR 0290) because the shift queue is shorter than the alert budget, Bet 003
froze coverage, position, story and load in operator units instead, and a ranking stage in
`src/phos/atlas/queue.py` was built and refused (ADR 0068). **A7 is not met:** three frozen benchmark
constants and the outside run, with both looks spent (ADRs 0268–0272). With C1 met, C2 not, S1 and S2
met and S3 not, that reconstructs the recorded **8 of 12** without a new measurement.

**A3 and A7 are recorded as questions, not tasks.** A3 has already had its instrument replaced once
and its ranking stage refused once; A7's two looks are spent. Each needs its own declaration stating
in advance what would show the criterion cannot be met, and a record saying it cannot is an ending
rather than a gap. A7 ranks above A3: A6 is met, but a single configuration nobody outside can execute
is a claim about a private machine, and A7 is the only criterion whose failure is partly
infrastructural rather than scientific.

**The engine spine is the declared-law page** (`declared_law.py`, `law_inlet.py`, ADR 0325), which is
what makes the constitution's speech contract code rather than intention. **Dispositions:** roadmap F
and the daily-leaps contract absorbed; brief G parked by ADR 0420 and **unparked** by ADR 0422, and brief H
**adopted** as Acts II–IV. G was parked because further protocols move neither
open criterion and a second dissector without a partner capture is specification without evidence, H
because its rungs H2–H4 were already closed until 6 January 2027 for the Ofwat Catalyst bid; brief E
stays closed with 0277–0284 unwritten. Parked means not deleted, not forbidden, and not restarted
without a record naming the criterion it moves. GENESIS is the method and is not a step. The first
item is the **ADR 0316 debt** — declared and never scored. **Lifts nothing:** P1 blocked, no
Intelligence, API or UI, frozen numbers frozen, tiers standing, v1 stays 8 of 12 and its freeze date
stays 24 January 2027.

## Build brief H, rung H2 — opened for its declarations, and the physics turns out to be unreadable by the engine (ADRs 0423, 0372)

**What opened, and what did not.** ADR 0369 closed H2, H3 and H4 "until after 6 January 2027, **or
until a later record opens them. Whichever comes first.**" ADR 0423 is that record, for H2 and for
one half of it: the laws may be **declared**, while the corpus, the generation, the scoring and the
verdict stay closed. The separation is that **declaring a law is a document and scoring it is a
programme**; the two halves were closed together because nothing had separated them. H3 and H4 stay
closed, ADR 0369 is not edited, and reaching the date is still not permission.

**What ADR 0423 also records.** The window ADR 0369 protected was not spent on the bid. Between 29
October and 7 November the packet foundation was judged (ADR 0346), brief G was unparked (ADR 0422),
an S7comm lane was declared, built, judged and landed (ADRs 0347, 0348), the roadmap was consolidated
(ADR 0420) and H1 ran and had its guard form refused (ADR 0383) — while the bid's own blocking step,
a licensed water company to lead the entry, still reads **Not started** and three emails drafted on
4 October still read **Not sent**. Closing a rung is not the same as advancing a bid. The expensive
half stays closed on its own merits rather than on that premise.

**The inlet is not measured.** Rung H2's worked example is "level change against flow in and flow
out". `data/phos-icssim-dev/roles.toml` carries **thirteen** tags, each role read from ICSSim's own
source at the pin and from nothing else, and **exactly one is a flow: `tank_output_flow_value`, the
outlet**. The simulator does compute an inflow — `ICSSIM_EDGES` carries
`("tank_input_valve_status", "tank_level_value")` for a tank that "fills through the input valve" —
but never publishes it as a tag, so the inlet reaches the data only as open or shut and never as how
much. The brief's own rule decides the rest: a quantity the corpus does not supply means the law is
**refused rather than approximated**, so the inflow is not guessed from the valve state. Register
entry **R29**, whose lift column names the cheapest instrument that moves it: **one flow meter on the
tank feed.** The never-read corpora cannot supply it either (`data-tiers.md`, ADR 0143).

**The finding: the physics exists, and Atlas is forbidden to read it.** This was not anticipated when
the rung was named. `src/phos/breaking/icssim_truth.py` carries twenty-one `driver -> driven` edges
read from `src/FactorySimulation.py` at the pin, including the pipework a physics law needs — the
bottle "fills from the outflow only while it is under the filler" — and ADR 0295 quotes that file's
constants (`TANK_OUTPUT_FLOW_RATE` 0.0001 litre per millisecond, `TANK_LEVEL_CAPACITY` 3 litres,
`TANK_MAX_LEVEL` 10). Its docstring forbids exactly this use — "**This is ground truth, so nothing
that learns may read it** … no module under `phos.atlas` imports this one, which a test checks" —
enforced at `tests/atlas/test_interventions.py:57`. The one source Atlas may read states no physical
relation at all: `roles.toml` gives tag roles and six **control** loops, no connection and no physics
constant, and its header closes the last shortcut, since roles were "Never inferred from the data,
and never from a tag's name." Every physics law relates two tags, so **H1's derivation does not
transfer**: H2's laws can only be hand declarations, at the exact standing of `controller_valve` —
the hand copy H1 exists to distrust. Register entry **R30**.

That is the product's shape arriving earlier than expected rather than a defect in the rung.
`DeclaredLaw` is documented as "a law the plant or the operator **already declared**": a plant
declares its physics and Atlas checks the plant against it. Atlas does not discover physics from
traffic, and R30's lift column says that lifting the entry must not let it start.

**The three laws, declared by hand, citing documents and importing nothing.**
`closed_outlet_no_flow` — output mode release and output valve closed means `tank_output_flow_value`
is zero; a non-zero reading through a shut valve means one of the two tags is wrong, and zero is not
a threshold anybody chose. `no_inflow_no_rise` — input mode release and input valve closed means
`tank_level_value` does not rise between consecutive samples; the break is a strict rise.
`outlet_rate_is_the_quoted_rate` — both modes release, inlet shut, outlet open and water in the tank
means the fall in level over an interval is `TANK_OUTPUT_FLOW_RATE` divided by `TANK_LEVEL_CAPACITY`
times the elapsed milliseconds. That third law is the only **quantitative** balance the corpus
supports and is the outlet half of what the brief asked for; its constants enter code the way
`controller_valve`'s four literals do, with their provenance quoted above them. Manual mode means a
law was not stated, and no statement carries a number.

**Both loose ends are declared, not deferred.** If quantisation makes the level read as a strict rise
while the inlet is shut, `no_inflow_no_rise` needs a tolerance, and none is quoted anywhere: ADR 0372
rules the law **refused, not given one**, because a tolerance chosen so a law passes is a knob. If the
corpus's sample timing cannot support an exact-up-to-floating-point comparison,
`outlet_rate_is_the_quoted_rate` is refused too. The rate is never fitted — ADR 0295 established this
plant has no continuous level-to-flow ratio, so there is nothing to fit.

**The bars are frozen before the build.** All three laws in `LAWS` with no numeral and no word from
`_SCORE_WORDS`; `CONTROLLER_VALVE` and its four literals byte-identical, since a hand copy is never
edited to make a new law fit; no module under `phos.atlas` importing `icssim_truth` and
`tests/atlas/test_interventions.py:57` still passing, with the two constants typed in beside their
provenance rather than imported; `inlet_balance` present as no code path under any name; and a break
producing a `LawBreak` that routes per ADR 0108 with equipment failing among the explanations, never
an attack claim on its own. Two prerequisites are recorded now: `ControllerSample` carries ten
measurements and none is the outlet flow, and two of the three laws need **two consecutive samples**
of one tag, a shape the register has never had. Neither is a reason to weaken a law.

**Lifts nothing.** No corpus opened, no command run, no code written, ADR 0373 reserved and unwritten.
The declared laws stay six until the build lands. v1 stays **8 of 12** with A3 and A7 open, tiers
stand, frozen numbers stay frozen, 0277–0284 stay unwritten, and **P1** stays the blocked human
conversation with Intelligence, the API and the UI behind it.

Volumes [10](10-synth-breaking-library.md), [11](11-data-licences-measurements.md). ADRs 0009–0014, 0018–0019, 0026–0027, 0034–0040, 0046–0048.

