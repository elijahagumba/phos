# G1 baseline table

Headline: recall within budget, 8 alerts per 8-hour shift.
Beside it: eTaPR at the reference defaults (theta_p=0.5, theta_r=0.1, delta=0.0), and eTaPR at HAICon pi=0.7, rho=0.1, 180 samples. Alpha=0.5 is not an argument.
Point-adjusted F1 is reported and is not the headline.
One Atlas configuration: ungated Mahalanobis, alert threshold 3.0. Result names start with `g1-baseline:`.
Nothing here is appended to `eval_runs/log.jsonl`.

## Recall within budget

| Corpus | Judges | Detector | Checked | Caught | Attacks | Recall within budget |
|---|---|---|---|---:|---:|---:|
| hai-20.07 | yes | g1-baseline:atlas-mahalanobis | engine | 9 | 38 | 0.236842 |
| hai-20.07 | yes | g1-baseline:simple-minmax | yes | 15 | 38 | 0.394737 |
| hai-20.07 | yes | g1-baseline:simple-steadytime | yes | 6 | 38 | 0.157895 |
| hai-20.07 | yes | g1-baseline:simple-histogram | yes | 6 | 38 | 0.157895 |
| hai-21.03 | yes | g1-baseline:atlas-mahalanobis | engine | 7 | 50 | 0.140000 |
| hai-21.03 | yes | g1-baseline:simple-minmax | yes | 14 | 50 | 0.280000 |
| hai-21.03 | yes | g1-baseline:simple-steadytime | yes | 12 | 50 | 0.240000 |
| hai-21.03 | yes | g1-baseline:simple-histogram | yes | 12 | 50 | 0.240000 |
| hai-22.04 | yes | g1-baseline:atlas-mahalanobis | engine | 5 | 58 | 0.086207 |
| hai-22.04 | yes | g1-baseline:simple-minmax | yes | 6 | 58 | 0.103448 |
| hai-22.04 | yes | g1-baseline:simple-steadytime | yes | 3 | 58 | 0.051724 |
| hai-22.04 | yes | g1-baseline:simple-histogram | yes | 3 | 58 | 0.051724 |
| hai-23.05 | yes | g1-baseline:atlas-mahalanobis | engine | 3 | 52 | 0.057692 |
| hai-23.05 | yes | g1-baseline:simple-minmax | yes | 4 | 52 | 0.076923 |
| hai-23.05 | yes | g1-baseline:simple-steadytime | yes | 2 | 52 | 0.038462 |
| hai-23.05 | yes | g1-baseline:simple-histogram | yes | 2 | 52 | 0.038462 |
| batadal | yes | g1-baseline:atlas-mahalanobis | engine | 5 | 5 | 1.000000 |
| batadal | yes | g1-baseline:simple-minmax | yes | 3 | 5 | 0.600000 |
| batadal | yes | g1-baseline:simple-steadytime | yes | 2 | 5 | 0.400000 |
| batadal | yes | g1-baseline:simple-histogram | yes | 2 | 5 | 0.400000 |
| batch-distillation | no | g1-baseline:atlas-mahalanobis | engine | 21 | 126 | 0.166667 |
| batch-distillation | no | g1-baseline:simple-minmax | yes | 16 | 126 | 0.126984 |
| batch-distillation | no | g1-baseline:simple-steadytime | yes | 3 | 126 | 0.023810 |
| batch-distillation | no | g1-baseline:simple-histogram | yes | 9 | 126 | 0.071429 |
| data4cyber | no | g1-baseline:atlas-mahalanobis | engine | 0 | 2 | 0.000000 |
| data4cyber | no | g1-baseline:simple-minmax | yes | 1 | 2 | 0.500000 |
| data4cyber | no | g1-baseline:simple-steadytime | yes | 0 | 2 | 0.000000 |
| data4cyber | no | g1-baseline:simple-histogram | yes | 0 | 2 | 0.000000 |

## Beside the headline

| Corpus | Detector | Recall within budget | eTaPR reference (theta_p=0.5, theta_r=0.1, delta=0) | eTaPR HAICon (pi=0.7, rho=0.1, 180 samples; alpha is not an argument) | Point-adjusted F1 (reported, not the headline) | Alerts before the cut |
|---|---|---:|---:|---:|---:|---:|
| hai-20.07 | g1-baseline:atlas-mahalanobis | 0.236842 | 0.281654 | 0.282505 | 0.758717 | 7653 |
| hai-20.07 | g1-baseline:simple-minmax | 0.394737 | 0.347471 | 0.354326 | 0.163805 | 187681 |
| hai-20.07 | g1-baseline:simple-steadytime | 0.157895 | 0.093015 | 0.093015 | 0.115027 | 36656 |
| hai-20.07 | g1-baseline:simple-histogram | 0.157895 | 0.093015 | 0.093015 | 0.115027 | 36656 |
| hai-21.03 | g1-baseline:atlas-mahalanobis | 0.140000 | 0.142731 | 0.193877 | 0.412680 | 12947 |
| hai-21.03 | g1-baseline:simple-minmax | 0.280000 | 0.622708 | 0.702513 | 0.794572 | 14287 |
| hai-21.03 | g1-baseline:simple-steadytime | 0.240000 | 0.204886 | 0.266554 | 0.304590 | 30441 |
| hai-21.03 | g1-baseline:simple-histogram | 0.240000 | 0.251549 | 0.328474 | 0.432224 | 1709 |
| hai-22.04 | g1-baseline:atlas-mahalanobis | 0.086207 | 0.097671 | 0.096321 | 0.334485 | 37574 |
| hai-22.04 | g1-baseline:simple-minmax | 0.103448 | 0.212024 | 0.212024 | 0.192879 | 2260 |
| hai-22.04 | g1-baseline:simple-steadytime | 0.051724 | 0.085608 | 0.085608 | 0.061168 | 251 |
| hai-22.04 | g1-baseline:simple-histogram | 0.051724 | 0.085608 | 0.085608 | 0.061168 | 251 |
| hai-23.05 | g1-baseline:atlas-mahalanobis | 0.057692 | 0.091212 | 0.099301 | 0.544110 | 6886 |
| hai-23.05 | g1-baseline:simple-minmax | 0.076923 | 0.132292 | 0.146616 | 0.338163 | 5507 |
| hai-23.05 | g1-baseline:simple-steadytime | 0.038462 | 0.026337 | 0.026337 | 0.293670 | 209 |
| hai-23.05 | g1-baseline:simple-histogram | 0.038462 | 0.026337 | 0.026337 | 0.293670 | 209 |
| batadal | g1-baseline:atlas-mahalanobis | 1.000000 | 0.490656 | 0.652324 | 0.832700 | 543 |
| batadal | g1-baseline:simple-minmax | 0.600000 | 0.219883 | 0.401105 | 0.757493 | 52 |
| batadal | g1-baseline:simple-steadytime | 0.400000 | 0.451672 | 0.690050 | 0.592784 | 206 |
| batadal | g1-baseline:simple-histogram | 0.400000 | 0.000000 | 0.487446 | 0.345865 | 650 |
| batch-distillation | g1-baseline:atlas-mahalanobis | 0.166667 | 0.269586 | 0.469920 | 0.851394 | 5265 |
| batch-distillation | g1-baseline:simple-minmax | 0.126984 | 0.242005 | 0.255238 | 0.684788 | 1884 |
| batch-distillation | g1-baseline:simple-steadytime | 0.023810 | 0.049400 | 0.050061 | 0.411625 | 41072 |
| batch-distillation | g1-baseline:simple-histogram | 0.071429 | 0.174735 | 0.177636 | 0.448470 | 3901 |
| data4cyber | g1-baseline:atlas-mahalanobis | 0.000000 | 0.859680 | 0.000000 | 0.673552 | 5411 |
| data4cyber | g1-baseline:simple-minmax | 0.500000 | 0.859680 | 0.000000 | 0.673552 | 16137 |
| data4cyber | g1-baseline:simple-steadytime | 0.000000 | 0.859680 | 0.000000 | 0.673552 | 13063 |
| data4cyber | g1-baseline:simple-histogram | 0.000000 | 0.859680 | 0.000000 | 0.673552 | 12613 |

## Atlas against the best checked opponent

hai-20.07: Atlas 9/38 is below g1-baseline:simple-minmax 15/38.
hai-21.03: Atlas 7/50 is below g1-baseline:simple-minmax 14/50.
hai-22.04: Atlas 5/58 is below g1-baseline:simple-minmax 6/58.
hai-23.05: Atlas 3/52 is below g1-baseline:simple-minmax 4/52.
batadal: Atlas 5/5 is above g1-baseline:simple-minmax 3/5.
batch-distillation: reported only. It does not judge.
data4cyber: reported only. It does not judge.

## Notes

- **hai-20.07** (scored): measured median step 1 s; declared 1 s. Fit on 550024 benign rows, 51 Atlas signals, 776 attack rows excluded from the fit. Delta is 180 samples on each file's scored index (180 seconds at the declared period), not rescaled. Point metrics drop unscored rows and collapse a timestamp to one point. The budget counts each feature alert. Measured step matches the declared period.
- **hai-21.03** (scored): measured median step 1 s; declared 1 s. Fit on 921603 benign rows, 57 Atlas signals, 0 attack rows excluded from the fit. Delta is 180 samples on each file's scored index (180 seconds at the declared period), not rescaled. Point metrics drop unscored rows and collapse a timestamp to one point. The budget counts each feature alert. Measured step matches the declared period.
- **hai-22.04** (scored): measured median step 1 s; declared 1 s. Clean run, scored once. Fit on 1004402 benign rows, 68 Atlas signals, 0 attack rows excluded. Declared denominator 58. Not labelled seen.
- **hai-23.05** (scored): measured median step 1 s; declared 1 s. Clean run, scored once. Fit on 896400 benign rows, 66 Atlas signals, 0 attack rows excluded. Declared denominator 52. Not labelled seen. Labels are joined by row, not by timestamp text. summary_label2.txt says Attacks: 40 times; the label column has 38 runs, so the denominator is 52.
- **batadal** (scored): measured median step 3600 s; declared 3600 s. Fit on 8761 benign rows, 36 Atlas signals, 0 attack rows excluded from the fit. Delta is 180 samples on each file's scored index (648000 seconds at the declared period), not rescaled. Point metrics drop unscored rows and collapse a timestamp to one point. The budget counts each feature alert. Measured step matches the declared period.
- **batch-distillation** (reported): measured median step 10 s; declared 10 s. Fit on 10904 benign rows, 27 Atlas signals, 0 attack rows excluded from the fit. Delta is 180 samples on each file's scored index (1800 seconds at the declared period), not rescaled. Point metrics drop unscored rows and collapse a timestamp to one point. The budget counts each feature alert. Measured step matches the declared period. Perturbation recall, not attack recall. Reported only.
- **data4cyber** (reported): measured median step 1 s; declared 1 s. Fit on 1798 benign rows, 145 Atlas signals, 0 attack rows excluded from the fit. Delta is 180 samples on each file's scored index (180 seconds at the declared period), not rescaled. Point metrics drop unscored rows and collapse a timestamp to one point. The budget counts each feature alert. Measured step matches the declared period. Process-phase recall, not attack recall. Reported only. Not a control-room budget.

## Grouped rows

Same Atlas configuration and the same three opponents, each through
`group_published_alerts` (ADR 0099). These rows do not replace the rows above.
HAI 22.04 and 23.05 are the clean run, scored once, and are not labelled seen.
Beyond grouping is grouped Atlas caught minus the best grouped checked opponent caught.

| Corpus | Exposure | Detector | Caught | Attacks | Recall within budget |
|---|---|---|---:|---:|---:|
| hai-20.07 | seen | g1-grouped:atlas-mahalanobis | 23 | 38 | 0.605263 |
| hai-20.07 | seen | g1-grouped:simple-minmax | 32 | 38 | 0.842105 |
| hai-20.07 | seen | g1-grouped:simple-steadytime | 7 | 38 | 0.184211 |
| hai-20.07 | seen | g1-grouped:simple-histogram | 7 | 38 | 0.184211 |

hai-20.07: beyond grouping -9. Attacks only grouped Atlas catches: test1.csv.gz#11, test1.csv.gz#27, test1.csv.gz#5.

| hai-21.03 | seen | g1-grouped:atlas-mahalanobis | 15 | 50 | 0.300000 |
| hai-21.03 | seen | g1-grouped:simple-minmax | 36 | 50 | 0.720000 |
| hai-21.03 | seen | g1-grouped:simple-steadytime | 14 | 50 | 0.280000 |
| hai-21.03 | seen | g1-grouped:simple-histogram | 14 | 50 | 0.280000 |

hai-21.03: beyond grouping -21. Attacks only grouped Atlas catches: test3.csv.gz#7.

| batadal |  | g1-grouped:atlas-mahalanobis | 5 | 5 | 1.000000 |
| batadal |  | g1-grouped:simple-minmax | 3 | 5 | 0.600000 |
| batadal |  | g1-grouped:simple-steadytime | 2 | 5 | 0.400000 |
| batadal |  | g1-grouped:simple-histogram | 2 | 5 | 0.400000 |

batadal: beyond grouping 2. Attacks only grouped Atlas catches: batadal-test-prepared.csv#3.

| batch-distillation |  | g1-grouped:atlas-mahalanobis | 26 | 126 | 0.206349 |
| batch-distillation |  | g1-grouped:simple-minmax | 33 | 126 | 0.261905 |
| batch-distillation |  | g1-grouped:simple-steadytime | 22 | 126 | 0.174603 |
| batch-distillation |  | g1-grouped:simple-histogram | 17 | 126 | 0.134921 |

batch-distillation: beyond grouping -7. Attacks only grouped Atlas catches: batch-distillation-test-prepared.csv#0, batch-distillation-test-prepared.csv#109, batch-distillation-test-prepared.csv#115, batch-distillation-test-prepared.csv#120, batch-distillation-test-prepared.csv#15, batch-distillation-test-prepared.csv#47, batch-distillation-test-prepared.csv#67.

| data4cyber |  | g1-grouped:atlas-mahalanobis | 1 | 2 | 0.500000 |
| data4cyber |  | g1-grouped:simple-minmax | 1 | 2 | 0.500000 |
| data4cyber |  | g1-grouped:simple-steadytime | 0 | 2 | 0.000000 |
| data4cyber |  | g1-grouped:simple-histogram | 0 | 2 | 0.000000 |

data4cyber: beyond grouping 0. Attacks only grouped Atlas catches: none.

| hai-22.04 |  | g1-grouped:atlas-mahalanobis | 5 | 58 | 0.086207 |
| hai-22.04 |  | g1-grouped:simple-minmax | 10 | 58 | 0.172414 |
| hai-22.04 |  | g1-grouped:simple-steadytime | 4 | 58 | 0.068966 |
| hai-22.04 |  | g1-grouped:simple-histogram | 4 | 58 | 0.068966 |

hai-22.04: beyond grouping -5. Attacks only grouped Atlas catches: test2.csv#0, test3.csv#9.

| hai-23.05 |  | g1-grouped:atlas-mahalanobis | 5 | 52 | 0.096154 |
| hai-23.05 |  | g1-grouped:simple-minmax | 6 | 52 | 0.115385 |
| hai-23.05 |  | g1-grouped:simple-steadytime | 2 | 52 | 0.038462 |
| hai-23.05 |  | g1-grouped:simple-histogram | 2 | 52 | 0.038462 |

hai-23.05: beyond grouping -1. Attacks only grouped Atlas catches: hai-test2.csv#0, hai-test2.csv#3, hai-test2.csv#37.

## Grouped notes

- **hai-20.07**: Same fit as the published row: 550024 benign rows, 51 Atlas signals, 776 attack rows excluded. Measured median step 1 s; declared 1 s. Each detector's published alerts pass through group_published_alerts. Beyond grouping uses the headline catch counts. Seen: the grouping constants were chosen on HAI 20.07 and held out on HAI 21.03.
- **hai-21.03**: Same fit as the published row: 921603 benign rows, 57 Atlas signals, 0 attack rows excluded. Measured median step 1 s; declared 1 s. Each detector's published alerts pass through group_published_alerts. Beyond grouping uses the headline catch counts. Seen: the grouping constants were chosen on HAI 20.07 and held out on HAI 21.03.
- **batadal**: Same fit as the published row: 8761 benign rows, 36 Atlas signals, 0 attack rows excluded. Measured median step 3600 s; declared 3600 s. Each detector's published alerts pass through group_published_alerts. Beyond grouping uses the headline catch counts.
- **batch-distillation**: Same fit as the published row: 10904 benign rows, 27 Atlas signals, 0 attack rows excluded. Measured median step 10 s; declared 10 s. Each detector's published alerts pass through group_published_alerts. Beyond grouping uses the headline catch counts. Perturbation recall, not attack recall. Reported only.
- **data4cyber**: Same fit as the published row: 1798 benign rows, 145 Atlas signals, 0 attack rows excluded. Measured median step 1 s; declared 1 s. Each detector's published alerts pass through group_published_alerts. Beyond grouping uses the headline catch counts. Process-phase recall, not attack recall. Reported only.
