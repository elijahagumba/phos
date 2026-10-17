# Sandbox candidate on the clean HAI editions

Recall within budget is the headline. Point-adjusted F1 is reported and is not.
Grouped Atlas and grouped MinMax are the published ADR 0102 counts.
Beyond grouped MinMax is the candidate's catches minus grouped MinMax's catches.

| Corpus | Detector | Caught | Attacks | Recall within budget | Point-adjusted F1 (reported, not the headline) | Beyond grouped MinMax |
|---|---|---:|---:|---:|---:|---:|
| hai-22.04 | g1-grouped:atlas-mahalanobis | 5 | 58 | 0.086207 | published |  |
| hai-22.04 | g1-grouped:simple-minmax | 10 | 58 | 0.172414 | published |  |
| hai-22.04 | sandbox-candidate:own-grouping | 53 | 58 | 0.913793 | 0.959394 | 43 |
| hai-22.04 | sandbox-candidate:shared-wrapper | 53 | 58 | 0.913793 | 0.959394 | 43 |
| hai-23.05 | g1-grouped:atlas-mahalanobis | 5 | 52 | 0.096154 | published |  |
| hai-23.05 | g1-grouped:simple-minmax | 6 | 52 | 0.115385 | published |  |
| hai-23.05 | sandbox-candidate:own-grouping | 36 | 52 | 0.692308 | 0.849475 | 30 |
| hai-23.05 | sandbox-candidate:shared-wrapper | 36 | 52 | 0.692308 | 0.849475 | 30 |

## Attacks only the candidate catches

hai-22.04 sandbox-candidate:own-grouping: test1.csv#0, test1.csv#1, test1.csv#2, test1.csv#3, test1.csv#4, test1.csv#5, test1.csv#6, test2.csv#0, test2.csv#10, test2.csv#13, test2.csv#14, test2.csv#15, test2.csv#16, test2.csv#2, test2.csv#3, test2.csv#4, test2.csv#5, test2.csv#6, test2.csv#7, test2.csv#8, test2.csv#9, test3.csv#0, test3.csv#2, test3.csv#3, test3.csv#4, test3.csv#7, test3.csv#8, test3.csv#9, test4.csv#1, test4.csv#11, test4.csv#15, test4.csv#16, test4.csv#17, test4.csv#18, test4.csv#19, test4.csv#20, test4.csv#22, test4.csv#23, test4.csv#3, test4.csv#5, test4.csv#6, test4.csv#7, test4.csv#8.
hai-22.04 sandbox-candidate:shared-wrapper: test1.csv#0, test1.csv#1, test1.csv#2, test1.csv#3, test1.csv#4, test1.csv#5, test1.csv#6, test2.csv#0, test2.csv#10, test2.csv#13, test2.csv#14, test2.csv#15, test2.csv#16, test2.csv#2, test2.csv#3, test2.csv#4, test2.csv#5, test2.csv#6, test2.csv#7, test2.csv#8, test2.csv#9, test3.csv#0, test3.csv#2, test3.csv#3, test3.csv#4, test3.csv#7, test3.csv#8, test3.csv#9, test4.csv#1, test4.csv#11, test4.csv#15, test4.csv#16, test4.csv#17, test4.csv#18, test4.csv#19, test4.csv#20, test4.csv#22, test4.csv#23, test4.csv#3, test4.csv#5, test4.csv#6, test4.csv#7, test4.csv#8.
hai-23.05 sandbox-candidate:own-grouping: hai-test1.csv#0, hai-test1.csv#1, hai-test1.csv#10, hai-test1.csv#12, hai-test1.csv#13, hai-test1.csv#2, hai-test1.csv#3, hai-test1.csv#4, hai-test1.csv#5, hai-test1.csv#6, hai-test1.csv#7, hai-test1.csv#8, hai-test2.csv#0, hai-test2.csv#13, hai-test2.csv#15, hai-test2.csv#16, hai-test2.csv#17, hai-test2.csv#2, hai-test2.csv#25, hai-test2.csv#26, hai-test2.csv#27, hai-test2.csv#29, hai-test2.csv#3, hai-test2.csv#30, hai-test2.csv#34, hai-test2.csv#37, hai-test2.csv#4, hai-test2.csv#5, hai-test2.csv#6, hai-test2.csv#7.
hai-23.05 sandbox-candidate:shared-wrapper: hai-test1.csv#0, hai-test1.csv#1, hai-test1.csv#10, hai-test1.csv#12, hai-test1.csv#13, hai-test1.csv#2, hai-test1.csv#3, hai-test1.csv#4, hai-test1.csv#5, hai-test1.csv#6, hai-test1.csv#7, hai-test1.csv#8, hai-test2.csv#0, hai-test2.csv#13, hai-test2.csv#15, hai-test2.csv#16, hai-test2.csv#17, hai-test2.csv#2, hai-test2.csv#25, hai-test2.csv#26, hai-test2.csv#27, hai-test2.csv#29, hai-test2.csv#3, hai-test2.csv#30, hai-test2.csv#34, hai-test2.csv#37, hai-test2.csv#4, hai-test2.csv#5, hai-test2.csv#6, hai-test2.csv#7.
