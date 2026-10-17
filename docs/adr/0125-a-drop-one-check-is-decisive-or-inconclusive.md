# ADR 0125 — A drop-one check is decisive or inconclusive

- **Status:** Accepted, amended by [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md). On its own, acceptance 1 and 2 were **not met** (see Findings)
- **Date:** 2026-10-15
- **PART:** ADR 0123, before step 3
- **Amends:** [ADR 0123](0123-the-plant-map-proposed.md) §5.2, the first of its three checks only
- **Depends on:** [ADR 0124](0124-the-plant-map-is-built-and-fits-in-seconds.md)

## Context

ADR 0124 recorded that §5.2's naming rule fails the controlled case. On the test tank a level
integrates inflow minus outflow, a PI loop acts on the reported level, and a liar holds that
report under the setpoint. The level's map score rises to about 50 and its reconstruction is
within a tenth of the reported error. But the first check, "out of band in its model and in every
one of its drop-one models", almost never holds: an integrating relation needs both flows, so
the model without either is poor and its band wide, and under the liar both fall back inside
those wide bands. The level was named at 1 of 20 rows tried, and a strict expected failure pins
it.

The defect was found on the fixture, before any slice was scored, so it is fixed now. Fixing it
after §9.7 had been measured would be post hoc.

The drop-one check is kept, not dropped. It is what stops a lying driver being blamed on its
child: when an inflow meter lies, the level it feeds disagrees with its drivers too, and only the
model without the inflow shows that the inflow is the one disagreeing. "Drivers in band" cannot
stand in for it, because a driver with no model (a setpoint, an unmapped signal) cannot be in
band or out of it. Elijah set the rule below on 15 October.

## Decision

**1. A drop-one model is decisive or inconclusive at a row.** For candidate *c* with driver *k*,
let *r* be the full model's residual (reading minus prediction) and *b* the drop-one model
*c*∖*k*'s band, both at the full model's **deciding band**: the one with the largest
|*r*| / band in the full model. A level form has one band. An increment form has one per horizon,
and the deciding one is the horizon that puts the full model furthest out of band. *c*∖*k* is
**decisive** when *b* < |*r*|: its band is narrow enough to have seen the discrepancy the full
model saw. Otherwise it is **inconclusive**.

**2. Only a decisive drop-one in band blocks naming.** A decisive *c*∖*k* that is in band (score
at most 1) means every other driver explains *c*, and only *k* disagrees: *c* is not named. An
inconclusive one neither blocks nor supports.

**3. The first check becomes:** *c* is out of band in its own model, and **no drop-one model of
*c* is decisively in band**. The other two checks (its drivers in band; at least half its
downstream children agree with the reconstruction and not the reading) are unchanged.

**4. The fact lists the inconclusive checks by driver**, so a reader sees which links could not
testify.

Nothing else in §5 changes: a broken link is still a full model out of band with its drop-one
model in band, and the candidates, the downstream rule, "not separable" and "reading true, plant
changed" are as ADR 0123 states them.

## Acceptance, tests first

1. The lying tank level is named, and the strict expected-failure marker is removed.
2. New: when the tank's inflow meter lies, the level is not named; the inflow is, or the verdict
   is not separable.
3. Every other plant-map test passes unchanged.

## Findings on the fixture (15 October 2026, before any slice)

The rule is implemented in `phos.atlas.plant_map_naming` (`_drop_one_testimony`). On the test
tank, with the map fitted as ADR 0123 states it:

| Configuration (exploratory, fixture only) | Lying level named | Inflow meter lies: level wrongly blamed | Inflow named |
| --- | ---: | ---: | ---: |
| This record's rule | 3 of 19 rows | 5 of 20 | 0 of 20 |
| + only a *unique* decisive drop-one in band blocks | 14 of 19 | 9 of 20 | 0 of 20 |
| This rule, map fitted without §3's cycle exclusion | 2 of 19 | 0 of 20 | 1 of 20 |
| Both changes | 7 of 19 | 0 of 20 | 1 of 20 |

Why the rule alone cannot pass:

- **Mid-liar, both drop-one models are decisively in band.** The held reading barely changes,
  and a model missing a needed flow predicts almost no change either, so it agrees with the lie.
  Its band is narrower than the full model's residual, so by §1 it counts as decisive.
- **The map learned the wrong tank.** §3's cycle exclusion stripped the real links. The fixture's
  inflow follows the valve one sample later, but the valve's model also used the inflow, so each
  was barred from the other's level form, and the inflow ended up modelled from the outflow. Its
  frozen reading is then nearly invisible. The quality signal, which follows the true level, was
  modelled from the flows, so the level has no downstream witness. With the exclusion removed
  (exploratory only), the map finds `valve -> inflow` (share 0.99) and `level -> quality`
  (0.99), and the level is never wrongly blamed.

So naming rests on the map's structure first and on the drop-one rule second. Acceptance is not
met, and no rule is changed further here: the cycle exclusion is ADR 0123 §3, and changing it
needs its own decision. Elijah took it on 15 October: [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md)
narrows the exclusion to declared loops and amends §2 of this record.

## Consequences

- No slice has been scored, so no §9 number moves. Step 3 starts from this rule.
- An inconclusive drop-one is a weaker check than ADR 0123 asked for. Where every drop-one of a
  candidate is inconclusive, the first check rests on the full model alone, and the downstream
  check carries more of the weight. §9.7 (a wrong name in over 10% of caught runs) is the measure
  of whether that is too weak.

## What would reverse this

Removing the drop-one check; letting an inconclusive check block or support naming; changing the
deciding band after a development score has been seen; or changing any other §5 rule under this
record.
