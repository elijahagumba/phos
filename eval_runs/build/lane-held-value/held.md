# A single held value, and which laws fire on it

Written by `scripts/lane_held_value_laws.py` on 2026-11-25. Synthetic construction only: no corpus, no file, and no plant is read. The tag, the value and the row count below are constants in that script, not readings from a plant.

One tag, `tank_level_max`, held at `6.9` for 720 one-second rows. The value is inside the ordinary band, so nothing in it is a departure. The class it belongs to is not any of the six classes the laws name.

The digest of the module under test is `508f65bb50267227349143a4e2e1136ff69566ed69e7e4a963821b8a09b512ca`.

## Which laws fire

| law | row reading | change reading | differs |
|---|---|---|---|
| `joint_move` | silent | silent |  |
| `subfloor_walk` | **fires** | silent | yes |
| `band_handoff` | silent | silent |  |
| `program_transfer` | silent | silent |  |
| `allowed_writer` | silent | silent |  |
| `controller_valve` | silent | silent |  |

## The metrics

| metric | value |
|---|---|
| `laws_fired_row` | 1 |
| `laws_fired_change` | 0 |
| `laws_reading_sensitive` | 1 |
| `subfloor_walk_fired_row` | 1 |
| `subfloor_walk_fired_change` | 0 |

## What a reader should take from this

A law that fires here is firing on a value whose class it does not name. A law that fires under one reading and not the other is reading runs rather than individual values, and the historian reading decides what a run is. Neither is edited by this harness.
