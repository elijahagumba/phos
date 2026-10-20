# Kelmarsh development log

Kelmarsh development SCADA is not attack-labelled. The share of alerts the turbine's own log explains, and the false alerts per shift, are not a detection claim and are not evidence the plant map detects attacks (ADR 0143). Hypothesis confidence is not reported.

The score did not run. These development year zips were not on disk:

- Kelmarsh_SCADA_2018_3084.zip
- Kelmarsh_SCADA_2019_3085.zip
- Kelmarsh_SCADA_2020_3086.zip
- Kelmarsh_SCADA_2021_4456.zip
- Kelmarsh_SCADA_2022_4457.zip

These year zips were present and were not scored:

- Kelmarsh_SCADA_2016_3082.zip. Size and md5 match the registry. It was opened once, before the score, to read the column header and the 2016 status vocabulary. ADR 0152. No detector was run on it.
- Kelmarsh_SCADA_2017_3083.zip. Size and md5 match the registry. Its members were not read.

2018, 2019, 2020 and 2021 were still downloading when this record was written. 2022 had not started. Zenodo closed the 2018 transfer once, and that file was resumed. A partial year set is not the development half, so there is no explained share and no false-alert rate.
