# ADR 0037 — Silence is judged against a comparable learned stretch

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Command-lead mechanical honesty, session 2 (moving-horizon baselines)
- **Supersedes:** the silence-rate clause of [ADR 0013](0013-command-behaviour-features-device-identity-and-the-command-graph.md) Decision 8 (expectation still comes from the learned graph, never the live span; it is no longer a rate whose denominator is the entire train)
- **Depends on:** [ADR 0013](0013-command-behaviour-features-device-identity-and-the-command-graph.md),
  [ADR 0035](0035-unknown-master-writes-still-do-not-lead.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)

## Context

ADR 0035 measured unknown-master command lead **0 of 4**. The window was flooded with
`silent_command_relationship` (hundreds per attack, ~1450 over the live capture). The expected
count was `command_count / learned_span * window_seconds`. A five-day train versus a 24-hour live
capture, sliced into one-minute tiles, treated every quiet minute of every learned poller as its
own act. Untyped silence still supports `engineering_maintenance`.

That is a duration mismatch, not a plant event. A workstation that wrote twelve times in five days
meets `min_edge_commands` and still produces a fractional per-minute expectation. The old judge
emitted a finding whenever that expectation existed, including when a comparable one-minute
stretch of the train was typically empty.

Session 1 (ADR 0036) is closed. A ceiling or epsilon tie is a refusal; `leads` / `newly_leads`
stay false when attack and maintenance share the lead. This record does not retune
`LEAD_TIE_EPSILON`, invert `template_id` order, or put known-link unexpected function on
maintenance-contradict.

`EwmaBaseline` was compared only as a moving-sensor diagnostic of the same defect (a recent
window's occupancy, not a smeared five-day mean). It is not a public Atlas row and must not
overwrite ungated Mahalanobis or gated joint-moment log names.

## Decision

**A live window is silent only against a comparable stretch of the learned graph.**

Learning records occupancy in one-minute bins (`DEFAULT_GRAPH_HORIZON`, matching
`GraphComparePolicy.window`). At compare time, the expected count is the mean of those bins
(aggregated when the live window is an integer multiple of the bin). The typical count is their
median. A finding is emitted only when the typical comparable stretch carried at least one
command (`_TYPICAL_SILENCE_FLOOR = 1`). That floor is "a comparable stretch typically had a
command". It is not `min_edge_commands` and must not be raised to starve silence until the attack
uniquely leads.

A chatty link that actually talks every minute is unchanged: a one-second poller going quiet is
still reported every live window it misses. `test_silence_is_judged_per_window_not_per_stream`
still holds. Silence is not reported once per capture.

Every silent finding records `learned_span_seconds`, `live_span_seconds`, and `horizon_seconds`
so a duration mismatch is reconstructable from stored `Observation.context`.

**Do not raise `min_edge_commands` to quiet D2. Do not keep cutting silence to manufacture a
unique attack lead.** Horizon matching is the mechanism named in ADR 0035. Causal drowning of
unrelated silence into a window's story is session 3.

## Remeasure (seed 7, issuer kinds apart)

`leads` means `unauthorised_control_activity` is the unique strongest explanation after commands
(`tied_leaders` empty). It does not mean `insufficient_evidence` sorted first. HEAD at measurement
was `77dd731`; the horizon change was in the working tree.

### Known-station (`scada` / `hmi`)

Report: `eval_runs/breaking/breaking-report-known-station.md`.

Of **16** command attacks, structure moved the attack explanation **up in 6** (was 12 under the
flood) and **led in 0**. Water command-evidence counts fell from 84–104 to 0–14. Power stays in
the hundreds: the SCADA poller is actually chatty. Known-link unexpected function still supports
both attack and maintenance (ADR 0014). Do not pool with unknown-master.

### Unknown-master (silent `engineering`)

Report: `eval_runs/breaking/breaking-report-unknown-master.md`.

Graph findings on the live capture: **13** (was ~1450). Command-evidence counts: 9, 8, 14, 3 (was
99, 98, 104, 93). FP/hour remains **1.1650** (21 FP / 18.02 normal hours). Do not quote this
corpus's recall as detection.

Of **4** unknown-master attacks, structure moved the attack explanation **up in 4** and made it
the unique leader in **1** (`wt-unknown-master-near-invisible`). `wt-unknown-master-subtle`
lists at rank 1 but `tied_leaders` is non-empty (two `unauthorised_control_activity` hypotheses),
so `leads` stays false — ADR 0036. Ranks after commands: 2, 3, 1 (tied, not a unique lead), 1
(unique).

That **1 of 4** is a D2 diagnostic that the silence flood was a real mechanism. It travels with
`ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. It is not the ≥70% contract, not a field rate, and not
a reason to cut silence further. Completing session 2 does not earn ≥70%.

## Consequences

**Gained.** Duration mismatch no longer manufactures a per-minute silence finding for every
learned poller. The unit test
`test_a_multi_day_train_does_not_manufacture_silence_every_minute` is the primary success. A
burst smeared across a long train no longer flags every quiet live minute. Chatty silence remains
per-window. Spans are on the finding.

**Cost.** Known-station "moved up" fell 12 → 6 because some of that movement was the flood.
Unknown-master uniquely led in 1 of 4 on attacks we wrote; three still do not. Unrelated silence
can still enter a window's story (session 3). Hypothesis confidence remains uncalibrated.

## Alternatives considered

- **Raise `min_edge_commands` until D2 is quiet.** Hides the flood. Forbidden.
- **Report silence once per live capture.** Breaks a link that dies part-way through
  (`silence-reported-once` mutation). Forbidden.
- **Emit whenever the smeared rate is positive, including fractions.** That is the defect.
- **Fit a per-feature command calibrator on this battery.** ADR 0035 / `POOLED_GRAPH_CALIBRATION_CAVEAT`.
- **Replace public Mahalanobis rows with EWMA.** Frozen public Atlas logs. EWMA is diagnostic only.
- **Keep cutting silence until all four unknown-master windows uniquely lead.** Starves the
  evidence. Session success is matched duration, not a unique attack lead.
- **Count the subtle window's rank-1 listing as a lead.** `tied_leaders` non-empty; ADR 0036
  says that is a refusal.

## When to revisit

When session 3 attaches graph findings only if they share an entity with in-window command
activity, or when a licence-confirmed public command capture is scored with issuer kinds apart.
Not when D2 `newly_leads` flips again.
