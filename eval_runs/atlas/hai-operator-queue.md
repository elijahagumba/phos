# Atlas operator queue on hai — recall at an alert budget

**Not a new detector and not a control-room budget.** This re-counts the alert set the
Atlas vertical already logged, ranked instead of in time order. The frozen public rows
are untouched: 646.58 FP/normal-hour ungated and 53.26 grouped. No threshold was
searched and no model was refitted.

- Queue: **424** subsystem events over **2** labelled attack window(s)
- Seed: `11`
- Commit: `15565e20152413c4b8571e037c375e860504aba1`
- Detector names: `atlas-queue:<key>` — never a vertical name

## Ranked by `magnitude`

`atlas-queue:magnitude` — 424 distinct score(s). This key **ranked the wrong way** — the median true alert sits in the back half of the queue, so this key buries incidents under the noise rather than surfacing them.

| Budget | Queued | TP | Random would find | Beats random | Precision@budget | Window recall | Cut score | Tie span | Cut decided by |
| ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |
| 6 | 6 | 0 | 0.08 | **no** | 0.0000 | 0.00 | 10.0993 | 1 | ranking |
| 12 | 12 | 0 | 0.17 | **no** | 0.0000 | 0.00 | 10.0976 | 1 | ranking |
| 24 | 24 | 0 | 0.34 | **no** | 0.0000 | 0.00 | 10.0943 | 1 | ranking |
| 48 | 48 | 0 | 0.68 | **no** | 0.0000 | 0.00 | 10.0904 | 1 | ranking |
| 96 | 96 | 0 | 1.36 | **no** | 0.0000 | 0.00 | 10.0783 | 1 | ranking |
| 192 | 192 | 1 | 2.72 | **no** | 0.0052 | 0.50 | 7.6571 | 1 | ranking |
| 424 | 424 | 6 | 6.00 | **no** | 0.0142 | 1.00 | 3.0008 | 1 | ranking |

The 6 true alert(s) sit at rank 187 (44%), 204 (48%), 255 (60%), 320 (75%), 348 (82%), 359 (85%) of 424. An operator reads from rank 0.

## Ranked by `weight`

`atlas-queue:weight` — 1 distinct score(s). This key **did not rank** — every alert shares one score, so the order is the tiebreak's.

| Budget | Queued | TP | Random would find | Beats random | Precision@budget | Window recall | Cut score | Tie span | Cut decided by |
| ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |
| 6 | 6 | 0 | 0.08 | **no** | 0.0000 | 0.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 12 | 12 | 0 | 0.17 | **no** | 0.0000 | 0.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 24 | 24 | 0 | 0.34 | **no** | 0.0000 | 0.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 48 | 48 | 6 | 0.68 | yes | 0.1250 | 1.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 96 | 96 | 6 | 1.36 | yes | 0.0625 | 1.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 192 | 192 | 6 | 2.72 | yes | 0.0312 | 1.00 | 0.0338 | 424 | **tiebreak (struck)** |
| 424 | 424 | 6 | 6.00 | **no** | 0.0142 | 1.00 | 0.0338 | 424 | ranking |

The 6 true alert(s) sit at rank 26 (6%), 27 (6%), 28 (7%), 29 (7%), 42 (10%), 43 (10%) of 424. An operator reads from rank 0.

## Ranked by `breadth`

`atlas-queue:breadth` — 4 distinct score(s). This key **ranked the wrong way** — the median true alert sits in the back half of the queue, so this key buries incidents under the noise rather than surfacing them.

| Budget | Queued | TP | Random would find | Beats random | Precision@budget | Window recall | Cut score | Tie span | Cut decided by |
| ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |
| 6 | 6 | 0 | 0.08 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 12 | 12 | 0 | 0.17 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 24 | 24 | 0 | 0.34 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 48 | 48 | 0 | 0.68 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 96 | 96 | 0 | 1.36 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 192 | 192 | 0 | 2.72 | **no** | 0.0000 | 0.00 | 3.0000 | 277 | **tiebreak (struck)** |
| 424 | 424 | 6 | 6.00 | **no** | 0.0142 | 1.00 | 1.0000 | 95 | ranking |

The 6 true alert(s) sit at rank 285 (67%), 286 (67%), 340 (80%), 341 (80%), 350 (83%), 351 (83%) of 424. An operator reads from rank 0.

## Read every number above with these

- Recall at an alert budget is not a control-room budget and not a deployment claim.
- This re-counts the alert set the vertical already logged. It does not replace 646.58 ungated or 53.26 grouped FP/normal-hour, and no threshold was searched.
- HAI's declared topology could not be partitioned below process level, so the subsystem events being ranked are coarse; a finer map would change the queue without changing the detector.
- Calibrated weights top out at 0.034 across four isotonic knots, because only 140 of 4,249 calibration candidates fall in attack windows. A weight-ranked queue is expected to tie.
- The budget cut fell inside a block of alerts sharing one score, so which alerts made the queue was decided by the deterministic tiebreak and not by the ranking signal. Precision here is a property of the sort order, not of Atlas.
