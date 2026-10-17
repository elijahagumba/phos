# ADR 0141 — Role files for HAI 21.03, 22.04 and 23.05, and none for BATADAL

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0117's gate for `atlas-plant-map-v1`, its inputs
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md),
  [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md),
  [ADR 0140](0140-the-plant-map-survives-the-fourth-set.md)

## Context

ADR 0140 made `atlas-plant-map-v1` (attempt 6) a candidate for ADR 0117's gate. The map models
only signals with declared roles, and the validation corpora had no role files, so on them the
challenger would be the champion exactly and could not catch more. ADR 0123 §3 says how roles are
read: from the corpus authors' documentation, each with a citation and a verbatim quote, and a
stated reason wherever the documentation supports none. Nothing is inferred from data or from the
shape of a name.

## Decision

**1. The three HAI files are generated, not hand-written.** `scripts/build_hai_roles.py` writes
`data/hai-{21.03,22.04,23.05}/roles.toml` from two sources only:

- HAI 20.07's role file, which was read row by row from the manual at the registry's pin
  (sha256 `0668345c…`). A point it declares, under the same column or under the manual name it
  records, keeps that declaration: role, citation and quote.
- `NEW_POINTS`: the 31 points the manual's data-points table (pp. 12–15) adds after 20.07, each
  with the role its own description states, its page and row, and its words quoted verbatim. All
  31 quotes were checked against the pinned manual's text.

Any other column gets no role, with the reason. A test checks that each committed file is exactly
what the builder writes, so no file is edited by hand.

| Edition | Columns | Sensors | Actuators | Setpoints | No role | Loops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HAI 21.03 | 79 | 27 | 22 | 12 | 18 | 6 |
| HAI 22.04 | 86 | 29 | 26 | 16 | 15 | 6 |
| HAI 23.05 | 86 | 29 | 25 | 9 | 23 | 6 |

**2. Decisions that cost the map signals, stated.**

- **No matching by the shape of a name.** HAI 23.05's `x1001_15_ASSIGN_OUT`-style columns look
  like the HAIEnd table's `1001.15-OUT` points, and 21.03's `P2_ASD` looks like `P2_AutoSD`. The
  table does not name them for those editions, so they get no role.
- **Operator buttons and switches get no role**, as in 20.07 (`P2_AutoGO`, `P2_ManualGO`, the
  mode switches and lamps). They are commands from a person, not sensor, actuator or setpoint.
- **Loops are 20.07's six**, with each point renamed where an edition uses the manual's name and
  dropped where the edition lacks it or gives it no role. So 21.03's `P2-SC` has no setpoint
  (it has no `P2_AutoSD`), and 23.05's four P1 loops have none: 23.05 has no `P1_B…` columns and
  carries P1's setpoints only as its seven `x…` columns (`x1001_05_SETPOINT_OUT` and the like),
  which the table does not name.

**3. BATADAL gets no role file.** The lab holds no citable copy of its documentation, and its site
is not reachable from the build container. Without a file, the gate declares every BATADAL signal
without a role, the map learns nothing, and the challenger is the champion there by construction
(ADR 0127). BATADAL can then tie and never gain. Writing roles for it from memory of the paper, or
from column names, would break ADR 0123 §3.

**4. Columns the gate's readers drop.** The readers that scored the champion leave out time,
label and unscored columns. The gate keeps only the roles of the columns its reader returns, and
drops any loop naming a dropped column. It stops, before any score, if a returned column is not in
the role file.

## Consequences

- The gate (ADR 0142) can now ask its question on the three HAI editions, where the champion
  already catches 42/50, 53/58 and 36/52. There is little room above it, so a pass is not likely
  by construction.
- These files were written before any challenger score on these editions and are pinned by sha256
  in ADR 0142. Changing one after the gate is a new declaration and a new look.

## What would reverse this

A role read from data, from a score, or from the shape of a column's name; a role file changed
after the gate's declaration; or a BATADAL role file written without its documentation.
