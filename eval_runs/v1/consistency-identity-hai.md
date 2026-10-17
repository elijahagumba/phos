# Consistency detector against ADR 0104's scored path, on clean HAI

Declared in ADR 0110. A reproduction check, not a new score. The reference is ADR 0104's
path: the frozen file's float32 scores, grouped as float64.

| Edition | Port path | Scores identical | Alert lists identical | Alerts | Reference alerts | Alerts not in reference | Caught | Reference caught |
|---|---|---|---|---:|---:|---:|---:|---:|
| hai-22.04 | port-float32-grouping | True | True | 101 | 101 | 0 | 53/58 | 53/58 |
| hai-22.04 | port-float64-grouping | True | True | 101 | 101 | 0 | 53/58 | 53/58 |
| hai-23.05 | port-float32-grouping | True | True | 73 | 73 | 0 | 36/52 | 36/52 |
| hai-23.05 | port-float64-grouping | True | True | 73 | 73 | 0 | 36/52 | 36/52 |
