# A2 status: atlas-v1-consistency on the five judging corpora

Declared in ADR 0115. Recall within budget, 8 alerts per 8-hour shift. The opponent is
the best grouped checked opponent. Chance is ADR 0106's null: 8 random rows per shift,
500 draws, seed 20261010.

| Corpus | Exposure | Consistency | Best grouped checked opponent | Strictly higher | Chance mean / 95th / max | Above every chance draw |
|---|---|---:|---:|---|---:|---|
| hai-20.07 | development: the candidate was tuned against it | 37/38 (this run) | 32/38 (ADR 0100) | yes | 4.478 / 8 / 11 | yes |
| hai-21.03 | held out once by the sandbox, now seen | 42/50 (this run) | 36/50 (ADR 0100) | yes | 2.728 / 5.05 / 8 | yes |
| hai-22.04 | scored once (ADR 0104), now seen | 53/58 (ADR 0104) | 10/58 (ADR 0102) | yes | 3.808 / 7 / 9 | yes |
| hai-23.05 | scored once (ADR 0104), now seen | 36/52 (ADR 0104) | 6/52 (ADR 0102) | yes | 3.060 / 6 / 8 | yes |
| batadal | scored once (ADR 0113), now seen | 5/5 (ADR 0113) | 3/5 (ADR 0100) | yes | 5.000 / 5 / 5 | no |

Strictly higher: 5 of 5. Strictly higher and above every chance draw: 4 of 5.
Sandbox figures reproduced by the lab scorer: {'hai-20.07': True, 'hai-21.03': True}.
