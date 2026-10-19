# ADR 0201 — The front page leads with real data, and gives one contact address

- **Status:** Accepted (Elijah's decision, 19 October 2026)
- **Date:** 2026-10-19
- **PART:** the public front page, after [ADR 0200](0200-the-public-repository-takes-the-house-style.md)
- **Depends on:** [ADR 0116](0116-a2-status-four-of-five-beyond-chance.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md), [ADR 0148](0148-bet-001-is-scored-once.md)

## Context

Read as a first visitor would, the front page after ADR 0200 had three problems. Its results card
showed only simulated results and a quiet real plant, leaving out Atlas's strongest real-data
result. Its record page opened with numbers from before the current detector ("about 53 false
alarms an hour"), which read as a contradiction. And it gave anyone who runs a plant no way to
get in touch.

## Decision

1. **The results card leads with real testbed data:** 131 of 160 attacks caught across HAI 21.03,
   22.04 and 23.05 at 8 alerts a shift, against 52 for the best baseline checked, from
   `eval_runs/v1/a2-status.json` (ADR 0116). It is worded "the best baseline we checked", not
   "published method", because the opponent is a simple baseline the lab reproduced.
2. **The record page opens with "start here" and the current numbers**, per edition and with the
   chance null, then the plant map's failed gate (ADR 0143), naming on simulated plants (ADR 0170)
   and Kelmarsh (ADR 0165). The earlier false-alarm figures stay, folded under "earlier
   measurements, before the current detector". Bet 001's loss is stated where the bet is.
3. **One public contact address**, `elijah.phosfounder@proton.me`, chosen by Elijah for the
   README's "Run a plant?" section. The export guard still refuses every other Proton address: its
   pattern excludes only this one (`public/manifest.toml`), so the personal address cannot leak.

## What would reverse this

A front-page figure with no record behind it, the earlier figures presented as current, or the
guard widened to admit any other address.
