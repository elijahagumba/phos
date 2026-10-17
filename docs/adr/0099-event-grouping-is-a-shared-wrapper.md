# ADR 0099 — Event grouping is a shared wrapper, and it has not been scored

- **Status:** Accepted
- **Date:** 2026-10-05
- **PART:** v1, after the sandbox finding and before any grouped row
- **Depends on:** [ADR 0095](0095-g1-baseline-table.md),
  [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md)

## Context

ADR 0096 found that grouping alerts into events, not a new detector, explains the sandbox
gap: MinMax's own rule with that grouping caught 41 of 50 on HAI 21.03, beside the
candidate's 42. It forbids comparing a grouped Atlas with ungrouped opponents. The
constants were chosen on HAI 20.07. They have to be written down, and shared, before
any grouped row is scored.

## Decision

`phos.eval.grouping.group_published_alerts` is the wrapper. It takes the alerts a
detector already published and returns one alert per event. It does not know which
detector that was. The constants are exactly the sandbox values, in seconds:

| Constant | Value |
|---|---|
| `FEATURE_GAP_SECONDS` | 60 |
| `EVENT_WINDOW_SECONDS` | 300 |
| `EVENT_SPAN_SECONDS` | 600 |
| `ONSET_FRACTION` | 0.1 |
| `ONSET_LEVEL` | 2.0 |
| `GROUPED_ALERTS_PER_SHIFT` | 8 |

A gap of 60 seconds on one feature closes into an episode. Episode onsets within 300
seconds, spanning at most 600 seconds, form one event, scored by its strongest peak.
The alert is placed where a member first reaches `max(2.0, 0.1 * peak)`, and not after
the peak. Each 8-hour shift, counted from the series' first timestamp, keeps the eight
strongest events. The sandbox's spare second alert at the peak is not part of this
wrapper.

On a one-second grid, 60 seconds is the sandbox's 60 samples. On an hourly grid it is
still 60 seconds, not 60 hours.

Nothing is scored. HAI 20.07 and 21.03 are not grouped in the table yet. HAI 22.04 and
23.05 stay unscored.

## Consequences

A later grouped row uses this function for Atlas and for every checked opponent. A
grouped Atlas beside an ungrouped opponent is not a result. Changing a constant is a
new wrapper, with a reason written before it is scored.

## What would reverse this

A grouped score that does not call this function, or a constant here that is no longer
the sandbox value.
