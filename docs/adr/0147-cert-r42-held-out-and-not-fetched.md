# ADR 0147 — CERT r4.2 is declared held out, and it is not fetched

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane A, Sentiel S3
- **Depends on:** [ADR 0023](0023-per-entity-reasoning-the-completed-competing-set-and-what-cert-r4-2-can-unblock.md),
  [ADR 0067](0067-follow-up-corpora-and-partner-icd-stay-closed.md),
  [ADR 0145](0145-bet-001-not-run.md)

## Context

S3 is a measurement on a larger CERT release than r3.1: at 48 tickets a day, more
distinct labelled insiders than the frozen 6B scorer, beside a label-free chance
null. The roadmap, the 2027 note and the handover name that release as r4.2. The
measurement has to be declared before any file of it is opened.

ADR 0067 left r4.2's events closed because they were not on disk. This lane checked
again. `data/cert-insider-threat/` still has no r4.2 directory. The deposit page
recorded for the dataset is on `kilthub.cmu.edu`. The file URLs recorded for the
same deposit's r3.1 archive are on `ndownloader.figshare.com`. r4.2's own file id is
not in the registry. Neither host is on the build allow-list.

## Decision

**r4.2 is held out.** `phos.sentiel.r42_holdout.CERT_R42` names the dataset, the
release, the role `held-out`, and `scored=False`. `r42_may_be_scored` returns false,
including on a machine where the files are already present. `r42_fetch_allowed`
returns false because the recorded hosts are outside the allow-list.

The archive was not fetched. No sha256 was invented for a file URL this repository
does not record. No row was scored. `eval_runs/log.jsonl` was not appended. The
frozen 6B row stays the ruler. Peer-group advantage stays retired; this record does
not treat r4.2 as a peer corpus.

## Consequences

The declaration S3 asked this lane for is in place. S3's pass bar — more labelled
insiders than 6B at 48, beside chance — is not met, because the release was not
scored and the files are not here.

A later score declares the command, the split, and the register it will use, in a
commit that precedes the run, and then runs once. It does not fetch from a host
outside the allow-list unless that list has changed. It does not retune the 6B scorer
to widen the gap.

## What this record does not decide

The licence conflict already recorded for the deposit (CC BY 4.0 on the deposit page,
the ExactData agreement inside the payload) is unchanged. No file was opened, so
nothing new was learned about r4.2's directory or its event schema.
