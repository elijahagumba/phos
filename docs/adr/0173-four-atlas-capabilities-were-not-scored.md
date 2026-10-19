# ADR 0173 — Four Atlas capabilities were not scored this round

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane E
- **Depends on:** [ADR 0170](0170-every-control-coupling-is-a-loop-and-bars-only-its-outputs.md),
  [ADR 0171](0171-explanation-confidence-is-calibrated-by-evidence-shape.md),
  [ADR 0172](0172-root-cause-ranking-points-an-alert-upstream.md)

## Context

Round 2 asked for event fusion, slow-drift detection, redundancy voting,
a command baseline, and maintenance patterns that lower rank without closing
an alert. Naming, calibrated confidence, and root-cause ranking were scored
on development seeds. The rest were not given a number.

## Decision

1. **Slow drift.** The scored liar is a step hold. No ramp corpus was
   generated. A recall on the step is not a slow-drift result, so none is
   quoted.
2. **Event fusion.** Merging alerts would change how many distinct attacks
   fit in eight per shift. That change was not built, and HAI 20.07 was not
   opened for it.
3. **Redundancy voting.** Chlorine residual, distribution pressure, and
   reactor pressure moved under ADR 0170's naming rule. A second voter was
   not added on top.
4. **Command baseline.** ICSSim development did not start: the harness binds
   addresses macOS does not have without extra privileges. No 4SICS pcap is
   on disk. No commander baseline was fitted.
5. **Maintenance without a work log.** Lane B's closer cites a work order or
   stays open. This lane did not add a rank penalty for a maintenance-shaped
   pattern.

GRFICS stays a machine limit: neither Docker nor Podman is installed.

## Consequences

The held-back look (seeds 97101–97120) scores only the three kept pieces:
naming, shape-calibrated confidence, and root-cause ranking. It does not
tune them.
