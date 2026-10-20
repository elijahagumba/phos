# Kelmarsh 2018–2022

19 October 2026. ADR 0165 and ADR 0166. Not a detection claim (ADR 0143).

Train is 2018. Score is 2019–2022, all six turbines. 2017 is not on disk. 2016 is smaller than the registry file and was not opened. 2023 and 2024 were not fetched: 4.5 GB was free and the two zips are 1.42 GB.

The kept scorer is `atlas-v1-consistency`, unchanged. A status row explains an alert when it covers that time and the service category is not `System OK (32)`.

| Scorer | Alerts | Explained | Share | Unexplained per shift | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Pooled (start, kept) | 74 | 57 | 0.770 | 0.0006 | kept |
| Declared modes | 616 | 261 | 0.424 | 0.0135 | revert |

Seventeen alerts were not explained, across 26,298 shifts. Modes raised both the alert count and the unexplained rate, and the explained share fell, so they were not kept.

The synthetic closure numbers were not re-run. `consistency.py` and the maintenance harness were not edited.
