# ADR 0262 — S2 is met on directory email; hosts and machines stay unnamed

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Sentiel v1, S2, the labelled score
- **Depends on:** [ADR 0261](0261-the-s2-register-is-the-directorys-email.md),
  [ADR 0230](0230-v1-stands-at-six-of-twelve.md)

## Context

ADR 0261 declared the register and was committed as `cc0eac2` before this score.
Each release's register is the 1000 email addresses in its LDAP snapshots. Hosts
and machines are empty. The empty-register zeros in `s2-r31.json` and
`s2-r42.json` stay the record of that earlier score.

The commands, run once each after that commit:

```
uv run python scripts/score_identity_features.py --release r3.1 --register directory --out eval_runs/build/v1/sentiel/s2-directory-r31.json
uv run python scripts/score_identity_features.py --release r4.2 --register directory --out eval_runs/build/v1/sentiel/s2-directory-r42.json
```

The r4.2 trace cache is the same 330452 person-days as the empty-register score.
The r3.1 cache is the same 340171 person-days. `insiders.csv` was read after the
feature summary, and only to count people. The address list is not in either
result file. The 34 features were not weighted. Frozen 6B was not rescored. S3
was not rescored.

## Decision

**S2 is met.** ADR 0230's condition was a register declared without labelled
insiders that names at least one host, destination or machine, then scored on
r3.1 and r4.2. This register names destinations. The destination features are
not zero.

| Release | Insiders | Destination sum | Destination max | Days that named one | New-destination sum | Hosts and machines |
| --- | --- | --- | --- | --- | --- | --- |
| r3.1 | 2 | 1950179 | 29 | 310296 | 455111 | 0 |
| r4.2 | 70 | 2274118 | 32 | 292539 | 301446 | 0 |

The hashes match ADR 0261. r4.2 has more labelled insiders than r3.1, which is
the larger release the frozen sentence asks for.

Hosts and machines are still unnamed. `declared_host_count`,
`declared_new_host_count`, `declared_pc_count` and `declared_new_pc_count` are
zero because the directory has no column for them. That is the limit of this
register, not a finding that nobody used a machine. A later register that names
hosts or machines is a new score.

This is not a detection result. It does not move S3, and it does not move the
frozen 6B row (precision 0.104 at 48 alerts).

**v1 stands at 7 of 12:** A2, A4, A5, A6, C1, S1 and S2. A1, A3, A7, S3 and C2
stay unmet. A3 and S3 stay the one-shot results. On 20 October
`scripts/measure_baseline_table.py` recomputed hai-20.07, batch distillation and
Data4Cyber and matched the committed G1 table; the four validation rows are
still reprints, so A1 stays unmet. The C2 sheet is still blank.

## What would reverse this

Calling the zero host and machine features a measurement of hosts and machines,
writing the address list into the repository, or treating this score as S3.
