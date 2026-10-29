# 66 — Four checks on the frozen candidate

The four checks that were written down first have now been run, once.

Eight random alerts a shift, drawn 500 times, catch on average 3.808 of the 58
attacks on the 2022 edition and 3.06 of the 52 on the 2023 edition. The busiest
draw catches 9 and 8. The frozen detector's 53 and 36 are above every draw.

On the 2022 edition, 11 of the 53 catches are the position command for the
PCV01 valve, `P1_PCV01D`. That is the only feature behind more than a fifth of
the catches. The plant-wide prediction, not the range, was the larger score on
all 11. No feature crosses that fifth on the 2023 edition.

The two controls, scored byte for byte, each catch 21 of 58 and 15 of 52. That
is above the grouped range check and below the frozen detector. Turning the
plant-wide prediction off and turning the range rule on land on the same counts.

The two published rows were not the same alert list. On the 2022 edition the
detector's own grouping keeps 101 alerts and the shared wrapper keeps 83. On
the 2023 edition both keep 73, on the same timestamps, with different features.
No corrected run was started. Nothing was adjusted after these counts.
