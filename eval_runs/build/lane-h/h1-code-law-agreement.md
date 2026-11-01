# code-law:valve-agreement

Declared by [ADR 0370](../../../docs/adr/0370-code-laws-are-derived-from-the-controller-program.md),
build brief H rung H1. This file reports **met or not met** against the bars as that record
words them. Every line in it is a standing, or a count of the cases that were checked. Nothing
in it measures how well anything did, and nothing in it may be restated as if it did.

The law below was read out of the pinned ICSSim source at `bcfd1844d3f063850c69f2643f6a052bac03d8ec`. The source was read
as text and parsed into a syntax tree. It was not imported, executed or simulated, and
`data/phos-icssim-dev/roles.toml` was not read.
<!-- evidence-ack: bcfd1844d3f063850c69f2643f6a052bac03d8ec — the pinned ICSSIM checkout's head under data/, not a commit in this repository -->

## Files read, and their digests

| File | sha256 |
| --- | --- |
| `src/PLC1.py` | `4651130bba9f137108c0426a6fdeb829db8705ea7eeedd40dfab378c9cf51316` |
| `src/Configs.py` | `242e19fe346550fc4614f3511d6eacd91c0dfadb3e9591fd616570352ad23bd3` |
| `src/ics_sim/Device.py` | `574660255d62e29e27015baaa797005071a11f14317af9525b6525258464ae92` |
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

## The bars

| # | Bar | Standing | What was found |
| --- | --- | --- | --- |
| 1 | literal agreement | met | close 0.0 from src/PLC1.py:18; open 1.0 from src/PLC1.py:20; release_mode 3.0 from src/Configs.py:49; belt_past_filler 1.0 from src/PLC1.py:26 |
| 2 | comparison agreement, input side | met | above the maximum closes, below the minimum opens, the band is silence |
| 3 | comparison agreement, output side | met | full or past the filler closes, every other reading opens |
| 4 | guard agreement | not met | the source states the comparison whenever a mode is not manual, and src/ics_sim/Device.py:404 names only 1.0, 2.0 as manual, so the stated set is wider than the single release literal 3.0 |
| 5 | equal decisions on every enumerated case | met | 1620 cases, none parted |
| 6 | certificate shape | met | 126 certificates checked, each naming its rows and its false comparison |
| 7 | the tree stays green | not met | not computed here: the suite, mypy --strict src, ruff and an empty diff on declared_law.py are reported by the session that runs them |

**Overall: not met.** A bar that is not met is a refusal of the
derivation as ADR 0370 words it. `controller_valve` is not edited, and its literals do not move.

## The literals the derivation read

| Literal | Value | As the source writes it | Read from |
| --- | --- | --- | --- |
| `close` | 0.0 | `0` | `src/PLC1.py`:18 |
| `open` | 1.0 | `1` | `src/PLC1.py`:20 |
| `release_mode` | 3.0 | `3.0` | `src/Configs.py`:49 |
| `belt_past_filler` | 1.0 | `1.0` | `src/PLC1.py`:26 |
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

## The rules the derivation read

**input valve** — writes `tank_input_valve_status`, guarded on `tank_input_valve_mode`.
1. `tank_level_value` > `tank_level_max` → writes 0.0 (line 17)
2. `tank_level_value` < `tank_level_min` → writes 1.0 (line 19)
Otherwise: nothing is required, which is silence.

**output valve** — writes `tank_output_valve_status`, guarded on `tank_output_valve_mode`.
1. `bottle_level_value` > `bottle_level_max` or `bottle_distance_to_filler_value` > `1.0` → writes 0.0 (line 26)
Otherwise: writes 1.0.

## The guard the derivation read

`src/ics_sim/Device.py`:404 names mode
1.0, 2.0 as manual. The comparison therefore
runs at every other mode. That is what the source states; it is not the same sentence as "the
mode is the release literal", and ADR 0370 names the difference in advance.
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

## Enumerated cases that parted

The enumeration is exhaustive over the cases ADR 0370 declares, so nothing is sampled and the
declared seed 20261029 is recorded rather than used.

- none
