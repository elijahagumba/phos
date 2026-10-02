# ADR 0028 — Precision policy: volume, peer-match, and the family gate

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Sentiel IT core (cycle contract: usable precision at 30–50 alerts/day-equivalent)
- **Supersedes:** nothing
- **Depends on:** [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md)

## Context

PART 6B's aggregated peer run on CERT r3.1 posted **~10.4% precision at 48 alerts** (5 TP / 43
FP, recall 0.5). The score is an equal-weight sum of bounded per-feature contributions over 34
features. That shape stopped the 1,668-alert floor. It did not stop a backup, a late login, or a
busy inbox from looking like an insider at SOC volume.

Three mechanisms, none of them a missing model:

1. **Volume features fire on benign administration.** `file_access_count`, `distinct_files`,
   `distinct_http_hosts` and their `_dev` / `_diff` / `_trend` companions move whenever someone
   has a large day. Equal weight means those days compete with a first thumb-drive connect.
2. **Off-hours is a weak discriminator on this corpus.** CERT's `off_hours` includes weekends.
   Engineers logging in on Saturday look like scenario 1's "begins logging in after hours".
3. **Self-relative without peer-relative is not an alarm.** A person who has changed role, or
   who is covering a colleague, leaves their own past and stays inside their group's envelope.
   ADR 0023's competing set already names that `legitimate_change` / `insufficient_evidence`.
   The templates cannot *contradict* a malicious explanation without sanction evidence, which
   CERT does not carry. So the scoring layer has to stop promoting that window into the budget
   in the first place.

The cycle contract asks the engine to prefer `legitimate_change` or `insufficient_evidence`
when someone matches their peers. Inventing a contradictory pattern would be a claim the
evidence does not support (ADR 0023). Down-ranking the window is the honest lever.

## Decisions

### Decision 1 — Identity remains the default

**Decided:** `AggregationPolicy()` is the PART 6B scorer. Every new factor defaults so existing
rows do not move. `precision_policy()` is opt-in (`--precision-policy` on both evaluation
scripts). Detector names gain `:precision` so a logged row cannot overwrite the 10.4% reference.

### Decision 2 — Stem weights, not dropped features

**Decided:** volume and off-hours stems are multiplied after the bounded squash, not removed.
A backup still contributes; it cannot dominate a window that also has a thumb-drive onset or a
peer departure. An exact `feature_weights` entry wins over the stem, so a later PART can
re-weight one companion without splitting the map.

The factors (0.25 volume, 0.35 off-hours) are **placeholders**, not fitted discriminating
powers, and must not be read as calibrated (Constitution §3.3).

### Decision 3 — Peer-match is a scoring discount, not a new template

**Decided:** if the window *observed* peer features, none of them left their band, and
something else did, every contribution is multiplied by `peer_match_factor` (0.25 in
`precision_policy`).

- No peer features observed → not a match. Ungrouped people are not "like their peers".
- A peer feature out of band → not a match. Unlike the group is the PEER family's job.
- A high-signal stem fired (`removable_device_connects`) → not discounted. CERT names that
  onset; burying it would hide the one behaviour the corpus actually wrote down as a start.

This is not `legitimate_change` winning in the reasoning layer. It is the window falling down
the SOC queue so the competing set is not asked to explain a busy day.

### Decision 4 — Two families, or a named onset

**Decided:** a window whose out-of-band evidence sits in a single `BehaviourFamily` is
multiplied by `single_family_factor` (0.2) unless a high-signal stem fired. Two families is
the scoring-level expression of "more than one artefact", which is what the competing set
was built to weigh over time.

## Consequences

**Gained.** A declared way to stop backups and peer-matching role changes consuming the 48-alert
budget, without changing 6B's default numbers or inventing a contradiction CERT cannot support.

**Cost.** The factors are unmeasured. CERT r3.1's insiders are largely self-relative; if they
also match their (department-sized) peer group, this policy will rank them down, which is the
honest reading of "matches peers → do not alarm" and may cost recall. That is a measurement,
not a promise. Peer-relative positives remain unexercised on this corpus (ADR 0023); this
record does not claim a peer-group detection advantage.

**Unchanged.** Hypothesis confidence is still uncalibrated. No template gained a contradictory
pattern. The 10.4% row stays on the log under its original detector name.
