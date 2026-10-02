# Public-data gates that are still closed (days 31–90)

Checked 2026-08-24. No fetch was attempted.

## CERT r4.2 events

`scripts/probe_cert_release.py --release r4.2` (2026-08-24): **70** labelled incidents,
3 scenarios. Scenario 3 has **10** account-holder-is-not-the-actor cases. Peer-relative
positives: **ABSENT**. Activity logs for r4.2 are **not on disk** (headers unchecked).
`compromised_account` vs `insider_misuse` ranking stays unrun. r3.1 6B remains the
ruler. Peer stays retired.

## SWaT / WADI

Registry `itrust-swat-wadi` is `operator-provided` / `form-required`. No CSV on disk.
In-plant Mahalanobis and any SWaT transfer row stay **REFUSED** until a human returns
the signed form and the files. Engineering does not scrape iTrust.

## ICSSim bottle-filling

Manifest licence is **read once**. Deposit identity is unestablished. Not acquired.
Not a labelled command corpus.

## Track C

Closed finding: [peer-baselining-gap.md](../../docs/data-campaign/peer-baselining-gap.md).
No downloads.

## Partner ICD

P1 remains `blocked_human_conversation`. Outreach is not a TAP in `src/phos`.
