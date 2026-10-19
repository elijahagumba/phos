# ADR 0154 — The Kelmarsh score did not run

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane B, A5 / W4
- **Depends on:** [ADR 0152](0152-kelmarsh-log-rule.md)

## Context

ADR 0152 named the log rule and left the alert count out. The score needs every development
year zip, 2016 through 2022, because a subset is not the development half. Those files are
on Zenodo record 16807551. This machine started without them.

## Decision

`eval_runs/build/lane-b/kelmarsh-log.json` records that the score did not run. There is no
explained share and no false alerts per shift.

1. **What matched the registry.** `Kelmarsh_SCADA_2016_3082.zip` (97,915,553 bytes,
   md5 `ca8efbb6dbcfae3516583937eb5b5402`) and `Kelmarsh_SCADA_2017_3083.zip` (174,604,722
   bytes, md5 `c78263ee52ee0e48e2cb4bbaa1ba211a`). The static sheet, the signal map, and the
   site kmz matched as well. 2016 was opened once, after that check, to read the turbine
   header and the 2016 status vocabulary that ADR 0152 names. No detector was run. 2017's
   members were not read.

2. **What was still incomplete.** 2018, 2019, 2020 and 2021 were mid-transfer. 2022 had not
   started. Zenodo closed the 2018 transfer early (`curl` error 18, about 142 MB still to
   read) and that file was resumed. A snapshot of the partials is in the JSON. Those byte
   counts are not final sizes, and the partials were not opened.

3. **Why there is no rate.** The declared split is train 2016–2018 and score 2019–2022, all
   six turbines. Scoring the two finished years would be a different configuration. Penmanshiel
   was not used. Kelmarsh was slow, and the files were still arriving. Held-back names were
   not downloaded and not opened.

Nothing was appended to `eval_runs/log.jsonl`. Templates, priors, `EVIDENCE_STRENGTH`, and
the consistency arithmetic were not edited. Hypothesis confidence is not in the file.

## Consequences

The Kelmarsh bar — the share of alerts the turbine's own log explains, and false alerts per
shift — is unmeasured. The synthetic bars in ADR 0153 are a different corpus and do not fill
this gap. A later run can score this same rule once every development zip matches the
registry. That run needs its own record. It must not treat this absence as a zero.

What would reverse this: quoting an explained share, or a false-alert rate, from the two
years that happened to finish.
