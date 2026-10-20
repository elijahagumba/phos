# ADR 0261 — The S2 register is the directory's own email addresses

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Sentiel v1, S2, before the labelled score
- **Depends on:** [ADR 0146](0146-identity-features-keep-the-thirty-four-symmetric.md),
  [ADR 0204](0204-the-identity-register-stays-empty.md),
  [ADR 0230](0230-v1-stands-at-six-of-twelve.md)

## Context

ADR 0230 left S2 unmet. The six identity features are implemented, and the empty
register's zeros stay the record of what an empty register produces (ADR 0204).
S2 is met only when a register declared without labelled insiders names at least
one host, destination or machine, and the features are scored with it on CERT
r3.1 and on r4.2. This commit is that declaration. It does not read
`insiders.csv`, and it does not score.

The names are the organisation's own directory. Each release's LDAP snapshots
list `email` for every employee. That column is not an activity log and not the
answer key. Web hosts are not in the directory. Machine names are not in the
directory. Inventing either from `http.csv` or `logon.csv` would be choosing
names from traffic that includes the labelled days.

## Decision

1. **The register is directory email, per release.** `directory_destination_register`
   takes the emails `EntityCatalogue.from_ldap_directory` already read. Hosts and
   machines stay empty. Matching stays exact after case-folding, including a
   domain entry, which this register does not use: every entry is a full address.
   The 34 features are not weighted. Bet 001 is not edited.
2. **The hashes were computed from the LDAP files before this score reads labels.**
   Each release has 1000 addresses, from 1000 directory users.

   | Release | Destinations | SHA-256 |
   | --- | --- | --- |
   | r3.1 | 1000 | `6bcb876c4d9887b2bec5d8b92826c6b18cf02b95b1b4dc069dc6e5b53c706f83` |
   | r4.2 | 1000 | `6b0597ae973edb27f2ff995ab1727e7bf12ae6af6aae57ba17c54169d294aac0` |

   A directory run on `data/cert-insider-threat` refuses to write if the hash
   differs. The address list is not written into the result file.
3. **The empty-register results stay.** `eval_runs/build/v1/sentiel/s2-r31.json`
   and `s2-r42.json` are not replaced. The commands, run once each, only after
   this commit:

   ```
   uv run python scripts/score_identity_features.py --release r3.1 --register directory --out eval_runs/build/v1/sentiel/s2-directory-r31.json
   uv run python scripts/score_identity_features.py --release r4.2 --register directory --out eval_runs/build/v1/sentiel/s2-directory-r42.json
   ```

   `insiders.csv` is read only after the feature summary exists, and only to
   count labelled insiders.

## Consequences

Whether S2 is met is what those two files say, not this declaration. A non-zero
destination count means the features named directory addresses. A zero means the
directory addresses did not appear as recipients, and S2 stays unmet. Neither
result is a detection claim, and neither moves S3 or the frozen 6B row.

## What would reverse this

Filling the register from `insiders.csv` or from an activity log, writing the
address list into the repository, or treating this score as a rescore of S3.
