"""The plant map: which signals drive which, with a delay and a normal band per link (ADR 0123).

For each signal with a declared role, learned from attack-free training only: a few **drivers**,
the **lag** or two at which each predicts it, a **form** (its level, or its one-sample increment,
which is how a level that integrates its flows is written), a **band** of normal error, and for
each link the band of the model without that driver. Every term has a lag of at least one
sample, so a link has a direction; the frozen detector keeps lag 0.

**Selection.** Forward stepwise over ``(driver, lag)`` terms on five contiguous blocks of
training, each term chosen for the largest drop in out-of-block squared error, stopping under a
1% gain or at six drivers and two lags per driver (`phos.atlas.plant_map_select`). Coefficients
use the frozen ridge penalty.

**Two passes, so a controller cannot cover for a lie (§3).** Pass one selects both forms from every
admissible term. A signal reachable from a target in that graph (its controller, and what the
controller moves) carries the target's past, so pass two re-selects the level form without those
descendants; they stay admissible in the increment form, where they enter as causes of change. Where
the role file declares control loops (ADR 0126), only a loop's outputs and what they reach are
barred, and only from the level form of the reading the loop holds. A setpoint never drives a
sensor. A signal with no declared role neither has a model nor drives one
(`phos.atlas.signal_roles`). The form a target keeps is the one whose reconstruction from its
drivers stays closer to it, out of block, at a 900-second horizon.

**Bands** are quantiles of out-of-block error: one for a level form, one per horizon for an
increment form (the change over 60, 300, 900 and 3600 s against its drivers' implied change), and
the same again for each drop-one model. An increment form also carries a **free-run band**: the
error of a reconstruction integrated from an anchor, by elapsed time, up to six hours.

`map_scores` is each signal's largest error over its band; detrending, calibration, events and
the budget are the frozen detector's and are applied by its caller. Naming and reconstruction
are `phos.atlas.plant_map_naming`. Nothing here changes `phos.atlas.consistency`.
"""

from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import (
    DEFAULT_SETTINGS,
    RESULT_NAME,
    Equation,
    Form,
    Link,
    MapSettings,
    PlantMap,
    TargetModel,
    equation_scores,
    map_scores,
    prediction,
    samples_for,
)

__all__ = [
    "DEFAULT_SETTINGS",
    "RESULT_NAME",
    "Equation",
    "Form",
    "Link",
    "MapSettings",
    "PlantMap",
    "TargetModel",
    "equation_scores",
    "fit_map",
    "map_scores",
    "prediction",
    "samples_for",
]
