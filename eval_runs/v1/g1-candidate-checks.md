# Four checks on the frozen candidate

Recall within budget is the headline where a check catches attacks.
Point-adjusted F1 is reported and is not. ADR 0104's 53/58 and 36/52 stay.
Grouped MinMax stays 10/58 and 6/52.

## Chance null

| Edition | Draws | Mean caught | 95th percentile | Max caught |
|---|---:|---:|---:|---:|
| hai-22.04 | 500 | 3.808000 | 7.000000 | 9 |
| hai-23.05 | 500 | 3.060000 | 6.000000 | 8 |

## Drivers

### hai-22.04

| Feature | Caught attacks | Range larger | Loop larger | Tie | Flagged |
|---|---:|---:|---:|---:|---|
| P1_PCV01D | 11 | 0 | 11 | 0 | True |
| P1_FT03Z | 8 | 0 | 8 | 0 | False |
| P3_LCV01D | 6 | 0 | 6 | 0 | False |
| P1_LIT01 | 5 | 0 | 5 | 0 | False |
| P1_LCV01D | 4 | 0 | 4 | 0 | False |
| P2_AutoSD | 4 | 3 | 1 | 0 | False |
| P1_B3005 | 3 | 0 | 3 | 0 | False |
| P2_SCO | 3 | 3 | 0 | 0 | False |
| P1_PP04 | 2 | 2 | 0 | 0 | False |
| P1_B4005 | 1 | 0 | 1 | 0 | False |
| P1_FCV01D | 1 | 0 | 1 | 0 | False |
| P1_TIT02 | 1 | 0 | 1 | 0 | False |
| P2_ManualSD | 1 | 1 | 0 | 0 | False |
| P2_SIT01 | 1 | 0 | 1 | 0 | False |
| P2_VT01 | 1 | 1 | 0 | 0 | False |
| P3_LH01 | 1 | 0 | 1 | 0 | False |

### hai-23.05

| Feature | Caught attacks | Range larger | Loop larger | Tie | Flagged |
|---|---:|---:|---:|---:|---|
| P1_FT03Z | 6 | 0 | 6 | 0 | False |
| P1_PCV01D | 6 | 0 | 6 | 0 | False |
| x1002_07_SETPOINT_OUT | 5 | 0 | 5 | 0 | False |
| P1_PIT01 | 4 | 0 | 4 | 0 | False |
| P1_FCV01D | 3 | 0 | 3 | 0 | False |
| x1002_08_SETPOINT_OUT | 3 | 0 | 3 | 0 | False |
| P2_SCO | 2 | 2 | 0 | 0 | False |
| P2_VT01 | 2 | 2 | 0 | 0 | False |
| P1_FCV02Z | 1 | 0 | 1 | 0 | False |
| P1_LCV01Z | 1 | 0 | 1 | 0 | False |
| P1_LIT01 | 1 | 0 | 1 | 0 | False |
| P1_PCV01Z | 1 | 0 | 1 | 0 | False |
| P1_PCV02D | 1 | 0 | 1 | 0 | False |

## Controls

| Edition | Control | Caught/attacks | Beyond grouped MinMax | Point-adjusted F1 |
|---|---|---:|---:|---:|
| hai-22.04 | sandbox-control:minmax-events | 21/58 | 11 | 0.461815 |
| hai-22.04 | sandbox-control:no-loop | 21/58 | 11 | 0.461815 |
| hai-23.05 | sandbox-control:minmax-events | 15/52 | 9 | 0.543522 |
| hai-23.05 | sandbox-control:no-loop | 15/52 | 9 | 0.543522 |

## Alert lists

| Edition | Row | Events before budget | Alerts after budget | Alerts kept | Point-adjusted F1 from |
|---|---|---:|---:|---:|---|
| hai-22.04 | sandbox-candidate:own-grouping | 83 | 101 | 101 | own-grouping budget output passed to _score_detector |
| hai-22.04 | sandbox-candidate:shared-wrapper | 83 | 83 | 83 | group_published_alerts output passed to _score_detector |
| hai-23.05 | sandbox-candidate:own-grouping | 85 | 73 | 73 | own-grouping budget output passed to _score_detector |
| hai-23.05 | sandbox-candidate:shared-wrapper | 85 | 73 | 73 | group_published_alerts output passed to _score_detector |

hai-22.04: same alert list False; same timestamps False.
hai-23.05: same alert list False; same timestamps True.
